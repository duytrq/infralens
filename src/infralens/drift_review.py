"""Deterministic review priorities and human reconciliation guidance for drift."""

from dataclasses import replace
from ipaddress import ip_network

from infralens.drift import (
    NETWORK_RULE_FIELDS,
    REVIEW_POLICY,
    DriftResult,
    ResourceDrift,
)

_SIGNALS = {
    "resource_missing": (
        "high",
        "The provider reports that this managed resource is missing.",
    ),
    "world_ingress_added_or_expanded": (
        "high",
        "An ingress rule for all IPv4 or IPv6 addresses was added or widened.",
    ),
    "network_rules_changed": (
        "medium",
        "Security group network rules changed; review intended access.",
    ),
    "instance_type_changed": (
        "medium",
        "Instance type changed; review workload capacity and availability.",
    ),
    "tag_context_required": (
        "unknown",
        "Tags changed; check their use in access rules and automation.",
    ),
    "values_unavailable": (
        "unknown",
        "Some changed values or required context are hidden, absent or unknown.",
    ),
    "network_details_unavailable": (
        "unknown",
        "Network rule details are incomplete or outside supported semantics.",
    ),
    "unclassified_change": (
        "unknown",
        "This change requires workload-specific review.",
    ),
}
_NOTE = (
    "Review priorities are built-in heuristics, not a security verdict. Unknown "
    "means manual review, not low risk. Reconcile against approved configuration; "
    "the saved state is an observation baseline, not a statement of desired intent."
)


def _world_rules(value):
    """Project known inline SG rules into world-source protocol/port coverage."""
    if not isinstance(value, list):
        raise ValueError
    result = set()
    for rule in value:
        if not isinstance(rule, dict):
            raise ValueError
        protocol = rule.get("protocol")
        protocol = {"6": "tcp", "17": "udp", "all": "-1"}.get(protocol, protocol)
        if protocol == "-1":
            lower, upper = 0, 65535
        elif protocol in ("tcp", "udp"):
            lower, upper = rule.get("from_port"), rule.get("to_port")
            if (
                type(lower) is not int
                or type(upper) is not int
                or not 0 <= lower <= upper <= 65535
            ):
                raise ValueError
        else:
            raise ValueError
        for key, family in (("cidr_blocks", 4), ("ipv6_cidr_blocks", 6)):
            cidrs = rule.get(key, [])
            if not isinstance(cidrs, list):
                raise ValueError
            for cidr in cidrs:
                if not isinstance(cidr, str):
                    raise ValueError
                network = ip_network(cidr, strict=False)
                if network.version != family:
                    raise ValueError
                if network.prefixlen == 0:
                    result.add((family, protocol, lower, upper))
    return result


def _covered(exposure, previous):
    family, protocol, lower, upper = exposure
    ranges = sorted(
        (start, end)
        for version, proto, start, end in previous
        if version == family and proto in ("-1", protocol)
    )
    next_port = lower
    for start, end in ranges:
        if end < next_port:
            continue
        if start > next_port:
            return False
        next_port = max(next_port, end + 1)
        if next_port > upper:
            return True
    return False


class _UnavailableNetworkValues(ValueError):
    """A rule field is redacted or not yet known."""


def _context_field(values, name, *, optional=False):
    value = values.get(name)
    if not isinstance(value, dict):
        raise ValueError
    if value.get("status") in ("sensitive", "unknown"):
        raise _UnavailableNetworkValues(name)
    if value.get("status") == "absent" and optional:
        return None
    if value.get("status") != "known" or "value" not in value:
        raise ValueError
    if value["value"] is None and not optional:
        raise ValueError
    return value["value"]


def _standalone_rule(kind, values):
    """Project one fully known CIDR rule; references/ICMP stay unclassified."""
    if not isinstance(values, dict):
        raise ValueError

    def field(name, **kwargs):
        return _context_field(values, name, **kwargs)

    group = field("security_group_id")
    region = field("region", optional=True)
    if not isinstance(group, str) or not group:
        raise ValueError
    if region is not None and (not isinstance(region, str) or not region):
        raise ValueError
    legacy = kind == "aws_security_group_rule"
    direction = (
        field("type")
        if legacy
        else "ingress"
        if kind == "aws_vpc_security_group_ingress_rule"
        else "egress"
    )
    if direction not in ("ingress", "egress"):
        raise ValueError
    if legacy:
        ipv4 = field("cidr_blocks", optional=True)
        ipv6 = field("ipv6_cidr_blocks", optional=True)
        ipv4 = [] if ipv4 is None else ipv4
        ipv6 = [] if ipv6 is None else ipv6
        prefixes = field("prefix_list_ids", optional=True)
        reference = field("source_security_group_id", optional=True)
        self_reference = field("self", optional=True)
        if (
            not isinstance(ipv4, list)
            or not isinstance(ipv6, list)
            or not (ipv4 or ipv6)
            or prefixes not in (None, [])
            or reference not in (None, "")
            or self_reference is not None
            and self_reference is not False
        ):
            raise ValueError
    else:
        sources = {
            name: field(name, optional=True)
            for name in (
                "cidr_ipv4",
                "cidr_ipv6",
                "prefix_list_id",
                "referenced_security_group_id",
            )
        }
        if any(v is not None and not isinstance(v, str) for v in sources.values()):
            raise ValueError
        if sum(bool(v) for v in sources.values()) != 1:
            raise ValueError
        if sources["prefix_list_id"] or sources["referenced_security_group_id"]:
            raise ValueError
        ipv4 = [sources["cidr_ipv4"]] if sources["cidr_ipv4"] else []
        ipv6 = [sources["cidr_ipv6"]] if sources["cidr_ipv6"] else []
    rule = {
        "protocol": field("protocol" if legacy else "ip_protocol"),
        "from_port": field("from_port", optional=True),
        "to_port": field("to_port", optional=True),
        "cidr_blocks": ipv4,
        "ipv6_cidr_blocks": ipv6,
    }
    return direction, (group, region), _world_rules([rule])


def _assess_standalone(resource, add):
    fields = set(NETWORK_RULE_FIELDS.get(resource.resource_type, ()))
    paths = (
        [
            change.path
            for change in resource.attributes
            if len(change.path) == 1 and change.path[0] in fields | {"description"}
        ]
        if fields
        else []
    )
    if not paths:
        return set()
    for change in resource.attributes:
        if change.path in paths and any(
            side.get("status") in ("sensitive", "unknown")
            for side in (change.before, change.after)
        ):
            add("values_unavailable", change.path)
    context = resource.network_context or {}
    try:
        if context.get("version") != "security-group-rule-v1":
            raise ValueError
        old_direction, old_scope, old = _standalone_rule(
            resource.resource_type, context.get("before")
        )
        direction, scope, new = _standalone_rule(
            resource.resource_type, context.get("after")
        )
    except _UnavailableNetworkValues as error:
        add("values_unavailable", (error.args[0],))
    except (ValueError, TypeError):
        for path in paths:
            add("network_details_unavailable", path)
    else:
        # Egress and a different SG/region cannot cover ingress at this target.
        if old_direction != "ingress" or old_scope != scope:
            old = set()
        for path in paths:
            add("network_rules_changed", path)
        if direction == "ingress" and any(not _covered(rule, old) for rule in new):
            for path in paths:
                add("world_ingress_added_or_expanded", path)
    return set(paths)


def _guidance(resource, signals):
    steps = [
        "Confirm whether the external change was approved and still represents intent.",
        "Review the current resource configuration, including pending code changes.",
    ]
    if resource.network_context is not None:
        steps.append(
            "Review the target security group, region, rule direction, protocol, "
            "CIDRs and port range together, including unchanged context."
        )
    if "world_ingress_added_or_expanded" in signals:
        steps.append(
            "Compare CIDRs, protocols and port ranges with approved network access."
        )
    if "instance_type_changed" in signals:
        steps.append(
            "Check workload capacity and change-window requirements before resizing."
        )
    if "tag_context_required" in signals:
        steps.append("Check whether changed tags control access or automation.")
    if resource.trace and resource.trace.get("events"):
        steps.append(
            "Use candidate CloudTrail events as context; "
            "verify the actor and change record."
        )
    if resource.actions == ("delete",):
        steps.append(
            "Confirm account, region and workspace; "
            "if data is affected, review recovery needs."
        )
    return {
        "review_steps": steps,
        "choices": [
            {
                "id": "restore_approved_configuration",
                "title": "Restore approved configuration",
                "steps": [
                    "Confirm the intended configuration and review "
                    "a normal Terraform plan.",
                    "Check all proposed changes and replacements "
                    "before the team's apply workflow.",
                ],
            },
            {
                "id": "adopt_approved_external_change",
                "title": "Adopt an approved external change",
                "steps": [
                    "Update configuration to express the approved "
                    "observed behavior or removal.",
                    "Review a normal Terraform plan through the team's change process; "
                    "a state-only refresh does not update code.",
                ],
            },
        ],
    }


def assess_resource(resource: ResourceDrift):
    signals = {}

    def add(code, path=()):
        signals.setdefault(code, set()).add(tuple(path))

    if resource.actions == ("delete",):
        add("resource_missing")
    else:
        network_paths = _assess_standalone(resource, add)
        for change in resource.attributes:
            path = change.path
            if path in network_paths:
                continue
            name = path[0] if path else None
            before, after = change.before, change.after
            if (
                before.get("status") != "known"
                or after.get("status") != "known"
                or "value" not in before
                or "value" not in after
            ):
                add("values_unavailable", path)
                continue
            if resource.resource_type == "aws_security_group" and path in (
                ("ingress",),
                ("egress",),
            ):
                try:
                    old = _world_rules(before["value"])
                    new = _world_rules(after["value"])
                except (ValueError, TypeError):
                    add("network_details_unavailable", path)
                    continue
                add("network_rules_changed", path)
                if name == "ingress" and any(not _covered(rule, old) for rule in new):
                    add("world_ingress_added_or_expanded", path)
            elif resource.resource_type == "aws_instance" and path == (
                "instance_type",
            ):
                if all(
                    isinstance(side["value"], str) and side["value"]
                    for side in (before, after)
                ):
                    add("instance_type_changed", path)
                else:
                    add("unclassified_change", path)
            elif name in ("tags", "tags_all"):
                add("tag_context_required", path)
            else:
                add("unclassified_change", path)
    if not signals:
        add("unclassified_change")
    priorities = {_SIGNALS[code][0] for code in signals}
    priority = (
        "high"
        if "high" in priorities
        else "unknown"
        if "unknown" in priorities
        else "medium"
    )
    return {
        "policy": REVIEW_POLICY,
        "priority": priority,
        "signals": [
            {
                "code": code,
                "priority": _SIGNALS[code][0],
                "description": _SIGNALS[code][1],
                "paths": [list(p) for p in sorted(paths)],
            }
            for code, paths in sorted(signals.items())
        ],
        "guidance": _guidance(resource, signals),
    }


def enrich_review(result: DriftResult):
    if not result.resources:
        return result
    return replace(
        result,
        resources=tuple(
            replace(resource, assessment=assess_resource(resource))
            for resource in result.resources
        ),
        notes=result.notes + (_NOTE,),
    )
