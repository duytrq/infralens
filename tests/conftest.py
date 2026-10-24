import io
import os
import sys
import zipfile
from importlib.resources import files
from pathlib import Path

import pytest


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "terraform project"
    path.mkdir()
    (path / "main.tf").write_text('variable "secret" {}\n')
    return path


@pytest.fixture
def symlink():
    def create(link, target):
        try:
            link.symlink_to(target)
        except OSError as exc:
            if os.name == "nt" and exc.winerror == 1314:
                if os.environ.get("INFRALENS_REQUIRE_SYMLINKS") == "1":
                    pytest.fail("CI requires symlink privilege; WinError 1314")
                pytest.skip("Windows token has no symlink privilege (WinError 1314)")
            raise

    return create


@pytest.fixture
def fake_trivy(tmp_path, monkeypatch):
    """A real executable boundary; scan policy and reporting run unmocked."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    source = (Path(__file__).parent / "fake_trivy.py").read_text(encoding="utf-8")
    script = bin_dir / ("trivy.exe" if os.name == "nt" else "trivy")
    if os.name == "nt":
        # A real Windows executable boundary, like an installed console script.
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("__main__.py", source)
        launcher = files("distlib").joinpath("w64.exe").read_bytes()
        script.write_bytes(
            launcher + f'#!"{sys.executable}"\n'.encode() + payload.getvalue()
        )
    else:
        script.write_text(f"#!{sys.executable}\n" + source, encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    log = tmp_path / "engine-calls.jsonl"
    monkeypatch.setenv("FAKE_TRIVY_LOG", str(log))
    return log


@pytest.fixture
def fake_terraform(tmp_path, monkeypatch):
    """Exercise Terraform's real process boundary without AWS or provider access."""
    bin_dir = tmp_path / "terraform-bin"
    bin_dir.mkdir()
    source = (Path(__file__).parent / "fake_terraform.py").read_text(encoding="utf-8")
    script = bin_dir / ("terraform.exe" if os.name == "nt" else "terraform")
    if os.name == "nt":
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("__main__.py", source)
        launcher = files("distlib").joinpath("w64.exe").read_bytes()
        script.write_bytes(
            launcher + f'#!"{sys.executable}"\n'.encode() + payload.getvalue()
        )
    else:
        script.write_text(f"#!{sys.executable}\n" + source, encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    log = tmp_path / "terraform-calls.jsonl"
    monkeypatch.setenv("FAKE_TERRAFORM_LOG", str(log))
    return log


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration", action="store_true", help="Run real Trivy tests"
    )
    parser.addoption(
        "--run-network", action="store_true", help="Run remote module tests"
    )
    parser.addoption("--run-docker", action="store_true", help="Run Docker image tests")
    parser.addoption(
        "--run-terraform", action="store_true", help="Run real Terraform drift tests"
    )


def pytest_collection_modifyitems(config, items):
    # External-tool suites are explicitly selected, not silently skipped on errors.
    selected, deselected = [], []
    for item in items:
        enabled = all(
            config.getoption(option) or item.get_closest_marker(marker) is None
            for marker, option in (
                ("integration", "--run-integration"),
                ("network", "--run-network"),
                ("docker", "--run-docker"),
                ("terraform", "--run-terraform"),
            )
        )
        (selected if enabled else deselected).append(item)
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
