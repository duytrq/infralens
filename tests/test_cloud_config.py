import json

import pytest
from typer.testing import CliRunner

from infralens.cli import app

runner = CliRunner()
API = "https://api.example.com"


def test_configure_persists_only_public_settings_and_status_reports_them(monkeypatch):
    from infralens import cloud_config

    monkeypatch.setenv("INFRALENS_ACCESS_TOKEN", "PRIVATE_TOKEN")
    response = runner.invoke(app, ["cloud", "configure", "--api-url", API + "/"])
    assert response.exit_code == 0, response.output
    saved = cloud_config.config_path().read_text()
    assert json.loads(saved) == {
        "schema_version": 1,
        "api_url": API,
        "project_id": None,
    }
    assert "PRIVATE_TOKEN" not in saved
    status = runner.invoke(app, ["cloud", "status"])
    assert status.exit_code == 0 and API in status.stdout
    assert "PRIVATE_TOKEN" not in status.output


def test_flags_override_env_and_saved_defaults_without_cross_origin_project_leak(
    monkeypatch,
):
    from infralens import cloud_config

    cloud_config.save(API, "saved-project")
    assert cloud_config.resolve() == (API, "saved-project")
    monkeypatch.setenv("INFRALENS_API_URL", "https://env.example.com")
    assert cloud_config.resolve() == ("https://env.example.com", None)
    monkeypatch.setenv("INFRALENS_PROJECT", "env-project")
    assert cloud_config.resolve() == ("https://env.example.com", "env-project")
    assert cloud_config.resolve("https://flag.example.com", "flag-project") == (
        "https://flag.example.com",
        "flag-project",
    )
    cloud_config.save("https://new.example.com")
    assert cloud_config.load()["project_id"] is None


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:1234",
        "https://user:password@example.com",
        "https://example.com/v1",
        "",
    ],
)
def test_invalid_config_url_does_not_write_file(value):
    from infralens import cloud_config

    response = runner.invoke(app, ["cloud", "configure", "--api-url", value])
    assert response.exit_code == 2
    assert not cloud_config.config_path().exists()
    assert "password" not in response.output


def test_local_scan_does_not_read_broken_cloud_config(project, monkeypatch):
    from infralens import cloud_config

    path = cloud_config.config_path()
    path.parent.mkdir(parents=True)
    path.write_text("broken PRIVATE_CONFIG")
    monkeypatch.setattr("infralens.cli.handle_scan", lambda options: None)
    response = runner.invoke(app, ["scan", str(project)])
    assert response.exit_code == 0, response.output
    cloud = runner.invoke(app, ["cloud", "status"])
    assert cloud.exit_code == 2 and "PRIVATE_CONFIG" not in cloud.output


def test_config_defaults_apply_to_both_upload_commands(project, tmp_path, monkeypatch):
    from infralens import cloud_config

    cloud_config.save(API, "demo")
    for command in ("scan", "drift"):
        received = []
        monkeypatch.setattr(f"infralens.cli.handle_{command}", received.append)
        response = runner.invoke(
            app,
            [
                command,
                str(project),
                "--format",
                "json",
                "--output",
                str(tmp_path / f"{command}.json"),
                "--upload",
                *(["--scope", "dev"] if command == "drift" else []),
            ],
        )
        assert response.exit_code == 0, response.output
        assert (
            received[0].upload.api_url == API and received[0].upload.project == "demo"
        )


def test_create_list_and_select_projects_use_authenticated_api(monkeypatch):
    from infralens import cloud_config, cloud_projects

    cloud_config.save(API)
    calls = []
    project = {
        "project_id": "demo",
        "name": "Demo",
        "created_at": "2026-10-29T00:00:00Z",
    }
    monkeypatch.setattr(cloud_projects, "access_token", lambda url: "PRIVATE_TOKEN")

    def http(method, url, **kwargs):
        calls.append((method, url, kwargs))
        assert kwargs["headers"]["Authorization"] == "Bearer PRIVATE_TOKEN"
        if "/v1/projects?" in url:
            return 200, json.dumps({"items": [project], "next_cursor": None}).encode()
        if method == "PUT":
            assert json.loads(kwargs["data"]) == {"name": "Demo"}
        return (201 if method == "PUT" else 200), json.dumps(project).encode()

    monkeypatch.setattr(cloud_projects, "http", http)
    for args in [["create", "demo", "--name", "Demo"], ["list"], ["use", "demo"]]:
        result = runner.invoke(app, ["cloud", "project", *args])
        assert result.exit_code == 0, result.output
        assert "demo" in result.stdout and "PRIVATE_TOKEN" not in result.output
    assert cloud_config.resolve() == (API, "demo")
    assert [call[0] for call in calls] == ["PUT", "GET", "GET"]


def test_failed_project_selection_keeps_current_selection(monkeypatch):
    from infralens import cloud_config, cloud_projects
    from infralens.errors import ExecutionError

    cloud_config.save(API, "old-project")
    monkeypatch.setattr(cloud_projects, "access_token", lambda url: "PRIVATE_TOKEN")

    def missing(*args, **kwargs):
        raise ExecutionError("Project not found.")

    monkeypatch.setattr(cloud_projects, "http", missing)
    result = runner.invoke(app, ["cloud", "project", "use", "missing"])
    assert result.exit_code == 3
    assert cloud_config.resolve() == (API, "old-project")


def test_retry_upload_command_is_not_exposed():
    result = runner.invoke(app, ["cloud", "--help"])
    assert "configure" in result.stdout and "project" in result.stdout
    assert "upload" not in result.stdout.lower()
    assert runner.invoke(app, ["cloud", "upload"]).exit_code == 2


@pytest.mark.parametrize(
    "record",
    [
        {"schema_version": True, "api_url": API, "project_id": None},
        {"schema_version": 1, "api_url": API, "project_id": None, "token": "PRIVATE"},
    ],
)
def test_unknown_or_malformed_config_is_not_echoed(record):
    from infralens import cloud_config

    path = cloud_config.config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record))
    response = runner.invoke(app, ["cloud", "status"])
    assert response.exit_code == 2 and "PRIVATE" not in response.output


def test_project_list_follows_empty_pages_with_one_authentication(monkeypatch):
    from infralens import cloud_config, cloud_projects

    cloud_config.save(API, "demo")
    auth = []
    monkeypatch.setattr(
        cloud_projects, "access_token", lambda url: auth.append(url) or "TOKEN"
    )
    calls = []

    def request(method, url, **kwargs):
        calls.append(url)
        return 200, json.dumps(
            {"items": [], "next_cursor": "cursor+value"}
            if len(calls) == 1
            else {
                "items": [{"project_id": "demo", "name": "Demo\u001b[2J"}],
                "next_cursor": None,
            }
        ).encode()

    monkeypatch.setattr(cloud_projects, "http", request)
    result = runner.invoke(app, ["cloud", "project", "list"])
    assert result.exit_code == 0, result.output
    assert len(calls) == 2 and "cursor=cursor%2Bvalue" in calls[1]
    assert auth == [API] and "\x1b" not in result.stdout and "*" in result.stdout


def test_project_response_cannot_select_a_different_id(monkeypatch):
    from infralens import cloud_config, cloud_projects

    cloud_config.save(API, "old")
    monkeypatch.setattr(cloud_projects, "access_token", lambda url: "TOKEN")
    monkeypatch.setattr(
        cloud_projects,
        "http",
        lambda *args, **kwargs: (200, b'{"project_id":"wrong","name":"PRIVATE"}'),
    )
    result = runner.invoke(app, ["cloud", "project", "use", "demo"])
    assert result.exit_code == 3 and "PRIVATE" not in result.output
    assert cloud_config.resolve() == (API, "old")


def test_cloud_project_operations_require_authentication(monkeypatch):
    from infralens import cloud_auth, cloud_config, cloud_projects

    cloud_config.save(API)
    monkeypatch.delenv("INFRALENS_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(cloud_auth.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        cloud_projects,
        "http",
        lambda *args, **kwargs: pytest.fail("Unauthenticated API request"),
    )
    result = runner.invoke(app, ["cloud", "project", "list"])
    assert result.exit_code == 3 and "Noninteractive cloud operations" in result.stderr
