import pytest

from infralens import cloud_config
from infralens.errors import InvalidInput

API = "https://api.example.com"


def test_input_directory_controls_repo_config_not_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    nested = repo / "infra"
    nested.mkdir()
    (repo / ".infralens.toml").write_text(
        f'api_url = "{API}"\nproject = "repo-project"\n'
    )
    monkeypatch.chdir(tmp_path)
    cloud_config.save(API)
    assert cloud_config.resolve(root=nested) == (API, "repo-project")
    monkeypatch.setenv("INFRALENS_PROJECT", "env")
    assert cloud_config.resolve(root=nested) == (API, "env")
    assert cloud_config.resolve(project_id="flag", root=nested) == (API, "flag")


def test_repo_cannot_leak_project_to_an_overridden_api(tmp_path):
    (tmp_path / ".infralens.toml").write_text(f'api_url = "{API}"\nproject = "repo"\n')
    assert cloud_config.resolve("https://other.example.com", root=tmp_path)[1] is None


def test_repo_search_stops_at_git_root(tmp_path):
    (tmp_path / ".infralens.toml").write_text(
        f'api_url = "{API}"\nproject = "outside"\n'
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: elsewhere")
    cloud_config.save(API)
    assert cloud_config.resolve(root=repo) == (API, None)


@pytest.mark.parametrize(
    "content", ['token = "PRIVATE"', 'project = ["bad"]', "broken toml"]
)
def test_malformed_repo_config_safe_error(tmp_path, content):
    (tmp_path / ".infralens.toml").write_text(content)
    with pytest.raises(InvalidInput) as error:
        cloud_config.resolve(root=tmp_path)
    assert "PRIVATE" not in str(error.value)
