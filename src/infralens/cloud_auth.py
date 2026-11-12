"""HTTPS transport and API-key selection for cloud operations."""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from infralens.errors import ExecutionError, InvalidInput


def origin(value):
    try:
        url = urllib.parse.urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise ValueError
        _ = url.port
    except (TypeError, ValueError):
        raise InvalidInput("--api-url must be an HTTPS origin.") from None
    return f"https://{url.netloc}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http(method, url, *, data=None, headers=None, statuses=(200,), timeout=30):
    try:
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError
        request = urllib.request.Request(
            url, data=data, headers=headers or {}, method=method
        )
    except (TypeError, ValueError):
        raise ExecutionError("The service returned an invalid HTTPS address.") from None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            status = response.status
            body = response.read(512 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ExecutionError(
            "Cannot connect to the cloud service. Check your network, "
            "DNS/proxy/TLS settings and API URL."
        ) from None
    if len(body) > 512 * 1024:
        raise ExecutionError("Cloud response exceeded the expected size.")
    if status in statuses:
        return status, body
    detail = ""
    try:
        code = json.loads(body).get("error", {}).get("code", "")
        if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
            detail = f" ({code})"
    except (ValueError, AttributeError, TypeError, UnicodeError):
        pass
    hints = {
        401: (
            "API key rejected. Run 'infralens cloud login' with a valid key "
            "or update INFRALENS_API_KEY."
        ),
        403: "Permission denied. Check your account and access rights.",
        404: "Resource not found. Check the project ID and API URL.",
        409: "Request conflict. Check the project or run state.",
        413: "The report exceeds the service size limit.",
        422: "The request was rejected. Check project and scan options.",
        429: "The service is busy. Try again later.",
    }
    hint = hints.get(
        status,
        "The cloud service is unavailable."
        if status >= 500
        else "Check your request and API URL.",
    )
    if status in (401, 403) and (headers or {}).get("Authorization", "").startswith(
        "Bearer il_key_"
    ):
        hint = "API key rejected or permission denied. Check expiration and revocation."
    raise ExecutionError(f"Cloud request failed: HTTP {status}{detail}. {hint}")


def interactive_input():
    """Windows NUL is a character device, but cannot host interactive login."""
    if not sys.stdin.isatty():
        return False
    if os.name == "nt":
        import ctypes
        import msvcrt

        try:
            mode = ctypes.c_ulong()
            handle = ctypes.c_void_p(msvcrt.get_osfhandle(sys.stdin.fileno()))
            return bool(
                ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            )
        except (OSError, ValueError, AttributeError):
            return False
    return True


def access_token(api_url):
    """Select an API key; retained name for shared cloud request callers."""
    from infralens import cloud_api_key

    key = cloud_api_key.selected(api_url)
    if key is None:
        raise ExecutionError(
            "No API key configured. Run 'infralens cloud login' "
            "or set INFRALENS_API_KEY for automation."
        )
    return key
