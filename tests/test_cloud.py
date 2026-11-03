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


def arguments(kind, project, output):
    return [
        kind,
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
        *(
            [
                "--scope",
                "dev",
                "--plan-json",
                "examples/drift/plan.json",
                "--fail-on",
                "ANY",
            ]
            if kind == "drift"
            else ["--fail-on", "HIGH"]
        ),
    ]


@pytest.fixture(params=["scan", "drift"])
def generated(request, project, tmp_path, monkeypatch, fake_trivy):
    received = []
    with monkeypatch.context() as patch:
        patch.setattr(cloud, "upload_report", lambda *args: received.append(args))
        output = tmp_path / "report.json"
        result = runner.invoke(app, arguments(request.param, project, output))
        assert result.exit_code == 1, result.output
    metadata, payload, api = received[0]
    assert not Path(str(output) + ".upload.json").exists()
    return request.param, output, metadata, payload


def test_upload_keeps_native_report_and_schema_valid_metadata_in_memory(generated):
    kind, path, metadata, payload = generated
    assert payload == path.read_bytes()
    assert metadata["artifact"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["artifact"]["size_bytes"] == len(payload)
    assert metadata["source"] == {"relative_path": "."}
    assert metadata["run_type"] == ("security_scan" if kind == "scan" else "drift")
    assert (
        metadata["result"]["threshold_status" if kind == "scan" else "gate_status"]
        == "failed"
    )
    spec = json.loads(Path("contracts/openapi.json").read_text())
    Draft202012Validator(
        {"$ref": "#/components/schemas/RunInput", "components": spec["components"]}
    ).validate(metadata)


@pytest.mark.parametrize("put_status", [200, 412])
def test_upload_sends_token_only_to_api_and_confirms_ready(
    generated, monkeypatch, put_status
):
    _, path, metadata, payload = generated
    calls = []

    def http(method, url, **kwargs):
        calls.append((method, url, kwargs))
        ready = {"run_id": metadata["run_id"], "upload_status": "ready"}
        if url.endswith("/v1/cli/runs"):
            assert json.loads(kwargs["data"]) == metadata
            return 201, json.dumps(
                {
                    "run": {"run_id": metadata["run_id"], "upload_status": "pending"},
                    "upload": {
                        "method": "PUT",
                        "url": "https://reports.s3.ap-southeast-1.amazonaws.com/report?signature=example",
                        "headers": {
                            "content-type": "application/json",
                            "content-length": str(len(payload)),
                            "x-amz-checksum-sha256": base64.b64encode(
                                hashlib.sha256(payload).digest()
                            ).decode(),
                            "x-amz-sdk-checksum-algorithm": "SHA256",
                            "x-amz-tagging": "state=pending",
                            "if-none-match": "*",
                        },
                    },
                }
            ).encode()
        return (
            (put_status, b"") if method == "PUT" else (200, json.dumps(ready).encode())
        )

    monkeypatch.setattr(cloud, "http", http)
    monkeypatch.setattr(cloud, "access_token", lambda *args: "PRIVATE_TOKEN")
    cloud.upload_report(metadata, payload, API)
    assert [call[0] for call in calls] == ["POST", "PUT", "POST"]
    assert calls[1][2]["data"] == path.read_bytes()
    assert "Authorization" not in calls[1][2]["headers"]
    assert calls[0][2]["headers"]["Authorization"] == "Bearer PRIVATE_TOKEN"


@pytest.mark.parametrize("change", ["sha", "size", "schema", "type"])
def test_invalid_payload_metadata_never_starts_auth(generated, monkeypatch, change):
    _, _, metadata, payload = generated
    if change == "sha":
        metadata["artifact"]["sha256"] = "0" * 64
    elif change == "size":
        metadata["artifact"]["size_bytes"] += 1
    elif change == "schema":
        metadata["artifact"]["schema_version"] = "unsupported"
    else:
        metadata["run_type"] = "unsupported"
    monkeypatch.setattr(
        cloud, "access_token", lambda *args: pytest.fail("Invalid payload started auth")
    )
    with pytest.raises(InvalidInput):
        cloud.upload_report(metadata, payload, API)


@pytest.mark.parametrize("kind", ["scan", "drift"])
def test_network_failure_keeps_report_without_sidecars(
    project, tmp_path, monkeypatch, fake_trivy, kind
):
    def fail(*args):
        raise ExecutionError("Cannot connect to the cloud service.")

    monkeypatch.setattr(cloud, "upload_report", fail)
    output = tmp_path / "report.json"
    result = runner.invoke(app, arguments(kind, project, output))
    assert result.exit_code == 3
    assert output.is_file() and not Path(str(output) + ".upload.json").exists()
    assert "Local report kept" in result.stderr and "Cannot connect" in result.stderr
    assert (
        "retry" not in result.output.lower() and "manifest" not in result.output.lower()
    )


@pytest.mark.parametrize("kind", ["scan", "drift"])
def test_native_windows_newlines_are_bound_to_uploaded_bytes(
    project, tmp_path, monkeypatch, fake_trivy, kind
):
    from infralens import handlers
    from infralens.reporting import write_report

    monkeypatch.setattr(
        handlers, "write_report", lambda p, t: write_report(p, t.replace("\n", "\r\n"))
    )
    got = []
    monkeypatch.setattr(cloud, "upload_report", lambda *args: got.append(args))
    out = tmp_path / "report.json"
    result = runner.invoke(app, arguments(kind, project, out))
    assert result.exit_code == 1, result.output
    metadata, payload, _ = got[0]
    assert payload == out.read_bytes()
    assert metadata["artifact"]["sha256"] == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    "kind,limit", [("scan", "MAX_SECURITY_REPORT_BYTES"), ("drift", "MAX_REPORT_BYTES")]
)
def test_oversized_upload_keeps_report_before_network(
    project, tmp_path, monkeypatch, fake_trivy, kind, limit
):
    monkeypatch.setattr(cloud, limit, 10)
    monkeypatch.setattr(
        cloud,
        "upload_report",
        lambda *args: pytest.fail("Oversized upload reached transport"),
    )
    out = tmp_path / "report.json"
    result = runner.invoke(app, arguments(kind, project, out))
    assert result.exit_code == 3 and out.is_file()
    assert not Path(str(out) + ".upload.json").exists()


@pytest.mark.parametrize("fixture", ["drift", "drift-review", "network-rules"])
@pytest.mark.parametrize("rule", ["ANY", "UNKNOWN", "MEDIUM", "HIGH,UNKNOWN"])
def test_imported_drift_report_and_posted_metadata_match_api_contract(
    tmp_path, monkeypatch, fixture, rule
):
    root = Path(__file__).resolve().parents[1]
    project = root / "examples" / fixture
    got = []
    monkeypatch.setattr(cloud, "upload_report", lambda *args: got.append(args))
    out = tmp_path / "report.json"
    response = runner.invoke(
        app,
        [
            "drift",
            str(project),
            "--plan-json",
            str(project / "plan.json"),
            "--format",
            "json",
            "--output",
            str(out),
            "--upload",
            "--project",
            "demo",
            "--scope",
            "dev",
            "--api-url",
            API,
            "--fail-on",
            rule,
        ],
    )
    assert response.exit_code in (0, 1), response.output
    assert (
        got[0][0]["drift_options"]["gate"]
        == json.loads(out.read_bytes())["gate"]["criteria"]
    )
    spec = json.loads((root / "contracts/openapi.json").read_text())
    for name, data in [
        ("DriftReport", json.loads(out.read_bytes())),
        ("RunInput", got[0][0]),
    ]:
        Draft202012Validator(
            {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
        ).validate(data)


@pytest.mark.parametrize(
    "status,hint",
    [
        (401, "API key"),
        (403, "Permission"),
        (404, "project"),
        (429, "busy"),
        (503, "unavailable"),
    ],
)
def test_http_errors_are_actionable_and_not_retried(monkeypatch, status, hint):
    import io
    import urllib.error

    from infralens import cloud_auth

    calls = []

    class Opener:
        def open(self, *args, **kwargs):
            calls.append(1)
            raise urllib.error.HTTPError(
                API,
                status,
                "PRIVATE_SERVER_ERROR",
                {},
                io.BytesIO(b'{"error":{"code":"safe_code","message":"PRIVATE_BODY"}}'),
            )

    monkeypatch.setattr(
        cloud_auth.urllib.request, "build_opener", lambda *args: Opener()
    )
    with pytest.raises(ExecutionError) as error:
        cloud_auth.http("GET", API + "/v1/projects")
    assert hint in str(error.value) and "PRIVATE" not in str(error.value)
    assert calls == [1]


def test_network_error_is_reported_once_without_secret_payload(monkeypatch):
    import urllib.error

    from infralens import cloud_auth

    calls = []

    class Opener:
        def open(self, *args, **kwargs):
            calls.append(1)
            raise urllib.error.URLError("PRIVATE_NETWORK_REASON")

    monkeypatch.setattr(
        cloud_auth.urllib.request, "build_opener", lambda *args: Opener()
    )
    with pytest.raises(ExecutionError, match="Cannot connect") as error:
        cloud_auth.http("GET", API)
    assert calls == [1] and "PRIVATE" not in str(error.value)


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

    monkeypatch.delenv("INFRALENS_API_KEY", raising=False)
    monkeypatch.setattr(cloud_auth.sys.stdin, "isatty", lambda: False)
    with pytest.raises(ExecutionError, match="No API key"):
        cloud_auth.access_token(API)
    monkeypatch.setenv(
        "INFRALENS_API_KEY",
        "il_key_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    assert cloud_auth.access_token(API) == "il_key_" + "a" * 32 + "_" + "b" * 43
    monkeypatch.setenv("INFRALENS_API_KEY", "PRIVATE_TOKEN\nInjection: value")
    with pytest.raises(ExecutionError):
        cloud_auth.access_token(API)
    assert "PRIVATE_TOKEN" not in capsys.readouterr().out
