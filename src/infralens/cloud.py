"""Sanitized drift manifests and resumable uploads over the existing storage API."""

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
from infralens.reporting import write_report

MAX_REPORT_BYTES = 2 * 1024 * 1024


def identifier(value, option):
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,63}", value
    ):
        raise InvalidInput(f"{option}: use 1-64 lowercase letters, digits, '_' or '-'.")
    return value


def manifest_path(output):
    return Path(str(output) + ".upload.json")


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


def save_manifest(report, text, options, started, finished):
    payload = text.encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise ExecutionError(
            "Drift report exceeds the 2 MiB upload limit; local JSON was saved."
        )
    metadata = build_manifest(report, payload, options, started, finished)
    path = manifest_path(options.output)
    write_report(
        path,
        json.dumps({"api_url": options.upload.api_url, "manifest": metadata}, indent=2)
        + "\n",
    )
    return path


def _load_json(path, maximum):
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise InvalidInput("Upload file exceeds its supported size.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise InvalidInput("Upload file must contain valid UTF-8 JSON.") from None
    return data, raw


def upload_files(report_path, saved_path, api_url):
    api_url = origin(api_url)
    saved, _ = _load_json(saved_path, 65536)
    report, payload = _load_json(report_path, MAX_REPORT_BYTES)
    try:
        metadata = saved["manifest"]
        artifact = metadata["artifact"]
        if (
            saved["api_url"] != api_url
            or metadata["run_type"] != "drift"
            or report["kind"] != "drift"
            or report["schema_version"] != "1.0"
            or artifact["sha256"] != hashlib.sha256(payload).hexdigest()
            or artifact["size_bytes"] != len(payload)
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise InvalidInput(
            "Report, manifest and API origin must match the saved upload."
        ) from None
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
        http(
            "POST",
            api_url + f"/v1/runs/{metadata['run_id']}/complete",
            data=b"{}",
            headers=headers,
        )
    typer.echo(f"Uploaded drift run {metadata['run_id']}.", err=True)
