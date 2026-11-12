"""Bounded native Trivy normalization and run-private derived findings."""

import hashlib
import json
import re
import tempfile

import ijson
from ijson.common import ObjectBuilder

from infralens_backend.schemas import SEVERITIES

VERSION = 1
RANK = {s: i for i, s in enumerate(reversed(SEVERITIES))}
ID_PATTERN = r"[0-4]-[0-9a-f]{32}"
MAX_FINDINGS = 100_000


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def normalize(item, ordinal):
    if not isinstance(item, dict):
        raise ValueError("Invalid finding")
    status = item.get("Status", "FAIL")
    if status in ("PASS", "EXCEPTION"):
        return None
    if (
        status != "FAIL"
        or not isinstance(item.get("Severity"), str)
        or item["Severity"] not in RANK
    ):
        raise ValueError("Invalid finding status or severity")
    rule = item.get("ID")
    if not isinstance(rule, str) or not rule or len(rule.encode()) > 1024:
        raise ValueError("Invalid rule ID")
    cause = item.get("CauseMetadata", {})
    refs = item.get("References", [])
    if not isinstance(cause, dict) or not isinstance(refs, list):
        raise ValueError("Invalid finding metadata")
    if any(not isinstance(r, str) for r in refs):
        raise ValueError("Invalid references")
    clipped = []

    def text(name, value, limit=16384):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Invalid text field")
        encoded = value.encode()
        if len(encoded) > limit:
            clipped.append(name)
            return encoded[:limit].decode("utf-8", errors="ignore")
        return value

    def line(name):
        value = cause.get(name)
        return value if type(value) is int and 0 < value <= 2**31 - 1 else None

    severity = item["Severity"]
    # Ordinal distinguishes repeated occurrences; source bytes are immutable.
    identifier = f"{RANK[severity]}-{digest(str(ordinal))[:32]}"
    result = {
        "finding_id": identifier,
        "rule_id": rule,
        "severity": severity,
        "title": text("title", item.get("Title") or rule, 1024),
        "message": text("message", item.get("Message") or item.get("Title") or rule),
        "description": text("description", item.get("Description") or ""),
        "resolution": text("resolution", item.get("Resolution") or ""),
        "resource": text("resource", cause.get("Resource"), 4096),
        "start_line": line("StartLine"),
        "end_line": line("EndLine"),
        "references": [text("references", r, 2048) for r in refs[:20]],
    }
    if len(refs) > 20:
        clipped.append("references")
    code = cause.get("Code") or {}
    if not isinstance(code, dict) or not isinstance(code.get("Lines", []), list):
        raise ValueError("Invalid source excerpt")
    lines = code.get("Lines", [])
    result["code"] = []
    for entry in lines[:40]:
        if not isinstance(entry, dict):
            raise ValueError("Invalid source line")
        number = entry.get("Number")
        if type(number) is not int or number <= 0:
            raise ValueError("Invalid source line number")
        result["code"].append(
            {
                "number": number,
                "content": text("code", entry.get("Content") or "", 1024),
                "is_cause": entry.get("IsCause") is True,
            }
        )
    if len(lines) > 40:
        clipped.append("code")
    result["truncated_fields"] = sorted(set(clipped))
    return result


def normalize_report(stream):
    """Spool one result to disk so Target may appear after its findings.

    Only a single native finding is materialized; even a report containing all
    findings in one Results entry never becomes one large Python object.
    """
    ordinal = 0
    target = None
    builder = None
    nodes = 0
    text_bytes = 0
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as spool:
        for prefix, event, value in ijson.parse(stream):
            if prefix == "Results.item" and event == "start_map":
                target = None
                spool.seek(0)
                spool.truncate()
            if prefix == "Results.item.Target":
                if event not in ("string", "null"):
                    raise ValueError("Invalid target")
                target = value
                if target is not None and len(target.encode()) > 4096:
                    raise ValueError("Target is too long")
            if prefix == "Results.item.Misconfigurations" and event not in (
                "start_array",
                "end_array",
                "null",
            ):
                raise ValueError("Invalid misconfigurations")
            if prefix == "Results.item.Misconfigurations.item" and event == "start_map":
                builder = ObjectBuilder()
                nodes = 0
                text_bytes = 0
            if builder is not None:
                nodes += 1
                if isinstance(value, str):
                    text_bytes += len(value.encode())
                if nodes > 8192 or text_bytes > 512 * 1024:
                    raise ValueError("Finding exceeds processing bounds")
                builder.event(event, value)
                if (
                    prefix == "Results.item.Misconfigurations.item"
                    and event == "end_map"
                ):
                    row = normalize(builder.value, ordinal)
                    ordinal += 1
                    if ordinal > MAX_FINDINGS:
                        raise ValueError("Too many findings")
                    if row is not None:
                        spool.write(json.dumps(row, ensure_ascii=False) + "\n")
                    builder = None
            elif prefix == "Results.item.Misconfigurations.item":
                raise ValueError("Invalid finding")
            if prefix == "Results.item" and event == "end_map":
                spool.seek(0)
                for line in spool:
                    yield {
                        **json.loads(line),
                        "file": None if target in (None, ".") else target,
                    }


def finding_id(value):
    if not re.fullmatch(ID_PATTERN, value):
        from infralens_backend.errors import invalid

        raise invalid("Invalid finding ID.")
    return value
