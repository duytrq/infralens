"""Single-attempt Security/Drift uploads with metadata kept only in memory."""

import base64
import hashlib
import json
import re
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import typer

from infralens.cloud_auth import access_token, http, origin
from infralens.errors import ExecutionError, InvalidInput
from infralens.options import SEVERITIES

MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_SECURITY_REPORT_BYTES = 50 * 1024 * 1024


def identifier(value, option):
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,63}", value
    ):
        raise InvalidInput(f"{option}: use 1-64 lowercase letters, digits, '_' or '-'.")
    return value


def cloud_report(data, root):
    """Keep resource values; remove machine-specific source locations."""
    report = deepcopy(data)
    root = root.resolve()
    for resource in report["resources"]:
        source = resource.get("source")
        if not source:
            continue
        locations = source.get("locations", [])
        relative = []
        outside = False
        for location in locations:
            try:
                path = Path(location["file"]).resolve().relative_to(root)
                if (
                    any(part in ("", "..") for part in path.parts)
                    or ":" in path.as_posix()
                    or "\\" in path.as_posix()
                ):
                    raise ValueError
            except (ValueError, OSError, RuntimeError):
                outside = True
                continue
            relative.append({**location, "file": path.as_posix()})
        if outside:
            source.update(status="unavailable", reason="outside_project_root")
        if relative:
            source["locations"] = relative
        else:
            source.pop("locations", None)
    return report


def build_manifest(report, payload, options, started, finished):
    counts = {"high": 0, "medium": 0, "unknown": 0}
    for resource in report["resources"]:
        assessment = resource.get("assessment", {})
        priority = assessment.get("priority")
        if assessment.get("policy") != "builtin-review-v2" or priority not in counts:
            priority = "unknown"
        counts[priority] += 1
    trace = report.get("trace", {})
    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "project_id": options.upload.project,
        "run_type": "drift",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": max(0, int((finished - started).total_seconds() * 1000)),
        "source": {"relative_path": "."},
        "tool": {
            "infralens_version": version("infralens"),
            "engine": "terraform",
            "engine_version": report["terraform_version"],
        },
        "scope": options.upload.scope,
        "drift_options": {
            "input_mode": report["input_mode"],
            "trace": options.trace,
            "lookback_days": options.lookback_days,
            "gate": {
                "any_drift": options.fail_on_drift,
                "minimum_priority": options.fail_on_priority,
                "unknown_priority": options.fail_on_unknown,
            },
        },
        "result": {
            "collection_status": "partial" if trace.get("has_errors") else "completed",
            "has_drift": report["has_drift"],
            "summary": report["summary"],
            "priority_counts": counts,
            "gate_status": report.get("gate", {}).get("status", "disabled"),
            "trace_status": trace.get("status", "disabled"),
        },
        "artifact": {
            "format": "json",
            "content_type": "application/json",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "schema_version": "1.0",
        },
    }


def upload_drift(report, options, started, finished):
    # The writer uses native newlines on Windows; sign the actual file bytes.
    payload = options.output.read_bytes()
    if len(payload) > MAX_REPORT_BYTES:
        raise ExecutionError(
            "Drift report exceeds the 2 MiB upload limit; local JSON was saved."
        )
    metadata = build_manifest(report, payload, options, started, finished)
    return upload_report(metadata, payload, options.upload.api_url)


def upload_scan(
    result, options, started, finished, engine_version, failed, ignore_sha256
):
    payload = options.output.read_bytes()
    if len(payload) > MAX_SECURITY_REPORT_BYTES:
        raise ExecutionError(
            "Security report exceeds the 50 MiB upload limit; local JSON was saved."
        )
    counts = {severity: 0 for severity in SEVERITIES}
    for finding in result.findings:
        counts[finding.severity] += 1
    warnings = sorted(
        {
            "embedded_checks" if "embedded checks" in message else "engine_warning"
            for message in result.diagnostics
        }
    )
    threshold_status = "not_evaluated"
    if options.fail_on is not None:
        threshold_status = "failed" if failed else "passed"
    metadata = {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "project_id": options.upload.project,
        "run_type": "security_scan",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": max(0, int((finished - started).total_seconds() * 1000)),
        "source": {"relative_path": "."},
        "tool": {
            "infralens_version": version("infralens"),
            "engine": "trivy",
            "engine_version": engine_version,
        },
        "scan_options": {
            "severity": list(options.severity),
            "fail_on": options.fail_on,
            "ignore_sha256": ignore_sha256,
        },
        "result": {
            "scan_status": "completed",
            "threshold_status": threshold_status,
            "findings": {"total": sum(counts.values()), "by_severity": counts},
            "warnings": warnings,
        },
        "artifact": {
            "format": "json",
            "content_type": "application/json",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "schema_version": 2,
        },
    }
    return upload_report(metadata, payload, options.upload.api_url)


def upload_report(metadata, payload, api_url):
    api_url = origin(api_url)
    try:
        run_type = metadata["run_type"]
        if run_type not in ("drift", "security_scan"):
            raise ValueError
        maximum = MAX_REPORT_BYTES if run_type == "drift" else MAX_SECURITY_REPORT_BYTES
        if len(payload) > maximum:
            raise ValueError
        report = json.loads(payload)
        schema = "1.0" if run_type == "drift" else 2
        artifact = metadata["artifact"]
        matches = isinstance(report, dict) and (
            report.get("kind") == "drift" and report.get("schema_version") == schema
            if run_type == "drift"
            else report.get("SchemaVersion") == schema
        )
        if (
            not matches
            or artifact["format"] != "json"
            or artifact["content_type"] != "application/json"
            or artifact["schema_version"] != schema
            or artifact["sha256"] != hashlib.sha256(payload).hexdigest()
            or artifact["size_bytes"] != len(payload)
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        raise InvalidInput("Report bytes do not match the upload metadata.") from None
    token = access_token(api_url)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    _, response = http(
        "POST",
        api_url + "/v1/runs",
        data=json.dumps(metadata).encode(),
        headers=headers,
        statuses=(200, 201),
    )
    try:
        registered = json.loads(response)
        if registered["run"]["run_id"] != metadata["run_id"]:
            raise ValueError
        upload = registered["upload"]
        if upload is None:
            if registered["run"]["upload_status"] != "ready":
                raise ValueError
        else:
            signed = urlsplit(upload["url"])
            expected = {
                "content-type": "application/json",
                "content-length": str(len(payload)),
                "x-amz-checksum-sha256": base64.b64encode(
                    hashlib.sha256(payload).digest()
                ).decode(),
                "x-amz-sdk-checksum-algorithm": "SHA256",
                "x-amz-tagging": "state=pending",
                "if-none-match": "*",
            }
            if (
                upload["method"] != "PUT"
                or upload["headers"] != expected
                or signed.scheme != "https"
                or signed.username
                or signed.password
                or not signed.hostname
                or not signed.hostname.endswith(".amazonaws.com")
                or ".s3." not in signed.hostname
                or signed.fragment
            ):
                raise ValueError
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise ExecutionError(
            "The service returned an invalid upload response."
        ) from None
    if upload is not None:
        # The access token is sent only to the configured API, never to S3.
        http(
            "PUT",
            upload["url"],
            data=payload,
            headers=upload["headers"],
            statuses=(200, 204, 412),
        )
        _, completed = http(
            "POST",
            api_url + f"/v1/runs/{metadata['run_id']}/complete",
            data=b"{}",
            headers=headers,
        )
        try:
            completed = json.loads(completed)
            if (
                completed["run_id"] != metadata["run_id"]
                or completed["upload_status"] != "ready"
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise ExecutionError(
                "The service did not confirm the uploaded report."
            ) from None
    kind = "drift run" if run_type == "drift" else "security scan"
    typer.echo(f"Uploaded {kind} {metadata['run_id']}.", err=True)
    if run_type == "security_scan":
        typer.echo(
            "Upload: ready; dashboard analysis may still be processing.", err=True
        )
