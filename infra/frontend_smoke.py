"""Verify real Cognito/browser/API integration with isolated temporary accounts.

No invitation is sent. Passwords are passed to the browser process on stdin, never
written to disk or logged. Test users and their project rows are removed in finally;
run tombstones remain for the backend's protected asynchronous cleanup.
"""

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]


def cleanup_users(cognito, table, pool, users):
    failures = []
    removed_projects = 0
    for user in users:
        try:
            rows = table.query(
                KeyConditionExpression=Key("pk").eq(f"USER#{user['sub']}")
                & Key("sk").begins_with("PROJECT#")
            )["Items"]
            for row in rows:
                table.delete_item(Key={"pk": row["pk"], "sk": row["sk"]})
                removed_projects += 1
        except Exception:
            failures.append("project cleanup")
        try:
            cognito.admin_delete_user(UserPoolId=pool, Username=user["username"])
        except Exception:
            failures.append("temporary account cleanup")
    if failures:
        raise RuntimeError("Smoke cleanup incomplete: " + ", ".join(failures))
    return removed_projects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--stack", default="infralens-dev")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument(
        "--security-cli",
        type=Path,
        help="Verify cloud project operations and scan --upload with real Trivy.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.security_cli:
        args.security_cli = args.security_cli.resolve(strict=True)
        if not args.security_cli.is_file():
            raise ValueError("--security-cli must be an executable file.")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    config = Config(connect_timeout=10, read_timeout=20, retries={"max_attempts": 3})
    if (
        session.client("sts", config=config).get_caller_identity()["Account"]
        != args.account
    ):
        raise ValueError("Unexpected AWS account.")
    cfn = session.client("cloudformation", config=config)
    stack = cfn.describe_stacks(StackName=args.stack)["Stacks"][0]
    tags = {item["Key"]: item["Value"] for item in stack["Tags"]}
    if tags.get("Project") != "infralens" or tags.get("Environment") != "dev":
        raise ValueError("Smoke is limited to the identified dev deployment.")
    values = {item["OutputKey"]: item["OutputValue"] for item in stack["Outputs"]}
    endpoint = values["ApiEndpoint"]
    with urlopen(endpoint + "/v1/dashboard-config", timeout=20) as response:
        dashboard = json.load(response)
    origins = ["http://localhost:5173"]
    if not args.local_only:
        frontend = cfn.describe_stacks(StackName=args.stack + "-frontend")["Stacks"][0]
        frontend_outputs = {
            item["OutputKey"]: item["OutputValue"] for item in frontend["Outputs"]
        }
        origins.insert(0, frontend_outputs["FrontendUrl"])
    if any(origin not in dashboard["auth"]["allowed_origins"] for origin in origins):
        raise ValueError("The smoke origins are not registered in the backend.")
    subprocess.run(
        ["npm", "run", "build"],
        cwd=ROOT / "frontend",
        check=True,
        env={**os.environ, "VITE_API_BASE_URL": endpoint},
        stdout=subprocess.DEVNULL,
    )
    users = []
    server = None
    cognito = session.client("cognito-idp", config=config)
    table = session.resource("dynamodb").Table(values["StorageTable"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cli_directory = tempfile.TemporaryDirectory(prefix="infralens-security-smoke-")
    bridge = Path(cli_directory.name) / "open-browser"
    login_url_file = str(Path(cli_directory.name) / "login-url")
    bridge.write_text(
        f"#!{sys.executable}\nimport sys\nfrom pathlib import Path\n"
        f"Path({login_url_file!r}).write_text(sys.argv[1])\n"
    )
    bridge.chmod(0o700)
    try:
        for _ in range(2):
            username = f"infralens-frontend-{uuid4()}@example.invalid"
            password = "Il9!" + secrets.token_urlsafe(30)
            created = cognito.admin_create_user(
                UserPoolId=values["UserPoolId"],
                Username=username,
                UserAttributes=[
                    {"Name": "email", "Value": username},
                    {"Name": "email_verified", "Value": "true"},
                ],
                MessageAction="SUPPRESS",
            )
            subject = next(
                item["Value"]
                for item in created["User"]["Attributes"]
                if item["Name"] == "sub"
            )
            users.append({"username": username, "password": password, "sub": subject})
            cognito.admin_set_user_password(
                UserPoolId=values["UserPoolId"],
                Username=username,
                Password=password,
                Permanent=True,
            )
        server = subprocess.Popen(
            ["npm", "run", "preview"],
            cwd=ROOT / "frontend",
            env={**os.environ, "VITE_API_BASE_URL": endpoint},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(50):
            if server.poll() is not None:
                raise RuntimeError(
                    "Local frontend server exited; port 5173 may be in use."
                )
            try:
                with urlopen("http://localhost:5173", timeout=1) as response:
                    if response.status == 200:
                        break
            except URLError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local frontend did not become ready.")
        result = subprocess.run(
            ["node", "scripts/aws-smoke.mjs"],
            cwd=ROOT / "frontend",
            input=json.dumps(
                {
                    "endpoint": endpoint,
                    "config": dashboard,
                    "origins": origins,
                    "accounts": users,
                    "screenshot_directory": str(ROOT / "frontend/verification"),
                    "security_cli": {
                        "executable": str(args.security_cli),
                        "python": sys.executable,
                        "browser_bridge": str(bridge),
                        "project": str(ROOT / "tests/fixtures/unsafe"),
                        "output_directory": cli_directory.name,
                    }
                    if args.security_cli
                    else None,
                }
            ),
            text=True,
            capture_output=True,
            timeout=600,
        )
        print(result.stderr, end="", flush=True)
        if result.returncode:
            raise RuntimeError("Browser smoke failed; no credentials were recorded.")
        evidence = {
            **json.loads(result.stdout),
            "checked_at": datetime.now(UTC).isoformat(),
            "account": args.account,
            "endpoint": endpoint,
            "origins": origins,
            "temporary_accounts": len(users),
            "cloudfront_included": not args.local_only,
            "build_mode": "production",
        }
    finally:
        try:
            if server is not None:
                # This process group was created by this invocation.
                try:
                    os.killpg(server.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                server.wait(timeout=10)
        finally:
            try:
                removed_projects = cleanup_users(
                    cognito, table, values["UserPoolId"], users
                )
            finally:
                cli_directory.cleanup()
    evidence.update(
        temporary_users_removed=len(users),
        project_rows_removed=removed_projects,
        run_cleanup="Protected tombstones/derived data use scheduled backend cleanup",
        real_security_cli=bool(args.security_cli),
    )
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": len(evidence["checks"]),
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
