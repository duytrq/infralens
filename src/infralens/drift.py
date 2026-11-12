"""Interpret observed Terraform drift, never planned configuration changes."""

import json
import math
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from infralens.errors import ExecutionError

_MISSING = object()
REVIEW_POLICY = "builtin-review-v2"
_VPC_RULE_FIELDS = (
    "security_group_id",
    "region",
    "ip_protocol",
    "from_port",
    "to_port",
    "cidr_ipv4",
    "cidr_ipv6",
    "prefix_list_id",
    "referenced_security_group_id",
)
NETWORK_RULE_FIELDS = {
    "aws_vpc_security_group_ingress_rule": _VPC_RULE_FIELDS,
    "aws_vpc_security_group_egress_rule": _VPC_RULE_FIELDS,
    "aws_security_group_rule": (
        "security_group_id",
        "region",
        "type",
        "protocol",
        "from_port",
        "to_port",
        "cidr_blocks",
        "ipv6_cidr_blocks",
        "prefix_list_ids",
        "source_security_group_id",
        "self",
    ),
}
_NOTES = (
    "Only managed resources in the selected Terraform workspace are checked.",
    "Configuration edits that have not been applied are not infrastructure drift.",
    "Detection depends on provider refresh behavior; untracked resources are excluded.",
    "Sensitive values are hidden only when Terraform marks them sensitive.",
)


@dataclass(frozen=True)
class AttributeChange:
    path: tuple[str, ...]
    before: dict
    after: dict


@dataclass(frozen=True)
class ResourceDrift:
    address: str
    resource_type: str
    actions: tuple[str, ...]
    attributes: tuple[AttributeChange, ...]
    identifiers: dict = field(default_factory=dict)
    trace: dict | None = None
    source: dict | None = None
    assessment: dict | None = None
    network_context: dict | None = None


@dataclass(frozen=True)
class DriftResult:
    terraform_version: str
    resources: tuple[ResourceDrift, ...]
    input_mode: str
    checked_at: str
    notes: tuple[str, ...] = _NOTES
    normalizations: tuple[dict, ...] = ()
    trace: dict | None = None

    def to_dict(self) -> dict:
        report = {
            "schema_version": "1.0",
            "kind": "drift",
            "terraform_version": self.terraform_version,
            "input_mode": self.input_mode,
            "checked_at": self.checked_at,
            "has_drift": bool(self.resources),
            "summary": {
                "resources": len(self.resources),
                "attributes": sum(len(r.attributes) for r in self.resources),
            },
            "resources": [asdict(resource) for resource in self.resources],
            "normalizations": list(self.normalizations),
            "notes": list(self.notes),
        }
        for resource in report["resources"]:
            for optional in ("trace", "source", "assessment", "network_context"):
                if resource[optional] is None:
                    del resource[optional]
        if self.trace is not None:
            report["trace"] = self.trace
        if summary := self.review_summary():
            report["review_summary"] = summary
        return report

    def review_summary(self):
        assessments = [r.assessment for r in self.resources if r.assessment is not None]
        if assessments:
            return {
                "policy": REVIEW_POLICY,
                "priority_counts": {
                    priority: sum(a["priority"] == priority for a in assessments)
                    for priority in ("high", "medium", "unknown")
                },
            }
        return None


def _mask(value: object, source: object = _MISSING) -> None:
    """Fail closed on invalid sensitivity/unknown metadata."""
    if type(value) is bool:
        return
    if isinstance(value, dict):
        if (
            source is not _MISSING
            and source is not None
            and not isinstance(source, dict)
        ):
            raise ValueError
        for key, child in value.items():
            _mask(child, _child(source, key))
    elif isinstance(value, list):
        if (
            source is not _MISSING
            and source is not None
            and not isinstance(source, list)
        ):
            raise ValueError
        for index, child in enumerate(value):
            item = (
                source[index]
                if isinstance(source, list) and index < len(source)
                else _MISSING
            )
            _mask(child, item)
    else:
        raise ValueError


def _marked(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, dict):
        return any(_marked(child) for child in value.values())
    if isinstance(value, list):
        return any(_marked(child) for child in value)
    return False


def _child(value: object, key: str) -> object:
    return value.get(key, _MISSING) if isinstance(value, dict) else _MISSING


def _value(value: object) -> dict:
    return (
        {"status": "absent"}
        if value is _MISSING
        else {"status": "known", "value": value}
    )


def _identifiers(change: dict, resource_type: str) -> dict:
    """Retain scoped identity only, including saved IDs for deleted resources."""
    identifiers = {}
    names = ("id", "arn")
    if resource_type in (
        "aws_vpc_security_group_ingress_rule",
        "aws_vpc_security_group_egress_rule",
    ):
        names += ("security_group_id", "security_group_rule_id")
    for name in names:
        before = _child(change.get("before"), name)
        after = _child(change.get("after"), name)
        masks = [
            change.get(side, False) for side in ("before_sensitive", "after_sensitive")
        ]
        sensitive = any(mask is True or _marked(_child(mask, name)) for mask in masks)
        if sensitive:
            if before is not _MISSING or after is not _MISSING:
                identifiers[name] = {"status": "sensitive"}
            continue
        unknown = change.get("after_unknown", False)
        unknown = unknown is True or _marked(_child(unknown, name))
        if isinstance(after, str) and after and not unknown:
            identifiers[name] = {
                "status": "known",
                "value": after,
                "source": "observed",
            }
        elif isinstance(before, str) and before:
            identifiers[name] = {"status": "known", "value": before, "source": "saved"}
    return identifiers


def _network_context(resource_type: str, change: dict) -> dict | None:
    """Keep only rule semantics, including unchanged fields needed for review.

    Apply sensitivity from either side to both observations, just like deltas.
    Nested collection masks hide the entire field. Never retain a raw snapshot.
    """
    fields = NETWORK_RULE_FIELDS.get(resource_type)
    if fields is None or change["actions"] != ["update"]:
        return None
    result = {"version": "security-group-rule-v1", "before": {}, "after": {}}
    for name in fields:
        sensitive = any(
            mask is True or _marked(_child(mask, name))
            for mask in (
                change.get("before_sensitive", False),
                change.get("after_sensitive", False),
            )
        )
        unknown = change.get("after_unknown", False)
        for side in ("before", "after"):
            if sensitive:
                value = {"status": "sensitive"}
            elif side == "after" and (
                unknown is True or _marked(_child(unknown, name))
            ):
                value = {"status": "unknown"}
            else:
                value = _value(_child(change.get(side), name))
            result[side][name] = value
    return result


def _canonical_aws_tags(entry: dict, before: dict, after: object):
    """AWS provider 6.x can refresh an unset tag map from null to {}.

    Limit this to observed AWS tag fields, retaining every real tag addition,
    removal and value change. Never equate arbitrary null/empty values.
    """
    resource_type = entry["type"]
    if (
        entry.get("provider_name") != "registry.terraform.io/hashicorp/aws"
        or resource_type not in ("aws_instance", "aws_security_group")
        or not isinstance(after, dict)
    ):
        return before, after, []
    before = deepcopy(before)
    after = deepcopy(after)
    changes = []

    def tag_map(old, new, key, path):
        if key not in old or key not in new:
            return
        if (old[key] is None and new[key] == {}) or (
            new[key] is None and old[key] == {}
        ):
            old[key] = new[key] = {}
            changes.append(
                {
                    "address": entry["address"],
                    "path": list(path),
                    "reason": (
                        "AWS provider empty tag map representation: null versus {}"
                    ),
                }
            )

    tag_map(before, after, "tags", ("tags",))
    if resource_type == "aws_instance":
        old_roots = before.get("root_block_device")
        new_roots = after.get("root_block_device")
        if (
            isinstance(old_roots, list)
            and isinstance(new_roots, list)
            and len(old_roots) == len(new_roots)
        ):
            for index, (old, new) in enumerate(zip(old_roots, new_roots)):
                if isinstance(old, dict) and isinstance(new, dict):
                    tag_map(old, new, "tags", ("root_block_device", index, "tags"))
    return before, after, changes


def _differences(
    before: object,
    after: object,
    before_sensitive: object,
    after_sensitive: object,
    unknown: object,
    path: tuple[str, ...] = (),
):
    if before == after and type(before) is type(after) and not _marked(unknown):
        return
    if before_sensitive is True or after_sensitive is True:
        yield AttributeChange(path, {"status": "sensitive"}, {"status": "sensitive"})
        return
    if unknown is True:
        old = (
            {"status": "sensitive"}
            if _marked(before_sensitive) or _marked(after_sensitive)
            else _value(before)
        )
        yield AttributeChange(path, old, {"status": "unknown"})
        return
    # Recurse through objects, including creates/deletes. Report arrays atomically:
    # JSON loses Terraform's list/set distinction, so indexes would imply false IDs.
    if (
        isinstance(before, dict)
        and (isinstance(after, dict) or after is _MISSING or after is None)
    ) or (
        isinstance(after, dict)
        and (isinstance(before, dict) or before is _MISSING or before is None)
    ):
        keys = set(before if isinstance(before, dict) else ())
        keys.update(after if isinstance(after, dict) else ())
        if isinstance(unknown, dict):
            keys.update(unknown)
        if keys:
            for key in sorted(keys):
                yield from _differences(
                    _child(before, key),
                    _child(after, key),
                    _child(before_sensitive, key),
                    _child(after_sensitive, key),
                    _child(unknown, key),
                    (*path, key),
                )
            return
    # A collection or a type change with nested sensitivity is redacted entirely.
    if _marked(before_sensitive) or _marked(after_sensitive):
        yield AttributeChange(path, {"status": "sensitive"}, {"status": "sensitive"})
    else:
        yield AttributeChange(
            path,
            _value(before),
            {"status": "unknown"} if _marked(unknown) else _value(after),
        )


def _reject_constant(value: str):
    raise ValueError


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def parse_plan(payload: str, *, input_mode: str = "imported_plan") -> DriftResult:
    """Consume terraform show -json, dropping raw state, outputs and variables."""
    try:
        plan = json.loads(
            payload,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            object_pairs_hook=_unique_object,
        )
        if not isinstance(plan, dict):
            raise ValueError
        if not re.fullmatch(r"1\.\d+", str(plan.get("format_version", ""))):
            raise ValueError
        version = plan.get("terraform_version")
        if not isinstance(version, str) or not re.fullmatch(r"1\.\d+\.\d+", version):
            raise ValueError
        if not isinstance(plan.get("planned_values"), dict):
            raise ValueError
        if plan.get("errored", False) is not False:
            raise ValueError
        if plan.get("complete", True) is not True or plan.get("deferred_changes"):
            raise ValueError
        entries = plan.get("resource_drift", [])
        if not isinstance(entries, list):
            raise ValueError
        resources = []
        normalizations = []
        addresses = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError
            address = entry.get("address")
            resource_type = entry.get("type")
            mode = entry.get("mode")
            change = entry.get("change")
            if (
                not isinstance(address, str)
                or not address
                or not isinstance(resource_type, str)
                or not resource_type
                or mode not in ("managed", "data")
                or not isinstance(change, dict)
            ):
                raise ValueError
            actions = change.get("actions")
            # Refresh-only detects updates and disappearance; it does not schedule
            # replacements/creates. Imported plans can use the same drift section.
            if actions not in (["update"], ["delete"], ["no-op"]):
                raise ValueError
            for name in ("before_sensitive", "after_sensitive", "after_unknown"):
                side = "before" if name == "before_sensitive" else "after"
                _mask(change.get(name, False), change.get(side, _MISSING))
            if mode != "managed" or actions == ["no-op"]:
                continue
            if address in addresses:
                raise ValueError
            addresses.add(address)
            before = change.get("before", _MISSING)
            after = change.get("after", _MISSING)
            if not isinstance(before, dict):
                raise ValueError
            if actions == ["update"] and not isinstance(after, dict):
                raise ValueError
            if actions == ["delete"] and after is not _MISSING and after is not None:
                raise ValueError
            before, after, normalized = _canonical_aws_tags(entry, before, after)
            normalizations.extend(normalized)
            if (
                normalized
                and actions == ["update"]
                and not _marked(change.get("after_unknown", False))
                and json.dumps(before, sort_keys=True)
                == json.dumps(after, sort_keys=True)
            ):
                continue
            resources.append(
                ResourceDrift(
                    address,
                    resource_type,
                    tuple(actions),
                    tuple(
                        _differences(
                            before,
                            after,
                            change.get("before_sensitive", False),
                            change.get("after_sensitive", False),
                            change.get("after_unknown", False),
                        )
                    ),
                    _identifiers(change, resource_type),
                    network_context=_network_context(resource_type, change),
                )
            )
    except (ValueError, TypeError, RecursionError):
        raise ExecutionError(
            "Terraform returned an invalid, incomplete or unsupported plan JSON. "
            "Expected terraform show -json with format 1.x and a complete plan."
        ) from None
    notes = _NOTES
    if normalizations:
        notes += (
            f"Normalized {len(normalizations)} empty AWS tag map representations; "
            "see normalizations for the exact resource paths.",
        )
    if input_mode == "imported_plan":
        notes += (
            "Imported plan: refresh coverage, workspace and freshness are unverified; "
            "an empty report does not certify the current infrastructure.",
        )
    return DriftResult(
        version,
        tuple(sorted(resources, key=lambda resource: resource.address)),
        input_mode,
        datetime.now(timezone.utc).isoformat(),
        notes,
        tuple(normalizations),
    )
