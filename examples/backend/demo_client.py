"""Exercise the local API with synthetic plans, without Terraform or AWS."""

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description="Local drift API history demo")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--gate-priority", choices=("high", "medium"))
    parser.add_argument("--gate-unknown", action="store_true")
    parser.add_argument("--gate-any", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=Path("reports/backend/demo.json")
    )
    args = parser.parse_args()
    token = (
        args.token_file.read_text().strip()
        if args.token_file
        else os.environ.get("INFRALENS_API_TOKEN", "")
    )
    if not token:
        print("Set INFRALENS_API_TOKEN or provide --token-file.")
        return 2

    def call(method, path, body=None, key=None):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if key:
            headers["Idempotency-Key"] = key
        request = Request(
            args.url.rstrip("/") + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def wait(identity):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            row = call("GET", f"/api/v1/runs/{identity}")
            if row["status"] not in ("queued", "running"):
                if row["status"] != "succeeded":
                    raise ValueError
                return row
            time.sleep(0.1)
        raise TimeoutError

    try:
        criteria = {
            "any_drift": args.gate_any,
            "minimum_priority": args.gate_priority,
            "unknown_priority": args.gate_unknown,
        }
        gate_payload = {"gate": criteria} if any(criteria.values()) else {}
        sample = Path(__file__).resolve().parents[1] / "drift-review" / "plan.json"
        payload = {
            "mode": "import",
            "plan": json.loads(sample.read_text()),
            **gate_payload,
        }
        key = "demo-" + uuid.uuid4().hex
        first = call("POST", "/api/v1/projects/drift-demo/runs", payload, key)
        replay = call("POST", "/api/v1/projects/drift-demo/runs", payload, key)
        if first["run"]["id"] != replay["run"]["id"] or replay["created"]:
            raise ValueError
        before = wait(first["run"]["id"])
        clean = {
            "format_version": "1.2",
            "terraform_version": "1.16.5",
            "planned_values": {},
            "resource_drift": [],
        }
        second = call(
            "POST",
            "/api/v1/projects/drift-demo/runs",
            {"mode": "import", "plan": clean, **gate_payload},
        )
        after = wait(second["run"]["id"])
        comparison = call(
            "GET", f"/api/v1/runs/{after['id']}/comparison?baseline_id={before['id']}"
        )
        if comparison["summary"]["no_longer_reported"] != 4:
            raise ValueError
        report = call("GET", f"/api/v1/runs/{before['id']}/report")
        clean_report = call("GET", f"/api/v1/runs/{after['id']}/report")
        if gate_payload:
            expected = (
                4
                if args.gate_any
                else (
                    2
                    if args.gate_priority == "high"
                    else 3
                    if args.gate_priority == "medium"
                    else 0
                )
                + int(args.gate_unknown)
            )
            if (
                before["gate"]["status"] != "failed"
                or report["gate"]["matched_count"] != expected
                or len(report["resources"]) != 4
                or after["gate"]["status"] != "passed"
                or clean_report["gate"]["matched_count"] != 0
            ):
                raise ValueError
        evidence = {
            "before": before,
            "after": after,
            "idempotency_verified": True,
            "comparison": comparison,
            "report": report,
            "clean_report": clean_report,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(
            "Demo passed: 2 completed runs, idempotency and history comparison. "
            f"Evidence: {args.output.resolve()}"
        )
        return 0
    except (HTTPError, URLError, OSError, ValueError, KeyError, TimeoutError):
        print("Demo failed. Check the server, token and registered demo project.")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
