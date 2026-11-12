"""Security upload policy without user-visible manifests or retry commands."""

import hashlib
import json

import pytest
from typer.testing import CliRunner

from infralens import cloud
from infralens.cli import app

runner = CliRunner()
pytestmark = pytest.mark.usefixtures("fake_trivy")


def args(project, output):
    return [
        "scan",
        str(project),
        "--format",
        "json",
        "--output",
        str(output),
        "--upload",
        "--project",
        "demo",
        "--api-url",
        "https://api.example.com",
    ]


def test_full_counts_and_threshold_ignore_terminal_filter(
    project, tmp_path, monkeypatch, fake_trivy
):
    got = []
    monkeypatch.setattr(cloud, "upload_report", lambda *values: got.append(values))
    ignore = b"EXAMPLE-IGNORE\n"
    (project / ".trivyignore").write_bytes(ignore)
    output = tmp_path / "report.json"
    response = runner.invoke(
        app, [*args(project, output), "--severity", "LOW", "--fail-on", "HIGH"]
    )
    assert response.exit_code == 1, response.output
    metadata, payload, _ = got[0]
    assert metadata["result"]["findings"] == {
        "total": 4,
        "by_severity": {"UNKNOWN": 1, "LOW": 1, "MEDIUM": 0, "HIGH": 1, "CRITICAL": 1},
    }
    assert metadata["result"]["threshold_status"] == "failed"
    assert metadata["scan_options"] == {
        "severity": ["LOW"],
        "fail_on": "HIGH",
        "ignore_sha256": hashlib.sha256(ignore).hexdigest(),
    }
    assert "TEST-HIGH" not in response.stdout and "TEST-LOW" in response.stdout
    assert {
        f["Severity"]
        for r in json.loads(payload)["Results"]
        for f in r["Misconfigurations"]
    } == {"LOW", "HIGH", "CRITICAL", "UNKNOWN"}
    assert (
        sum(
            "config" in json.loads(line) for line in fake_trivy.read_text().splitlines()
        )
        == 1
    )


@pytest.mark.parametrize(
    "fail_on,expected", [(None, "not_evaluated"), ("HIGH", "passed")]
)
def test_clean_scan_records_gate_status(
    project, tmp_path, monkeypatch, fail_on, expected
):
    got = []
    monkeypatch.setattr(cloud, "upload_report", lambda *values: got.append(values))
    monkeypatch.setenv("FAKE_TRIVY_MODE", "clean")
    response = runner.invoke(
        app,
        [
            *args(project, tmp_path / "report.json"),
            *(["--fail-on", fail_on] if fail_on else []),
        ],
    )
    assert response.exit_code == 0, response.output
    assert got[0][0]["result"]["threshold_status"] == expected
    assert got[0][0]["result"]["findings"]["total"] == 0


@pytest.mark.parametrize("mode", ["fail", "broken", "parse", "version"])
def test_failed_scanner_never_uploads(project, tmp_path, monkeypatch, mode):
    monkeypatch.setenv("FAKE_TRIVY_MODE", mode)
    monkeypatch.setattr(
        cloud,
        "upload_report",
        lambda *args: pytest.fail("Failed scanner started upload"),
    )
    out = tmp_path / "report.json"
    result = runner.invoke(app, args(project, out))
    assert result.exit_code == 3 and not out.exists()


@pytest.mark.parametrize(
    "mode,code", [("warning", "engine_warning"), ("embedded", "embedded_checks")]
)
def test_warning_codes_are_safe(project, tmp_path, monkeypatch, mode, code):
    monkeypatch.setenv("FAKE_TRIVY_MODE", mode)
    got = []
    monkeypatch.setattr(cloud, "upload_report", lambda *args: got.append(args))
    result = runner.invoke(app, args(project, tmp_path / "report.json"))
    assert result.exit_code == 0, result.output
    assert got[0][0]["result"]["warnings"] == [code]
    assert "PRIVATE" not in result.output + json.dumps(got[0][0])
