import os
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
