"""User-facing gate and trace syntax, tested through the real CLI parser."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens.cli import app

runner = CliRunner()
DEMO = Path(__file__).resolve().parents[1] / "examples/drift-review"


@pytest.mark.parametrize(
    "value,matched,criteria",
    [
        ("ANY", 4, (True, None, False)),
        ("HIGH", 2, (False, "high", False)),
        ("MEDIUM", 3, (False, "medium", False)),
        ("UNKNOWN", 1, (False, None, True)),
        (" high , UNKNOWN,high ", 3, (False, "high", True)),
        ("HIGH,MEDIUM", 3, (False, "medium", False)),
        ("MEDIUM,UNKNOWN", 4, (False, "medium", True)),
        ("ANY,HIGH,UNKNOWN", 4, (True, None, False)),
    ],
)
def test_single_fail_on_maps_to_full_report_gate(value, matched, criteria):
    response = runner.invoke(
        app,
        [
            "drift",
            str(DEMO),
            "--plan-json",
            str(DEMO / "plan.json"),
            "--format",
            "json",
            "--severity",
            "HIGH",
            "--fail-on",
            value,
        ],
    )
    assert response.exit_code == 1, response.output
    report = json.loads(response.stdout)
    assert len(report["resources"]) == 4
    assert report["gate"]["matched_count"] == matched
    assert report["gate"]["criteria"] == dict(
        zip(("any_drift", "minimum_priority", "unknown_priority"), criteria)
    )


@pytest.mark.parametrize(
    "value", ["", " ", "LOW", "CRITICAL", "HIGH,", ",UNKNOWN", "ANY,bad"]
)
def test_invalid_fail_on_stops_before_engine_or_report(
    project, tmp_path, monkeypatch, value
):
    monkeypatch.setattr(
        "infralens.cli.handle_drift",
        lambda *_: pytest.fail("Invalid flag reached engine"),
    )
    output = tmp_path / "new" / "report.json"
    response = runner.invoke(
        app,
        ["drift", str(project), "--fail-on", value, "--output", str(output)],
    )
    assert response.exit_code == 2
    assert "--fail-on" in response.stderr
    assert not output.parent.exists()


@pytest.mark.parametrize("days", [None, 1, 7, 90])
def test_trace_days_explicit_and_disabled_by_default(project, monkeypatch, days):
    received = []
    monkeypatch.setattr("infralens.cli.handle_drift", received.append)
    response = runner.invoke(
        app,
        ["drift", str(project), *(["--trace", str(days)] if days else [])],
    )
    assert response.exit_code == 0, response.output
    assert received[0].trace is (days is not None)
    assert received[0].lookback_days == days


@pytest.mark.parametrize(
    "flags",
    [
        ["--trace"],
        ["--trace", "0"],
        ["--trace", "91"],
        ["--trace", "-1"],
        ["--trace", "1.5"],
    ],
)
def test_invalid_trace_stops_before_engine(project, monkeypatch, flags):
    monkeypatch.setattr(
        "infralens.cli.handle_drift",
        lambda *_: pytest.fail("Invalid trace reached engine"),
    )
    response = runner.invoke(app, ["drift", str(project), *flags])
    assert response.exit_code == 2
    assert "--trace" in response.stderr


@pytest.mark.parametrize(
    "flags",
    [
        ["--fail-on-drift"],
        ["--fail-on-priority", "HIGH"],
        ["--fail-on-unknown"],
        ["--lookback-days", "7"],
    ],
)
def test_removed_flags_are_rejected_and_absent_from_help(project, flags):
    response = runner.invoke(app, ["drift", str(project), *flags])
    assert response.exit_code == 2
    assert flags[0] in response.stderr
    help_text = runner.invoke(app, ["drift", "--help"]).stdout
    assert flags[0] not in help_text
    assert "--trace DAYS" in help_text
    assert "ANY" in help_text and "UNKNOWN" in help_text
