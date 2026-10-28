import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens.cli import app

runner = CliRunner()
API = "https://api.example.com"


def args(project, output):
    return [
        "drift",
        str(project),
        "--plan-json",
        "examples/drift/plan.json",
        "--format",
        "json",
        "--output",
        str(output),
        "--upload",
        "--project",
        "demo",
        "--scope",
        "dev-default",
        "--api-url",
        API,
    ]


def test_upload_preserves_gate_and_writes_sanitized_retry_files(
    project, tmp_path, monkeypatch
):
    from infralens import cloud

    received = []
    (project / "main.tf").write_text('resource "aws_instance" "demo" {}\n')
    monkeypatch.setattr(cloud, "upload_files", lambda *values: received.append(values))
    output = tmp_path / "report.json"
    result = runner.invoke(app, [*args(project, output), "--fail-on-drift"])
    assert result.exit_code == 1, result.output
    report = json.loads(output.read_text())
    assert report["resources"][0]["source"]["locations"][0]["file"] == "main.tf"
    assert str(project) not in output.read_text()
    saved = json.loads(Path(str(output) + ".upload.json").read_text())
    metadata = saved["manifest"]
    assert (
        metadata["artifact"]["sha256"]
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert metadata["result"]["gate_status"] == "failed"
    assert metadata["scope"] == "dev-default"
    assert saved["api_url"] == API
    assert received


def test_upload_failure_keeps_report_and_manifest_for_retry(
    project, tmp_path, monkeypatch
):
    from infralens import cloud
    from infralens.errors import ExecutionError

    def fail(*args):
        raise ExecutionError("Upload failed; retry the saved manifest.")

    monkeypatch.setattr(cloud, "upload_files", fail)
    output = tmp_path / "report.json"
    response = runner.invoke(app, [*args(project, output), "--fail-on-drift"])
    assert response.exit_code == 3
    assert output.exists()
    manifest = Path(str(output) + ".upload.json")
    original = manifest.read_bytes()
    received = []
    monkeypatch.setattr(cloud, "upload_files", lambda *values: received.append(values))

    def forbidden(*args, **kwargs):
        pytest.fail("Retry must not run Terraform")

    monkeypatch.setattr("infralens.handlers.collect_drift", forbidden)
    response = runner.invoke(
        app,
        [
            "cloud",
            "upload",
            "--manifest",
            str(manifest),
            "--report",
            str(output),
            "--api-url",
            API,
        ],
    )
    assert response.exit_code == 0, response.output
    assert received
    assert manifest.read_bytes() == original


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--project", "demo"],
        ["--project", "demo", "--scope", "dev", "--api-url", "http://localhost:1234"],
        ["--project", "../bad", "--scope", "dev", "--api-url", API],
    ],
)
def test_invalid_upload_options_fail_before_engine(project, tmp_path, extra):
    response = runner.invoke(app, ["drift", str(project), "--upload", *extra])
    assert response.exit_code == 2
    assert not (tmp_path / "report.json").exists()


def test_existing_retry_manifest_is_not_overwritten(project, tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    sidecar = Path(str(output) + ".upload.json")
    sidecar.write_text("previous immutable upload")
    response = runner.invoke(app, args(project, output))
    assert response.exit_code == 2
    assert sidecar.read_text() == "previous immutable upload"
    assert not output.exists()


@pytest.fixture
def upload_pair(project, tmp_path, monkeypatch):
    from infralens import cloud

    output = tmp_path / "report.json"
    with monkeypatch.context() as patch:
        patch.setattr(cloud, "upload_files", lambda *args: None)
        result = runner.invoke(app, args(project, output))
        assert result.exit_code == 0, result.output
    return output, Path(str(output) + ".upload.json")


def test_upload_transport_sends_token_only_to_api_and_completes_existing_put(
    upload_pair, monkeypatch
):
    import base64

    from infralens import cloud

    report, saved = upload_pair
    metadata = json.loads(saved.read_text())["manifest"]
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/v1/runs"):
            assert json.loads(kwargs["data"])["run_id"] == metadata["run_id"]
            return 201, json.dumps(
                {
                    "run": {"run_id": metadata["run_id"], "upload_status": "pending"},
                    "upload": {
                        "url": "https://reports.s3.ap-southeast-1.amazonaws.com/report?signature=example",
                        "method": "PUT",
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
    monkeypatch.setattr(cloud, "access_token", lambda api: "PRIVATE_TOKEN")
    cloud.upload_files(report, saved, API)
    assert [call[0] for call in calls] == ["POST", "PUT", "POST"]
    assert "Authorization" not in calls[1][2]["headers"]
    assert calls[0][2]["headers"]["Authorization"] == "Bearer PRIVATE_TOKEN"
    assert "PRIVATE_TOKEN" not in saved.read_text()


def test_retry_rejects_changed_report_before_auth_or_network(upload_pair, monkeypatch):
    from infralens import cloud
    from infralens.errors import InvalidInput

    report, saved = upload_pair
    report.write_text(report.read_text() + " ")
    monkeypatch.setattr(
        cloud, "access_token", lambda *args: pytest.fail("No login for changed report")
    )
    with pytest.raises(InvalidInput, match="must match"):
        cloud.upload_files(report, saved, API)


def test_cloud_report_marks_external_locations_unavailable_without_touching_local(
    tmp_path,
):
    from infralens.cloud import cloud_report

    original = {
        "resources": [
            {
                "source": {
                    "status": "located",
                    "locations": [{"file": str(tmp_path.parent / "outside.tf")}],
                }
            }
        ]
    }
    report = cloud_report(original, tmp_path)
    assert report["resources"][0]["source"]["status"] == "unavailable"
    assert "locations" not in report["resources"][0]["source"]
    assert original["resources"][0]["source"]["status"] == "located"


def test_noninteractive_auth_requires_explicit_token_and_never_prints_it(
    monkeypatch, capsys
):
    from infralens import cloud_auth
    from infralens.errors import ExecutionError

    monkeypatch.delenv("INFRALENS_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(cloud_auth.sys.stdin, "isatty", lambda: False)
    with pytest.raises(ExecutionError, match="Noninteractive"):
        cloud_auth.access_token(API)
    monkeypatch.setenv("INFRALENS_ACCESS_TOKEN", "PRIVATE_TOKEN")
    assert cloud_auth.access_token(API) == "PRIVATE_TOKEN"
    monkeypatch.setenv("INFRALENS_ACCESS_TOKEN", "PRIVATE_TOKEN\nInjection: value")
    with pytest.raises(ExecutionError):
        cloud_auth.access_token(API)
    assert "PRIVATE_TOKEN" not in capsys.readouterr().out


def test_pkce_login_checks_state_and_exchanges_code_without_logging(
    monkeypatch, capsys
):
    import base64
    import socket
    import threading
    import urllib.error
    import urllib.parse
    import urllib.request

    from infralens import cloud_auth

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = {
        "auth": {
            "callback_url": f"http://localhost:{port}/callback",
            "authorization_endpoint": "https://login.example.com/oauth2/authorize",
            "token_endpoint": "https://login.example.com/oauth2/token",
            "pkce_method": "S256",
            "scopes": ["openid", "infralens/api"],
            "client_id": "client",
        }
    }
    authorization = {}
    statuses = []
    threads = []

    def browser(url):
        authorization.update(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))

        def redirect():
            for state in ("wrong-state", authorization["state"][0]):
                query = urllib.parse.urlencode({"state": state, "code": "PRIVATE_CODE"})
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/callback?{query}", timeout=5
                    ) as response:
                        statuses.append(response.status)
                except urllib.error.HTTPError as exc:
                    statuses.append(exc.code)

        thread = threading.Thread(target=redirect)
        threads.append(thread)
        thread.start()
        return True

    def exchange(method, url, **kwargs):
        form = urllib.parse.parse_qs(kwargs["data"].decode())
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(form["code_verifier"][0].encode()).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        assert challenge == authorization["code_challenge"][0]
        assert authorization["code_challenge_method"] == ["S256"]
        assert form["code"] == ["PRIVATE_CODE"]
        return 200, b'{"access_token":"PRIVATE_TOKEN"}'

    monkeypatch.setattr(cloud_auth.webbrowser, "open", browser)
    monkeypatch.setattr(cloud_auth, "http", exchange)
    assert cloud_auth.login(config, timeout=5) == "PRIVATE_TOKEN"
    for thread in threads:
        thread.join(timeout=5)
    assert statuses == [400, 200]
    captured = capsys.readouterr()
    assert "PRIVATE_CODE" not in captured.out + captured.err
    assert "PRIVATE_TOKEN" not in captured.out + captured.err


def test_manifest_checksum_uses_written_bytes_with_windows_newlines(
    project, tmp_path, monkeypatch
):
    from infralens import cloud, handlers
    from infralens.reporting import write_report

    monkeypatch.setattr(cloud, "upload_files", lambda *args: None)
    monkeypatch.setattr(
        handlers,
        "write_report",
        lambda path, text: write_report(path, text.replace("\n", "\r\n")),
    )
    output = tmp_path / "report.json"
    response = runner.invoke(app, args(project, output))
    assert response.exit_code == 0, response.output
    artifact = json.loads(Path(str(output) + ".upload.json").read_text())["manifest"][
        "artifact"
    ]
    assert artifact["size_bytes"] == len(output.read_bytes())
    assert artifact["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


@pytest.mark.parametrize("fixture", ["drift", "drift-review", "network-rules"])
def test_real_cli_report_and_manifest_match_exported_api_contract(
    tmp_path, monkeypatch, fixture
):
    from jsonschema import Draft202012Validator

    from infralens import cloud

    root = Path(__file__).resolve().parents[1]
    project = root / "examples" / fixture
    output = tmp_path / "report.json"
    monkeypatch.setattr(cloud, "upload_files", lambda *args: None)
    result = runner.invoke(
        app,
        [
            "drift",
            str(project),
            "--plan-json",
            str(project / "plan.json"),
            "--format",
            "json",
            "--output",
            str(output),
            "--upload",
            "--project",
            "demo",
            "--scope",
            "dev-default",
            "--api-url",
            API,
            "--fail-on",
            "high",
            "--fail-on-unknown",
        ],
    )
    assert result.exit_code in (0, 1), result.output
    spec = json.loads((root / "contracts/openapi.json").read_text())
    manifest = json.loads(Path(str(output) + ".upload.json").read_text())["manifest"]
    for name, document in [
        ("DriftReport", json.loads(output.read_text())),
        ("RunInput", manifest),
    ]:
        Draft202012Validator(
            {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
        ).validate(document)
