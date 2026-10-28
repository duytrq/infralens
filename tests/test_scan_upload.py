"""Security uploads preserve the native report and retry without scanning again."""

import base64
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from infralens import cloud
from infralens.cli import app
from infralens.errors import ExecutionError, InvalidInput

runner = CliRunner()
API = "https://api.example.com"
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
        API,
    ]


@pytest.fixture
def scan_pair(project, tmp_path, monkeypatch):
    output = tmp_path / "security.json"
    with monkeypatch.context() as patch:
        patch.setattr(cloud, "upload_files", lambda *args: None)
        response = runner.invoke(app, args(project, output))
        assert response.exit_code == 0, response.output
    return output, Path(str(output) + ".upload.json")


def test_upload_keeps_all_findings_with_filtered_terminal_and_failed_gate(
    project,
    tmp_path,
    monkeypatch,
    fake_trivy,
):
    calls = []
    monkeypatch.setattr(cloud, "upload_files", lambda *values: calls.append(values))
    ignore = b"AWS-EXAMPLE\n"
    (project / ".trivyignore").write_bytes(ignore)
    output = tmp_path / "security.json"
    response = runner.invoke(
        app, [*args(project, output), "--severity", "LOW", "--fail-on", "HIGH"]
    )
    assert response.exit_code == 1, response.output
    assert "TEST-LOW" in response.stdout and "TEST-HIGH" not in response.stdout
    report = json.loads(output.read_bytes())
    assert {
        f["Severity"] for r in report["Results"] for f in r["Misconfigurations"]
    } == {
        "UNKNOWN",
        "LOW",
        "HIGH",
        "CRITICAL",
    }
    saved = Path(str(output) + ".upload.json")
    metadata = json.loads(saved.read_bytes())["manifest"]
    assert metadata["run_type"] == "security_scan"
    assert metadata["tool"]["engine_version"] == "0.76.0"
    assert metadata["source"] == {"relative_path": "."}
    assert "scope" not in metadata
    assert metadata["scan_options"] == {
        "severity": ["LOW"],
        "fail_on": "HIGH",
        "ignore_sha256": hashlib.sha256(ignore).hexdigest(),
    }
    assert metadata["result"]["threshold_status"] == "failed"
    assert metadata["result"]["findings"] == {
        "total": 4,
        "by_severity": {"UNKNOWN": 1, "LOW": 1, "MEDIUM": 0, "HIGH": 1, "CRITICAL": 1},
    }
    assert (
        metadata["artifact"]["sha256"]
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert metadata["artifact"]["size_bytes"] == len(output.read_bytes())
    assert metadata["artifact"]["schema_version"] == 2
    assert calls == [(output.resolve(), saved.resolve(), API)]
    engine_calls = [json.loads(line) for line in fake_trivy.read_text().splitlines()]
    assert sum("config" in call for call in engine_calls) == 1
    spec = json.loads(
        (Path(__file__).resolve().parents[1] / "contracts/openapi.json").read_text()
    )
    Draft202012Validator(
        {"$ref": "#/components/schemas/RunInput", "components": spec["components"]}
    ).validate(metadata)


@pytest.mark.parametrize(
    "fail_on,expected", [(None, "not_evaluated"), ("HIGH", "passed")]
)
def test_clean_scan_upload_records_gate_status(
    project, tmp_path, monkeypatch, fail_on, expected
):
    monkeypatch.setenv("FAKE_TRIVY_MODE", "clean")
    monkeypatch.setattr(cloud, "upload_files", lambda *args: None)
    output = tmp_path / "clean.json"
    response = runner.invoke(
        app, [*args(project, output), *(["--fail-on", fail_on] if fail_on else [])]
    )
    assert response.exit_code == 0, response.output
    metadata = json.loads(Path(str(output) + ".upload.json").read_bytes())["manifest"]
    assert metadata["result"]["threshold_status"] == expected
    assert metadata["result"]["findings"]["total"] == 0


@pytest.mark.parametrize(
    "extra",
    [
        ["--upload"],
        ["--upload", "--format", "json"],
        ["--upload", "--format", "json", "--project", "demo"],
        ["--upload", "--format", "json", "--project", "../bad", "--api-url", API],
        [
            "--upload",
            "--format",
            "json",
            "--project",
            "demo",
            "--api-url",
            "http://api.example.com",
        ],
        ["--upload", "--format", "sarif", "--project", "demo", "--api-url", API],
        ["--project", "demo"],
        ["--api-url", API],
    ],
)
def test_invalid_security_upload_options_precede_engine(
    project, tmp_path, fake_trivy, extra
):
    output = tmp_path / "report.json"
    response = runner.invoke(
        app, ["scan", str(project), "--output", str(output), *extra]
    )
    assert response.exit_code == 2
    assert not fake_trivy.exists()
    assert not output.exists()


def test_existing_security_manifest_is_preserved(project, tmp_path, fake_trivy):
    output = tmp_path / "security.json"
    saved = Path(str(output) + ".upload.json")
    saved.write_text("immutable")
    response = runner.invoke(app, args(project, output))
    assert response.exit_code == 2
    assert saved.read_text() == "immutable"
    assert not fake_trivy.exists()


def test_upload_failure_preserves_security_retry_files(project, tmp_path, monkeypatch):
    def fail(*args):
        raise ExecutionError("Upload failed; retry the saved manifest.")

    monkeypatch.setattr(cloud, "upload_files", fail)
    output = tmp_path / "security.json"
    response = runner.invoke(app, [*args(project, output), "--fail-on", "HIGH"])
    assert response.exit_code == 3
    assert output.exists() and Path(str(output) + ".upload.json").exists()


def test_security_retry_sends_bound_bytes_and_never_runs_trivy(
    scan_pair, fake_trivy, monkeypatch
):
    report, saved = scan_pair
    metadata = json.loads(saved.read_bytes())["manifest"]
    before = fake_trivy.read_bytes()
    original = saved.read_bytes()
    requests = []

    def request(method, url, **kwargs):
        requests.append((method, url, kwargs))
        if url.endswith("/v1/runs"):
            assert json.loads(kwargs["data"]) == metadata
            return 201, json.dumps(
                {
                    "run": {"run_id": metadata["run_id"], "upload_status": "pending"},
                    "upload": {
                        "method": "PUT",
                        "url": "https://reports.s3.ap-southeast-1.amazonaws.com/report?signature=example",
                        "headers": {
                            "content-type": "application/json",
                            "content-length": str(report.stat().st_size),
                            "x-amz-checksum-sha256": base64.b64encode(
                                hashlib.sha256(report.read_bytes()).digest()
                            ).decode(),
                            "x-amz-sdk-checksum-algorithm": "SHA256",
                            "x-amz-tagging": "state=pending",
                            "if-none-match": "*",
                        },
                    },
                }
            ).encode()
        return (412 if method == "PUT" else 200), b"{}"

    monkeypatch.setattr(cloud, "http", request)
    monkeypatch.setattr(cloud, "access_token", lambda *args: "PRIVATE_TOKEN")
    response = runner.invoke(
        app,
        [
            "cloud",
            "upload",
            "--report",
            str(report),
            "--manifest",
            str(saved),
            "--api-url",
            API,
        ],
    )
    assert response.exit_code == 0, response.output
    assert "Uploaded security scan" in response.stderr
    assert [call[0] for call in requests] == ["POST", "PUT", "POST"]
    assert requests[1][2]["data"] == report.read_bytes()
    assert "Authorization" not in requests[1][2]["headers"]
    assert "PRIVATE_TOKEN" not in response.output + saved.read_text()
    assert fake_trivy.read_bytes() == before
    assert saved.read_bytes() == original


@pytest.mark.parametrize("change", ["bytes", "origin", "type", "schema"])
def test_security_retry_mismatch_rejected_before_login(scan_pair, monkeypatch, change):
    report, saved = scan_pair
    data = json.loads(saved.read_bytes())
    if change == "bytes":
        report.write_bytes(report.read_bytes() + b" ")
    elif change == "origin":
        data["api_url"] = "https://other.example.com"
    elif change == "type":
        data["manifest"]["run_type"] = "drift"
    else:
        data["manifest"]["artifact"]["schema_version"] = "1.0"
    saved.write_text(json.dumps(data))
    monkeypatch.setattr(
        cloud,
        "access_token",
        lambda *args: pytest.fail("No auth for mismatched bytes/type/origin"),
    )
    with pytest.raises(InvalidInput):
        cloud.upload_files(report, saved, API)


def test_security_manifest_hashes_actual_windows_newlines(
    project, tmp_path, monkeypatch
):
    from infralens import handlers
    from infralens.reporting import write_report

    monkeypatch.setattr(
        handlers,
        "write_report",
        lambda path, text: write_report(path, text.replace("\n", "\r\n")),
    )
    monkeypatch.setattr(cloud, "upload_files", lambda *args: None)
    output = tmp_path / "security.json"
    response = runner.invoke(app, args(project, output))
    assert response.exit_code == 0, response.output
    artifact = json.loads(Path(str(output) + ".upload.json").read_bytes())["manifest"][
        "artifact"
    ]
    assert artifact["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert artifact["size_bytes"] == output.stat().st_size


def test_security_upload_size_limit_keeps_local_report(project, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "MAX_SECURITY_REPORT_BYTES", 10, raising=False)
    monkeypatch.setattr(
        cloud, "access_token", lambda *args: pytest.fail("No auth for oversized report")
    )
    output = tmp_path / "security.json"
    response = runner.invoke(app, args(project, output))
    assert response.exit_code == 3
    assert output.is_file()
    assert not Path(str(output) + ".upload.json").exists()


@pytest.mark.parametrize("mode", ["fail", "broken", "parse", "version"])
def test_security_scan_failure_does_not_create_cloud_run(
    project, tmp_path, monkeypatch, mode
):
    monkeypatch.setenv("FAKE_TRIVY_MODE", mode)
    monkeypatch.setattr(
        cloud, "access_token", lambda *args: pytest.fail("No upload after failed scan")
    )
    output = tmp_path / "security.json"
    response = runner.invoke(app, args(project, output))
    assert response.exit_code == 3
    assert not output.exists()
    assert not Path(str(output) + ".upload.json").exists()


@pytest.mark.parametrize("padding", [0, 2 * 1024 * 1024])
def test_security_retry_accepts_ready_runs_and_reports_above_drift_limit(
    scan_pair, monkeypatch, padding
):
    report, saved = scan_pair
    data = json.loads(report.read_bytes())
    data["Extra"] = "x" * padding
    report.write_bytes(json.dumps(data).encode())
    record = json.loads(saved.read_bytes())
    artifact = record["manifest"]["artifact"]
    artifact["size_bytes"] = report.stat().st_size
    artifact["sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
    saved.write_text(json.dumps(record))
    requests = []

    def request(method, url, **kwargs):
        requests.append(method)
        return 200, json.dumps(
            {
                "run": {
                    "run_id": record["manifest"]["run_id"],
                    "upload_status": "ready",
                },
                "upload": None,
            }
        ).encode()

    monkeypatch.setattr(cloud, "access_token", lambda *args: "PRIVATE_TOKEN")
    monkeypatch.setattr(cloud, "http", request)
    cloud.upload_files(report, saved, API)
    assert requests == ["POST"]


@pytest.mark.parametrize(
    "mode,code", [("warning", "engine_warning"), ("embedded", "embedded_checks")]
)
def test_security_metadata_uses_safe_warning_codes(
    project, tmp_path, monkeypatch, mode, code
):
    monkeypatch.setenv("FAKE_TRIVY_MODE", mode)
    monkeypatch.setattr(cloud, "upload_files", lambda *args: None)
    output = tmp_path / "security.json"
    response = runner.invoke(app, args(project, output))
    assert response.exit_code == 0, response.output
    text = Path(str(output) + ".upload.json").read_text()
    assert json.loads(text)["manifest"]["result"]["warnings"] == [code]
    assert "PRIVATE" not in response.output + text
