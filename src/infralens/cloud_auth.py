"""HTTPS and memory-only Cognito PKCE login for CLI uploads."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import typer

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


def http(method, url, *, data=None, headers=None, statuses=(200,)):
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
            response = opener.open(request, timeout=30)
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
            "Sign-in failed or expired. Sign in again or supply "
            "a fresh INFRALENS_ACCESS_TOKEN."
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
    raise ExecutionError(f"Cloud request failed: HTTP {status}{detail}. {hint}")


def login(config, timeout=180, *, session=False):
    try:
        auth = config["auth"]
        callback = urllib.parse.urlsplit(auth["callback_url"])
        auth_url = urllib.parse.urlsplit(auth["authorization_endpoint"])
        token_url = urllib.parse.urlsplit(auth["token_endpoint"])
        if (
            callback.scheme != "http"
            or callback.hostname != "localhost"
            or callback.username
            or callback.password
            or not callback.port
            or callback.query
            or callback.fragment
            or callback.path != "/callback"
            or auth_url.scheme != "https"
            or token_url.scheme != "https"
            or auth_url.netloc != token_url.netloc
            or not auth_url.hostname
            or auth_url.username
            or token_url.username
            or auth_url.password
            or token_url.password
            or auth_url.path != "/oauth2/authorize"
            or token_url.path != "/oauth2/token"
            or auth_url.query
            or token_url.query
            or auth_url.fragment
            or token_url.fragment
            or auth["pkce_method"] != "S256"
            or "infralens/api" not in auth["scopes"]
            or not isinstance(auth["client_id"], str)
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ExecutionError(
            "The service returned invalid login configuration."
        ) from None
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    received = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            valid = (
                parsed.path == callback.path
                and len(params.get("state", [])) == 1
                and params["state"][0].isascii()
                and hmac.compare_digest(params["state"][0], state)
            )
            if valid:
                codes = params.get("code", [])
                received["code"] = codes[0] if len(codes) == 1 else None
            self.send_response(200 if valid else 400)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(b"Return to the InfraLens terminal.")

    try:
        server = HTTPServer(("127.0.0.1", callback.port), Callback)
    except OSError:
        raise ExecutionError(
            "Login callback port is busy; close the other login and retry."
        ) from None
    with server:
        server.timeout = 0.1
        url = (
            auth["authorization_endpoint"]
            + "?"
            + urllib.parse.urlencode(
                {
                    "response_type": "code",
                    "client_id": auth["client_id"],
                    "redirect_uri": auth["callback_url"],
                    "scope": " ".join(auth["scopes"]),
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )
        typer.echo("Sign in using the browser.", err=True)
        if not webbrowser.open(url):
            typer.echo(f"Open this sign-in URL on this machine: {url}", err=True)
        deadline = time.monotonic() + timeout
        while "code" not in received and time.monotonic() < deadline:
            server.handle_request()
    code = received.get("code")
    if not isinstance(code, str) or not code or len(code) > 4096:
        raise ExecutionError(
            "Login was cancelled, timed out or returned no authorization code."
        )
    form = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": auth["client_id"],
            "redirect_uri": auth["callback_url"],
            "code": code,
            "code_verifier": verifier,
        }
    ).encode()
    _, payload = http(
        "POST",
        auth["token_endpoint"],
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        token = json.loads(payload)["access_token"]
        if (
            not isinstance(token, str)
            or not token
            or not re.fullmatch(r"[A-Za-z0-9_.~-]{1,16384}", token)
        ):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise ExecutionError("Cognito did not return a valid access token.") from None
    return json.loads(payload) if session else token


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
    token = os.environ.get("INFRALENS_ACCESS_TOKEN")
    if token is not None:
        if not re.fullmatch(r"[A-Za-z0-9_.~-]{1,16384}", token):
            raise ExecutionError(
                "INFRALENS_ACCESS_TOKEN must contain a valid access token."
            )
        return token
    from infralens import cloud_session

    token = cloud_session.token(api_url)
    if token is not None:
        return token
    if not interactive_input():
        raise ExecutionError(
            "Noninteractive cloud operations require INFRALENS_ACCESS_TOKEN "
            "or a saved session. Run 'infralens cloud login' interactively."
        )
    return cloud_session.sign_in(api_url)
