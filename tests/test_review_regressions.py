import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens.cli import app
from infralens.errors import ExecutionError
from infralens.process import ProcessResult
from infralens.trivy import Trivy, _diagnostics


@pytest.mark.parametrize("name", ["linked.tf", "linked.tf.json"])
@pytest.mark.parametrize("mixed", [False, True])
def test_symlinked_source_is_rejected(project, tmp_path, name, mixed, symlink):
    target = tmp_path / "unsafe-source"
    target.write_text('resource "aws_s3_bucket" "unsafe" {}')
    if not mixed:
        (project / "main.tf").unlink()
    symlink(project / name, target)
    result = CliRunner().invoke(app, ["scan", str(project), "--fail-on", "HIGH"])
    assert result.exit_code == 2, result.output
    assert "symlink" in result.stderr.lower()
    assert not result.stdout


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_report_cannot_replace_root_ignore(
    project, tmp_path, fake_trivy, alias, symlink
):
    policy = project / ".trivyignore"
    policy.write_text("AWS-0107\n")
    before = (policy.read_bytes(), policy.stat().st_mtime_ns)
    output = policy
    if alias != "direct":
        output = tmp_path / "report.json"
        if alias == "symlink":
            symlink(output, policy)
        else:
            os.link(policy, output)
    result = CliRunner().invoke(app, ["scan", str(project), "--output", str(output)])
    assert result.exit_code == 2, result.output
    assert (policy.read_bytes(), policy.stat().st_mtime_ns) == before
    assert not fake_trivy.exists()


def test_parser_error_with_fallback_in_filename_is_fatal():
    diagnostic = (
        "time\tERROR\t[terraform parser] Error parsing file\t"
        'file="Falling back to embedded checks.tf" error="invalid Terraform"'
    )
    with pytest.raises(ExecutionError, match="completely analyze"):
        _diagnostics(diagnostic)


def test_actual_embedded_checks_fallback_is_a_warning():
    messages = _diagnostics(
        'time\tERROR\t[misconfig] Falling back to embedded checks\terror="unavailable"'
    )
    assert len(messages) == 1
    assert "embedded checks" in messages[0]


def test_policy_filename_cannot_be_used_for_a_new_report(project, tmp_path):
    output = tmp_path / ".TRIVYIGNORE"
    result = CliRunner().invoke(app, ["scan", str(project), "--output", str(output)])
    assert result.exit_code == 2
    assert not output.exists()


def test_relative_path_executable_is_resolved_before_changing_cwd(
    project, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("infralens.executable.shutil.which", lambda _: "bin/trivy")
    calls = []

    def execute(arguments, **kwargs):
        calls.append(arguments)
        return ProcessResult(0, "Version: 0.76.0\n", "")

    monkeypatch.setattr("infralens.trivy.run_process", execute)
    Trivy(project)
    assert Path(calls[0][0]).is_absolute()
    assert Path(calls[0][0]) == tmp_path / "bin" / "trivy"
