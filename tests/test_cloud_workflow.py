import json

import pytest
from typer.testing import CliRunner

from infralens import cloud_config, cloud_projects, cloud_workflow
from infralens.cli import app

runner = CliRunner()
API = "https://api.example.com"


@pytest.mark.parametrize("kind", ["scan", "drift"])
def test_minimal_upload_uses_repo_and_creates_unique_json(kind, project, monkeypatch):
    monkeypatch.chdir(project)
    cloud_config.save_repo(project, API, "repo-project")
    received = []
    monkeypatch.setattr(f"infralens.cli.handle_{kind}", received.append)
    args = [kind, "--upload"] + (["--scope", "dev"] if kind == "drift" else [])
    for _ in range(2):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
    assert all(
        o.format == "json" and o.upload.project == "repo-project" for o in received
    )
    assert received[0].output != received[1].output
    assert received[0].output.parent == project / ".infralens" / "reports"


def test_setup_and_project_picker_keep_secrets_out_of_repo(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.setattr(cloud_workflow, "interactive", lambda: None)
    monkeypatch.setattr("infralens.cloud_auth.access_token", lambda api: "SECRET")
    monkeypatch.setattr(cloud_projects, "access_token", lambda api: "SECRET")

    def http(method, url, **kw):
        data = {"project_id": "demo", "name": "Demo"}
        return 200, json.dumps(
            {"items": [data], "next_cursor": None} if "?" in url else data
        ).encode()

    monkeypatch.setattr(cloud_projects, "http", http)
    result = runner.invoke(app, ["cloud", "setup", "--api-url", API], input="1\n")
    assert result.exit_code == 0, result.output
    file = project / ".infralens.toml"
    assert "demo" in file.read_text() and "SECRET" not in file.read_text()
    status = runner.invoke(app, ["cloud", "status"])
    assert (
        status.exit_code == 0 and "demo" in status.output and str(file) in status.output
    )
    # Rerunning setup must not require deleting valid repo settings.
    result = runner.invoke(app, ["cloud", "setup", "--api-url", API], input="1\n")
    assert result.exit_code == 0, result.output


def test_setup_never_prompts_in_ci(monkeypatch):
    monkeypatch.setattr(cloud_workflow.cloud_auth, "interactive_input", lambda: False)
    result = runner.invoke(app, ["cloud", "setup"])
    assert result.exit_code == 2 and "interactive" in result.output.lower()


def test_explicit_non_json_upload_fails_before_engine(project, monkeypatch):
    monkeypatch.setattr(
        "infralens.cli.handle_scan", lambda *a: pytest.fail("Engine started")
    )
    result = runner.invoke(app, ["scan", str(project), "--upload", "--format", "sarif"])
    assert result.exit_code == 2 and "json" in result.output


def test_cancelled_setup_preserves_settings(project, monkeypatch):
    monkeypatch.chdir(project)
    cloud_config.save(API)
    monkeypatch.setattr(cloud_workflow, "interactive", lambda: None)
    monkeypatch.setattr(cloud_workflow.cloud_auth, "access_token", lambda api: "TOKEN")
    monkeypatch.setattr(cloud_projects, "list_projects", lambda *a, **k: [])
    response = runner.invoke(app, ["cloud", "setup"], input="")
    assert response.exit_code == 130
    assert "project_id" not in cloud_config.load()
    assert not (project / ".infralens.toml").exists()


def test_setup_creates_project_when_list_is_empty(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.setattr(cloud_workflow, "interactive", lambda: None)
    monkeypatch.setattr("infralens.cloud_auth.access_token", lambda api: "TOKEN")
    monkeypatch.setattr(cloud_projects, "access_token", lambda api: "TOKEN")
    writes = []

    def http(method, url, **kw):
        if method == "PUT":
            writes.append(json.loads(kw["data"]))
        data = {"project_id": "new-project", "name": "New project"}
        return 200, json.dumps(
            {"items": [], "next_cursor": None} if "?" in url else data
        ).encode()

    monkeypatch.setattr(cloud_projects, "http", http)
    response = runner.invoke(
        app, ["cloud", "setup", "--api-url", API], input="0\nnew-project\nNew project\n"
    )
    assert response.exit_code == 0, response.output
    assert writes == [{"name": "New project"}]
    assert cloud_config.resolve(root=project) == (API, "new-project")
    assert not cloud_config.config_path().exists()
