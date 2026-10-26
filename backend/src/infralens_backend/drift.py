"""Bounded drift validation and private report/comparison reads."""

import json
import math
import time

from infralens_backend import validation as v
from infralens_backend.drift_schemas import MAX_REPORT_BYTES, REPORT, RESULT
from infralens_backend.errors import ApiError, conflict


def invalid_report():
    return ApiError(409, "artifact_invalid", "Invalid normalized drift report.")


def priority(resource):
    assessment = resource.get("assessment", {})
    candidate = assessment.get("priority")
    if assessment.get("policy") == "builtin-review-v2" and candidate in (
        "high",
        "medium",
        "unknown",
    ):
        return candidate, False
    return "unknown", True


def summarize(report, criteria):
    resources = report["resources"]
    counts = {"high": 0, "medium": 0, "unknown": 0}
    matches, unassessed = [], 0
    for resource in resources:
        value, uncertain = priority(resource)
        counts[value] += 1
        unassessed += int(uncertain)
        reasons = []
        if criteria["any_drift"]:
            reasons.append("any_drift")
        threshold = criteria["minimum_priority"]
        if threshold and (
            value == "high" or threshold == "medium" and value == "medium"
        ):
            reasons.append("priority_threshold")
        if criteria["unknown_priority"] and value == "unknown":
            reasons.append("unknown_priority")
        if reasons:
            matches.append(
                {"address": resource["address"], "priority": value, "reasons": reasons}
            )
    trace = report.get("trace", {})
    trace_error = trace.get("has_errors", False)
    enabled = any(criteria.values())
    gate_status = "incomplete" if trace_error else "failed" if matches else "passed"
    summary = {
        "resources": len(resources),
        "attributes": sum(len(r["attributes"]) for r in resources),
    }
    result = {
        "collection_status": "partial" if trace_error else "completed",
        "has_drift": bool(resources),
        "summary": summary,
        "priority_counts": counts,
        "gate_status": gate_status if enabled else "disabled",
        "trace_status": trace.get("status", "disabled"),
    }
    gate = (
        {
            "policy": "drift-gate-v1",
            "review_policy": "builtin-review-v2",
            "status": gate_status,
            "exit_code": 3 if trace_error else 1 if matches else 0,
            "criteria": criteria,
            "priority_counts": counts,
            "unassessed_resources": unassessed,
            "matched_count": len(matches),
            "matched_resources": matches,
            "reason_codes": ["cloudtrail_incomplete"] if trace_error else [],
        }
        if enabled
        else None
    )
    return result, gate


def validate_metadata(payload):
    options, result = payload["drift_options"], payload["result"]
    if options["trace"] != (options["lookback_days"] is not None):
        raise v.invalid("Trace requires lookback_days; disabled trace requires null.")
    if result["has_drift"] != bool(result["summary"]["resources"]):
        raise v.invalid("Drift summary is inconsistent.")
    if sum(result["priority_counts"].values()) != result["summary"]["resources"]:
        raise v.invalid("Priority counts must equal resource count.")
    if options["trace"] != (result["trace_status"] != "disabled"):
        raise v.invalid("Trace options and result disagree.")
    if bool(any(options["gate"].values())) != (result["gate_status"] != "disabled"):
        raise v.invalid("Gate options and result disagree.")


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


def validate_report(stream, metadata):
    try:
        raw = stream.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise invalid_report()
        report = json.loads(
            raw,
            object_pairs_hook=v.no_duplicates,
            parse_constant=v.reject_constant,
            parse_float=finite_float,
        )
        stack = [(report, 0)]
        while stack:
            value, depth = stack.pop()
            if depth > 64:
                raise invalid_report()
            if isinstance(value, dict):
                if any(len(key) > 4096 for key in value):
                    raise invalid_report()
                stack.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                stack.extend((child, depth + 1) for child in value)
        v.validate(report, REPORT)
        # API Gateway uses a Lambda proxy response; JSON escaping also counts
        # towards Lambda's response limit, even for a small UTF-8 input object.
        if len(json.dumps({"body": json.dumps(report)}).encode()) > 5 * 1024**2:
            raise invalid_report()
        addresses = set()
        for resource in report["resources"]:
            if resource["address"] in addresses:
                raise invalid_report()
            addresses.add(resource["address"])
            paths = [tuple(a["path"]) for a in resource["attributes"]]
            if len(paths) != len(set(paths)):
                raise invalid_report()
            source = resource.get("source", {})
            locations = source.get("locations", [])
            if source.get("status") == "located" and len(locations) != 1:
                raise invalid_report()
            for location in locations:
                v.relative_path(location["file"])
                if location["end_line"] < location["start_line"]:
                    raise invalid_report()
        options = metadata["drift_options"]
        trace = report.get("trace")
        resource_traces = [
            resource.get("trace", {}) for resource in report["resources"]
        ]
        if trace:
            if trace["status"] == "error" and not trace["has_errors"]:
                raise invalid_report()
            if (
                any(t.get("status") == "error" for t in resource_traces)
                and not trace["has_errors"]
            ):
                raise invalid_report()
            if trace["status"] == "complete" and (
                trace["has_errors"]
                or any(
                    t.get("status") not in ("matched", "no_events")
                    for t in resource_traces
                )
            ):
                raise invalid_report()
            if trace["status"] == "not_needed" and report["resources"]:
                raise invalid_report()
        elif any(resource_traces):
            raise invalid_report()
        result, gate = summarize(report, options["gate"])
        v.validate(result, RESULT)
        if (
            report["summary"] != result["summary"]
            or report["has_drift"] != result["has_drift"]
            or result != metadata["result"]
            or report["input_mode"] != options["input_mode"]
            or report["terraform_version"] != metadata["tool"]["engine_version"]
            or options["trace"] != ("trace" in report)
            or report.get("gate") != gate
        ):
            raise invalid_report()
        review = report.get("review_summary")
        if review and (
            review["policy"] != "builtin-review-v2"
            or review["priority_counts"] != result["priority_counts"]
        ):
            raise invalid_report()
        return report
    except (
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
        OverflowError,
        ApiError,
    ):
        raise invalid_report() from None


class Drift:
    def __init__(self, runs):
        self.runs = runs

    def ready(self, owner, run):
        item = self.runs.get(owner, run)
        if item["data"]["run_type"] != "drift":
            raise conflict("This operation requires a drift run.")
        if item["data"]["upload_status"] != "ready":
            raise conflict("Report upload has not completed.")
        return item

    def read(self, owner, item):
        response = self.runs.s3.get_object(
            Bucket=self.runs.settings.bucket,
            Key=self.runs.object_key(owner, item),
            ChecksumMode="ENABLED",
        )
        with response["Body"] as stream:
            report = validate_report(stream, item["data"])
        # Do not expose data after concurrent deletion or reuse of this UUID.
        current = self.runs.get(owner, item["data"]["run_id"])
        if current["generation"] != item["generation"]:
            raise conflict("Run changed; refresh and retry.")
        return report

    def report(self, owner, run):
        return self.read(owner, self.ready(owner, run))

    def baseline(self, owner, current):
        data = current["data"]
        cursor = None
        deadline = time.monotonic() + 8
        for _ in range(120):
            if time.monotonic() >= deadline:
                break
            params = {
                "project_id": data["project_id"],
                "run_type": "drift",
                "scope": data["scope"],
                "to": data["started_at"],
                "limit": "20",
            }
            if cursor:
                params["cursor"] = cursor
            page = self.runs.history(owner, {"queryStringParameters": params})
            for candidate in page["items"]:
                if (
                    (candidate["started_at"], candidate["run_id"])
                    < (data["started_at"], data["run_id"])
                    and candidate["drift_options"]["input_mode"]
                    == data["drift_options"]["input_mode"]
                    and candidate["result"]["collection_status"] == "completed"
                ):
                    return self.ready(owner, candidate["run_id"])
            cursor = page["next_cursor"]
            if not cursor:
                return None
        raise ApiError(
            503, "baseline_unavailable", "Baseline lookup is busy; retry later."
        )

    def comparison(self, owner, run, event):
        from infralens_backend.drift_comparison import compare_runs

        params = v.query(event, ["baseline_id", "limit", "cursor"])
        current = self.ready(owner, run)
        data = current["data"]
        baseline = (
            self.ready(owner, v.run_id(params["baseline_id"]))
            if "baseline_id" in params
            else self.baseline(owner, current)
        )
        if baseline:
            other = baseline["data"]
            if (
                run == other["run_id"]
                or any(data[key] != other[key] for key in ("project_id", "scope"))
                or data["drift_options"]["input_mode"]
                != other["drift_options"]["input_mode"]
                or other["result"]["collection_status"] != "completed"
            ):
                raise v.invalid(
                    "Baseline requires a completed run in the same project, scope/mode."
                )
        scope = {
            "owner": owner,
            "run": run,
            "generation": current["generation"],
            "baseline": baseline["data"]["run_id"] if baseline else None,
            "baseline_generation": baseline["generation"] if baseline else None,
        }
        cursor = v.decode_cursor(params.get("cursor"), scope, {"offset": None})
        offset = int(cursor["offset"]) if cursor and cursor["offset"].isdigit() else 0
        if cursor and not cursor["offset"].isdigit():
            raise v.invalid("Invalid comparison cursor.")
        current_report = self.read(owner, current)
        baseline_report = self.read(owner, baseline) if baseline else None
        compared = compare_runs(
            {"id": run, "report_json": current_report},
            {"id": baseline["data"]["run_id"], "report_json": baseline_report}
            if baseline
            else None,
        )
        limit = v.page_limit(params)
        total = len(compared["resources"])
        compared["resources"] = compared["resources"][offset : offset + limit]
        compared["next_cursor"] = (
            v.encode_cursor({"offset": str(offset + limit)}, scope)
            if offset + limit < total
            else None
        )
        latest = self.ready(owner, run)
        if latest["generation"] != current["generation"]:
            raise conflict("Run changed; refresh and retry.")
        if baseline:
            latest = self.ready(owner, baseline["data"]["run_id"])
            if latest["generation"] != baseline["generation"]:
                raise conflict("Baseline changed; refresh and retry.")
        return compared
