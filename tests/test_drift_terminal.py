import json
import re
from dataclasses import replace

import pytest

from infralens.drift import AttributeChange, DriftResult, ResourceDrift
from infralens.drift_reporting import render_drift
from infralens.drift_review import enrich_review


def result():
    resource = ResourceDrift(
        "aws_instance.demo",
        "aws_instance",
        ("update",),
        (
            AttributeChange(
                ("instance_type",),
                {"status": "known", "value": "t3.micro"},
                {"status": "known", "value": "t3.small"},
            ),
        ),
    )
    return enrich_review(DriftResult("1.15.7", (resource,), "refresh_only", "now"))


def test_cards_show_priority_and_compact_diff_without_generic_advice():
    report = render_drift(result())
    assert "[MEDIUM] aws_instance.demo" in report
    assert '- "t3.micro"' in report and '+ "t3.small"' in report
    assert "instance_type" in report
    assert "Choice:" not in report and "Confirm whether" not in report
    assert "Review the current resource" not in report
    assert "RESOURCE | ACTION" not in report


def test_color_is_presentation_only():
    before = result().to_dict()
    plain = render_drift(result())
    colored = render_drift(result(), color=True)
    assert "\x1b[33m" in colored
    assert re.sub(r"\x1b\[[0-9;]*m", "", colored) == plain
    assert result().to_dict() == before


def test_sensitive_values_and_terminal_controls_are_never_echoed():
    resource = replace(
        result().resources[0],
        attributes=(
            AttributeChange(
                ("password",),
                {"status": "sensitive", "value": "PRIVATE_PASSWORD"},
                {"status": "sensitive", "value": "PRIVATE_PASSWORD"},
            ),
        ),
    )
    report = render_drift(replace(result(), resources=(resource,)))
    assert "[sensitive]" in report and "PRIVATE_PASSWORD" not in report


def test_trace_is_inline_and_explains_skipped_resources():
    resource = replace(
        result().resources[0],
        trace={"status": "skipped", "reason": "unsupported_resource"},
    )
    report = render_drift(
        replace(
            result(),
            resources=(resource,),
            trace={"status": "partial", "has_errors": False},
        )
    )
    assert "Trace: unsupported resource" in report
    assert "CloudTrail trace: partial" in report
    assert "Trace aws_instance.demo" not in report


def test_nested_network_diffs_are_readable_leaves():
    old = [
        {
            "cidr_blocks": ["10.0.0.0/16"],
            "from_port": 22,
            "to_port": 22,
            "protocol": "tcp",
        }
    ]
    new = [{**old[0], "cidr_blocks": ["0.0.0.0/0"]}]
    resource = replace(
        result().resources[0],
        attributes=(
            AttributeChange(
                ("ingress",),
                {"status": "known", "value": old},
                {"status": "known", "value": new},
            ),
        ),
    )
    report = render_drift(replace(result(), resources=(resource,)))
    assert "ingress[0].cidr_blocks[0]" in report
    assert '"from_port"' not in report and '- "10.0.0.0/16"' in report


def test_priority_filter_never_hides_gate_or_json_resources(tmp_path):
    from pathlib import Path

    from typer.testing import CliRunner

    from infralens.cli import app

    root = Path(__file__).resolve().parents[1] / "examples/drift-review"
    output = tmp_path / "report.json"
    response = CliRunner().invoke(
        app,
        [
            "drift",
            str(root),
            "--plan-json",
            str(root / "plan.json"),
            "--severity",
            "high",
            "--fail-on",
            "MEDIUM",
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )
    assert response.exit_code == 1, response.output
    raw = json.loads(output.read_text())
    assert raw["gate"]["priority_counts"]["medium"] > 0
    assert raw["gate"]["status"] == "failed"
    assert "\n[MEDIUM]" not in response.stdout and "\n[HIGH]" in response.stdout
    assert "\x1b" not in output.read_text()


def test_drift_rejects_security_only_priorities_before_engine(project, monkeypatch):
    from typer.testing import CliRunner

    from infralens.cli import app

    monkeypatch.setattr(
        "infralens.cli.handle_drift",
        lambda *a: pytest.fail("Engine started"),
    )
    for value in ("LOW", "CRITICAL", "HIGH,,MEDIUM"):
        response = CliRunner().invoke(app, ["drift", str(project), "--severity", value])
        assert response.exit_code == 2 and "--severity" in response.stderr


def test_cli_color_and_no_color_keep_json_clean(tmp_path, monkeypatch):
    from pathlib import Path

    from typer.testing import CliRunner

    from infralens import cli

    root = Path(__file__).resolve().parents[1] / "examples/drift-review"
    monkeypatch.setattr(cli, "color_enabled", lambda no_color: not no_color)
    for disabled in (False, True):
        output = tmp_path / f"report-{disabled}.json"
        response = CliRunner().invoke(
            cli.app,
            [
                *(["--no-color"] if disabled else []),
                "drift",
                str(root),
                "--plan-json",
                str(root / "plan.json"),
                "--format",
                "json",
                "--output",
                str(output),
            ],
            color=True,
        )
        assert response.exit_code == 0, response.output
        assert ("\x1b[" in response.stdout) is (not disabled)
        assert "\x1b[" not in output.read_text()
        assert "Current configuration" not in output.read_text()
