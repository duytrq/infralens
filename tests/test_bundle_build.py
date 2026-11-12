import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def module():
    spec = importlib.util.spec_from_file_location(
        "bundle_build", ROOT / "scripts" / "bundle_trivy.py"
    )
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_wrong_archive_checksum_is_rejected_before_extraction(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    archive.write_bytes(b"untrusted archive")
    with pytest.raises(ValueError, match="checksum"):
        module().stage("linux_x86_64", tmp_path / "stage", archive=archive)
    assert not (tmp_path / "stage" / "manifest.json").exists()


def test_staged_executable_tampering_fails_build(tmp_path):
    binary = tmp_path / "trivy"
    binary.write_bytes(b"original")
    (tmp_path / "LICENSE").write_text("Apache License")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "platform": "linux_x86_64",
                "version": "0.76.0",
                "executable": "trivy",
                "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "archive_sha256": (
                    "e24b1c51293c1b15e4ba8d45bbc7891ba053f90278ec2698f3562c993e145fe7"
                ),
            }
        )
    )
    binary.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        module().validate_stage(tmp_path, "linux_x86_64")


def test_unsupported_target_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="platform"):
        module().stage("darwin_arm64", tmp_path)
