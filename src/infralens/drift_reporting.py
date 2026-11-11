"""Compact drift cards over normalized, sensitivity-filtered report data."""

import json
from collections import Counter
from itertools import islice

import typer

from infralens.drift import REVIEW_POLICY, DriftResult
from infralens.reporting import _severity, plain

MAX_CHANGES = 12
MAX_EVENTS = 2


def priority(resource):
    assessment = resource.assessment or {}
    if assessment.get("policy") != REVIEW_POLICY:
        return "UNKNOWN"
    value = assessment.get("priority", "unknown")
    return value.upper() if value in ("high", "medium", "unknown") else "UNKNOWN"


def _display(value):
    if value["status"] != "known":
        return f"[{plain(value['status'])}]"
    raw = value["value"]
    if isinstance(raw, str) and len(raw) > 180:
        raw = raw[:180] + "..."
    elif isinstance(raw, (dict, list)):
        return "[complex value; see JSON report]"
    return plain(json.dumps(raw, ensure_ascii=False, sort_keys=True))


def _path(parts):
    text = ""
    for part in parts:
        if isinstance(part, int):
            text += f"[{part}]"
        elif str(part).isidentifier():
            text += ("." if text else "") + str(part)
        else:
            text += "[" + json.dumps(part, ensure_ascii=True) + "]"
    return plain(text) or "(resource)"


def changed_values(path, before, after, depth=0):
    if before == after and before["status"] == "known":
        return
    if before["status"] == after["status"] == "known" and depth < 8:
        old, new = before["value"], after["value"]
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys()):
                yield from changed_values(
                    (*path, key),
                    {"status": "known", "value": old[key]}
                    if key in old
                    else {"status": "absent"},
                    {"status": "known", "value": new[key]}
                    if key in new
                    else {"status": "absent"},
                    depth + 1,
                )
            return
        if isinstance(old, list) and isinstance(new, list):
            for index in range(max(len(old), len(new))):
                yield from changed_values(
                    (*path, index),
                    {"status": "known", "value": old[index]}
                    if index < len(old)
                    else {"status": "absent"},
                    {"status": "known", "value": new[index]}
                    if index < len(new)
                    else {"status": "absent"},
                    depth + 1,
                )
            return
    yield path, before, after


def _trace(resource):
    trace = resource.trace or {}
    events = trace.get("events", [])
    status = trace.get("status", "not_collected")
    reason = trace.get("reason", "")
    if events:
        suffix = (
            "; exact rule ID" if trace.get("correlation") == "exact_rule_id" else ""
        )
        lines = [f"  Trace: {len(events)} candidate event(s){suffix}"]
        for event in events[:MAX_EVENTS]:
            actor = event.get("actor", {})
            identity = (
                actor.get("arn")
                or actor.get("userName")
                or actor.get("type")
                or "unknown"
            )
            lines.append(
                f"    Candidate {plain(event['event_time'])} "
                f"{plain(event['event_name'])}"
            )
            lines.append(f"      Actor: {plain(str(identity))}")
        if len(events) > MAX_EVENTS:
            lines.append(
                f"    ... {len(events) - MAX_EVENTS} more event(s) in JSON report"
            )
        if status in ("partial", "error"):
            lines.append(f"    Lookup {status}: results may be incomplete")
        return lines
    if reason == "unsupported_resource":
        return ["  Trace: unsupported resource"]
    detail = {
        "no_events": "no matching events found",
        "skipped": "skipped",
        "not_needed": "not needed",
        "error": "lookup failed",
        "partial": "incomplete lookup",
        "not_collected": "not collected",
    }.get(status, status)
    return [f"  Trace: {plain(detail)}" + (f" ({plain(reason)})" if reason else "")]


def render_drift(
    result: DriftResult, *, color=False, severity=None, excerpts=None
) -> str:
    allowed = set(severity or ("HIGH", "MEDIUM", "UNKNOWN"))
    resources = sorted(
        (r for r in result.resources if priority(r) in allowed),
        key=lambda r: ({"HIGH": 0, "MEDIUM": 1, "UNKNOWN": 2}[priority(r)], r.address),
    )
    counts = Counter(priority(r) for r in result.resources)
    lines = [
        f"Resources with drift: {len(result.resources)} | Displayed: {len(resources)}",
        "Review priorities: "
        + " ".join(
            _severity(f"[{p}: {counts[p]}]", p, color, dim=not counts[p])
            for p in ("HIGH", "MEDIUM", "UNKNOWN")
        ),
    ]
    if not result.resources:
        lines.append("No managed resource drift recorded in the plan.")
    elif not resources:
        lines.append("No resources match the displayed priorities.")
    for resource in resources:
        level = priority(resource)
        lines.extend(
            [
                "",
                _severity(f"[{level}]", level, color)
                + " "
                + (
                    typer.style(plain(resource.address), bold=True)
                    if color
                    else plain(resource.address)
                )
                + f" ({','.join(resource.actions)})",
            ]
        )
        source = resource.source or {}
        for location in source.get("locations", [])[:1]:
            location_text = (
                f"  {plain(location['file'])}:{location['start_line']}"
                f"-{location['end_line']}"
            )
            lines.append(
                typer.style(location_text, fg="cyan") if color else location_text
            )
        identity = resource.identifiers.get("id")
        if identity is not None:
            lines.append(f"  ID: {_display(identity)}")
        group = resource.identifiers.get("security_group_id")
        if group is not None:
            lines.append(f"  Security group: {_display(group)}")
        signals = (resource.assessment or {}).get("signals", [])
        signals = sorted(
            signals,
            key=lambda s: {"high": 0, "unknown": 1, "medium": 2}.get(
                s.get("priority"), 3
            ),
        )
        if signals:
            lines.append("  " + plain(signals[0]["description"]))
        if excerpts and resource.address in excerpts:
            lines.extend(
                _severity(line, level, color)
                if line.startswith("  > ")
                else typer.style(line, bold=True)
                if color and "Current configuration" in line
                else line
                for line in excerpts[resource.address]
            )
        changes = (
            leaf
            for attribute in resource.attributes
            for leaf in changed_values(
                attribute.path, attribute.before, attribute.after
            )
        )
        selected = list(islice(changes, MAX_CHANGES + 1))
        if selected:
            heading = "  Saved state -> Observed:"
            lines.append(typer.style(heading, bold=True) if color else heading)
            for path, before, after in selected[:MAX_CHANGES]:
                lines.append(f"    {_path(path)}")
                old, new = f"      - {_display(before)}", f"      + {_display(after)}"
                lines.extend(
                    [
                        typer.style(old, fg="red") if color else old,
                        typer.style(new, fg="green") if color else new,
                    ]
                )
            if len(selected) > MAX_CHANGES:
                lines.append("    ... more changed values in JSON report")
        else:
            lines.append("  Resource changed; no visible attribute delta.")
        if result.trace is not None:
            trace_lines = _trace(resource)
            status = (resource.trace or {}).get("status")
            if color and trace_lines:
                trace_color = (
                    "red"
                    if status == "error"
                    else "yellow"
                    if status == "partial"
                    else "cyan"
                )
                trace_lines[0] = typer.style(trace_lines[0], fg=trace_color)
            lines.extend(trace_lines)
    if result.trace is not None:
        unsupported = sum(
            (r.trace or {}).get("reason") == "unsupported_resource"
            for r in result.resources
        )
        matches = sum(bool((r.trace or {}).get("events")) for r in result.resources)
        lines.extend(
            [
                "",
                f"CloudTrail trace: {plain(result.trace['status'])} | "
                f"candidates={matches}/{len(result.resources)} | "
                f"unsupported={unsupported} | "
                f"lookup errors={'yes' if result.trace.get('has_errors') else 'no'}",
            ]
        )
        if result.trace.get("message"):
            lines.append("  " + plain(result.trace["message"]))
    if result.normalizations:
        lines.append(
            f"Normalized {len(result.normalizations)} provider representation "
            "difference(s); details in JSON."
        )
    return "\n".join(lines) + "\n"
