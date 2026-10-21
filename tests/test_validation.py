import os

import pytest
from typer.testing import CliRunner

from infralens.cli import app
from infralens.errors import InvalidInput
from infralens.options import SEVERITIES
from infralens.validation import failure_threshold, severity_filter

runner = CliRunner()


@pytest.mark.parametrize("level", SEVERITIES)
def test_severity_normalization(level):
    assert severity_filter(f" {level.lower()}, {level} ") == (level,)


@pytest.mark.parametrize("level", SEVERITIES[1:])
def test_threshold_normalization(level):
    assert failure_threshold(f" {level.lower()} ") == level


@pytest.mark.parametrize("value", ["", " ", ",", "HIGH,", ",LOW"])
def test_empty_severity_components_are_rejected(value):
    with pytest.raises(InvalidInput, match="--severity"):
        severity_filter(value)


@pytest.mark.parametrize(
    "target, parameter",
    [
        ("directory", "PATH"),
        ("main.tf", "PATH"),
        ("vars.tfvars", "--var-file"),
        ("report.json", "--output"),
        ("parent", "--output"),
    ],
)
def test_unreadable_or_unwritable_paths(project, monkeypatch, target, parameter):
    variables = project / "vars.tfvars"
    variables.write_text("SECRET")
    output = project / "report.json"
    output.write_text("existing report")
    blocked = project if target in ("directory", "parent") else project / target
    access = os.access

    def deny(path, mode):
        if path == blocked and (target != "parent" or mode & os.W_OK):
            return False
        return access(path, mode)

    monkeypatch.setattr(os, "access", deny)
    result = runner.invoke(
        app,
        ["drift", str(project), "--var-file", variables.name, "--output", str(output)],
    )
    assert result.exit_code == 2
    assert parameter in result.stderr


def test_var_file_directory_is_rejected(project):
    result = runner.invoke(app, ["drift", str(project), "--var-file", "."])
    assert result.exit_code == 2
    assert "--var-file" in result.stderr


def test_output_parent_cannot_be_file(project):
    result = runner.invoke(
        app,
        [
            "scan",
            str(project),
            "--output",
            str(project / "main.tf" / "reports" / "out.json"),
        ],
    )
    assert result.exit_code == 2
    assert "--output" in result.stderr


def test_scan_defaults_do_not_infer_format_from_output(project, monkeypatch):
    from infralens import cli

    received = []
    monkeypatch.setattr(cli, "handle_scan", received.append)
    monkeypatch.chdir(project.parent)
    result = runner.invoke(app, ["scan", project.name, "--output", "out.sarif"])
    assert result.exit_code == 0
    options = received[0]
    assert options.severity == SEVERITIES
    assert options.fail_on is None
    assert options.format == "table"
    assert options.output == project.parent / "out.sarif"


def test_output_symlink_loop_is_invalid_input(project, symlink):
    output = project / "loop"
    symlink(output, output)
    result = runner.invoke(app, ["scan", str(project), "--output", str(output)])
    assert result.exit_code == 2
    assert "--output" in result.stderr
