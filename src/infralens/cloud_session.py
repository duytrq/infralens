"""Per-API Cognito sessions; private files and serialized refresh/logout."""

import hashlib
import json
import math
import os
import stat
import time
from contextlib import contextmanager
from urllib.parse import urlencode, urlsplit

import typer

from infralens import cloud_auth, cloud_config
from infralens.errors import ExecutionError
from infralens.reporting import write_report


def directory():
    root = cloud_config.config_path().parent / "sessions"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink():
        raise ExecutionError("Session directory must not be a symbolic link.")
    protect(root, directory=True)
    return root


def protect(path, *, directory=False):
    if path.is_symlink():
        raise ExecutionError("Session storage must not be a symbolic link.")
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
            raise ExecutionError("Session storage is not owned by the current user.")
        if directory:
            path.chmod(0o700)
        elif mode.st_mode & 0o077:
            raise ExecutionError("Session file permissions are unsafe; use chmod 600.")


def path(api):
    digest = hashlib.sha256(cloud_auth.origin(api).encode()).hexdigest()
    return directory() / (digest + ".json")


@contextmanager
def locked(api):
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
                            "Another cloud command is updating the session; try later."
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


def valid_secret(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 16384
        and all(33 <= ord(c) <= 126 for c in value)
    )


def auth_settings(auth):
    try:
        token = urlsplit(auth["token_endpoint"])
        issuer = urlsplit(auth["issuer"])
        if (
            cloud_auth.origin("https://" + token.netloc) + "/oauth2/token"
            != auth["token_endpoint"]
            or token.scheme != "https"
            or issuer.scheme != "https"
            or not issuer.hostname
            or issuer.username
            or issuer.password
            or issuer.query
            or issuer.fragment
            or not valid_secret(auth["client_id"])
        ):
            raise ValueError
        revoke = "https://" + token.netloc + "/oauth2/revoke"
        if auth.get("revocation_endpoint", revoke) != revoke:
            raise ValueError
        return {
            "issuer": auth["issuer"],
            "client_id": auth["client_id"],
            "token_endpoint": auth["token_endpoint"],
            "revocation_endpoint": revoke,
        }
    except (KeyError, TypeError, ValueError, cloud_auth.InvalidInput):
        raise ExecutionError("Invalid Cognito session configuration.") from None


def read(api):
    file = path(api)
    if not file.exists() and not file.is_symlink():
        return None
    try:
        protect(file)
        with file.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError
        record = json.loads(raw)
        if (
            record["api_url"] != cloud_auth.origin(api)
            or record["schema_version"] != 1
            or not valid_secret(record["access_token"])
            or not valid_secret(record["refresh_token"])
            or type(record["expires_at"]) not in (int, float)
            or not math.isfinite(record["expires_at"])
        ):
            raise ValueError
        record["auth"] = auth_settings(record["auth"])
        return record
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        raise ExecutionError(
            "Saved session is invalid. Run 'infralens cloud logout' then 'cloud login'."
        ) from None


def write(api, record):
    file = path(api)
    write_report(file, json.dumps(record))
    protect(file)


def configuration(api):
    _, payload = cloud_auth.http("GET", cloud_auth.origin(api) + "/v1/config")
    try:
        return json.loads(payload)
    except (ValueError, UnicodeError, RecursionError):
        raise ExecutionError("Invalid Cognito login configuration.") from None


def record_tokens(api, auth, response, previous=None):
    try:
        token = response["access_token"]
        refresh = response.get("refresh_token") or (previous or {}).get("refresh_token")
        expires = response["expires_in"]
        if (
            not valid_secret(token)
            or not valid_secret(refresh)
            or type(expires) is not int
            or not 60 < expires <= 86400
        ):
            raise ValueError
    except (TypeError, KeyError, ValueError):
        raise ExecutionError("Cognito did not return a valid session.") from None
    record = {
        "schema_version": 1,
        "api_url": cloud_auth.origin(api),
        "auth": auth,
        "access_token": token,
        "refresh_token": refresh,
        "expires_at": time.time() + expires,
    }
    write(api, record)
    return token


def sign_in(api):
    with locked(api):
        config = configuration(api)
        auth = auth_settings(config["auth"])
        response = cloud_auth.login(config, session=True)
        token = record_tokens(api, auth, response)
    typer.echo("Signed in. Session saved for future cloud commands.", err=True)
    return token


def token(api):
    with locked(api):
        record = read(api)
        if record is None:
            return None
        if record["expires_at"] > time.time() + 60:
            return record["access_token"]
        # Revalidate API/client binding before sending the long-lived refresh token.
        auth = auth_settings(configuration(api)["auth"])
        if auth != record["auth"]:
            raise ExecutionError(
                "Cloud login configuration changed. Run 'cloud login'."
            )
        status, payload = cloud_auth.http(
            "POST",
            auth["token_endpoint"],
            data=urlencode(
                {
                    "grant_type": "refresh_token",
                    "client_id": auth["client_id"],
                    "refresh_token": record["refresh_token"],
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            statuses=(200, 400),
        )
        try:
            response = json.loads(payload)
        except (ValueError, UnicodeError, RecursionError):
            raise ExecutionError(
                "Cognito returned an invalid refresh response."
            ) from None
        if status == 400:
            if isinstance(response, dict) and response.get("error") == "invalid_grant":
                path(api).unlink(missing_ok=True)
                return None
            raise ExecutionError(
                "Cognito rejected session refresh; check login configuration."
            )
        return record_tokens(api, auth, response, record)


def logout(api):
    with locked(api):
        try:
            record = read(api)
        except ExecutionError:
            record = None
        path(api).unlink(missing_ok=True)
        if record is not None:
            try:
                cloud_auth.http(
                    "POST",
                    record["auth"]["revocation_endpoint"],
                    data=urlencode(
                        {
                            "client_id": record["auth"]["client_id"],
                            "token": record["refresh_token"],
                        }
                    ).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except ExecutionError:
                typer.echo(
                    "Local session removed; server revocation was not confirmed.",
                    err=True,
                )
                return
    typer.echo("Local session removed. API and project settings kept.", err=True)
