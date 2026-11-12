"""Shared CLI syntax stays consistent while each engine keeps its own policies."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens.cli import app

runner = CliRunner()
API = "https://api.example.com"
COMMON_FLAGS = (
    "--format",
    "--output",
    "--fail-on",
    "--timeout",
    "--upload",
    "--project",
    "--api-url",
    "--severity",
)


@pytest.mark.parametrize("command", ["scan", "drift"])
def test_common_flags_accept_the_same_arguments(
    project, tmp_path, monkeypatch, command
):
    received = []
    monkeypatch.setattr(f"infralens.cli.handle_{command}", received.append)
    output = tmp_path / f"{command}.json"
    response = runner.invoke(
        app,
        [
            command,
            str(project),
            "--format",
            "json",
            "--output",
            str(output),
            "--fail-on",
            " HIGH ",
            "--timeout",
            "45",
            "--upload",
            "--project",
            "demo",
            "--api-url",
            API,
            *(["--scope", "dev-default"] if command == "drift" else []),
        ],
    )
    assert response.exit_code == 0, response.output
    options = received[0]
    assert options.path == project.resolve()
    assert options.format == "json" and options.output == output
    assert options.timeout == 45
    assert options.upload.project == "demo" and options.upload.api_url == API
    if command == "scan":
        assert options.fail_on == "HIGH" and options.upload.scope is None
    else:
        assert (
            options.fail_on_priority == "high" and options.upload.scope == "dev-default"
        )
    assert not output.exists()


def test_help_lists_common_options_in_the_same_order():
    for command in ("scan", "drift"):
        response = runner.invoke(app, [command, "--help"])
        assert response.exit_code == 0
        positions = [response.stdout.index("\n  " + flag) for flag in COMMON_FLAGS]
        assert positions == sorted(positions)
        assert "Engine timeout in seconds." in response.stdout
        assert "Upload JSON to the InfraLens dashboard." in response.stdout


@pytest.mark.parametrize("command", ["scan", "drift"])
def test_common_defaults_and_no_upload_are_identical(project, monkeypatch, command):
    received = []
    monkeypatch.setattr(f"infralens.cli.handle_{command}", received.append)
    response = runner.invoke(app, [command, str(project), "--no-upload"])
    assert response.exit_code == 0, response.output
    options = received[0]
    assert options.format == "table" and options.output is None
    assert options.timeout == 300 and options.upload is None


@pytest.mark.parametrize("command", ["scan", "drift"])
@pytest.mark.parametrize("missing", ["--project", "--api-url"])
def test_shared_upload_requirements_fail_before_engine(
    project, tmp_path, monkeypatch, command, missing
):
    monkeypatch.setattr(
        f"infralens.cli.handle_{command}",
        lambda *args: pytest.fail("Invalid upload started engine"),
    )
    output = tmp_path / "result.json"
    flags = {
        "--format": "json",
        "--output": str(output),
        "--project": "demo",
        "--api-url": API,
    }
    arguments = [
        item
        for flag, value in flags.items()
        if flag != missing
        for item in (flag, value)
    ]
    response = runner.invoke(
        app,
        [
            command,
            str(project),
            "--upload",
            *arguments,
            *(["--scope", "dev-default"] if command == "drift" else []),
        ],
    )
    assert response.exit_code == 2
    expected = {
        "--format": "--upload requires --format json and --output.",
        "--output": "--upload requires --format json and --output.",
        "--project": "No project bound",
        "--api-url": "No API URL configured",
    }
    assert expected[missing] in response.stderr
    assert not output.exists()


@pytest.mark.parametrize("value,matched", [("HIGH", 2), (" medium ", 3)])
def test_drift_fail_on_keeps_inclusive_thresholds(value, matched):
    fixture = Path(__file__).resolve().parents[1] / "examples/drift-review"
    response = runner.invoke(
        app,
        [
            "drift",
            str(fixture),
            "--plan-json",
            str(fixture / "plan.json"),
            "--format",
            "json",
            "--fail-on",
            value,
        ],
    )
    assert response.exit_code == 1, response.output
    assert json.loads(response.stdout)["gate"]["matched_count"] == matched


@pytest.mark.parametrize(
    "command,threshold", [("scan", "unknown"), ("drift", "low"), ("drift", "critical")]
)
def test_fail_on_rejects_thresholds_outside_its_engine_policy(
    project, monkeypatch, command, threshold
):
    monkeypatch.setattr(
        f"infralens.cli.handle_{command}",
        lambda *args: pytest.fail("Invalid threshold started engine"),
    )
    response = runner.invoke(app, [command, str(project), "--fail-on", threshold])
    assert response.exit_code == 2
    assert "--fail-on" in response.stderr
