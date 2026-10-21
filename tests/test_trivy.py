import json
from copy import deepcopy

import pytest

from infralens.errors import ExecutionError
from infralens.process import ProcessResult
from infralens.trivy import Trivy, parse_report


@pytest.fixture
def report():
    return {
        "SchemaVersion": 2,
        "Trivy": {"Version": "0.76.0"},
        "ArtifactType": "filesystem",
        "Results": [
            {
                "Target": "nested/main.tf",
                "Class": "config",
                "Type": "terraform",
                "Misconfigurations": [
                    {
                        "ID": "AWS-0107",
                        "Severity": "HIGH",
                        "Title": "Public ingress",
                        "Message": "SSH is public",
                        "Status": "FAIL",
                        "Resolution": "Restrict ingress",
                        "References": ["https://example.org/rule"],
                        "CauseMetadata": {
                            "Resource": "aws_security_group.public",
                            "StartLine": 7,
                            "EndLine": 7,
                        },
                    }
                ],
            }
        ],
    }


def test_parse_report_keeps_optional_location_and_ignores_passes(report):
    passed = deepcopy(report["Results"][0]["Misconfigurations"][0])
    passed["Status"] = "PASS"
    report["Results"][0]["Misconfigurations"].append(passed)
    parsed = parse_report(json.dumps(report))
    (finding,) = parsed.findings
    assert (finding.rule_id, finding.severity, finding.file, finding.start_line) == (
        "AWS-0107",
        "HIGH",
        "nested/main.tf",
        7,
    )
    assert finding.resource == "aws_security_group.public"
    assert parsed.raw == report


def test_no_source_location_is_allowed(report):
    item = report["Results"][0]
    item.pop("Target")
    item["Misconfigurations"][0].pop("CauseMetadata")
    (finding,) = parse_report(json.dumps(report)).findings
    assert finding.file is None
    assert finding.start_line is None


@pytest.mark.parametrize(
    "payload",
    [
        "broken PRIVATE",
        "{}",
        "[]",
        '{"SchemaVersion":99}',
        '{"SchemaVersion":2,"Results":"wrong"}',
        '{"SchemaVersion":2,"Results":[{"Misconfigurations":{}}]}',
    ],
)
def test_invalid_report_is_safe(payload):
    with pytest.raises(ExecutionError, match="invalid|unsupported") as error:
        parse_report(payload)
    assert "PRIVATE" not in str(error.value)


def test_unknown_severity_is_rejected(report):
    report["Results"][0]["Misconfigurations"][0]["Severity"] = "SEVERE"
    with pytest.raises(ExecutionError, match="invalid"):
        parse_report(json.dumps(report))


def test_empty_native_report_can_omit_results():
    assert (
        parse_report('{"SchemaVersion":2,"Trivy":{"Version":"0.76.0"}}').findings == ()
    )


def test_adapter_cannot_inherit_filters_or_project_config(
    tmp_path, report, monkeypatch
):
    (tmp_path / ".trivyignore").write_text("AWS-0000\n")
    monkeypatch.setenv("TRIVY_SEVERITY", "LOW")
    monkeypatch.setenv("TRIVY_CONFIG", "hostile.yaml")
    monkeypatch.setenv("TRIVY_OUTPUT", "input.tf")
    monkeypatch.setenv("TRIVY_CACHE_DIR", "/tmp/test-cache")
    calls = []

    def execute(args, **kwargs):
        calls.append((args, kwargs))
        if "--version" in args:
            return ProcessResult(0, "Version: 0.76.0\n", "")
        return ProcessResult(0, json.dumps(report), "")

    monkeypatch.setattr("infralens.executable.shutil.which", lambda name: "/bin/trivy")
    monkeypatch.setattr("infralens.trivy.run_process", execute)
    engine = Trivy(tmp_path)
    result = engine.scan(300)
    assert result.findings[0].severity == "HIGH"
    args, kwargs = calls[-1]
    assert args[args.index("--misconfig-scanners") + 1] == "terraform"
    assert args[args.index("--config") + 1] == ""
    assert args[args.index("--ignorefile") + 1] == str(tmp_path / ".trivyignore")
    assert kwargs["env"]["TRIVY_CACHE_DIR"] == "/tmp/test-cache"
    assert not {"TRIVY_SEVERITY", "TRIVY_CONFIG", "TRIVY_OUTPUT"} & kwargs["env"].keys()


def test_missing_ignore_file_is_disabled(tmp_path, report, monkeypatch):
    calls = []

    def execute(args, **kwargs):
        calls.append(args)
        payload = "Version: 0.76.0" if "--version" in args else json.dumps(report)
        return ProcessResult(0, payload, "")

    monkeypatch.setattr("infralens.executable.shutil.which", lambda name: "/bin/trivy")
    monkeypatch.setattr("infralens.trivy.run_process", execute)
    Trivy(tmp_path).scan(300)
    args = calls[-1]
    assert args[args.index("--ignorefile") + 1] == ""


@pytest.mark.parametrize("version", ["0.75.0", "1.0.0", "0.76.0-dev", "not-a-version"])
def test_unsupported_binary_is_rejected(tmp_path, monkeypatch, version):
    monkeypatch.setattr("infralens.executable.shutil.which", lambda name: "/bin/trivy")
    monkeypatch.setattr(
        "infralens.trivy.run_process",
        lambda *a, **kw: ProcessResult(0, f"Version: {version}", ""),
    )
    with pytest.raises(ExecutionError, match="0.76.x"):
        Trivy(tmp_path)


def test_missing_binary_has_installation_hint(tmp_path, monkeypatch):
    monkeypatch.setattr("infralens.executable.shutil.which", lambda name: None)
    with pytest.raises(ExecutionError, match="PATH.*Docker"):
        Trivy(tmp_path)
