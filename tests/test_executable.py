import hashlib
import json
from pathlib import Path

import pytest

from infralens.errors import ExecutionError
from infralens.executable import discover_trivy


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "installed package" / "_vendor" / "trivy"
    root.mkdir(parents=True)
    binary = root / "trivy"
    binary.write_bytes(b"bundled executable")
    binary.chmod(0o755)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "version": "0.76.0",
                "platform": "linux_x86_64",
                "executable": "trivy",
                "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            }
        )
    )
    (root.parent.parent / "_bundle.json").write_bytes(
        (root / "manifest.json").read_bytes()
    )
    return root


def test_bundle_has_priority_over_path(bundle, monkeypatch):
    monkeypatch.setattr("infralens.executable.current_platform", lambda: "linux_x86_64")
    monkeypatch.setattr(
        "infralens.executable.shutil.which", lambda _: pytest.fail("PATH searched")
    )
    found = discover_trivy(bundle)
    assert found.path == (bundle / "trivy").resolve()
    assert found.source == "bundle"
    assert found.expected_version == "0.76.0"


@pytest.mark.parametrize(
    "damage",
    [
        "missing binary",
        "tampered binary",
        "missing manifest",
        "missing marker",
        "invalid manifest",
        "traversal",
        "platform",
    ],
)
def test_damaged_bundle_never_falls_back(bundle, monkeypatch, damage):
    monkeypatch.setattr("infralens.executable.current_platform", lambda: "linux_x86_64")
    monkeypatch.setattr(
        "infralens.executable.shutil.which", lambda _: pytest.fail("PATH fallback")
    )
    manifest = bundle / "manifest.json"
    if damage == "missing binary":
        (bundle / "trivy").unlink()
    elif damage == "tampered binary":
        (bundle / "trivy").write_bytes(b"replacement that claims Version: 0.76.0")
    elif damage == "missing manifest":
        manifest.unlink()
    elif damage == "missing marker":
        (bundle.parent.parent / "_bundle.json").unlink()
    elif damage == "invalid manifest":
        manifest.write_text("broken")
    else:
        data = json.loads(manifest.read_text())
        data["executable" if damage == "traversal" else "platform"] = (
            "../../trivy" if damage == "traversal" else "win_amd64"
        )
        manifest.write_text(json.dumps(data))
    with pytest.raises(ExecutionError, match="[Rr]einstall"):
        discover_trivy(bundle)


def test_source_install_resolves_relative_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("infralens.executable.shutil.which", lambda _: "bin/trivy")
    found = discover_trivy(tmp_path / "no bundle")
    assert found.path == Path.cwd() / "bin" / "trivy"
    assert found.source == "PATH"
    assert found.expected_version is None


def test_deleted_bundle_directory_is_not_a_source_install(bundle, monkeypatch):
    import shutil

    marker = bundle.parent.parent / "_bundle.json"
    marker.write_bytes((bundle / "manifest.json").read_bytes())
    shutil.rmtree(bundle)
    monkeypatch.setattr(
        "infralens.executable.shutil.which", lambda _: pytest.fail("PATH fallback")
    )
    with pytest.raises(ExecutionError, match="[Rr]einstall"):
        discover_trivy(bundle)
