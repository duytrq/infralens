"""Normalized drift documents and manifests; independent of the CLI runtime."""

from copy import deepcopy

from infralens_backend.schemas import COUNT, RUN, TIME, obj

MAX_REPORT_BYTES = 2 * 1024 * 1024
TEXT = {"type": "string", "maxLength": 8192}
NAME = {"type": "string", "minLength": 1, "maxLength": 4096}
PRIORITY = {"enum": ["high", "medium", "unknown"]}
PRIORITY_COUNTS = obj({name: COUNT for name in ("high", "medium", "unknown")})
SUMMARY = obj({"resources": COUNT, "attributes": COUNT})
PATH = {"type": "array", "maxItems": 64, "items": TEXT}
STRINGS = {"type": "array", "maxItems": 10000, "items": TEXT}
CRITERIA = obj(
    {
        "any_drift": {"type": "boolean"},
        "minimum_priority": {"enum": [None, "high", "medium"]},
        "unknown_priority": {"type": "boolean"},
    }
)
VALUE = {
    "oneOf": [
        obj(
            {
                "status": {"const": "known"},
                "value": {},
                "source": {"enum": ["saved", "observed"]},
            },
            optional=("source",),
        ),
        obj({"status": {"enum": ["sensitive", "unknown", "absent"]}}),
    ]
}
ATTRIBUTE = obj({"path": PATH, "before": VALUE, "after": VALUE})
SOURCE = obj(
    {
        "status": {"enum": ["located", "ambiguous", "unavailable"]},
        "context": {"const": "current_configuration"},
        "block_address": NAME,
        "reason": TEXT,
        "locations": {
            "type": "array",
            "maxItems": 1000,
            "items": obj(
                {
                    "file": NAME,
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "syntax": {"enum": ["hcl", "json"]},
                }
            ),
        },
    },
    optional=("block_address", "reason", "locations"),
)
ASSESSMENT = obj(
    {
        "policy": NAME,
        "priority": PRIORITY,
        "signals": {
            "type": "array",
            "maxItems": 1000,
            "items": obj(
                {
                    "code": NAME,
                    "priority": PRIORITY,
                    "description": TEXT,
                    "paths": {"type": "array", "maxItems": 10000, "items": PATH},
                }
            ),
        },
        "guidance": obj(
            {
                "review_steps": STRINGS,
                "choices": {
                    "type": "array",
                    "maxItems": 1000,
                    "items": obj(
                        {
                            "id": NAME,
                            "title": TEXT,
                            "steps": STRINGS,
                        }
                    ),
                },
            }
        ),
    }
)
EVENT = obj(
    {
        "event_id": NAME,
        "event_name": NAME,
        "event_source": NAME,
        "event_time": TIME,
        "region": NAME,
        "actor": obj(
            {
                key: TEXT
                for key in (
                    "type",
                    "arn",
                    "userName",
                    "invokedBy",
                    "session_issuer_arn",
                )
            },
            optional=("type", "arn", "userName", "invokedBy", "session_issuer_arn"),
        ),
        "matched_attributes": STRINGS,
        "relation": {"const": "candidate"},
    }
)
RESOURCE_TRACE = obj(
    {
        "status": {"enum": ["matched", "no_events", "partial", "skipped", "error"]},
        "events": {"type": "array", "maxItems": 1000, "items": EVENT},
        "reason": TEXT,
        "pages_scanned": COUNT,
        "truncated": {"type": "boolean"},
        "malformed_events": COUNT,
        "unsupported_attributes": STRINGS,
        "correlation": {"const": "exact_rule_id"},
        "lookup_scope": {"const": "parent_security_group"},
        "unresolved_rule_events": COUNT,
    },
    optional=(
        "reason",
        "pages_scanned",
        "truncated",
        "malformed_events",
        "unsupported_attributes",
        "correlation",
        "lookup_scope",
        "unresolved_rule_events",
    ),
)
TRACE = obj(
    {
        "status": {"enum": ["not_needed", "partial", "complete", "error"]},
        "has_errors": {"type": "boolean"},
        "message": TEXT,
        "start_time": TIME,
        "end_time": TIME,
        "max_resources": COUNT,
        "max_pages_per_resource": COUNT,
        "account_id": NAME,
        "region": NAME,
    },
    optional=(
        "message",
        "start_time",
        "end_time",
        "max_resources",
        "max_pages_per_resource",
        "account_id",
        "region",
    ),
)
NETWORK_FIELDS = {
    "aws_vpc_security_group_ingress_rule": (
        "security_group_id",
        "region",
        "ip_protocol",
        "from_port",
        "to_port",
        "cidr_ipv4",
        "cidr_ipv6",
        "prefix_list_id",
        "referenced_security_group_id",
    ),
    "aws_security_group_rule": (
        "security_group_id",
        "region",
        "type",
        "protocol",
        "from_port",
        "to_port",
        "cidr_blocks",
        "ipv6_cidr_blocks",
        "prefix_list_ids",
        "source_security_group_id",
        "self",
    ),
}
NETWORK_FIELDS["aws_vpc_security_group_egress_rule"] = NETWORK_FIELDS[
    "aws_vpc_security_group_ingress_rule"
]
NETWORK_VALUES = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        name: VALUE for name in sorted(set(sum(NETWORK_FIELDS.values(), ())))
    },
}
RESOURCE = obj(
    {
        "address": NAME,
        "resource_type": NAME,
        "actions": {"enum": [["update"], ["delete"]]},
        "attributes": {"type": "array", "maxItems": 10000, "items": ATTRIBUTE},
        "identifiers": obj(
            {
                key: VALUE
                for key in ("id", "arn", "security_group_id", "security_group_rule_id")
            },
            optional=("id", "arn", "security_group_id", "security_group_rule_id"),
        ),
        "source": SOURCE,
        "assessment": ASSESSMENT,
        "trace": RESOURCE_TRACE,
        "network_context": obj(
            {
                "version": {"const": "security-group-rule-v1"},
                "before": NETWORK_VALUES,
                "after": NETWORK_VALUES,
            }
        ),
    },
    optional=("source", "assessment", "trace", "network_context"),
)
GATE = obj(
    {
        "policy": {"const": "drift-gate-v1"},
        "review_policy": {"const": "builtin-review-v2"},
        "status": {"enum": ["passed", "failed", "incomplete"]},
        "exit_code": {"enum": [0, 1, 3]},
        "criteria": CRITERIA,
        "priority_counts": PRIORITY_COUNTS,
        "unassessed_resources": COUNT,
        "matched_count": COUNT,
        "matched_resources": {
            "type": "array",
            "maxItems": 10000,
            "items": obj(
                {
                    "address": NAME,
                    "priority": PRIORITY,
                    "reasons": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {
                            "enum": [
                                "any_drift",
                                "priority_threshold",
                                "unknown_priority",
                            ]
                        },
                    },
                }
            ),
        },
        "reason_codes": STRINGS,
    }
)
REPORT = obj(
    {
        "schema_version": {"const": "1.0"},
        "kind": {"const": "drift"},
        "terraform_version": {"type": "string", "pattern": r"^1\.[0-9]+\.[0-9]+$"},
        "input_mode": {"enum": ["refresh_only", "imported_plan"]},
        "checked_at": TIME,
        "has_drift": {"type": "boolean"},
        "summary": SUMMARY,
        "resources": {"type": "array", "maxItems": 10000, "items": RESOURCE},
        "normalizations": {
            "type": "array",
            "maxItems": 10000,
            "items": obj(
                {
                    "address": NAME,
                    "path": {"type": "array", "items": {"type": ["string", "integer"]}},
                    "reason": TEXT,
                }
            ),
        },
        "notes": STRINGS,
        "trace": TRACE,
        "gate": GATE,
        "review_summary": obj({"policy": NAME, "priority_counts": PRIORITY_COUNTS}),
    },
    optional=("trace", "gate", "review_summary"),
)
RESULT = obj(
    {
        "collection_status": {"enum": ["completed", "partial"]},
        "has_drift": {"type": "boolean"},
        "summary": SUMMARY,
        "priority_counts": PRIORITY_COUNTS,
        "gate_status": {"enum": ["disabled", "passed", "failed", "incomplete"]},
        "trace_status": {
            "enum": ["disabled", "not_needed", "partial", "complete", "error"]
        },
    }
)

_common = deepcopy(RUN["properties"])
DRIFT_RUN = obj(
    {
        **{key: value for key, value in _common.items() if key != "scan_options"},
        "run_type": {"const": "drift"},
        "scope": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
        "tool": obj(
            {
                **{
                    key: value
                    for key, value in _common["tool"]["properties"].items()
                    if key != "checks_version"
                },
                "engine": {"const": "terraform"},
            }
        ),
        "drift_options": obj(
            {
                "input_mode": REPORT["properties"]["input_mode"],
                "trace": {"type": "boolean"},
                "lookback_days": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 90,
                },
                "gate": CRITERIA,
            }
        ),
        "result": RESULT,
        "artifact": obj(
            {
                **_common["artifact"]["properties"],
                "size_bytes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_REPORT_BYTES,
                },
                "schema_version": {"const": "1.0"},
            }
        ),
    }
)
RUN_INPUT = {"oneOf": [RUN, DRIFT_RUN]}
COMPARISON_STATUSES = (
    "new",
    "no_longer_reported",
    "changed",
    "unchanged",
    "indeterminate",
)
COMPARISON = obj(
    {
        "current_run_id": NAME,
        "baseline_run_id": {"type": ["string", "null"]},
        "status": {"enum": ["baseline_missing", "compared"]},
        "resources": {
            "type": "array",
            "items": obj(
                {
                    "address": NAME,
                    "status": {"enum": list(COMPARISON_STATUSES)},
                    "changed_paths": {"type": "array", "items": PATH},
                }
            ),
        },
        "summary": obj({status: COUNT for status in COMPARISON_STATUSES}),
        "notes": STRINGS,
        "next_cursor": {"type": ["string", "null"]},
    }
)
