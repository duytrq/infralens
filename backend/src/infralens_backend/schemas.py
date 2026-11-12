"""Request schemas shared by runtime validation and the exported OpenAPI contract."""

SEVERITIES = ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL")
SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
TIME_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
TIME = {
    "type": "string",
    "format": "date-time",
    "maxLength": 40,
    "pattern": TIME_PATTERN,
}
COUNT = {"type": "integer", "minimum": 0, "maximum": 10_000_000}
VERSION = {"type": "string", "pattern": "^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$"}


def obj(properties, optional=()):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": [p for p in properties if p not in optional],
    }


PROJECT = obj(
    {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120,
            "pattern": r"^\S(?:[^\x00-\x1f\x7f]*\S)?$",
        }
    }
)

RUN = obj(
    {
        "schema_version": {"const": 1},
        "run_id": {"type": "string", "format": "uuid"},
        "project_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
        "run_type": {"const": "security_scan"},
        "started_at": TIME,
        "finished_at": TIME,
        "duration_ms": {"type": "integer", "minimum": 0, "maximum": 86_400_000},
        "source": obj(
            {
                "relative_path": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 512,
                    "pattern": r"^[^\x00-\x1f\x7f]+$",
                },
                "git": obj(
                    {
                        "commit": {
                            "type": "string",
                            "pattern": "^([0-9a-f]{40}|[0-9a-f]{64})$",
                        },
                        "branch": {
                            "type": ["string", "null"],
                            "maxLength": 255,
                            "pattern": r"^[^\x00-\x1f\x7f]+$",
                        },
                        "dirty": {"type": "boolean"},
                    }
                ),
            },
            optional=("git",),
        ),
        "tool": obj(
            {
                "infralens_version": VERSION,
                "engine": {"const": "trivy"},
                "engine_version": VERSION,
                "checks_version": VERSION,
            },
            optional=("checks_version",),
        ),
        "scan_options": obj(
            {
                "fail_on": {"enum": [None, *SEVERITIES[1:]]},
                "severity": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "uniqueItems": True,
                    "items": {"enum": list(SEVERITIES)},
                },
                "ignore_sha256": {"anyOf": [SHA256, {"type": "null"}]},
            }
        ),
        "result": obj(
            {
                "scan_status": {"const": "completed"},
                "threshold_status": {"enum": ["passed", "failed", "not_evaluated"]},
                "findings": obj(
                    {"total": COUNT, "by_severity": obj({s: COUNT for s in SEVERITIES})}
                ),
                "warnings": {
                    "type": "array",
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
                },
            }
        ),
        "artifact": obj(
            {
                "format": {"const": "json"},
                "content_type": {"const": "application/json"},
                "size_bytes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50 * 1024 * 1024,
                },
                "sha256": SHA256,
                "schema_version": {"const": 2},
            }
        ),
    }
)
