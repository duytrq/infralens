"""Bounded, read-only CloudTrail correlation. Events are candidates, not causation."""

import json
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from infralens.cloudtrail_rules import (
    RULE_FIELDS,
    RULE_TYPES,
    match_rule_request,
    rule_operations,
)
from infralens.drift import DriftResult, ResourceDrift
from infralens.errors import ExecutionCancelled
from infralens.options import DriftOptions

MAX_RESOURCES = 20
MAX_PAGES = 4
_EVENTS = {
    "aws_instance": {
        "instance_type": {"ModifyInstanceAttribute"},
        "tags": {"CreateTags", "DeleteTags"},
        "tags_all": {"CreateTags", "DeleteTags"},
    },
    "aws_security_group": {
        "ingress": {
            "AuthorizeSecurityGroupIngress",
            "RevokeSecurityGroupIngress",
            "ModifySecurityGroupRules",
        },
        "egress": {
            "AuthorizeSecurityGroupEgress",
            "RevokeSecurityGroupEgress",
            "ModifySecurityGroupRules",
        },
        "tags": {"CreateTags", "DeleteTags"},
        "tags_all": {"CreateTags", "DeleteTags"},
    },
}
_NOTE = (
    "CloudTrail events are related candidates, not proof of the cause of drift. "
    "Event history is regional, covers up to 90 days of management events, and "
    "can arrive late. No events does not prove that no change occurred."
)


class TraceBudgetExceeded(Exception):
    """Stop starting requests after the trace budget expires."""


class LookupThrottle:
    """Apply CloudTrail's two-requests/second quota across pages and resources."""

    def __init__(self, deadline, cancel=None):
        self.deadline = deadline
        self.cancel = cancel
        self.next_request = 0.0

    def __call__(self, **kwargs):
        if self.cancel is not None and self.cancel.is_set():
            raise ExecutionCancelled("Execution cancelled.")
        now = time.monotonic()
        delay = max(0.0, self.next_request - now)
        if now + delay >= self.deadline:
            raise TraceBudgetExceeded
        if delay:
            time.sleep(delay)
        self.next_request = time.monotonic() + 0.55


def _operations(resource: ResourceDrift) -> dict[str, list[str]]:
    if resource.resource_type in RULE_TYPES:
        return rule_operations(resource)
    if resource.resource_type not in _EVENTS:
        return {}
    if resource.actions == ("delete",):
        name = (
            "TerminateInstances"
            if resource.resource_type == "aws_instance"
            else "DeleteSecurityGroup"
        )
        return {name: ["(resource deletion)"]}
    operations = {}
    for change in resource.attributes:
        if change.path:
            attribute = change.path[0]
            for name in _EVENTS[resource.resource_type].get(attribute, ()):
                operations.setdefault(name, []).append(attribute)
    return operations


def _target(resource: ResourceDrift):
    is_rule = resource.resource_type in RULE_TYPES
    if resource.resource_type not in _EVENTS and not is_rule:
        return None, "unsupported_resource"
    if not _operations(resource):
        return None, "unsupported_change"
    identifiers = resource.identifiers
    if any(value.get("status") == "sensitive" for value in identifiers.values()):
        return None, "sensitive_identifiers"
    identity, arn = (identifiers.get(name, {}) for name in ("id", "arn"))
    if any(value.get("status") != "known" for value in (identity, arn)):
        return None, "missing_identifiers"
    resource_id, arn = identity.get("value"), arn.get("value")
    kind, prefix = (
        ("security-group-rule", "sgr")
        if is_rule
        else (
            ("instance", "i")
            if resource.resource_type == "aws_instance"
            else ("security-group", "sg")
        )
    )
    if not isinstance(resource_id, str) or not re.fullmatch(
        rf"{prefix}-(?:[0-9a-f]{{8}}|[0-9a-f]{{17}})", resource_id
    ):
        return None, "invalid_identifiers"
    match = re.fullmatch(
        rf"arn:aws:ec2:([a-z0-9-]+):(\d{{12}}):{kind}/{resource_id}",
        arn if isinstance(arn, str) else "",
    )
    if not match:
        return None, "invalid_identifiers"
    if is_rule:
        if not re.fullmatch(r"sgr-[0-9a-f]{17}", resource_id):
            return None, "invalid_identifiers"
        alias = identifiers.get("security_group_rule_id")
        if alias is not None and (
            alias.get("status") != "known" or alias.get("value") != resource_id
        ):
            return None, "conflicting_rule_identifiers"
        parent = identifiers.get("security_group_id", {})
        if parent.get("status") != "known":
            return None, "missing_parent_group"
        group = parent.get("value")
        if not isinstance(group, str) or not re.fullmatch(
            r"sg-(?:[0-9a-f]{8}|[0-9a-f]{17})", group
        ):
            return None, "invalid_parent_group"
        expected_source = "saved" if resource.actions == ("delete",) else "observed"
        if (
            any(
                value.get("source") != expected_source
                for value in (identity, identifiers["arn"], parent)
            )
            or alias is not None
            and alias.get("source") != expected_source
        ):
            return None, "ambiguous_rule_identity"
        return (group, match[1], match[2]), None
    return (resource_id, match[1], match[2]), None


def _text(value):
    return value if isinstance(value, str) and value else None


def _references(event: dict, resource_id: str, arn: str) -> bool:
    if any(
        item.get("ResourceName") in (resource_id, arn)
        for item in event.get("Resources", [])
        if isinstance(item, dict)
    ):
        return True
    return False


def _event(wrapper, raw, resource, target, operations, start, end, unresolved=None):
    resource_id, region, account = target
    name = _text(raw.get("eventName"))
    is_rule = resource.resource_type in RULE_TYPES
    referenced = _references(wrapper, resource_id, resource.identifiers["arn"]["value"])
    if is_rule:
        parent_arn = f"arn:aws:ec2:{region}:{account}:security-group/{resource_id}"
        referenced = (
            referenced
            or _references(wrapper, resource_id, parent_arn)
            or _references(
                wrapper,
                resource.identifiers["id"]["value"],
                resource.identifiers["arn"]["value"],
            )
        )
    if (
        name not in operations
        or raw.get("eventSource") != "ec2.amazonaws.com"
        or raw.get("awsRegion") != region
        or raw.get("recipientAccountId") != account
        or not (raw.get("readOnly") is False or raw.get("readOnly") == "false")
        or raw.get("errorCode")
        or raw.get("eventCategory", "Management") != "Management"
        or raw.get("managementEvent", True) is not True
        or not referenced
    ):
        return None
    if name == "ModifyInstanceAttribute":
        parameters = raw.get("requestParameters")
        if not isinstance(parameters, dict) or "instanceType" not in parameters:
            return None
    event_id = _text(raw.get("eventID"))
    if not event_id or event_id != wrapper.get("EventId"):
        return None
    try:
        timestamp = datetime.fromisoformat(raw["eventTime"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None or not start <= timestamp <= end:
            return None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    matched_attributes = sorted(set(operations[name]))
    if is_rule:
        matched = match_rule_request(
            raw, resource_id, resource.identifiers["id"]["value"], matched_attributes
        )
        if matched is None:
            if unresolved is not None:
                unresolved.add(event_id)
            return None
        if matched is False:
            return None
        matched_attributes = matched
    identity = raw.get("userIdentity")
    identity = identity if isinstance(identity, dict) else {}
    actor = {}
    for key in ("type", "arn", "userName", "invokedBy"):
        if value := _text(identity.get(key)):
            actor[key] = value
    context = identity.get("sessionContext")
    if isinstance(context, dict) and isinstance(context.get("sessionIssuer"), dict):
        if issuer := _text(context["sessionIssuer"].get("arn")):
            actor["session_issuer_arn"] = issuer
    return {
        "event_id": event_id,
        "event_name": name,
        "event_source": "ec2.amazonaws.com",
        "event_time": timestamp.astimezone(timezone.utc).isoformat(),
        "region": region,
        "actor": actor,
        "matched_attributes": matched_attributes,
        "relation": "candidate",
    }


def lookup_resource(client, resource, target, start, end, deadline, recovered=None):
    events = recovered if recovered is not None else {}
    pages = malformed = 0
    truncated = False
    operations = _operations(resource)
    unresolved = set()
    paginator = client.get_paginator("lookup_events")
    for page in paginator.paginate(
        LookupAttributes=[
            {"AttributeKey": "ResourceName", "AttributeValue": target[0]}
        ],
        StartTime=start,
        EndTime=end,
        PaginationConfig={"PageSize": 50},
    ):
        pages += 1
        for wrapper in page.get("Events", []):
            try:
                raw = json.loads(wrapper["CloudTrailEvent"])
                if not isinstance(raw, dict):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                malformed += 1
                continue
            event = _event(
                wrapper, raw, resource, target, operations, start, end, unresolved
            )
            if event:
                events[event["event_id"]] = event
        if pages >= MAX_PAGES or time.monotonic() >= deadline:
            truncated = bool(page.get("NextToken"))
            break
    unsupported = (
        []
        if resource.actions == ("delete",)
        else [
            list(change.path)
            for change in resource.attributes
            if not change.path
            or (
                len(change.path) != 1 or change.path[0] not in RULE_FIELDS
                if resource.resource_type in RULE_TYPES
                else change.path[0] not in _EVENTS[resource.resource_type]
            )
        ]
    )
    trace = {
        "status": "partial"
        if truncated or malformed or unsupported or unresolved
        else ("matched" if events else "no_events"),
        "events": sorted(
            events.values(), key=lambda event: event["event_time"], reverse=True
        ),
        "pages_scanned": pages,
        "truncated": truncated,
        "malformed_events": malformed,
        "unsupported_attributes": unsupported,
    }
    if resource.resource_type in RULE_TYPES:
        trace.update(
            correlation="exact_rule_id",
            lookup_scope="parent_security_group",
            unresolved_rule_events=len(unresolved),
        )
    return trace


def _trace(resource, status, reason):
    return replace(resource, trace={"status": status, "reason": reason, "events": []})


def _session(options):
    import boto3

    return boto3.Session(profile_name=options.profile, region_name=options.region)


def enrich_trace(result: DriftResult, options: DriftOptions) -> DriftResult:
    """Adapter boundary: preserve drift evidence even when AWS tracing fails."""
    metadata = {"status": "not_needed", "has_errors": False}
    resources = list(result.resources)
    targets = {}
    for index, resource in enumerate(resources):
        target, reason = _target(resource)
        if reason:
            resources[index] = _trace(resource, "skipped", reason)
        elif len(targets) >= MAX_RESOURCES:
            resources[index] = _trace(resource, "skipped", "resource_limit")
        else:
            targets[index] = target
    if not resources:
        return replace(result, trace=metadata, notes=result.notes + (_NOTE,))
    if not targets:
        metadata["status"] = "partial"
        return replace(
            result,
            resources=tuple(resources),
            trace=metadata,
            notes=result.notes + (_NOTE,),
        )
    try:
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        for index in targets:
            resources[index] = _trace(resources[index], "error", "dependency_missing")
        metadata.update(
            status="error",
            has_errors=True,
            message="Install InfraLens with the aws-trace extra.",
        )
    else:
        end = datetime.fromisoformat(result.checked_at)
        start = end - timedelta(days=options.lookback_days or 7)
        deadline = time.monotonic() + options.timeout
        metadata.update(
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            max_resources=MAX_RESOURCES,
            max_pages_per_resource=MAX_PAGES,
        )
        try:
            session = _session(options)
            region = options.region or session.region_name
            if not region:
                raise ValueError("region_required")
            config = Config(
                connect_timeout=5,
                read_timeout=10,
                retries={"total_max_attempts": 2, "mode": "standard"},
            )
            account = session.client("sts", config=config).get_caller_identity()[
                "Account"
            ]
            metadata.update(account_id=account, region=region)
            client = session.client("cloudtrail", region_name=region, config=config)
            client.meta.events.register(
                "before-send.cloudtrail.LookupEvents",
                LookupThrottle(deadline, options.cancel),
            )
            for index, target in targets.items():
                if options.cancel is not None and options.cancel.is_set():
                    raise ExecutionCancelled("Execution cancelled.")
                resource = resources[index]
                if target[1:] != (region, account):
                    resources[index] = _trace(resource, "skipped", "scope_mismatch")
                    continue
                if time.monotonic() >= deadline:
                    resources[index] = _trace(resource, "error", "budget_exhausted")
                    metadata["has_errors"] = True
                    continue
                recovered = {}
                try:
                    trace = lookup_resource(
                        client, resource, target, start, end, deadline, recovered
                    )
                    resources[index] = replace(resource, trace=trace)
                except (BotoCoreError, ClientError, TraceBudgetExceeded) as error:
                    # Handle AWS errors here to retain the normalized drift report.
                    reason = (
                        "budget_exhausted"
                        if isinstance(error, TraceBudgetExceeded)
                        else "aws_lookup_failed"
                    )
                    resources[index] = replace(
                        resource,
                        trace={
                            "status": "error",
                            "reason": reason,
                            "events": sorted(
                                recovered.values(),
                                key=lambda event: event["event_time"],
                                reverse=True,
                            ),
                        },
                    )
                    metadata["has_errors"] = True
        except ImportError:
            metadata.update(
                status="error",
                has_errors=True,
                message="Install InfraLens with the aws-trace extra.",
            )
            for index in targets:
                if resources[index].trace is None:
                    resources[index] = _trace(
                        resources[index], "error", "dependency_missing"
                    )
        except (BotoCoreError, ClientError, ValueError):
            metadata.update(status="error", has_errors=True)
            for index in targets:
                if resources[index].trace is None:
                    resources[index] = _trace(
                        resources[index], "error", "aws_session_or_scope_failed"
                    )
        if metadata["status"] != "error":
            metadata["status"] = (
                "complete"
                if all(
                    resource.trace["status"] in ("matched", "no_events")
                    for resource in resources
                )
                else "partial"
            )
    return replace(
        result,
        resources=tuple(resources),
        trace=metadata,
        notes=result.notes + (_NOTE,),
    )
