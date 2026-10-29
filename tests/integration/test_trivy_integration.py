import json
import os
import re
import shutil
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from infralens.cli import app

pytestmark = pytest.mark.integration
runner = CliRunner()
FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture(autouse=True)
def actual_engine(monkeypatch, tmp_path):
    executable = os.environ.get("INFRALENS_TEST_TRIVY") or shutil.which("trivy")
    assert executable and Path(executable).is_file(), (
        "Install Trivy 0.76.x or set INFRALENS_TEST_TRIVY."
    )
    monkeypatch.setenv(
        "PATH", str(Path(executable).parent) + os.pathsep + os.environ["PATH"]
    )
    # Some cases scan tmp_path itself; keep the test's cache outside its inputs.
    cache = os.environ.get(
        "TRIVY_CACHE_DIR", str(tmp_path.parent / (tmp_path.name + "-trivy-cache"))
    )
    monkeypatch.setenv("TRIVY_CACHE_DIR", cache)


@pytest.mark.parametrize("format", ["json", "sarif"])
def test_real_export_matches_table_and_does_not_modify_inputs(tmp_path, format):
    root = tmp_path / "Terraform project"
    shutil.copytree(FIXTURES / "unsafe", root)
    source = root / "main.tf"
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    output = tmp_path / "reports" / f"security.{format}"
    result = runner.invoke(
        app,
        [
            "scan",
            str(root),
            "--format",
            format,
            "--output",
            str(output),
            "--fail-on",
            "HIGH",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "AWS-0107" in result.stdout
    assert "main.tf:7" in result.stdout
    assert re.search(r">\s+7\s+\|\s+cidr_blocks", result.stdout)
    assert "Security scan (Trivy" not in result.stdout
    data = json.loads(output.read_text())
    table_rules = set(
        re.findall(
            r"^\[(?:CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN)\] ([^\s]+)",
            result.stdout,
            re.MULTILINE,
        )
    )
    if format == "sarif":
        schema = json.loads((FIXTURES / "sarif-schema-2.1.0.json").read_text())
        jsonschema.Draft7Validator(schema).validate(data)
        exported_rules = {
            f["ruleId"] for run in data["runs"] for f in run.get("results", [])
        }
        assert any(
            f["ruleId"] == "AWS-0107"
            for run in data["runs"]
            for f in run.get("results", [])
        )
    else:
        exported_rules = {
            f["ID"] for r in data["Results"] for f in r.get("Misconfigurations", [])
        }
        assert any(
            f["ID"] == "AWS-0107"
            for r in data["Results"]
            for f in r.get("Misconfigurations", [])
        )
    assert table_rules == exported_rules
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert sorted(p.name for p in root.iterdir()) == ["main.tf"]


def test_real_filter_does_not_weaken_fail_on(tmp_path):
    result = runner.invoke(
        app,
        [
            "scan",
            str(FIXTURES / "unsafe"),
            "--format",
            "json",
            "--severity",
            "LOW",
            "--fail-on",
            "HIGH",
        ],
    )
    assert result.exit_code == 1, result.output
    report = json.loads(result.stdout)
    assert {
        f["Severity"] for r in report["Results"] for f in r.get("Misconfigurations", [])
    } == {"LOW"}


def test_real_upload_json_and_manifest_keep_findings_hidden_by_filter(
    tmp_path, monkeypatch
):
    from infralens import cloud

    uploads = []
    monkeypatch.setattr(cloud, "upload_files", lambda *args: uploads.append(args))
    output = tmp_path / "security.json"
    response = runner.invoke(
        app,
        [
            "scan",
            str(FIXTURES / "unsafe"),
            "--format",
            "json",
            "--output",
            str(output),
            "--severity",
            "LOW",
            "--fail-on",
            "HIGH",
            "--upload",
            "--project",
            "demo",
            "--api-url",
            "https://api.example.com",
        ],
    )
    assert response.exit_code == 1, response.output
    report = json.loads(output.read_bytes())
    metadata = json.loads(Path(str(output) + ".upload.json").read_bytes())["manifest"]
    counts = {level: 0 for level in ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL")}
    for result in report["Results"]:
        for finding in result.get("Misconfigurations", []):
            if finding.get("Status", "FAIL") == "FAIL":
                counts[finding["Severity"]] += 1
    assert counts["HIGH"] and counts["LOW"]
    assert metadata["result"]["findings"]["by_severity"] == counts
    assert metadata["result"]["threshold_status"] == "failed"
    assert metadata["tool"]["engine_version"].startswith("0.76.")
    assert uploads
    assert "AWS-0107" not in response.stdout


def test_real_clean_scan():
    result = runner.invoke(app, ["scan", str(FIXTURES / "clean")])
    assert result.exit_code == 0, result.output
    assert "Findings: 0" in result.stdout


def test_real_invalid_terraform_is_not_reported_as_clean(tmp_path):
    (tmp_path / "main.tf").write_text('resource "aws_s3_bucket" "bad" {\n broken = [\n')
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 3, result.output
    assert not result.stdout
    assert "completely analyze" in result.stderr


def test_real_nested_local_module(tmp_path):
    shutil.copytree(FIXTURES / "unsafe", tmp_path / "modules" / "security")
    (tmp_path / "main.tf").write_text(
        'module "security" {\n source = "./modules/security"\n}\n'
    )
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "AWS-0107" in result.stdout
    assert "main.tf:7" in result.stdout


def test_real_native_tf_json(tmp_path):
    payload = {
        "resource": {
            "aws_security_group_rule": {
                "public": {
                    "type": "ingress",
                    "security_group_id": "sg-test",
                    "from_port": 22,
                    "to_port": 22,
                    "protocol": "tcp",
                    "cidr_blocks": ["0.0.0.0/0"],
                }
            }
        }
    }
    (tmp_path / "main.tf.json").write_text(json.dumps(payload))
    result = runner.invoke(app, ["scan", str(tmp_path), "--fail-on", "HIGH"])
    assert result.exit_code == 1, result.output
    assert "AWS-0107" in result.stdout
    assert "main.tf.json" in result.stdout


def test_real_root_ignore_and_hostile_config(tmp_path, monkeypatch):
    shutil.copy(FIXTURES / "unsafe" / "main.tf", tmp_path / "main.tf")
    (tmp_path / ".trivyignore").write_text("AWS-0107\n")
    (tmp_path / "trivy.yaml").write_text("output: main.tf\nseverity: [CRITICAL]\n")
    monkeypatch.setenv("TRIVY_OUTPUT", str(tmp_path / "main.tf"))
    before = (tmp_path / "main.tf").read_bytes()
    result = runner.invoke(app, ["scan", str(tmp_path), "--fail-on", "HIGH"])
    assert result.exit_code == 0, result.output
    assert "AWS-0107" not in result.stdout
    assert "AWS-0099" in result.stdout
    assert (tmp_path / "main.tf").read_bytes() == before


@pytest.mark.network
def test_real_remote_module(tmp_path):
    (tmp_path / "main.tf").write_text("""module "security" {
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-security-group.git?ref=v5.3.0"
  name = "test"
  vpc_id = "vpc-test"
  ingress_cidr_blocks = ["0.0.0.0/0"]
  ingress_rules = ["ssh-tcp"]
}
""")
    result = runner.invoke(app, ["scan", str(tmp_path), "--timeout", "180"])
    assert result.exit_code == 0, result.output
    assert "AWS-0107" in result.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["main.tf"]
