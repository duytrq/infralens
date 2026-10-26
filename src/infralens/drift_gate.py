"""CI exit policy over all drift findings, independent of report presentation."""

from infralens.drift import REVIEW_POLICY, DriftResult
from infralens.reporting import plain


def evaluate_gate(
    result: DriftResult,
    *,
    fail_on_drift: bool = False,
    fail_on_priority: str | None = None,
    fail_on_unknown: bool = False,
) -> dict:
    if fail_on_priority not in (None, "medium", "high"):
        raise ValueError("Unsupported drift gate priority.")
    counts = {"high": 0, "medium": 0, "unknown": 0}
    matches = []
    unassessed = 0
    for resource in result.resources:
        assessment = resource.assessment
        candidate = assessment.get("priority") if isinstance(assessment, dict) else None
        if (
            not isinstance(assessment, dict)
            or assessment.get("policy") != REVIEW_POLICY
            or not isinstance(candidate, str)
            or candidate not in counts
        ):
            priority = "unknown"
            unassessed += 1
        else:
            priority = assessment["priority"]
        counts[priority] += 1
        reasons = []
        if fail_on_drift:
            reasons.append("any_drift")
        if fail_on_priority is not None and (
            priority == "high" or priority == "medium" and fail_on_priority == "medium"
        ):
            reasons.append("priority_threshold")
        if fail_on_unknown and priority == "unknown":
            reasons.append("unknown_priority")
        if reasons:
            matches.append(
                {"address": resource.address, "priority": priority, "reasons": reasons}
            )
    trace_error = bool(result.trace and result.trace.get("has_errors"))
    exit_code = 3 if trace_error else 1 if matches else 0
    return {
        "policy": "drift-gate-v1",
        "review_policy": REVIEW_POLICY,
        "status": "incomplete" if trace_error else "failed" if matches else "passed",
        "exit_code": exit_code,
        "criteria": {
            "any_drift": fail_on_drift,
            "minimum_priority": fail_on_priority,
            "unknown_priority": fail_on_unknown,
        },
        "priority_counts": counts,
        "unassessed_resources": unassessed,
        "matched_count": len(matches),
        "matched_resources": matches,
        "reason_codes": ["cloudtrail_incomplete"] if trace_error else [],
    }


def render_gate(gate: dict) -> str:
    criteria = gate["criteria"]
    lines = [
        f"CI gate: {gate['status']} (exit {gate['exit_code']}); "
        f"matched resources: {gate['matched_count']}",
        f"  Any drift: {str(criteria['any_drift']).lower()}; "
        f"minimum priority: {criteria['minimum_priority'] or 'disabled'}; "
        f"unknown priority: {'fail' if criteria['unknown_priority'] else 'allow'}",
    ]
    for match in gate["matched_resources"]:
        lines.append(
            f"  {plain(match['address'])}: {match['priority']} "
            f"({', '.join(match['reasons'])})"
        )
    lines.append(
        "  Gate passed does not mean no drift or complete infrastructure coverage."
    )
    return "\n".join(lines) + "\n"
