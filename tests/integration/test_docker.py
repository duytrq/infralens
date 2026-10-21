"""Docker smoke tests use isolated volumes, including with remote daemons."""

import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import jsonschema
import pytest

pytestmark = pytest.mark.docker
FIXTURES = Path(__file__).parents[1] / "fixtures"
IMAGE = os.environ.get("INFRALENS_TEST_IMAGE", "infralens:local")


def docker(*args, input=None, check=True, timeout=90):
    command = os.environ.get("INFRALENS_TEST_DOCKER", "docker")
    result = subprocess.run(
        [command, *args], input=input, capture_output=True, timeout=timeout
    )
    if check:
        assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result


@pytest.fixture
def mounts():
    volumes = [f"infralens-test-{uuid.uuid4().hex}" for _ in range(3)]
    created = []
    try:
        for volume in volumes:
            docker("volume", "create", volume)
            created.append(volume)
        rw = [
            arg
            for volume, target in zip(
                volumes, ("/workspace", "/reports", "/cache"), strict=True
            )
            for arg in (
                "--mount",
                f"type=volume,source={volume},target={target},volume-nocopy",
            )
        ]
        setup = """import sys
from pathlib import Path
Path('/workspace/main.tf').write_text(sys.stdin.read())
Path('/reports').chmod(0o777)
Path('/cache').chmod(0o777)
"""
        docker(
            "run",
            "--rm",
            "-i",
            "--user",
            "0",
            *rw,
            "--entrypoint",
            "python",
            IMAGE,
            "-c",
            setup,
            input=(FIXTURES / "unsafe" / "main.tf").read_bytes(),
        )
        readonly = rw.copy()
        readonly[1] += ",readonly"
        yield readonly, rw
    finally:
        for volume in created:
            docker("volume", "rm", volume)


def inspect_files(mounts):
    code = """import hashlib,json
from pathlib import Path
report = Path('/reports/security.sarif')
print(json.dumps({'source':hashlib.sha256(Path('/workspace/main.tf').read_bytes()).hexdigest(),
'uid':report.stat().st_uid, 'mode':report.stat().st_mode & 0o777,
'report':json.loads(report.read_text()),
'cache':list(str(p) for p in Path('/cache').iterdir())}))
"""
    result = docker(
        "run",
        "--rm",
        "--user",
        "1000:1000",
        *mounts,
        "--entrypoint",
        "python",
        IMAGE,
        "-c",
        code,
    )
    return json.loads(result.stdout)


def test_docker_bundles_trivy_and_defaults_to_nonroot():
    result = docker("image", "inspect", "--format", "{{.Config.User}}", IMAGE)
    assert result.stdout.decode().strip() == "10001:10001"
    result = docker("run", "--rm", "--entrypoint", "trivy", IMAGE, "--version")
    assert "Version: 0.76.0" in result.stdout.decode()
    result = docker("run", "--rm", IMAGE, "--help")
    assert "scan" in result.stdout.decode()


def test_docker_readonly_scan_export_ownership_and_cache(mounts):
    readonly, _ = mounts
    denied = docker(
        "run",
        "--rm",
        "--user",
        "0",
        *readonly,
        "--entrypoint",
        "python",
        IMAGE,
        "-c",
        "from pathlib import Path; Path('/workspace/main.tf').write_text('changed')",
        check=False,
    )
    assert denied.returncode != 0
    assert b"Read-only file system" in denied.stderr
    result = docker(
        "run",
        "--rm",
        "--init",
        "--user",
        "1000:1000",
        "-e",
        "HOME=/tmp",
        *readonly,
        IMAGE,
        "scan",
        "/workspace",
        "--format",
        "sarif",
        "--output",
        "/reports/security.sarif",
        "--fail-on",
        "HIGH",
        check=False,
    )
    assert result.returncode == 1, result.stderr.decode()
    assert b"AWS-0107" in result.stdout
    files = inspect_files(readonly)
    assert files["uid"] == 1000
    assert files["mode"] == 0o600
    schema = json.loads((FIXTURES / "sarif-schema-2.1.0.json").read_text())
    jsonschema.Draft7Validator(schema).validate(files["report"])

    assert (
        files["source"]
        == hashlib.sha256((FIXTURES / "unsafe" / "main.tf").read_bytes()).hexdigest()
    )
    assert files["cache"], "Trivy must use the persisted cache mount"


def test_docker_sigint_returns_130(mounts):
    readonly, rw = mounts
    fake = (
        "#!/usr/local/bin/python\n"
        + (Path(__file__).parents[1] / "fake_trivy.py").read_text()
    )
    setup = """import sys
from pathlib import Path
Path('/workspace/bin').mkdir()
p=Path('/workspace/bin/trivy')
p.write_text(sys.stdin.read())
p.chmod(0o755)
"""
    docker(
        "run",
        "--rm",
        "-i",
        "--user",
        "0",
        *rw,
        "--entrypoint",
        "python",
        IMAGE,
        "-c",
        setup,
        input=fake.encode(),
    )
    name = f"infralens-interrupt-{uuid.uuid4().hex}"
    try:
        docker(
            "run",
            "-d",
            "--init",
            "--name",
            name,
            *readonly,
            "-e",
            "PATH=/workspace/bin:/app/.venv/bin:/usr/local/bin:/usr/bin:/bin",
            "-e",
            "FAKE_TRIVY_LOG=/reports/calls.jsonl",
            "-e",
            "FAKE_TRIVY_MODE=timeout",
            IMAGE,
            "scan",
            "/workspace",
        )
        deadline = time.monotonic() + 15
        while True:
            log = docker("exec", name, "cat", "/reports/calls.jsonl", check=False)
            if b'"config"' in log.stdout:
                break
            assert time.monotonic() < deadline, "Scan child did not start"
            time.sleep(0.1)
        docker("kill", "--signal", "SIGINT", name)
        result = docker("wait", name, timeout=10)
        assert result.stdout.decode().strip() == "130"
        logs = docker("logs", name)
        assert b"Interrupted" in logs.stderr + logs.stdout
    finally:
        docker("rm", "--force", name)
