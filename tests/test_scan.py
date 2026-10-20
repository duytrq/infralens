import json

import pytest
from typer.testing import CliRunner

from infralens.cli import app

runner = CliRunner()
pytestmark = pytest.mark.usefixtures("fake_trivy")


def test_scan_table_and_severity_order(project):
    result = runner.invoke(app, ["scan", str(project)])
    assert result.exit_code == 0, result.output
    assert "main.tf:7" in result.stdout
    assert "aws_security_group.public" in result.stdout
    assert result.stdout.index("TEST-CRITICAL") < result.stdout.index("TEST-HIGH")
    assert "4" in result.stdout
    assert "\x1b[" not in result.stdout


def test_fail_on_sees_findings_hidden_by_filter(project):
    result = runner.invoke(
        app, ["scan", str(project), "--severity", "LOW", "--fail-on", "HIGH"]
    )
    assert result.exit_code == 1
    assert "TEST-LOW" in result.stdout
    assert "TEST-HIGH" not in result.stdout


@pytest.mark.parametrize("format", ["json", "sarif"])
def test_machine_stdout_and_single_scan(project, fake_trivy, format):
    result = runner.invoke(
        app, ["scan", str(project), "--format", format, "--severity", "LOW"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    if format == "json":
        assert [
            f["Severity"] for r in data["Results"] for f in r["Misconfigurations"]
        ] == ["LOW"]
    else:
        assert data["version"] == "2.1.0"
    calls = [json.loads(line) for line in fake_trivy.read_text().splitlines()]
    assert sum("config" in call for call in calls) == 1


@pytest.mark.parametrize("format", ["table", "json", "sarif"])
def test_export_precedes_findings_exit(project, tmp_path, format):
    output = tmp_path / "reports" / "result"
    result = runner.invoke(
        app,
        [
            "scan",
            str(project),
            "--format",
            format,
            "--output",
            str(output),
            "--fail-on",
            "HIGH",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "TEST-HIGH" in result.stdout
    assert output.is_file()
    if format != "table":
        json.loads(output.read_text())
    assert str(output) in result.stderr


@pytest.mark.parametrize("mode", ["fail", "broken", "parse", "version", "convert"])
def test_engine_failure_preserves_old_report_and_hides_payload(
    project, tmp_path, monkeypatch, mode
):
    monkeypatch.setenv("FAKE_TRIVY_MODE", mode)
    output = tmp_path / "report.json"
    output.write_text("old report")
    result = runner.invoke(
        app,
        [
            "--verbose",
            "scan",
            str(project),
            "--format",
            "json",
            "--output",
            str(output),
            "--fail-on",
            "LOW",
        ],
    )
    assert result.exit_code == 3, result.output
    assert result.stdout == ""
    assert "PRIVATE" not in result.output
    assert output.read_text() == "old report"
    assert sorted(p.name for p in tmp_path.glob("report*")) == ["report.json"]


def test_clean_and_filtered_empty_have_distinct_messages(project, monkeypatch):
    filtered = runner.invoke(app, ["scan", str(project), "--severity", "MEDIUM"])
    assert filtered.exit_code == 0
    assert "No findings match" in filtered.stdout
    monkeypatch.setenv("FAKE_TRIVY_MODE", "clean")
    clean = runner.invoke(app, ["scan", str(project)])
    assert clean.exit_code == 0
    assert "No security findings" in clean.stdout


def test_recursive_scan_and_input_collision(project):
    child = project / "nested"
    child.mkdir()
    source = child / "main.tf.json"
    source.write_text("{}")
    (project / "main.tf").unlink()
    assert runner.invoke(app, ["scan", str(project)]).exit_code == 0
    collision = runner.invoke(app, ["scan", str(project), "--output", str(source)])
    assert collision.exit_code == 2
    assert source.read_text() == "{}"


@pytest.mark.parametrize(
    "name",
    ["dev.tfvars", "dev.tfvars.json", "terraform.tfstate", "terraform.tfstate.backup"],
)
def test_protects_auxiliary_inputs(project, name):
    source = project / name
    source.write_text("private")
    result = runner.invoke(app, ["scan", str(project), "--output", str(source)])
    assert result.exit_code == 2
    assert source.read_text() == "private"


@pytest.mark.parametrize("timeout", ["0", "-1", "abc"])
def test_invalid_timeout_precedes_engine(project, fake_trivy, timeout):
    result = runner.invoke(app, ["scan", str(project), "--timeout", timeout])
    assert result.exit_code == 2
    assert not fake_trivy.exists()


def test_scan_does_not_modify_inputs_or_state(project):
    (project / "dev.tfvars").write_text("SECRET")
    (project / "terraform.tfstate").write_text("SECRET")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in project.iterdir()}
    result = runner.invoke(app, ["--verbose", "scan", str(project)])
    assert result.exit_code == 0
    assert "SECRET" not in result.output
    assert before == {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in project.iterdir()
    }


def test_scan_timeout_is_controlled(project, monkeypatch):
    monkeypatch.setenv("FAKE_TRIVY_MODE", "timeout")
    result = runner.invoke(app, ["scan", str(project), "--timeout", "1"])
    assert result.exit_code == 3
    assert "timed out" in result.stderr
    assert result.stdout == ""


def test_output_failure_preserves_report_and_cleans_temp(
    project, tmp_path, monkeypatch
):
    output = tmp_path / "existing.json"
    output.write_text("old")

    def failed_replace(*args):
        raise OSError(5, "PRIVATE_PAYLOAD", str(output))

    monkeypatch.setattr("infralens.reporting.os.replace", failed_replace)
    result = runner.invoke(
        app, ["scan", str(project), "--output", str(output), "--fail-on", "LOW"]
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    assert "PRIVATE" not in result.stderr
    assert output.read_text() == "old"
    assert not list(tmp_path.glob(".infralens-*.tmp"))
