import json
import os
import time

import pytest

from infralens.errors import ExecutionError

API = "https://api.example.com"
AUTH = {
    "issuer": "https://issuer.example.com/pool",
    "client_id": "client",
    "token_endpoint": "https://auth.example.com/oauth2/token",
    "revocation_endpoint": "https://auth.example.com/oauth2/revoke",
}


def seed(monkeypatch):
    from infralens import cloud_auth, cloud_session

    monkeypatch.setattr(
        cloud_auth,
        "login",
        lambda *a, **k: {
            "access_token": "ACCESS",
            "refresh_token": "REFRESH",
            "expires_in": 900,
        },
    )
    monkeypatch.setattr(cloud_session, "configuration", lambda api: {"auth": AUTH})
    cloud_session.sign_in(API)
    return cloud_session


def test_login_survives_new_call_without_browser(monkeypatch):
    from infralens import cloud_auth

    session = seed(monkeypatch)
    monkeypatch.setattr(
        cloud_auth, "login", lambda *a, **k: pytest.fail("Browser reopened")
    )
    assert session.token(API) == "ACCESS"
    assert session.token("https://other.example.com") is None
    if os.name != "nt":
        assert session.path(API).stat().st_mode & 0o777 == 0o600
    else:
        import win32security

        descriptor = win32security.GetNamedSecurityInfo(
            str(session.path(API)),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        acl = descriptor.GetSecurityDescriptorDacl()
        assert acl.GetAceCount() == 1
        assert (
            descriptor.GetSecurityDescriptorControl()[0]
            & win32security.SE_DACL_PROTECTED
        )


def test_refresh_keeps_original_refresh_token_and_never_logs(monkeypatch, capsys):
    from infralens import cloud_auth

    session = seed(monkeypatch)
    record = session.read(API)
    record["expires_at"] = time.time() - 1
    session.write(API, record)

    def http(method, url, **kw):
        assert url == AUTH["token_endpoint"]
        assert b"grant_type=refresh_token" in kw["data"]
        return 200, b'{"access_token":"NEW_ACCESS","expires_in":900}'

    monkeypatch.setattr(cloud_auth, "http", http)
    assert session.token(API) == "NEW_ACCESS"
    assert session.read(API)["refresh_token"] == "REFRESH"
    assert "REFRESH" not in capsys.readouterr().out


def test_refresh_network_error_preserves_session(monkeypatch):
    from infralens import cloud_auth

    session = seed(monkeypatch)
    record = session.read(API)
    record["expires_at"] = 0
    session.write(API, record)

    def fail(*a, **kw):
        raise ExecutionError("Cannot connect")

    monkeypatch.setattr(cloud_auth, "http", fail)
    with pytest.raises(ExecutionError, match="Cannot connect"):
        session.token(API)
    assert session.read(API)["refresh_token"] == "REFRESH"


def test_logout_clears_local_even_if_revoke_fails(monkeypatch):
    from infralens import cloud_auth

    session = seed(monkeypatch)

    def fail(*a, **kw):
        raise ExecutionError("Cannot connect")

    monkeypatch.setattr(cloud_auth, "http", fail)
    session.logout(API)
    assert session.read(API) is None


def test_insecure_or_corrupt_session_is_not_read(monkeypatch):
    session = seed(monkeypatch)
    session.path(API).write_text("PRIVATE_BAD_JSON")
    with pytest.raises(ExecutionError) as error:
        session.token(API)
    assert "PRIVATE" not in str(error.value)


def test_invalid_grant_removes_expired_session(monkeypatch):
    from infralens import cloud_auth

    session = seed(monkeypatch)
    record = session.read(API)
    record["expires_at"] = 0
    session.write(API, record)
    monkeypatch.setattr(
        cloud_auth,
        "http",
        lambda *a, **kw: (400, json.dumps({"error": "invalid_grant"}).encode()),
    )
    assert session.token(API) is None
    assert session.read(API) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_world_readable_session_is_rejected(monkeypatch):
    session = seed(monkeypatch)
    session.path(API).chmod(0o644)
    with pytest.raises(ExecutionError, match="permissions"):
        session.token(API)


def test_refresh_rotation_replaces_refresh_token(monkeypatch):
    from infralens import cloud_auth

    session = seed(monkeypatch)
    record = session.read(API)
    record["expires_at"] = 0
    session.write(API, record)
    monkeypatch.setattr(
        cloud_auth,
        "http",
        lambda *a, **kw: (
            200,
            b'{"access_token":"NEXT","refresh_token":"ROTATED","expires_in":900}',
        ),
    )
    assert session.token(API) == "NEXT"
    assert session.read(API)["refresh_token"] == "ROTATED"


def test_parallel_processes_refresh_only_once(monkeypatch, tmp_path):
    import subprocess
    import sys

    session = seed(monkeypatch)
    record = session.read(API)
    record["expires_at"] = 0
    session.write(API, record)
    calls = tmp_path / "calls"
    script = f"""
import json, time
from pathlib import Path
from infralens import cloud_auth, cloud_session
cloud_session.configuration = lambda api: {{'auth': {AUTH!r}}}
def http(*args, **kwargs):
    with Path({str(calls)!r}).open('a') as stream:
        stream.write('refresh\\n')
    time.sleep(0.2)
    return 200, b'{{"access_token":"NEXT","expires_in":900}}'
cloud_auth.http = http
assert cloud_session.token({API!r}) == 'NEXT'
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr.decode()
        assert not stdout
    assert calls.read_text().splitlines() == ["refresh"]


def test_null_stdin_is_noninteractive_in_a_real_process():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from infralens.cloud_auth import interactive_input; "
            "assert interactive_input() is False",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode()
