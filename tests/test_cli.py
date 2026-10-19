from importlib.metadata import version

import pytest
from typer.testing import CliRunner

from infralens.cli import app

runner = CliRunner()


@pytest.mark.parametrize("args", [[], ["--help"]])
def test_root_help(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert result.stderr == ""


def test_version_from_metadata():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"infralens {version('infralens')}"
    assert result.stderr == ""


@pytest.mark.parametrize("fmt", ["table", "json", "sarif"])
def test_scan_reports_missing_engine(project, tmp_path, fmt):
    output = tmp_path / "reports" / "security.json"
    result = runner.invoke(
        app, ["scan", str(project), "--format", fmt, "--output", str(output)]
    )
    assert result.exit_code == 4
    assert "Scan engine is not implemented" in result.stderr
    assert result.stdout == ""
    assert not output.parent.exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--format", "xml"],
        ["--severity", ""],
        ["--severity", "high,,low"],
        ["--severity", "severe"],
        ["--fail-on", "UNKNOWN"],
        ["--fail-on", "HIGH,CRITICAL"],
        ["--unknown"],
    ],
)
def test_scan_invalid_options_precede_engine(project, extra):
    result = runner.invoke(app, ["scan", str(project), *extra])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not implemented" not in result.stderr


def test_scan_normalized_options_are_passed_to_handler(project, monkeypatch):
    from infralens import cli
    from infralens.options import ScanOptions

    received = []
    monkeypatch.setattr(cli, "handle_scan", received.append)
    result = runner.invoke(
        app,
        ["scan", str(project), "--severity", " low, HIGH,low ", "--fail-on", " high "],
    )
    assert result.exit_code == 0
    assert received == [
        ScanOptions(project.resolve(), ("LOW", "HIGH"), "table", None, "HIGH")
    ]


@pytest.mark.parametrize("kind", ["missing", "file", "empty", "nested"])
def test_rejects_invalid_project(tmp_path, kind):
    path = tmp_path / "project"
    if kind == "file":
        path.write_text("")
    elif kind != "missing":
        path.mkdir()
        if kind == "nested":
            (path / "child").mkdir()
            (path / "child" / "main.tf").write_text("")
    result = runner.invoke(app, ["scan", str(path)])
    assert result.exit_code == 2
    assert "PATH" in result.stderr


def test_tf_json_is_recognized(tmp_path):
    (tmp_path / "main.tf.json").write_text("{}")
    assert runner.invoke(app, ["scan", str(tmp_path)]).exit_code == 4


@pytest.mark.parametrize("target", ["directory", "input", "symlink", "hardlink"])
def test_rejects_output_collision(project, target):
    output = project
    if target == "input":
        output = project / "main.tf"
    elif target == "symlink":
        output = project / "report.json"
        output.symlink_to(project / "main.tf")
    elif target == "hardlink":
        output = project / "report.json"
        output.hardlink_to(project / "main.tf")
    result = runner.invoke(app, ["scan", str(project), "--output", str(output)])
    assert result.exit_code == 2
    assert "--output" in result.stderr


def test_missing_path():
    assert runner.invoke(app, ["scan"]).exit_code == 2
