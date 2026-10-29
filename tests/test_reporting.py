import json
import re

import pytest

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


def source_report(lines=None):
    return {
        "SchemaVersion": 2,
        "Trivy": {"Version": "0.76.0"},
        "Results": [
            {
                "Target": "main.tf",
                "Misconfigurations": [
                    {
                        "ID": "AWS-0107",
                        "Severity": "HIGH",
                        "Title": "Public SSH",
                        "Message": "SSH is accessible from the Internet.",
                        "CauseMetadata": {
                            "Resource": "aws_security_group.public",
                            "StartLine": 7,
                            "EndLine": 7,
                            "Code": {
                                "Lines": lines
                                if lines is not None
                                else [
                                    {
                                        "Number": 5,
                                        "Content": "  ingress {",
                                        "IsCause": False,
                                    },
                                    {
                                        "Number": 6,
                                        "Content": "    from_port = 22",
                                        "IsCause": False,
                                    },
                                    {
                                        "Number": 7,
                                        "Content": '    cidr_blocks = ["0.0.0.0/0"]',
                                        "IsCause": True,
                                    },
                                    {"Number": 8, "Content": "  }", "IsCause": False},
                                ]
                            },
                        },
                    }
                ],
            }
        ],
    }


def test_finding_cards_show_source_context_and_mark_cause_without_engine_banner():
    report = render_table(parse_report(json.dumps(source_report())), SEVERITIES)
    assert "Security scan (Trivy" not in report and "0.76.0" not in report
    assert "[HIGH] AWS-0107" in report
    assert "main.tf:7" in report and "aws_security_group.public" in report
    assert '    cidr_blocks = ["0.0.0.0/0"]' in report
    assert re.search(r">\s+7\s+\|\s+cidr_blocks", report)
    assert re.search(r"\s+6\s+\|\s+from_port", report)
    assert "\x1b" not in report


def test_color_is_trusted_and_changes_only_presentation():
    payload = source_report()
    payload["Results"][0]["Misconfigurations"][0]["CauseMetadata"]["Code"]["Lines"][
        2
    ].update(
        Content='    cidr_blocks = ["0.0.0.0/0"]\x1b[2J\r\nINJECT',
        Highlighted="PRIVATE_HIGHLIGHTED_FIELD\x1b[2J",
    )
    result = parse_report(json.dumps(payload))
    plain = render_table(result, SEVERITIES)
    colored = render_table(result, SEVERITIES, color=True)
    assert "\x1b[" in colored
    assert "\x1b[2J" not in colored
    assert "PRIVATE_HIGHLIGHTED_FIELD" not in colored
    assert re.sub(r"\x1b\[[0-9;]*m", "", colored) == plain
    assert result.raw == payload


def test_each_severity_has_a_distinct_color_and_a_readable_label():
    payload = source_report()
    template = payload["Results"][0]["Misconfigurations"][0]
    payload["Results"][0]["Misconfigurations"] = [
        {**template, "ID": f"RULE-{level}", "Severity": level} for level in SEVERITIES
    ]
    colored = render_table(parse_report(json.dumps(payload)), SEVERITIES, color=True)
    styles = [
        re.search(r"((?:\x1b\[[0-9;]*m)+)\[" + level + r"\]", colored).group(1)
        for level in SEVERITIES
    ]
    assert len(set(styles)) == len(SEVERITIES)


def test_source_line_fallback_preserves_indent_and_bounds_long_lines():
    payload = source_report(
        [
            {"Number": 6, "Content": "\tcontext = true"},
            {"Number": 7, "Content": "\tsetting = " + "x" * 2000},
        ]
    )
    report = render_table(parse_report(json.dumps(payload)), SEVERITIES)
    assert re.search(r">\s+7\s+\| {5}setting", report)
    assert "..." in report
    assert max(len(line) for line in report.splitlines()) < 210


def test_large_source_excerpt_is_bounded_and_keeps_the_cause_line():
    payload = source_report(
        [
            {"Number": n, "Content": f"    setting_{n} = false", "IsCause": n == 50}
            for n in range(1, 101)
        ]
    )
    cause = payload["Results"][0]["Misconfigurations"][0]["CauseMetadata"]
    cause.update(StartLine=50, EndLine=50)
    report = render_table(parse_report(json.dumps(payload)), SEVERITIES)
    assert re.search(r">\s+50\s+\|\s+setting_50", report)
    assert len(re.findall(r"^\s*>?\s+\d+\s+\|", report, re.M)) <= 9
    assert "..." in report


@pytest.mark.parametrize(
    "code",
    [None, {}, {"Lines": None}, {"Lines": [None, {"Number": "7", "Content": "bad"}]}],
)
def test_missing_or_bad_optional_code_does_not_hide_the_finding(code):
    payload = source_report()
    payload["Results"][0]["Misconfigurations"][0]["CauseMetadata"]["Code"] = code
    result = parse_report(json.dumps(payload))
    report = render_table(result, SEVERITIES)
    assert len(result.findings) == 1
    assert "[HIGH] AWS-0107" in report and "Source excerpt unavailable" in report


@pytest.mark.parametrize(
    "no_color,tty,environment,expected",
    [
        (False, True, {}, True),
        (False, False, {}, False),
        (True, True, {}, False),
        (False, True, {"NO_COLOR": "1"}, False),
        (False, True, {"TERM": "dumb"}, False),
        (True, True, {"FORCE_COLOR": "1"}, False),
    ],
)
def test_terminal_color_respects_tty_and_disable_controls(
    monkeypatch, no_color, tty, environment, expected
):
    import infralens.reporting as reporting

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(reporting.sys.stdout, "isatty", lambda: tty)
    assert reporting.color_enabled(no_color) is expected
