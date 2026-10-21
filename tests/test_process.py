import os
import signal
import subprocess
import sys
import time

import pytest

from infralens.errors import ExecutionError
from infralens.process import run_process


def test_captures_streams_and_preserves_arguments(tmp_path):
    result = run_process(
        [
            sys.executable,
            "-c",
            "import sys; print(sys.argv[1]); print('warn', file=sys.stderr)",
            "a path; $(not-a-command)",
        ],
        cwd=tmp_path,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout == "a path; $(not-a-command)\n"
    assert result.stderr == "warn\n"


def test_nonzero_is_returned_without_exposing_payload(tmp_path):
    result = run_process(
        [
            sys.executable,
            "-c",
            "import sys; print('payload', file=sys.stderr); sys.exit(7)",
        ],
        cwd=tmp_path,
        timeout=5,
    )
    assert result.returncode == 7
    assert result.stderr == "payload\n"


def test_timeout_terminates_descendants(tmp_path):
    marker = tmp_path / "survived"
    child = (
        "import time; from pathlib import Path; time.sleep(1); "
        f"Path({str(marker)!r}).touch()"
    )
    script = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
    )
    with pytest.raises(ExecutionError, match="timed out"):
        run_process([sys.executable, "-c", script], cwd=tmp_path, timeout=0.2)
    time.sleep(1.1)
    assert not marker.exists()


def test_missing_executable_is_controlled(tmp_path):
    with pytest.raises(ExecutionError, match="could not start"):
        run_process([str(tmp_path / "missing")], cwd=tmp_path, timeout=5)


def test_runner_passes_explicit_environment(tmp_path):
    result = run_process(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('SCANNER_TEST','absent'))",
        ],
        cwd=tmp_path,
        timeout=5,
        env={**os.environ, "SCANNER_TEST": "present"},
    )
    assert result.stdout == "present\n"


def test_interrupt_terminates_descendants(tmp_path):
    marker, ready = tmp_path / "survived", tmp_path / "ready"
    child = (
        "import time; from pathlib import Path; time.sleep(1.5); "
        f"Path({str(marker)!r}).touch()"
    )
    parent = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"Path({str(ready)!r}).touch(); time.sleep(30)"
    )
    controller = f"""
import signal,sys
from pathlib import Path
from infralens.process import run_process
if hasattr(signal, "SIGBREAK"):
    signal.signal(signal.SIGBREAK, signal.default_int_handler)
try:
    run_process(
        [sys.executable, "-c", {parent!r}],
        cwd=Path({str(tmp_path)!r}), timeout=30,
    )
except KeyboardInterrupt:
    sys.exit(130)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", controller],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.02)
        process.send_signal(
            signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT
        )
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 130, (stdout, stderr)
        time.sleep(1.6)
        assert not marker.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
