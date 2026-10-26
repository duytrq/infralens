"""Windows process trees: assign a suspended child to a Job Object before resume."""

import subprocess
import threading
import time
from pathlib import Path

import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32job
import win32pipe
import win32process
import winerror

from infralens.errors import ExecutionCancelled, ExecutionError
from infralens.process import ProcessResult


def run_windows_process(
    arguments: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str] | None,
    cancel: threading.Event | None = None,
) -> ProcessResult:
    handles = []
    readers = []
    output = [bytearray(), bytearray()]
    read_errors = []
    job = process = None
    started = False

    def own(handle):
        handles.append(handle)
        return handle

    def read_pipe(handle, destination):
        try:
            while True:
                try:
                    _, block = win32file.ReadFile(handle, 65536)
                except pywintypes.error as exc:
                    if exc.winerror in (
                        winerror.ERROR_BROKEN_PIPE,
                        winerror.ERROR_HANDLE_EOF,
                    ):
                        break
                    raise
                if not block:
                    break
                destination.extend(block)
        except pywintypes.error:
            read_errors.append(True)

    try:
        job = own(win32job.CreateJobObject(None, ""))
        limits = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation
        )
        limits["BasicLimitInformation"]["LimitFlags"] |= (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        win32job.SetInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation, limits
        )
        security = pywintypes.SECURITY_ATTRIBUTES()
        security.bInheritHandle = True
        pipes = [win32pipe.CreatePipe(security, 0) for _ in range(2)]
        for read, write in pipes:
            own(read)
            own(write)
            win32api.SetHandleInformation(read, win32con.HANDLE_FLAG_INHERIT, 0)
        stdin = own(
            win32file.CreateFile(
                "NUL",
                win32con.GENERIC_READ,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                security,
                win32con.OPEN_EXISTING,
                0,
                None,
            )
        )
        startup = win32process.STARTUPINFO()
        startup.dwFlags = win32process.STARTF_USESTDHANDLES
        startup.hStdInput = stdin
        startup.hStdOutput, startup.hStdError = pipes[0][1], pipes[1][1]
        process, thread, _, _ = win32process.CreateProcess(
            arguments[0],
            subprocess.list2cmdline(arguments),
            None,
            None,
            True,
            win32process.CREATE_SUSPENDED
            | win32process.CREATE_NEW_PROCESS_GROUP
            | win32process.CREATE_UNICODE_ENVIRONMENT,
            env,
            str(cwd),
            startup,
        )
        own(process)
        own(thread)
        win32job.AssignProcessToJobObject(job, process)
        for _, write in pipes:
            write.Close()
        stdin.Close()
        for (read, _), destination in zip(pipes, output):
            reader = threading.Thread(
                target=read_pipe, args=(read, destination), daemon=True
            )
            reader.start()
            readers.append(reader)
        win32process.ResumeThread(thread)
        started = True
        deadline = time.monotonic() + timeout
        while win32event.WaitForSingleObject(process, 50) == win32event.WAIT_TIMEOUT:
            if cancel is not None and cancel.is_set():
                raise ExecutionCancelled("Execution cancelled.")
            if time.monotonic() >= deadline:
                raise ExecutionError(
                    f"External tool timed out after {timeout:g} seconds."
                )
        returncode = win32process.GetExitCodeProcess(process)
    except pywintypes.error:
        raise ExecutionError(
            "External tool could not start or complete. "
            "Check installation and permissions."
        ) from None
    finally:
        if process is not None:
            # Also handles assignment failure while the child is still suspended.
            if started:
                win32job.TerminateJobObject(job, 1)
            else:
                win32api.TerminateProcess(process, 1)
            win32event.WaitForSingleObject(process, 5000)
        if job is not None:
            job.Close()
        for reader in readers:
            reader.join(timeout=5)
        for handle in reversed(handles):
            if handle:
                handle.Close()
    if read_errors or any(reader.is_alive() for reader in readers):
        raise ExecutionError("External tool output could not be read completely.")
    try:
        stdout = output[0].decode("utf-8")
    except UnicodeDecodeError:
        raise ExecutionError("External tool returned invalid UTF-8 output.") from None
    # Windows console programs commonly emit CRLF; match POSIX report behavior.
    return ProcessResult(
        returncode,
        stdout.replace("\r\n", "\n"),
        output[1].decode("utf-8", errors="replace").replace("\r\n", "\n"),
    )
