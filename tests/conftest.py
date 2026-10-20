import sys
from pathlib import Path

import pytest


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "terraform project"
    path.mkdir()
    (path / "main.tf").write_text('variable "secret" {}\n')
    return path


@pytest.fixture
def fake_trivy(tmp_path, monkeypatch):
    """A real executable boundary; scan policy and reporting run unmocked."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "trivy"
    script.write_text(
        f"#!{sys.executable}\n" + (Path(__file__).parent / "fake_trivy.py").read_text()
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    log = tmp_path / "engine-calls.jsonl"
    monkeypatch.setenv("FAKE_TRIVY_LOG", str(log))
    return log


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration", action="store_true", help="Run real Trivy tests"
    )
    parser.addoption(
        "--run-network", action="store_true", help="Run remote module tests"
    )
    parser.addoption("--run-docker", action="store_true", help="Run Docker image tests")


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
            )
        )
        (selected if enabled else deselected).append(item)
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
