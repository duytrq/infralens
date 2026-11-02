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
    assert cloud_api_key.route("jwt.token.value", "/v1/projects") == "/v1/projects"
    monkeypatch.setenv("INFRALENS_API_KEY", "invalid")
    with pytest.raises(ExecutionError):
        cloud_auth.access_token(API)


def test_cli_set_status_and_clear_do_not_reveal_key(monkeypatch, tmp_path):
    from infralens import cloud_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cloud_auth, "interactive_input", lambda: True)
    cloud_config.save(API)
    runner = CliRunner()
    result = runner.invoke(app, ["cloud", "api-key", "set"], input=KEY + "\n")
    assert result.exit_code == 0, result.output
    assert KEY not in result.output
    result = runner.invoke(app, ["cloud", "status"])
    assert result.exit_code == 0 and "saved API key" in result.output
    assert KEY not in result.output
    result = runner.invoke(app, ["cloud", "api-key", "clear"])
    assert result.exit_code == 0
    assert cloud_api_key.read(API) is None
