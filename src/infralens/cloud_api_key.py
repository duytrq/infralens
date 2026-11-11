"""Private, per-origin API-key storage and interactive login."""

import hashlib
import os
import re
import stat
import tempfile
import time
from contextlib import contextmanager

import typer

from infralens import cloud_auth, cloud_config
from infralens.errors import ExecutionError, InvalidInput

PATTERN = re.compile(r"il_key_[a-f0-9]{32}_[A-Za-z0-9_-]{43}")


def validate(key):
    if not isinstance(key, str) or not PATTERN.fullmatch(key):
        raise ExecutionError("Invalid API key format.")
    return key


def protect(path, *, directory=False, writable=True):
    if path.is_symlink():
        raise ExecutionError("Credential storage must not be a symbolic link.")
    if os.name == "nt":
        import ntsecuritycon
        import win32api
        import win32con
        import win32security

        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
        try:
            sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        finally:
            token.Close()
        if not writable:
            descriptor = win32security.GetNamedSecurityInfo(
                str(path),
                win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION,
            )
            acl = descriptor.GetSecurityDescriptorDacl()
            if acl is None:
                raise ExecutionError("Credential storage permissions are unsafe.")
            for index in range(acl.GetAceCount()):
                ace = acl.GetAce(index)
                if ace[0][0] != win32security.ACCESS_ALLOWED_ACE_TYPE or ace[2] != sid:
                    raise ExecutionError("Credential storage permissions are unsafe.")
            return
        acl = win32security.ACL()
        acl.AddAccessAllowedAce(
            win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, sid
        )
        win32security.SetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
    else:
        mode = path.lstat()
        if mode.st_uid != os.getuid() or not (
            stat.S_ISDIR(mode.st_mode) if directory else stat.S_ISREG(mode.st_mode)
        ):
            raise ExecutionError("Credential storage is not owned by the current user.")
        if directory:
            if writable:
                path.chmod(0o700)
            elif mode.st_mode & 0o077:
                raise ExecutionError(
                    "Credential directory permissions are unsafe; use chmod 700."
                )
        elif mode.st_mode & 0o077:
            raise ExecutionError(
                "Credential file permissions are unsafe; use chmod 600."
            )


def path(api):
    digest = hashlib.sha256(cloud_auth.origin(api).encode()).hexdigest()
    return cloud_config.config_path().parent / "sessions" / (digest + ".apikey")


@contextmanager
def locked(api):
    root = path(api).parent
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    protect(root, directory=True)
    lock = path(api).with_suffix(".lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        protect(lock)
        with os.fdopen(fd, "r+b", closefd=False) as stream:
            if os.name == "nt":
                import msvcrt

                if os.fstat(fd).st_size == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
            else:
                import fcntl

            deadline = time.monotonic() + 10
            while True:
                try:
                    if os.name == "nt":
                        stream.seek(0)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ExecutionError(
                            "Another cloud command is updating credentials; try later."
                        ) from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def read(api):
    file = path(api)
    if file.parent.is_symlink():
        raise ExecutionError("Credential directory must not be a symbolic link.")
    if not file.exists() and not file.is_symlink():
        return None
    try:
        protect(file.parent, directory=True, writable=False)
        protect(file, writable=False)
        with file.open("r", encoding="utf-8") as stream:
            return validate(stream.read(256))
    except FileNotFoundError:
        # Writes replace whole files atomically; logout may remove one during a read.
        return None
    except UnicodeError:
        raise ExecutionError(
            "Saved API key is invalid. Run 'infralens cloud login'."
        ) from None


def save(api, key):
    validate(key)
    with locked(api):
        file = path(api)
        if file.is_symlink():
            raise ExecutionError("API key storage must not be a symbolic link.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=file.parent,
                delete=False,
                prefix=".infralens-",
                suffix=".tmp",
            ) as stream:
                temporary = type(file)(stream.name)
                protect(temporary)
                stream.write(key)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, file)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def clear(api):
    file = path(api)
    legacy = file.with_suffix(".json")
    if not file.parent.exists() and not file.parent.is_symlink():
        return
    protect(file.parent, directory=True, writable=False)
    if not any(item.exists() or item.is_symlink() for item in (file, legacy)):
        return
    with locked(api):
        for credential in (file, legacy):
            if credential.is_symlink():
                raise ExecutionError("Credential storage must not be a symbolic link.")
            credential.unlink(missing_ok=True)


def selected(api):
    key = os.environ.get("INFRALENS_API_KEY")
    return validate(key) if key is not None else read(api)


def route(token, path):
    if not path.startswith("/v1/") or path.startswith("/v1/cli/"):
        raise ExecutionError("Invalid cloud API route.")
    return "/v1/cli/" + path.removeprefix("/v1/")


def login(api):
    if not cloud_auth.interactive_input():
        raise InvalidInput(
            "Login requires an interactive terminal; set INFRALENS_API_KEY in CI."
        )
    typer.echo("Create an API key in the dashboard, then paste it here.")
    key = validate(typer.prompt("API key", hide_input=True))
    cloud_auth.http(
        "GET",
        cloud_auth.origin(api) + "/v1/cli/projects?limit=1",
        headers={"Authorization": f"Bearer {key}"},
    )
    save(api, key)
    typer.echo("Signed in. API key verified and saved locally.")
    if os.environ.get("INFRALENS_API_KEY") is not None:
        typer.echo("INFRALENS_API_KEY overrides the saved key until unset.")
    return key
