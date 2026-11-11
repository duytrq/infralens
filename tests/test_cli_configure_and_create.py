import pytest
from typer.testing import CliRunner

from infralens import cloud_auth, cloud_config, cloud_projects
from infralens.cli import app

runner = CliRunner()
API = "https://api.example.com"


def test_configure_list_is_status_alias_without_network_or_secrets(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    cloud_config.save_repo(tmp_path, API, "demo")
    monkeypatch.setenv("INFRALENS_ACCESS_TOKEN", "PRIVATE_TOKEN")
    monkeypatch.setattr(
        cloud_auth, "http", lambda *a, **k: pytest.fail("Network called")
    )
    result = runner.invoke(app, ["cloud", "configure", "list"])
    assert result.exit_code == 0, result.output
    assert "demo" in result.stdout and API in result.stdout and "Auth:" in result.stdout
    assert "PRIVATE_TOKEN" not in result.output
    assert result.stdout == runner.invoke(app, ["cloud", "status"]).stdout


@pytest.mark.parametrize(
    "args,input_text",
    [
        ([], "demo\nDemo name\n"),
        (["demo"], "Demo name\n"),
        (["demo", "--name", "Explicit"], ""),
        (["--name", "Explicit"], "demo\n"),
    ],
)
def test_project_create_prompts_missing_fields_only(
    args, input_text, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cloud_auth, "interactive_input", lambda: True)
    received = []
    monkeypatch.setattr(cloud_projects, "create", lambda *a: received.append(a))
    response = runner.invoke(
        app, ["cloud", "project", "create", *args], input=input_text
    )
    assert response.exit_code == 0, response.output
    assert received[0][:2] == ("demo", "Explicit" if "--name" in args else "Demo name")
    assert ("Display name" in response.stdout) is ("--name" not in args)


def test_missing_name_in_ci_does_not_create_project(monkeypatch):
    monkeypatch.setattr(cloud_auth, "interactive_input", lambda: False)
    monkeypatch.setattr(
        cloud_projects, "create", lambda *a: pytest.fail("Project created")
    )
    response = runner.invoke(app, ["cloud", "project", "create", "demo"])
    assert response.exit_code == 2 and "--name" in response.output


def test_configure_list_with_setter_flag_never_mutates_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cloud_config.save(API)
    before = cloud_config.config_path().read_bytes()
    response = runner.invoke(
        app, ["cloud", "configure", "--api-url", "https://other.example.com", "list"]
    )
    assert response.exit_code == 2
    assert cloud_config.config_path().read_bytes() == before
