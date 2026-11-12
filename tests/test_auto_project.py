"""First-upload onboarding at the CLI/API/config boundary."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens import cloud_config, cloud_projects
from infralens.cli import app
from infralens.errors import ExecutionError

API = "https://api.example.com"
GIT = shutil.which("git")
runner = CliRunner()


@pytest.fixture
def repo(project, monkeypatch):
    subprocess.run(["git", "init", str(project)], check=True, capture_output=True)
    cloud_config.save(API)
    monkeypatch.setattr(cloud_projects, "access_token", lambda api: "SECRET")
    return project


@pytest.fixture
def service(monkeypatch):
    projects = {}

    def http(method, url, **kwargs):
        project_id = url.rsplit("/", 1)[1]
        if method == "GET":
            return (
                (200, json.dumps(projects[project_id]).encode())
                if project_id in projects
                else (404, b'{"error":{"code":"not_found"}}')
            )
        assert method == "PUT"
        value = {"project_id": project_id, **json.loads(kwargs["data"])}
        if project_id in projects:
            if projects[project_id] != value:
                return 409, b'{"error":{"code":"conflict"}}'
            return 200, json.dumps(value).encode()
        projects[project_id] = value
        return 201, json.dumps(value).encode()

    monkeypatch.setattr(cloud_projects, "http", http)
    return projects


@pytest.mark.parametrize("kind", ["scan", "drift"])
def test_first_upload_creates_project_and_next_upload_remembers(
    repo, tmp_path, monkeypatch, service, kind
):
    nested = repo / "environments" / "dev"
    nested.mkdir(parents=True)
    (nested / "main.tf").write_text('variable "test" {}')
    monkeypatch.chdir(tmp_path)
    received = []
    monkeypatch.setattr(f"infralens.cli.handle_{kind}", received.append)
    args = [kind, str(nested), "--upload"]
    if kind == "drift":
        args += ["--scope", "dev"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    binding = repo / ".infralens.toml"
    assert binding.exists() and "SECRET" not in binding.read_text()
    selected = received[0].upload.project
    assert selected == "terraform-project"
    assert service[selected]["name"] == repo.name
    assert cloud_config.resolve(root=nested) == (API, selected)
    assert not (tmp_path / ".infralens.toml").exists()
    assert not (nested / ".infralens.toml").exists()
    monkeypatch.setattr(
        cloud_projects, "http", lambda *a, **k: pytest.fail("Recreated")
    )
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert received[1].upload.project == selected


@pytest.mark.parametrize("source", ["repo", "flag", "env"])
def test_existing_selection_wins(repo, monkeypatch, source):
    if source == "repo":
        cloud_config.save_repo(repo, API, "selected")
    elif source == "env":
        monkeypatch.setenv("INFRALENS_PROJECT", "selected")
    monkeypatch.setattr(cloud_projects, "http", lambda *a, **k: pytest.fail("Created"))
    received = []
    monkeypatch.setattr("infralens.cli.handle_scan", received.append)
    args = ["scan", str(repo), "--upload"]
    if source == "flag":
        args += ["--project", "selected"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert received[0].upload.project == "selected"


@pytest.mark.parametrize(
    "name, expected",
    [("Company Infra", "company-infra"), ("---", "repo"), ("a" * 80, "a" * 64)],
)
def test_repo_name_becomes_readable_id(repo, monkeypatch, service, name, expected):
    renamed = repo.rename(repo.parent / name)
    monkeypatch.setattr("infralens.cli.handle_scan", lambda options: None)
    result = runner.invoke(app, ["scan", str(renamed), "--upload"])
    assert result.exit_code == 0, result.output
    assert cloud_config.resolve(root=renamed) == (API, expected)
    assert service[expected]["name"] == name


@pytest.mark.parametrize("scope", [None, "INVALID SCOPE"])
def test_invalid_drift_scope_never_creates(repo, monkeypatch, scope):
    monkeypatch.setattr(cloud_projects, "http", lambda *a, **k: pytest.fail("Created"))
    args = ["drift", str(repo), "--upload"]
    if scope is not None:
        args += ["--scope", scope]
    result = runner.invoke(app, args)
    assert result.exit_code == 2 and "scope" in result.output
    assert not (repo / ".infralens.toml").exists()


def test_api_failure_does_not_save_binding(repo, monkeypatch):
    def fail(*a, **k):
        raise ExecutionError("Service unavailable")

    monkeypatch.setattr(cloud_projects, "http", fail)
    result = runner.invoke(app, ["scan", str(repo), "--upload"])
    assert result.exit_code == 3, result.output
    assert not (repo / ".infralens.toml").exists()


def test_api_override_preserves_existing_binding(repo, monkeypatch):
    binding = cloud_config.save_repo(repo, API, "old-project")
    before = binding.read_bytes()
    monkeypatch.setattr(cloud_projects, "http", lambda *a, **k: pytest.fail("Created"))
    result = runner.invoke(
        app,
        ["scan", str(repo), "--upload", "--api-url", "https://other.example.com"],
    )
    assert result.exit_code == 2, result.output
    assert binding.read_bytes() == before


@pytest.mark.parametrize(
    "input_text, expected",
    [("y\n", "terraform-project"), ("n\ncompany-infra-lab\n", "company-infra-lab")],
)
def test_collision_offers_reuse_or_another_id(
    repo, monkeypatch, service, input_text, expected
):
    service["terraform-project"] = {
        "project_id": "terraform-project",
        "name": "Existing infrastructure",
    }
    monkeypatch.setattr("infralens.cloud_auth.interactive_input", lambda: True)
    monkeypatch.setattr("infralens.cli.handle_scan", lambda options: None)
    result = runner.invoke(app, ["scan", str(repo), "--upload"], input=input_text)
    assert result.exit_code == 0, result.output
    assert "Existing infrastructure" in result.output
    assert cloud_config.resolve(root=repo) == (API, expected)
    assert service["terraform-project"]["name"] == "Existing infrastructure"
    # Once saved, this choice is not asked again.
    monkeypatch.setattr(cloud_projects, "http", lambda *a, **k: pytest.fail("Network"))
    again = runner.invoke(app, ["scan", str(repo), "--upload"])
    assert again.exit_code == 0, again.output


def test_collision_in_ci_requires_explicit_selection(repo, monkeypatch, service):
    service["terraform-project"] = {
        "project_id": "terraform-project",
        "name": repo.name,
    }
    monkeypatch.setattr("infralens.cloud_auth.interactive_input", lambda: False)
    monkeypatch.setattr(
        "infralens.cli.handle_scan", lambda options: pytest.fail("Scanned")
    )
    result = runner.invoke(app, ["scan", str(repo), "--upload"])
    assert result.exit_code == 2 and "--project" in result.output
    assert not (repo / ".infralens.toml").exists()


def test_cancel_collision_does_not_bind(repo, monkeypatch, service):
    service["terraform-project"] = {
        "project_id": "terraform-project",
        "name": repo.name,
    }
    monkeypatch.setattr("infralens.cloud_auth.interactive_input", lambda: True)
    result = runner.invoke(app, ["scan", str(repo), "--upload"], input="")
    assert result.exit_code == 130, result.output
    assert not (repo / ".infralens.toml").exists()


@pytest.mark.parametrize("status", [200, 409])
def test_racing_project_creation_is_not_silently_reused(repo, monkeypatch, status):
    reads = []

    def http(method, url, **kwargs):
        if method == "GET":
            reads.append(url)
            if len(reads) == 1:
                return 404, b'{"error":{"code":"not_found"}}'
            return 200, json.dumps(
                {"project_id": "terraform-project", "name": repo.name}
            ).encode()
        return status, json.dumps(
            {"project_id": "terraform-project", "name": repo.name}
        ).encode()

    monkeypatch.setattr(cloud_projects, "http", http)
    monkeypatch.setattr("infralens.cloud_auth.interactive_input", lambda: False)
    monkeypatch.setattr("infralens.cli.handle_scan", lambda options: None)
    result = runner.invoke(app, ["scan", str(repo), "--upload"])
    assert result.exit_code == 2, result.output
    assert not (repo / ".infralens.toml").exists()


def test_auto_project_uploads_the_scanner_report(
    repo, service, fake_trivy, monkeypatch
):
    from infralens import cloud

    monkeypatch.setenv("PATH", os.environ["PATH"] + os.pathsep + str(Path(GIT).parent))
    monkeypatch.chdir(repo)
    uploaded = []
    monkeypatch.setattr(cloud, "upload_report", lambda *args: uploaded.append(args))
    result = runner.invoke(app, ["scan", "--upload"])
    assert result.exit_code == 0, result.output
    assert len(uploaded) == 1
    metadata, payload, api = uploaded[0]
    assert api == API and metadata["project_id"] in service
    assert json.loads(payload)["SchemaVersion"] == 2
    assert len(list((repo / ".infralens" / "reports").glob("*.json"))) == 1


def test_worktree_gets_its_own_binding(repo, tmp_path, service, monkeypatch):
    subprocess.run(
        [
            GIT,
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        check=True,
        capture_output=True,
    )
    worktree = tmp_path / "worktree"
    subprocess.run(
        [GIT, "-C", str(repo), "worktree", "add", "--detach", str(worktree)],
        check=True,
        capture_output=True,
    )
    (worktree / "main.tf").write_text('variable "test" {}')
    monkeypatch.setattr("infralens.cli.handle_scan", lambda options: None)
    result = runner.invoke(app, ["scan", str(worktree), "--upload"])
    assert result.exit_code == 0, result.output
    assert (worktree / ".infralens.toml").exists()
    assert not (repo / ".infralens.toml").exists()


def test_cloned_binding_reuses_project_without_creating(
    repo, tmp_path, service, monkeypatch
):
    monkeypatch.setattr("infralens.cli.handle_scan", lambda options: None)
    first = runner.invoke(app, ["scan", str(repo), "--upload"])
    assert first.exit_code == 0, first.output
    copied = tmp_path / "clone"
    shutil.copytree(repo, copied)
    monkeypatch.setattr(cloud_projects, "http", lambda *a, **k: pytest.fail("Created"))
    second = runner.invoke(app, ["scan", str(copied), "--upload"])
    assert second.exit_code == 0, second.output
    assert cloud_config.resolve(root=copied) == cloud_config.resolve(root=repo)
