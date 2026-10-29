import pytest
from typer.testing import CliRunner

from infralens.cli import app

runner = CliRunner()


@pytest.mark.parametrize(
    "extra",
    [
        ["--trace", "7"],
        ["--trace", "14"],
    ],
)
def test_clean_trace_requires_no_aws_calls(project, extra, fake_terraform, monkeypatch):
    def forbidden(*args):
        pytest.fail("Clean drift must not initialize an AWS session")

    monkeypatch.setattr("infralens.cloudtrail._session", forbidden)
    result = runner.invoke(app, ["drift", str(project), *extra])
    assert result.exit_code == 0
    assert "CloudTrail trace: not_needed" in result.stdout


@pytest.mark.parametrize(
    "extra, parameter",
    [
        (["--trace"], "--trace"),
        (["--trace", "0"], "--trace"),
        (["--trace", "-1"], "--trace"),
        (["--trace", "1.5"], "--trace"),
        (["--trace", "91"], "--trace"),
        (["--profile", "  "], "--profile"),
        (["--region", ""], "--region"),
        (["--trace", "7", "--var-file", "missing.tfvars"], "--var-file"),
        (["--format", "sarif"], "--format"),
        (["--unknown"], "--unknown"),
    ],
)
def test_drift_invalid_input_precedes_missing_feature(project, extra, parameter):
    result = runner.invoke(app, ["drift", str(project), *extra])
    assert result.exit_code == 2
    assert parameter in result.stderr
    assert "not supported" not in result.stderr
    assert "not implemented" not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("trace, days", [(False, None), (True, 7)])
def test_drift_options_and_relative_paths(project, tmp_path, monkeypatch, trace, days):
    from infralens import cli
    from infralens.options import DriftOptions

    relative = project / "dev vars.tfvars"
    absolute = tmp_path / "shared.tfvars"
    relative.write_text('secret = "DO_NOT_PRINT"')
    absolute.write_text("{}")
    received = []
    monkeypatch.setattr(cli, "handle_drift", received.append)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "drift",
            project.name,
            "--var-file",
            relative.name,
            "--var-file",
            str(absolute),
            "--var-file",
            relative.name,
            "--output",
            "reports/drift.json",
            "--profile",
            " dev ",
            "--region",
            " us-east-1 ",
            "--fail-on",
            "ANY",
            *(["--trace", "7"] if trace else []),
        ],
    )
    assert result.exit_code == 0
    assert received == [
        DriftOptions(
            project,
            (relative, absolute, relative),
            "table",
            tmp_path / "reports/drift.json",
            "dev",
            "us-east-1",
            trace,
            days,
            True,
        )
    ]
    assert not (tmp_path / "reports").exists()


@pytest.mark.parametrize("link", [False, True])
def test_output_cannot_overwrite_var_file(project, link, symlink):
    variables = project / "dev.tfvars"
    variables.write_text('secret = "DO_NOT_PRINT"')
    output = variables
    if link:
        output = project / "report.json"
        symlink(output, variables)
    result = runner.invoke(
        app,
        ["drift", str(project), "--var-file", variables.name, "--output", str(output)],
    )
    assert result.exit_code == 2
    assert "--output" in result.stderr
    assert "DO_NOT_PRINT" not in result.output


def test_drift_requires_path():
    assert runner.invoke(app, ["drift"]).exit_code == 2
