import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from infralens_backend import validation


@pytest.fixture
def smoke_tool():
    path = Path(__file__).resolve().parents[1] / "scripts/smoke.py"
    spec = importlib.util.spec_from_file_location("backend_smoke_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_requires_api_key(smoke_tool, monkeypatch):
    monkeypatch.delenv("INFRALENS_API_KEY", raising=False)
    with pytest.raises(ValueError, match="INFRALENS_API_KEY"):
        smoke_tool.api_key()
    key = "il_key_" + "a" * 32 + "_" + "b" * 43
    monkeypatch.setenv("INFRALENS_API_KEY", key)
    assert smoke_tool.api_key() == key
    monkeypatch.setenv("INFRALENS_API_KEY", "invalid-secret")
    with pytest.raises(ValueError) as error:
        smoke_tool.api_key()
    assert "invalid-secret" not in str(error.value)


def test_smoke_metadata_counts_findings_and_preserves_report_digest(smoke_tool):
    report = json.dumps(
        {
            "SchemaVersion": 2,
            "Trivy": {"Version": "0.76.0"},
            "Results": [
                {
                    "Misconfigurations": [
                        {"Severity": "HIGH", "Status": "FAIL"},
                        {"Severity": "LOW", "Status": "EXCEPTION"},
                    ]
                }
            ],
        }
    ).encode()
    payload = smoke_tool.metadata(report, "smoke")
    validation.scan(payload, 50 * 1024 * 1024)
    assert payload["result"]["findings"]["total"] == 1
    assert payload["result"]["findings"]["by_severity"]["HIGH"] == 1
    assert payload["artifact"]["sha256"] == hashlib.sha256(report).hexdigest()
