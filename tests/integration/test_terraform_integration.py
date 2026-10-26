"""Real Terraform, isolated local resources only. Never creates cloud resources."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens.cli import app
from infralens.options import DriftOptions
from infralens.terraform import terraform_environment

pytestmark = pytest.mark.terraform
runner = CliRunner()


def setup_terraform(project, monkeypatch):
    executable = os.environ.get("INFRALENS_TEST_TERRAFORM") or shutil.which("terraform")
    assert executable, "Install Terraform or set INFRALENS_TEST_TERRAFORM"
    binary = Path(executable).resolve()
    monkeypatch.setenv("PATH", str(binary.parent) + os.pathsep + os.environ["PATH"])
    options = DriftOptions(project, (), "json", None, None, None, False, None, False)
    env = terraform_environment(options)

    def execute(*args):
        result = subprocess.run(
            [str(binary), *args],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    return execute


def report(project, expected=0):
    result = runner.invoke(
        app, ["drift", str(project), "--format", "json", "--fail-on-drift"]
    )
    assert result.exit_code == expected, result.output
    return json.loads(result.stdout)


def test_real_plan_ignores_unapplied_resource_creation(tmp_path, monkeypatch):
    (tmp_path / "main.tf").write_text(
        'variable "infralensMixedCaseFixture" { type = string }\n'
        'resource "terraform_data" "demo" { input = var.infralensMixedCaseFixture }\n'
    )
    name = "TF_VAR_infralensMixedCaseFixture"
    if os.name == "nt":
        # Mimic the original mixed-case environment block inherited from PowerShell.
        os.putenv(name, "synthetic Unicode \U0001f30f value")
    else:
        monkeypatch.setenv(name, "synthetic Unicode \U0001f30f value")
    try:
        execute = setup_terraform(tmp_path, monkeypatch)
        execute("init", "-input=false", "-no-color")
        assert report(tmp_path)["has_drift"] is False
        assert not (tmp_path / "terraform.tfstate").exists()
    finally:
        if os.name == "nt":
            os.unsetenv(name)


@pytest.mark.network
def test_real_external_edits_deletion_and_configuration_only_changes(
    tmp_path, monkeypatch
):
    configuration = """
terraform {
  required_providers {
    local = { source = "hashicorp/local", version = "= 2.5.3" }
  }
}
resource "local_file" "demo" {
  filename = "${path.module}/managed.txt"
  content  = "original content"
}
"""
    source = tmp_path / "main.tf"
    source.write_text(configuration)
    execute = setup_terraform(tmp_path, monkeypatch)
    execute("init", "-input=false", "-no-color")
    # Apply only this isolated local_file fixture to establish saved state.
    execute("apply", "-auto-approve", "-input=false", "-no-color")
    state = tmp_path / "terraform.tfstate"
    baseline = (state.read_bytes(), state.stat().st_mtime_ns)
    managed = tmp_path / "managed.txt"
    assert report(tmp_path)["has_drift"] is False

    # Removing a declaration without apply also leaves real infrastructure intact.
    source.write_text(configuration.split('resource "local_file"')[0])
    assert report(tmp_path)["has_drift"] is False
    source.write_text(configuration)

    source.write_text(configuration.replace("original content", "pending code edit"))
    assert report(tmp_path)["has_drift"] is False
    assert managed.read_text() == "original content"

    managed.write_text("external change")
    drift = report(tmp_path, expected=1)
    assert drift["has_drift"] is True
    assert drift["resources"][0]["address"] == "local_file.demo"
    # local_file identifies content by hash and reports an edited file as missing.
    assert drift["resources"][0]["actions"] == ["delete"]
    source_location = drift["resources"][0]["source"]
    assert source_location["status"] == "located"
    assert source_location["locations"][0]["file"] == str(source.resolve())
    assert source_location["locations"][0]["start_line"] == 7
    assert managed.read_text() == "external change"

    source.write_text(configuration)
    managed.unlink()
    assert report(tmp_path, expected=1)["has_drift"] is True
    assert not managed.exists()
    assert (state.read_bytes(), state.stat().st_mtime_ns) == baseline
    assert not (tmp_path / "terraform.tfstate.backup").exists()


@pytest.mark.network
def test_real_nested_modules_and_escaped_instance_keys(tmp_path, monkeypatch):
    (tmp_path / "main.tf").write_text("""terraform {
  required_providers {
    local = { source = "hashicorp/local", version = "= 2.5.3" }
  }
}
module "app" {
  source = "./modules/app"
  for_each = { "prod.eu]" = true }
}
""")
    app_path = tmp_path / "modules" / "app"
    leaf = app_path / "leaf"
    leaf.mkdir(parents=True)
    (app_path / "main.tf").write_text("""module "child" {
  source = "./leaf"
  count = 1
}
""")
    source = leaf / "files.tf"
    source.write_text("""resource "local_file" "demo" {
  for_each = { "key.with]\\\"quote" = true }
  filename = "${path.module}/managed.txt"
  content = "original"
}
""")
    execute = setup_terraform(tmp_path, monkeypatch)
    execute("init", "-input=false", "-no-color")
    execute("apply", "-auto-approve", "-input=false", "-no-color")
    state = tmp_path / "terraform.tfstate"
    fingerprint = state.read_bytes(), state.stat().st_mtime_ns
    (leaf / "managed.txt").unlink()
    observed = report(tmp_path, expected=1)["resources"][0]
    assert (
        observed["address"]
        == 'module.app["prod.eu]"].module.child[0].local_file.demo["key.with]\\"quote"]'
    )
    assert observed["source"]["status"] == "located"
    assert observed["source"]["locations"][0] == {
        "file": str(source.resolve()),
        "start_line": 1,
        "end_line": 5,
        "syntax": "hcl",
    }
    assert fingerprint == (state.read_bytes(), state.stat().st_mtime_ns)


@pytest.mark.network
def test_real_json_array_configuration_source_locations(tmp_path, monkeypatch):
    configuration = {
        "terraform": {
            "required_providers": {
                "local": {"source": "hashicorp/local", "version": "= 2.5.3"}
            }
        },
        "resource": [
            {
                "local_file": [
                    {
                        "demo": {
                            "filename": "${path.module}/managed.txt",
                            "content": "original",
                        }
                    }
                ]
            }
        ],
    }
    source = tmp_path / "main.tf.json"
    source.write_text(json.dumps(configuration, indent=2))
    execute = setup_terraform(tmp_path, monkeypatch)
    execute("init", "-input=false", "-no-color")
    execute("apply", "-auto-approve", "-input=false", "-no-color")
    (tmp_path / "managed.txt").unlink()
    observed = report(tmp_path, expected=1)["resources"][0]
    assert observed["address"] == "local_file.demo"
    assert observed["source"]["status"] == "located"
    location = observed["source"]["locations"][0]
    assert location["syntax"] == "json"
    assert location["file"] == str(source.resolve())
    assert (
        source.read_text().splitlines()[location["start_line"] - 1].strip()
        == '"demo": {'
    )
