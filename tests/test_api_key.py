import pytest
from typer.testing import CliRunner

from infralens import cloud_api_key, cloud_auth
from infralens.cli import app
from infralens.errors import ExecutionError

KEY = "il_key_" + "a" * 32 + "_" + "b" * 43
OTHER = "il_key_" + "c" * 32 + "_" + "d" * 43
API = "https://api.example.com"


def test_saved_key_is_api_scoped_and_cleared(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: tmp_path / "config.json"
    )
    cloud_api_key.save(API, KEY)
    assert cloud_api_key.read(API) == KEY
    assert cloud_api_key.read("https://other.example.com") is None
    cloud_api_key.clear(API)
    assert cloud_api_key.read(API) is None


def test_priority_and_routing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: tmp_path / "config.json"
    )
    cloud_api_key.save(API, KEY)
    monkeypatch.setenv("INFRALENS_ACCESS_TOKEN", "jwt.token.value")
    assert cloud_auth.access_token(API) == KEY
    monkeypatch.setenv("INFRALENS_API_KEY", OTHER)
    assert cloud_auth.access_token(API) == OTHER
    assert (
        cloud_api_key.route(OTHER, "/v1/projects?limit=20")
        == "/v1/cli/projects?limit=20"
    )
    assert cloud_api_key.route("jwt.token.value", "/v1/projects") == "/v1/cli/projects"
    monkeypatch.setenv("INFRALENS_API_KEY", "invalid")
    with pytest.raises(ExecutionError):
        cloud_auth.access_token(API)


def test_cli_login_hides_input_and_status_does_not_reveal_key(monkeypatch, tmp_path):
    from infralens import cloud_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cloud_auth, "interactive_input", lambda: True)
    cloud_config.save(API)
    monkeypatch.setattr(
        cloud_auth, "http", lambda *a, **kw: (200, b'{"items":[],"next_cursor":null}')
    )
    runner = CliRunner()
    result = runner.invoke(app, ["cloud", "login"], input=KEY + "\n")
    assert result.exit_code == 0, result.output
    assert KEY not in result.output
    result = runner.invoke(app, ["cloud", "status"])
    assert result.exit_code == 0 and "saved API key" in result.output
    assert KEY not in result.output
    result = runner.invoke(app, ["cloud", "logout"])
    assert result.exit_code == 0
    assert cloud_api_key.read(API) is None


def test_missing_credentials_do_not_create_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: tmp_path / "config.json"
    )
    monkeypatch.delenv("INFRALENS_API_KEY", raising=False)
    monkeypatch.setenv("INFRALENS_ACCESS_TOKEN", "legacy-token")
    assert cloud_api_key.read(API) is None
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ExecutionError, match="cloud login"):
        cloud_auth.access_token(API)
    cloud_api_key.clear(API)
    assert list(tmp_path.iterdir()) == []


def test_environment_key_bypasses_storage(monkeypatch):
    monkeypatch.setenv("INFRALENS_API_KEY", KEY)
    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: pytest.fail("Storage accessed")
    )
    assert cloud_auth.access_token(API) == KEY


def test_failed_login_preserves_saved_key(monkeypatch, tmp_path):
    from infralens import cloud_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cloud_config, "config_path", lambda: tmp_path / "config.json")
    cloud_config.save(API)
    cloud_api_key.save(API, KEY)
    monkeypatch.setattr(cloud_auth, "interactive_input", lambda: True)

    def reject(*a, **kw):
        assert kw["headers"]["Authorization"] == f"Bearer {OTHER}"
        raise ExecutionError("API key rejected")

    monkeypatch.setattr(cloud_auth, "http", reject)
    result = CliRunner().invoke(app, ["cloud", "login"], input=OTHER + "\n")
    assert result.exit_code == 3
    assert OTHER not in result.output
    assert cloud_api_key.read(API) == KEY


@pytest.mark.parametrize("failure", ["network", "invalid", "cancelled"])
def test_login_failure_does_not_replace_key(monkeypatch, tmp_path, failure):
    from infralens import cloud_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cloud_config, "config_path", lambda: tmp_path / "config.json")
    cloud_config.save(API)
    cloud_api_key.save(API, KEY)
    monkeypatch.setattr(cloud_auth, "interactive_input", lambda: True)
    monkeypatch.setattr(
        cloud_auth,
        "http",
        lambda *a, **kw: (_ for _ in ()).throw(ExecutionError("Cannot connect")),
    )
    result = CliRunner().invoke(
        app,
        ["cloud", "login"],
        input={"network": OTHER + "\n", "invalid": "bad\n", "cancelled": ""}[failure],
    )
    assert result.exit_code != 0
    assert cloud_api_key.read(API) == KEY


def test_read_racing_with_logout_returns_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: tmp_path / "config.json"
    )
    cloud_api_key.save(API, KEY)
    original = cloud_api_key.protect

    def remove_after_check(file, **kwargs):
        original(file, **kwargs)
        if file.suffix == ".apikey":
            file.unlink()

    monkeypatch.setattr(cloud_api_key, "protect", remove_after_check)
    assert cloud_api_key.read(API) is None


def test_logout_is_local_and_removes_legacy_session(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: tmp_path / "config.json"
    )
    cloud_api_key.save(API, KEY)
    legacy = cloud_api_key.path(API).with_suffix(".json")
    legacy.write_text("obsolete-refresh-token")
    monkeypatch.setattr(
        cloud_auth, "http", lambda *a, **k: pytest.fail("Network called")
    )
    cloud_api_key.clear(API)
    assert cloud_api_key.read(API) is None
    assert not legacy.exists()


def test_private_storage_and_unsafe_permissions(monkeypatch, tmp_path):
    import os

    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: tmp_path / "config.json"
    )
    cloud_api_key.save(API, KEY)
    file = cloud_api_key.path(API)
    if os.name == "nt":
        import win32security

        descriptor = win32security.GetNamedSecurityInfo(
            str(file),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        assert descriptor.GetSecurityDescriptorDacl().GetAceCount() == 1
    else:
        assert file.stat().st_mode & 0o777 == 0o600
        assert file.parent.stat().st_mode & 0o777 == 0o700
        file.chmod(0o644)
        with pytest.raises(ExecutionError, match="permissions"):
            cloud_api_key.read(API)


def test_symlink_credentials_are_rejected(monkeypatch, tmp_path):
    import os

    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: tmp_path / "config.json"
    )
    cloud_api_key.save(API, KEY)
    file = cloud_api_key.path(API)
    target = tmp_path / "target"
    target.write_text(KEY)
    file.unlink()
    try:
        file.symlink_to(target)
    except OSError:
        if os.name == "nt":
            pytest.skip("Symlink privilege unavailable")
        raise
    for operation in (
        lambda: cloud_api_key.read(API),
        lambda: cloud_api_key.save(API, OTHER),
        lambda: cloud_api_key.clear(API),
    ):
        with pytest.raises(ExecutionError, match="symbolic link"):
            operation()
    assert target.read_text() == KEY


def test_null_stdin_is_noninteractive_in_a_real_process():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from infralens.cloud_auth import interactive_input; "
            "assert not interactive_input()",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_parallel_writes_leave_complete_key(monkeypatch, tmp_path):
    import subprocess
    import sys

    monkeypatch.setattr(
        "infralens.cloud_config.config_path", lambda: tmp_path / "config.json"
    )
    script = """
from pathlib import Path
from infralens import cloud_api_key, cloud_config
import sys
cloud_config.config_path = lambda: Path(sys.argv[1])
for _ in range(10):
    cloud_api_key.save(sys.argv[2], sys.argv[3])
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path / "config.json"), API, key],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for key in (KEY, OTHER)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr.decode()
        assert not stdout
    assert cloud_api_key.read(API) in (KEY, OTHER)


def test_windows_rejects_unsupported_acl_entries(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace

    monkeypatch.setattr(cloud_api_key, "os", SimpleNamespace(name="nt"))
    monkeypatch.setitem(
        sys.modules, "ntsecuritycon", SimpleNamespace(FILE_ALL_ACCESS=1)
    )
    monkeypatch.setitem(
        sys.modules, "win32api", SimpleNamespace(GetCurrentProcess=lambda: None)
    )
    monkeypatch.setitem(sys.modules, "win32con", SimpleNamespace(TOKEN_QUERY=1))
    acl = SimpleNamespace(
        GetAceCount=lambda: 1, GetAce=lambda index: ((5, 0), 1, "foreign")
    )
    security = SimpleNamespace(
        OpenProcessToken=lambda *a: SimpleNamespace(Close=lambda: None),
        GetTokenInformation=lambda *a: ["owner"],
        TokenUser=1,
        GetNamedSecurityInfo=lambda *a: SimpleNamespace(
            GetSecurityDescriptorDacl=lambda: acl
        ),
        SE_FILE_OBJECT=1,
        DACL_SECURITY_INFORMATION=1,
        ACCESS_ALLOWED_ACE_TYPE=0,
    )
    monkeypatch.setitem(sys.modules, "win32security", security)
    with pytest.raises(ExecutionError, match="permissions"):
        cloud_api_key.protect(tmp_path, directory=True, writable=False)


def test_login_verifies_entered_key_even_with_environment_override(
    monkeypatch, tmp_path
):
    from infralens import cloud_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cloud_config, "config_path", lambda: tmp_path / "config.json")
    cloud_config.save(API)
    monkeypatch.setenv("INFRALENS_API_KEY", OTHER)
    monkeypatch.setattr(cloud_auth, "interactive_input", lambda: True)

    def verify(method, url, **kwargs):
        assert method == "GET"
        assert url == API + "/v1/cli/projects?limit=1"
        assert kwargs["headers"]["Authorization"] == f"Bearer {KEY}"
        return 200, b'{"items":[],"next_cursor":null}'

    monkeypatch.setattr(cloud_auth, "http", verify)
    result = CliRunner().invoke(app, ["cloud", "login"], input=KEY + "\n")
    assert result.exit_code == 0, result.output
    assert "overrides" in result.output
    assert KEY not in result.output and OTHER not in result.output
    assert cloud_api_key.read(API) == KEY
    assert cloud_auth.access_token(API) == OTHER
