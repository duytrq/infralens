import base64
import hashlib
import importlib.util
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from infralens_backend import validation
from infralens_backend.settings import Settings


@pytest.fixture
def smoke_tool():
    path = Path(__file__).resolve().parents[1] / "scripts/smoke.py"
    spec = importlib.util.spec_from_file_location("backend_smoke_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_config():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return Settings(
        "table",
        "bucket",
        "https://issuer",
        "client",
        "https://example.auth",
        callback_url=f"http://localhost:{port}/callback",
    ).public()


def test_browser_login_checks_state_and_uses_pkce(smoke_tool, monkeypatch):
    config = local_config()
    observed = {}

    def exchange(method, url, data, headers):
        fields = urllib.parse.parse_qs(data.decode())
        verifier = fields["code_verifier"][0]
        actual = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert actual == observed["code_challenge"][0]
        assert fields["code"] == ["one-time-code"]
        assert fields["redirect_uri"] == [config["auth"]["callback_url"]]
        assert method == "POST" and url == config["auth"]["token_endpoint"]
        assert "client_secret" not in fields
        return 200, b'{"access_token":"access-token"}'

    monkeypatch.setattr(smoke_tool, "http", exchange)
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = []

        def browser(url):
            observed.update(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))
            assert observed["code_challenge_method"] == ["S256"]
            callback = (
                config["auth"]["callback_url"]
                + "?"
                + urllib.parse.urlencode(
                    {
                        "state": observed["state"][0],
                        "code": "one-time-code",
                    }
                )
            )
            futures.append(pool.submit(urllib.request.urlopen, callback, timeout=2))
            return True

        monkeypatch.setattr(smoke_tool.webbrowser, "open", browser)
        assert smoke_tool.login(config, timeout=2) == "access-token"
        with futures[0].result() as response:
            assert response.status == 200


def test_browser_login_rejects_an_unrelated_callback(smoke_tool, monkeypatch):
    config = local_config()
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = []

        def browser(url):
            callback = config["auth"]["callback_url"] + "?state=wrong&code=stolen"
            futures.append(pool.submit(urllib.request.urlopen, callback, timeout=2))
            return True

        monkeypatch.setattr(smoke_tool.webbrowser, "open", browser)
        with pytest.raises(RuntimeError, match="timed out"):
            smoke_tool.login(config, timeout=0.3)
        with pytest.raises(urllib.error.HTTPError) as error:
            futures[0].result()
        assert error.value.code == 400


def test_smoke_metadata_counts_findings_and_preserves_report_digest(smoke_tool):
    report = json.dumps(
        {
            "SchemaVersion": 2,
            "Trivy": {"Version": "0.76.0"},
            "Results": [
                {
                    "Misconfigurations": [
                        {"Severity": "HIGH", "Status": "FAIL"},
                        {"Severity": "LOW", "Status": "EXCEPTION"},
                    ]
                }
            ],
        }
    ).encode()
    payload = smoke_tool.metadata(report, "smoke")
    validation.scan(payload, 50 * 1024 * 1024)
    assert payload["result"]["findings"]["total"] == 1
    assert payload["result"]["findings"]["by_severity"]["HIGH"] == 1
    assert payload["artifact"]["sha256"] == hashlib.sha256(report).hexdigest()
