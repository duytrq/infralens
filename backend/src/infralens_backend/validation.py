"""Bounded input and pagination validation for API Gateway events."""

import base64
import binascii
import json
import re
from datetime import UTC, datetime
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker

from infralens_backend.errors import ApiError, invalid
from infralens_backend.schemas import RUN, SEVERITIES, TIME_PATTERN

PROJECT_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"


def project_id(value):
    if not isinstance(value, str) or not re.fullmatch(PROJECT_PATTERN, value):
        raise invalid("Project ID must be 1-64 lowercase letters, digits, '_' or '-'.")
    return value


def run_id(value):
    try:
        parsed = UUID(value)
        if str(parsed) != value or parsed.version != 4:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise invalid("Run ID must be a canonical UUID v4.") from None
    return value


def timestamp(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(TIME_PATTERN, value):
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise invalid("Timestamps must include a UTC offset.") from None


def iso(value):
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def integer_only_float(value):
    raise invalid("Numeric metadata fields must use JSON integer values.")


def reject_constant(value):
    raise ValueError


def body(event, schema):
    content_type = event.get("headers", {}).get("content-type", "").lower()
    if content_type.split(";", 1)[0].strip() != "application/json":
        raise ApiError(
            415, "unsupported_media_type", "Use Content-Type application/json."
        )
    try:
        raw = event.get("body", "")
        if not isinstance(raw, str):
            raise ValueError
        if len(raw) > 90000:
            raise ApiError(413, "request_too_large", "Metadata exceeds 64 KiB.")
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        if len(raw.encode("utf-8")) > 65536:
            raise ApiError(413, "request_too_large", "Metadata exceeds 64 KiB.")
        value = json.loads(
            raw,
            object_pairs_hook=no_duplicates,
            parse_float=integer_only_float,
            parse_constant=reject_constant,
        )
    except (ValueError, UnicodeError, binascii.Error, RecursionError):
        raise ApiError(400, "invalid_json", "Invalid JSON request.") from None
    validate(value, schema)
    return value


def validate(value, schema):
    errors = Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
        value
    )
    if next(errors, None) is not None:
        raise invalid()


def scan(payload, max_report_bytes):
    validate(payload, RUN)
    run_id(payload["run_id"])
    start = timestamp(payload["started_at"])
    finish = timestamp(payload["finished_at"])
    if finish < start or payload["artifact"]["size_bytes"] > max_report_bytes:
        raise invalid()
    path = payload["source"]["relative_path"]
    if (
        path.startswith("/")
        or "\\" in path
        or ":" in path
        or any(p in ("", "..") for p in path.split("/"))
    ):
        raise invalid("Source path must be relative and cannot contain '..'.")
    counts = payload["result"]["findings"]["by_severity"]
    if payload["result"]["findings"]["total"] != sum(counts.values()):
        raise invalid("Finding total must equal the sum of severity counts.")
    threshold = payload["scan_options"]["fail_on"]
    expected = "not_evaluated"
    if threshold is not None:
        expected = (
            "failed"
            if any(counts[s] for s in SEVERITIES[SEVERITIES.index(threshold) :])
            else "passed"
        )
    if payload["result"]["threshold_status"] != expected:
        raise invalid("Threshold status does not match finding counts and fail_on.")
    payload["started_at"] = iso(start)
    payload["finished_at"] = iso(finish)
    return payload


def query(event, allowed):
    params = event.get("queryStringParameters") or {}
    if not isinstance(params, dict) or set(params) - set(allowed):
        raise invalid("Unsupported query parameter.")
    if any(not isinstance(v, str) or len(v) > 8192 for v in params.values()):
        raise invalid()
    return params


def page_limit(params):
    value = params.get("limit", "20")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", value) or int(value) > 100:
        raise invalid("Limit must be between 1 and 100.")
    return int(value)


def encode_cursor(key, scope):
    if not key:
        return None
    payload = json.dumps({"key": key, "scope": scope}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(value, scope, required):
    if value is None:
        return None
    try:
        data = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        key = data["key"]
        if data["scope"] != scope or set(key) != set(required):
            raise ValueError
        if any(not isinstance(v, str) or len(v) > 512 for v in key.values()):
            raise ValueError
        if any(
            key[name] != expected
            for name, expected in required.items()
            if expected is not None
        ):
            raise ValueError
        return key
    except (
        ValueError,
        KeyError,
        TypeError,
        binascii.Error,
        UnicodeError,
        RecursionError,
    ):
        raise invalid("Invalid cursor for this query.") from None
