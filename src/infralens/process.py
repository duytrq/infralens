"""Run external tools without a shell and reap their process groups."""

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from infralens.errors import ExecutionError


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


def _terminate(process: subprocess.Popen) -> None:
    # The child starts a session: kill descendants even if the parent exits first.
    def send(sig: signal.Signals) -> None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    send(signal.SIGTERM)
    try:
        process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    finally:
        send(signal.SIGKILL)
        process.communicate()


def run_process(
    arguments: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """Capture streams; callers classify engine exits without leaking payloads."""
    if os.name == "nt":
        from infralens.windows_process import run_windows_process

        return run_windows_process(arguments, cwd=cwd, timeout=timeout, env=env)
    try:
        process = subprocess.Popen(
            arguments,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
    except OSError:
        raise ExecutionError(
            "External tool could not start. Check installation and permissions."
        ) from None
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate(process)
        raise ExecutionError(
            f"External tool timed out after {timeout:g} seconds."
        ) from None
    except BaseException:
        _terminate(process)
        raise
    try:
        decoded = stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise ExecutionError("External tool returned invalid UTF-8 output.") from None
    return ProcessResult(
        process.returncode, decoded, stderr.decode("utf-8", errors="replace")
    )
