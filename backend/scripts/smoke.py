"""Exercise a deployed backend using browser PKCE login and a native JSON report.

Tokens live only in memory. This is an operator verification tool, not CLI login.
"""

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from uuid import uuid4

from infralens_backend.schemas import SEVERITIES
from infralens_backend.validation import iso, project_id


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http(method, url, data=None, headers=None, statuses=(200,), limit=2 * 1024 * 1024):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Service and S3 URLs must use HTTPS.")
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method=method
    )
    try:
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        if response.status not in statuses:
            raise RuntimeError(f"HTTP request failed with status {response.status}.")
        body = response.read(limit + 1)
        if len(body) > limit:
            raise RuntimeError("HTTP response exceeded the expected size.")
        return response.status, body


def login(config, timeout=180):
    auth = config["auth"]
    callback = urllib.parse.urlsplit(auth["callback_url"])
    if (
        callback.scheme != "http"
        or callback.hostname != "localhost"
        or not callback.port
    ):
        raise ValueError("Smoke login requires the registered localhost callback.")
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
            pass  # Never log callback codes or OAuth state.

        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            valid = parsed.path == callback.path and params.get("state") == [state]
            valid = valid and hmac.compare_digest(params["state"][0], state)
            if valid:
                codes = params.get("code", [])
                received["code"] = codes[0] if len(codes) == 1 else None
            self.send_response(200 if valid else 400)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(b"Return to the InfraLens terminal.")

    with HTTPServer(("127.0.0.1", callback.port), Callback) as server:
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
        print("Sign in using the browser. Tokens are not saved.")
        if not webbrowser.open(url):
            print("Open this sign-in URL on this machine:", url)
        deadline = time.monotonic() + timeout
        while "code" not in received and time.monotonic() < deadline:
            server.handle_request()
    code = received.get("code")
    if not isinstance(code, str) or not code or len(code) > 4096:
        raise RuntimeError(
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
    token = json.loads(payload).get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Cognito did not return an access token.")
    return token


def metadata(report, project):
    raw = json.loads(report)
    if not isinstance(raw, dict) or raw.get("SchemaVersion") != 2:
        raise ValueError("Use a native Trivy schema-2 JSON report.")
    counts = dict.fromkeys(SEVERITIES, 0)
    for result in raw.get("Results", []):
        for finding in result.get("Misconfigurations", []):
            status = finding.get("Status", "FAIL")
            if status in ("PASS", "EXCEPTION"):
                continue
            if status != "FAIL" or finding.get("Severity") not in counts:
                raise ValueError("Unsupported finding in the native report.")
            counts[finding["Severity"]] += 1
    now = iso(datetime.now(UTC))
    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "project_id": project,
        "run_type": "security_scan",
        "started_at": now,
        "finished_at": now,
        "duration_ms": 0,
        "source": {"relative_path": "."},
        "tool": {
            "infralens_version": "0.1.0",
            "engine": "trivy",
            "engine_version": raw.get("Trivy", {}).get("Version") or "unknown",
        },
        "scan_options": {
            "fail_on": None,
            "severity": list(SEVERITIES),
            "ignore_sha256": None,
        },
        "result": {
            "scan_status": "completed",
            "threshold_status": "not_evaluated",
            "findings": {"total": sum(counts.values()), "by_severity": counts},
            "warnings": [],
        },
        "artifact": {
            "format": "json",
            "content_type": "application/json",
            "size_bytes": len(report),
            "sha256": hashlib.sha256(report).hexdigest(),
            "schema_version": 2,
        },
    }


def smoke(endpoint, config, token, report, project):
    def api(method, path, body=None, statuses=(200,)):
        data = json.dumps(body).encode() if body is not None else None
        status, content = http(
            method,
            endpoint + path,
            data=data,
            statuses=statuses,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        return status, json.loads(content) if content else None

    api("PUT", f"/v1/projects/{project}", {"name": "Backend smoke test"}, (200, 201))
    payload = metadata(report, project)
    run = payload["run_id"]
    try:
        _, registered = api("POST", "/v1/runs", payload, (201,))
        _, retried = api("POST", "/v1/runs", payload)
        assert registered["run"] == retried["run"]
        upload = registered["upload"]
        # A same-length modified payload must fail the signed checksum.
        modified = bytes([report[0] ^ 1]) + report[1:]
        http("PUT", upload["url"], modified, upload["headers"], (400,))
        http("PUT", upload["url"], report, upload["headers"], (200,))
        http("PUT", upload["url"], report, upload["headers"], (412,))
        _, ready = api("POST", f"/v1/runs/{run}/complete")
        assert ready["upload_status"] == "ready"
        assert api("POST", f"/v1/runs/{run}/complete")[1] == ready
        assert api("POST", "/v1/runs", payload)[1]["upload"] is None
        assert api("GET", f"/v1/runs/{run}")[1] == ready
        _, download = api("GET", f"/v1/runs/{run}/artifacts/json")
        assert (
            http("GET", download["url"], limit=config["upload"]["max_report_bytes"])[1]
            == report
        )
        visible = False
        for _ in range(20):
            _, history = api("GET", f"/v1/runs?project_id={project}")
            if any(item["run_id"] == run for item in history["items"]):
                visible = True
                break
            time.sleep(0.5)
        assert visible, "History index did not become visible within ten seconds."
        print(
            "Verified upload, checksum, immutability, retry, "
            "completion, history and download."
        )
    finally:
        status, _ = api("DELETE", f"/v1/runs/{run}", statuses=(202, 204, 404))
        print("Smoke run deletion:", "scheduled" if status == 202 else "complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--project", default="backend-smoke")
    args = parser.parse_args()
    project = project_id(args.project)
    endpoint = args.endpoint.rstrip("/")
    parsed = urllib.parse.urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.query
        or parsed.fragment
        or parsed.path
    ):
        raise ValueError("Endpoint must be an HTTPS origin without a path.")
    _, payload = http("GET", endpoint + "/v1/config")
    config = json.loads(payload)
    with args.report.open("rb") as stream:
        report = stream.read(config["upload"]["max_report_bytes"] + 1)
    if not report or len(report) > config["upload"]["max_report_bytes"]:
        raise ValueError("Report is empty or exceeds the upload limit.")
    metadata(report, project)  # Validate before opening a browser or creating data.
    http("GET", endpoint + "/v1/projects", statuses=(401,))
    token = login(config)
    smoke(endpoint, config, token, report, project)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, AssertionError) as exc:
        raise SystemExit(str(exc)) from None
