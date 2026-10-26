"""Render only the normalized, sensitivity-filtered drift report."""

import json

from infralens.drift import DriftResult
from infralens.reporting import plain


def _display(value: dict) -> str:
    if value["status"] != "known":
        return f"[{value['status']}]"
    return plain(json.dumps(value["value"], ensure_ascii=True, sort_keys=True))


def render_drift(result: DriftResult) -> str:
    lines = [
        f"Infrastructure drift (Terraform {plain(result.terraform_version)})",
        f"Resources with drift: {len(result.resources)}",
    ]
    if summary := result.review_summary():
        counts = ", ".join(f"{k}={v}" for k, v in summary["priority_counts"].items())
        lines.append(f"Review priorities: {counts}")
    if not result.resources:
        lines.append("No managed resource drift recorded in the plan.")
    else:
        lines.extend(["", "RESOURCE | ACTION | ATTRIBUTE | SAVED STATE -> OBSERVED"])
        for resource in result.resources:
            if resource.assessment is not None:
                assessment = resource.assessment
                lines.append(
                    f"Review {plain(resource.address)}: {assessment['priority']}"
                )
                for signal in assessment["signals"]:
                    lines.append(f"  {signal['code']}: {signal['description']}")
                for step in assessment["guidance"]["review_steps"]:
                    lines.append(f"  {step}")
                for choice in assessment["guidance"]["choices"]:
                    lines.append(f"  Choice: {choice['title']}")
                    lines.extend(f"    {step}" for step in choice["steps"])
            if resource.source is not None:
                source = resource.source
                lines.append(
                    f"Source {plain(resource.address)}: {source['status']}"
                    + (f" ({source['reason']})" if source.get("reason") else "")
                )
                for location in source.get("locations", []):
                    lines.append(
                        f"  {plain(location['file'])}:{location['start_line']}"
                        f"-{location['end_line']} (resource block)"
                    )
            if resource.identifiers:
                identity = "; ".join(
                    f"{name}={_display(value)}"
                    + (f" ({value['source']})" if value.get("source") else "")
                    for name, value in resource.identifiers.items()
                )
                lines.append(f"Identity {plain(resource.address)}: {identity}")
            if resource.network_context is not None:
                context = resource.network_context
                lines.append("  Network context (includes unchanged rule fields):")
                for name, before in context["before"].items():
                    after = context["after"][name]
                    if before["status"] == after["status"] == "absent":
                        continue
                    lines.append(f"    {name}: {_display(before)} -> {_display(after)}")
            for attribute in resource.attributes:
                # JSON path components avoid ambiguous dots in tag/map keys.
                path = json.dumps(list(attribute.path), ensure_ascii=True)
                lines.append(
                    f"{plain(resource.address)} | {','.join(resource.actions)} | "
                    f"{path} | {_display(attribute.before)} -> "
                    f"{_display(attribute.after)}"
                )
            if not resource.attributes:
                lines.append(
                    f"{plain(resource.address)} | {','.join(resource.actions)} | "
                    "(resource change; no visible attribute delta)"
                )
    if result.trace is not None:
        lines.append(f"CloudTrail trace: {result.trace['status']}")
        if result.trace.get("message"):
            lines.append(plain(result.trace["message"]))
        for resource in result.resources:
            trace = resource.trace or {}
            lines.append(
                f"Trace {plain(resource.address)}: {trace.get('status', 'unknown')}"
                + (f" ({trace['reason']})" if trace.get("reason") else "")
            )
            if trace.get("correlation") == "exact_rule_id":
                lines.append(
                    "  Match: exact rule ID; lookup: parent security group; "
                    f"unresolved events: {trace['unresolved_rule_events']}"
                )
            for event in trace.get("events", []):
                actor = json.dumps(event["actor"], ensure_ascii=True, sort_keys=True)
                lines.append(
                    f"  Candidate {plain(event['event_time'])} "
                    f"{plain(event['event_name'])} actor={actor} "
                    f"event_id={plain(event['event_id'])}"
                )
    for normalization in result.normalizations:
        path = json.dumps(normalization["path"], ensure_ascii=True)
        lines.append(
            f"Normalized {plain(normalization['address'])} {path}: "
            f"{plain(normalization['reason'])}"
        )
    lines.extend(f"Note: {note}" for note in result.notes)
    return "\n".join(lines) + "\n"
