import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens import cli
from infralens.logging import logger

runner = CliRunner()
SECRET = "PRIVATE_TERRAFORM_VALUE_123"


def test_drift_has_no_external_calls_or_file_changes(project, monkeypatch):
    command = "drift"
    (project / "main.tf").write_text(SECRET)
    variables = project / "dev.tfvars"
    variables.write_text(SECRET)
    (project / "terraform.tfstate").write_text(SECRET)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in project.iterdir()}

    def forbidden(*args, **kwargs):
        pytest.fail("Command attempted external work or read input contents")

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(os, "system", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        result = runner.invoke(
            cli.app,
            [
                "--verbose",
                command,
                str(project),
                "--output",
                str(project / "reports" / "report.json"),
                *(["--var-file", variables.name] if command == "drift" else []),
            ],
        )
    assert result.exit_code == 4
    assert result.stdout == ""
    assert SECRET not in result.output
    assert before == {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in project.iterdir()
    }


@pytest.mark.parametrize("verbose", [False, True])
@pytest.mark.parametrize("command", ["scan", "drift"])
def test_unexpected_errors_hide_payload_and_locals(
    project, monkeypatch, verbose, command
):
    def broken(options):
        credentials = SECRET
        raise RuntimeError(credentials)

    monkeypatch.setattr(cli, f"handle_{command}", broken)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SECRET)
    result = runner.invoke(
        cli.app,
        [
            *(["--verbose"] if verbose else []),
            command,
            str(project),
        ],
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    assert "Unexpected execution error" in result.stderr
    assert SECRET not in result.output
    assert "credentials" not in result.output
    assert ("in broken" in result.stderr) is verbose


@pytest.mark.parametrize("command", ["scan", "drift"])
def test_interrupt_returns_130(project, monkeypatch, command):
    def interrupt(options):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, f"handle_{command}", interrupt)
    result = runner.invoke(cli.app, [command, str(project)])
    assert result.exit_code == 130
    assert result.stdout == ""
    assert "Interrupted" in result.stderr


def test_io_error_is_safe_and_mentions_path(project, monkeypatch):
    def fail(path):
        raise OSError(5, SECRET, str(project))

    monkeypatch.setattr(Path, "iterdir", fail)
    result = runner.invoke(cli.app, ["--verbose", "drift", str(project)])
    assert result.exit_code == 3
    assert "I/O operation failed" in result.stderr
    assert str(project) in result.stderr
    assert SECRET not in result.output


def test_logging_is_not_duplicated_and_level_resets(project, fake_trivy):
    args = ["--verbose", "scan", str(project)]
    first = runner.invoke(cli.app, args)
    second = runner.invoke(cli.app, args)
    assert first.stderr == second.stderr
    assert second.stderr.count("Scan validation complete") == 1
    assert logger.level == logging.DEBUG
    normal = runner.invoke(cli.app, ["scan", str(project)])
    assert "DEBUG" not in normal.stderr
    assert logger.level == logging.WARNING


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--help"],
        ["--version"],
        ["scan", "--help"],
        ["drift", "--help"],
        ["scan"],
        ["--invalid"],
    ],
)
@pytest.mark.parametrize(
    "prefix, env",
    [
        (["--no-color"], {"FORCE_COLOR": "1", "CLICOLOR_FORCE": "1"}),
        ([], {"NO_COLOR": "1", "FORCE_COLOR": "1"}),
        ([], {}),
    ],
)
def test_plain_help_and_errors(args, prefix, env):
    result = runner.invoke(cli.app, prefix + args, env=env, color=True)
    assert "\x1b[" not in result.output
    if result.exit_code == 0:
        assert result.stdout
        assert not result.stderr
    else:
        assert result.exit_code == 2
        assert not result.stdout
        assert result.stderr


@pytest.mark.parametrize("entry", ["console", "module"])
def test_installed_entrypoints(entry, project, tmp_path, fake_trivy):
    prefix = (
        [str(Path(sys.executable).with_name("infralens"))]
        if entry == "console"
        else [sys.executable, "-m", "infralens"]
    )
    cases = [
        ([], 0, "Usage:"),
        (["--version"], 0, "infralens 0.1.0"),
        (["scan", str(project)], 0, "Security scan"),
        (["drift", str(project), "--trace"], 4, "CloudTrail trace"),
        (["drift"], 2, "Missing argument"),
    ]
    for args, code, message in cases:
        result = subprocess.run(
            prefix + args, cwd=tmp_path, capture_output=True, text=True, timeout=10
        )
        assert result.returncode == code
        assert message in (result.stdout if code == 0 else result.stderr)
        assert not (result.stderr if code == 0 else result.stdout)


def test_main_handles_unexpected_startup_error(monkeypatch, capsys):
    def broken():
        raise ValueError(SECRET)

    monkeypatch.setattr(cli, "app", broken)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert SECRET not in captured.err


def test_real_sigint_returns_130(project):
    script = """
import os
import signal
from infralens import cli
def interrupt(options):
    os.kill(os.getpid(), signal.SIGINT)
cli.handle_scan = interrupt
cli.main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, "scan", str(project)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 130
    assert "Interrupted" in result.stderr
    assert not result.stdout


def test_sigint_while_scan_child_is_running(project, fake_trivy, monkeypatch):
    monkeypatch.setenv("FAKE_TRIVY_MODE", "timeout")
    process = subprocess.Popen(
        [sys.executable, "-m", "infralens", "scan", str(project)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while not fake_trivy.exists() or '"config"' not in fake_trivy.read_text():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 130
        assert stdout == b""
        assert b"Interrupted" in stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
