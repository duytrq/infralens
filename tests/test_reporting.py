import json

from infralens.options import SEVERITIES
from infralens.reporting import render_table
from infralens.trivy import parse_report


def test_report_without_location_and_terminal_controls():
    raw = {
        "SchemaVersion": 2,
        "Results": [
            {
                "Misconfigurations": [
                    {
                        "ID": "TEST-1",
                        "Severity": "UNKNOWN",
                        "Title": "Warning",
                        "Message": "Unsafe\x1b[31m\nconfiguration",
                        "Status": "FAIL",
                    }
                ]
            }
        ],
    }
    report = render_table(parse_report(json.dumps(raw)), SEVERITIES)
    assert "unknown location" in report
    assert "TEST-1" in report
    assert "\x1b" not in report
    assert "Unsafe" in report and "configuration" in report


def test_empty_report_with_warning_is_not_presented_as_clean():
    result = parse_report('{"SchemaVersion":2}', ("Analysis may be incomplete.",))
    report = render_table(result, SEVERITIES)
    assert "see scan warnings" in report
    assert "No security findings found" not in report
