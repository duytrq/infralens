import os
import shutil
import subprocess

import pytest

from infralens.git_source import source_metadata

GIT = shutil.which("git")


def git(path, *args):
    return subprocess.check_output(
        [GIT, "-C", str(path), *args],
        encoding="utf-8",
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    ).strip()


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "hạ tầng"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    (path / "infra").mkdir()
    (path / "infra/main.tf").write_text("# infra\n")
    git(path, "add", ".")
    git(path, "commit", "-m", "initial")
    return path


def test_reads_target_repo_subdirectory_not_cwd_or_git_environment(
    repository, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    data = source_metadata(repository / "infra")
    assert data == {
        "relative_path": "infra",
        "git": {
            "commit": git(repository, "rev-parse", "HEAD"),
            "branch": "main",
            "dirty": False,
        },
    }


def test_dirty_and_detached_head(repository):
    git(repository, "checkout", "--detach", "HEAD")
    (repository / "untracked.tf").write_text("# change")
    data = source_metadata(repository)
    assert data["git"]["branch"] is None
    assert data["git"]["dirty"] is True
    assert data["relative_path"] == "."


def test_worktree_branch(repository, tmp_path):
    worktree = tmp_path / "worktree"
    git(repository, "worktree", "add", "-b", "demo-branch", str(worktree))
    assert source_metadata(worktree)["git"]["branch"] == "demo-branch"


def test_non_git_unborn_and_missing_git_fall_back(tmp_path, monkeypatch):
    assert source_metadata(tmp_path) == {"relative_path": "."}
    git(tmp_path, "init")
    assert source_metadata(tmp_path) == {"relative_path": "."}
    monkeypatch.setenv("PATH", str(tmp_path / "missing"))
    assert source_metadata(tmp_path) == {"relative_path": "."}


def test_git_timeout_does_not_block_scan(repository, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert source_metadata(repository) == {"relative_path": "."}


@pytest.mark.parametrize("kind", ["scan", "drift"])
def test_upload_captures_git_before_writing_report(
    repository, fake_trivy, monkeypatch, kind
):
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator
    from typer.testing import CliRunner

    from infralens import cloud
    from infralens.cli import app

    monkeypatch.setenv("PATH", os.environ["PATH"] + os.pathsep + str(Path(GIT).parent))
    captured = []
    monkeypatch.setattr(cloud, "upload_report", lambda *args: captured.append(args[0]))
    args = [
        kind,
        str(repository / "infra"),
        "--upload",
        "--project",
        "demo",
        "--api-url",
        "https://api.example.com",
        "--output",
        str(repository / "generated.json"),
    ]
    if kind == "drift":
        args += ["--plan-json", "examples/drift/plan.json", "--scope", "test"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert captured[0]["source"]["git"]["dirty"] is False
    assert captured[0]["source"]["git"]["branch"] == "main"
    assert captured[0]["source"]["relative_path"] == "infra"
    assert source_metadata(repository)["git"]["dirty"] is True
    spec = json.loads(Path("contracts/openapi.json").read_text())
    Draft202012Validator(
        {"$ref": "#/components/schemas/RunInput", "components": spec["components"]}
    ).validate(captured[0])
