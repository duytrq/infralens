"""Locally stored API keys, scoped to the API origin."""

import os
import re

from infralens import cloud_session
from infralens.errors import ExecutionError
from infralens.reporting import write_report

PATTERN = re.compile(r"il_key_[a-f0-9]{32}_[A-Za-z0-9_-]{43}")


def validate(key):
    if not isinstance(key, str) or not PATTERN.fullmatch(key):
        raise ExecutionError("Invalid API key format.")
    return key


def path(api):
    return cloud_session.path(api).with_suffix(".apikey")


def read(api):
    with cloud_session.locked(api):
        file = path(api)
        if not file.exists() and not file.is_symlink():
            return None
        cloud_session.protect(file)
        with file.open("r", encoding="utf-8") as stream:
            return validate(stream.read(256))


def save(api, key):
    validate(key)
    with cloud_session.locked(api):
        file = path(api)
        if file.is_symlink():
            raise ExecutionError("API key storage must not be a symbolic link.")
        write_report(file, key)
        cloud_session.protect(file)


def clear(api):
    with cloud_session.locked(api):
        file = path(api)
        if file.is_symlink():
            raise ExecutionError("API key storage must not be a symbolic link.")
        file.unlink(missing_ok=True)


def selected(api):
    key = os.environ.get("INFRALENS_API_KEY")
    return validate(key) if key is not None else read(api)


def route(token, path):
    if token.startswith("il_key_"):
        validate(token)
        if not path.startswith("/v1/"):
            raise ExecutionError("Invalid cloud API route.")
        return "/v1/cli/" + path.removeprefix("/v1/")
    return path
