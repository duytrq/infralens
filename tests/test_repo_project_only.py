import json

import pytest
from typer.testing import CliRunner

from infralens import cloud_config
from infralens.cli import app

runner = CliRunner()
API = "https://api.example.com"


def test_legacy_machine_project_is_never_reused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    file = cloud_config.config_path()
    file.parent.mkdir(parents=True)
    file.write_text(
        json.dumps({"schema_version": 1, "api_url": API, "project_id": "old-global"})
    )
    assert cloud_config.resolve() == (API, None)
    response = runner.invoke(app, ["cloud", "configure", "--api-url", API])
    assert response.exit_code == 0
    assert json.loads(file.read_text()) == {"schema_version": 2, "api_url": API}


@pytest.mark.parametrize(
    "command", [["cloud", "setup"], ["cloud", "project", "use", "demo"]]
)
def test_local_flag_removed(command):
    response = runner.invoke(app, [*command, "--local"])
    assert response.exit_code == 2 and "No such option" in response.output


def test_machine_project_does_not_authorize_an_unbound_repo(project, monkeypatch):
    file = cloud_config.config_path()
    file.parent.mkdir(parents=True)
    file.write_text(
        json.dumps({"schema_version": 1, "api_url": API, "project_id": "old-global"})
    )
    monkeypatch.setattr(
        "infralens.cli.handle_scan", lambda *a: pytest.fail("Engine started")
    )
    response = runner.invoke(app, ["scan", str(project), "--upload"])
    assert response.exit_code == 2 and "project" in response.output.lower()
