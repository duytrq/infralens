"""Validate the native JSON envelope without materializing a 50 MiB document."""

import ijson

from infralens_backend.errors import ApiError


def invalid_report():
    return ApiError(
        409, "artifact_invalid", "Report must be native Trivy schema-2 JSON."
    )


def validate_report(stream):
    schema_seen = False
    root_seen = False
    root_keys = set()
    depth = 0
    try:
        for prefix, event, value in ijson.parse(stream):
            if not root_seen:
                if prefix != "" or event != "start_map":
                    raise invalid_report()
                root_seen = True
            if event == "map_key":
                if len(value) > 4096:
                    raise invalid_report()
                if prefix == "":
                    if value in root_keys or len(root_keys) >= 128:
                        raise invalid_report()
                    root_keys.add(value)
            if prefix == "SchemaVersion":
                if event != "number" or type(value) is not int or value != 2:
                    raise invalid_report()
                schema_seen = True
            if prefix == "Results" and event not in ("start_array", "end_array"):
                raise invalid_report()
            if prefix == "Results.item" and event not in (
                "start_map",
                "end_map",
                "map_key",
            ):
                raise invalid_report()
            if prefix == "Trivy" and event not in ("start_map", "end_map", "map_key"):
                raise invalid_report()
            if event in ("start_map", "start_array"):
                depth += 1
                if depth > 64:
                    raise invalid_report()
            elif event in ("end_map", "end_array"):
                depth -= 1
        if not schema_seen:
            raise invalid_report()
    except (ijson.JSONError, UnicodeError, ValueError):
        raise invalid_report() from None
