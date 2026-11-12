"""Reproducible dashboard publishing and rollback using existing AWS credentials.

No credentials, tokens or scan data are put in release artifacts. Infrastructure
and backend origin updates are separate, explicit operator steps.
"""

import argparse
import hashlib
import io
import json
import mimetypes
import os
import re
import subprocess
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
MAX_BUNDLE = 100 * 1024 * 1024
RELEASE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def release_files(bundle):
    """Reject unsafe archives before any S3 write; never extract to disk."""
    if len(bundle) > MAX_BUNDLE:
        raise ValueError("Release archive is too large.")
    files = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
        for member in archive:
            parts = member.name.split("/")
            allowed = member.name == "index.html" or (
                len(parts) == 2 and parts[0] == "assets" and parts[1]
            )
            if (
                not member.isfile()
                or not allowed
                or any(part in {".", "..", ""} for part in parts)
                or "\\" in member.name
                or member.name in files
                or member.size < 0
            ):
                raise ValueError("Unsafe release archive entry.")
            total += member.size
            if total > MAX_BUNDLE:
                raise ValueError("Expanded release is too large.")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Missing release file.")
            files[member.name] = source.read()
    if "index.html" not in files or not any(key.startswith("assets/") for key in files):
        raise ValueError("Release must contain HTML and bundled assets.")
    return files


def bundle_files(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, data in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


def publish_files(s3, bucket, files):
    # HTML is the commit point. Keep old hashed assets for existing browser tabs.
    for name in sorted(files, key=lambda value: value == "index.html"):
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        s3.put_object(
            Bucket=bucket,
            Key=name,
            Body=files[name],
            ContentType=content_type,
            CacheControl=(
                "no-store"
                if name == "index.html"
                else "public,max-age=31536000,immutable"
            ),
            ServerSideEncryption="AES256",
        )


def outputs(stack):
    return {item["OutputKey"]: item["OutputValue"] for item in stack["Outputs"]}


def get_stack(cfn, name):
    return cfn.describe_stacks(StackName=name)["Stacks"][0]


def artifact_bucket(cfn, args, backend):
    stack = get_stack(cfn, args.artifacts_stack)
    expected = {row["Key"]: row["Value"] for row in backend["Tags"]}
    tags = {row["Key"]: row["Value"] for row in stack["Tags"]}
    if any(tags.get(key) != value for key, value in expected.items()):
        raise ValueError("Artifacts stack belongs to a different deployment.")
    return outputs(stack)["ArtifactsBucket"]


def wait_stack(cfn, name):
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        stack = get_stack(cfn, name)
        status = stack["StackStatus"]
        print(f"{name}: {status}", flush=True)
        if status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
            return stack
        if not status.endswith("IN_PROGRESS"):
            raise RuntimeError(f"Stack did not deploy successfully: {status}")
        time.sleep(15)
    raise TimeoutError("Stack is still in progress; inspect before retrying.")


def prepare(cfn, args, backend):
    values = outputs(backend)
    tags = {item["Key"]: item["Value"] for item in backend["Tags"]}
    parameters = {
        "Environment": tags["Environment"],
        "Deployment": args.backend_stack,
        "ApiOrigin": values["ApiEndpoint"],
        "AuthOrigin": values["AuthDomain"],
        "IssuerOrigin": f"https://cognito-idp.{args.region}.amazonaws.com",
    }
    request = {
        "StackName": args.frontend_stack,
        "TemplateBody": (ROOT / "infra/frontend.yaml").read_text(),
        "Parameters": [
            {"ParameterKey": key, "ParameterValue": value}
            for key, value in parameters.items()
        ],
        "Tags": [{"Key": key, "Value": value} for key, value in tags.items()],
    }
    try:
        existing = get_stack(cfn, args.frontend_stack)
    except ClientError as exc:
        if exc.response["Error"][
            "Code"
        ] != "ValidationError" or "does not exist" not in str(exc):
            raise
        cfn.create_stack(**request)
    else:
        existing_tags = {row["Key"]: row["Value"] for row in existing["Tags"]}
        if any(existing_tags.get(key) != value for key, value in tags.items()):
            raise ValueError("Frontend stack belongs to a different deployment.")
        if existing["StackStatus"].endswith("IN_PROGRESS"):
            return wait_stack(cfn, args.frontend_stack)
        if existing["StackStatus"] == "ROLLBACK_COMPLETE":
            raise ValueError(
                "The previous creation rolled back. Preserve inventory/events, "
                "resolve the AWS error, then deliberately delete the failed stack "
                "before preparing again. Its retained bucket needs separate cleanup."
            )
        try:
            cfn.update_stack(**request)
        except ClientError as exc:
            if "No updates are to be performed" not in str(exc):
                raise
    return wait_stack(cfn, args.frontend_stack)


def configure_backend(cfn, args, backend, frontend=None):
    artifact = artifact_bucket(cfn, args, backend)
    parameters = {
        row["ParameterKey"]: row["ParameterValue"] for row in backend["Parameters"]
    }
    if frontend is not None:
        parameters["DashboardOrigin"] = outputs(frontend)["FrontendUrl"]
    parameters["EnableLocalDashboard"] = "true"
    subprocess.run(
        [
            "uvx",
            "--from",
            "aws-sam-cli==1.169.0",
            "sam",
            "build",
            "--template-file",
            str(ROOT / "infra/template.yaml"),
        ],
        cwd=ROOT,
        check=True,
        env={**os.environ, "SAM_CLI_TELEMETRY": "0"},
    )
    subprocess.run(
        [
            "uvx",
            "--from",
            "aws-sam-cli==1.169.0",
            "sam",
            "deploy",
            "--template-file",
            str(ROOT / ".aws-sam/build/template.yaml"),
            "--stack-name",
            args.backend_stack,
            "--profile",
            args.profile,
            "--region",
            args.region,
            "--s3-bucket",
            artifact,
            "--s3-prefix",
            args.backend_stack,
            "--capabilities",
            "CAPABILITY_IAM",
            "--no-confirm-changeset",
            "--no-fail-on-empty-changeset",
            "--parameter-overrides",
            *[f"{key}={value}" for key, value in parameters.items()],
            "--tags",
            *[f"{row['Key']}={row['Value']}" for row in backend["Tags"]],
        ],
        cwd=ROOT,
        check=True,
        env={**os.environ, "SAM_CLI_TELEMETRY": "0"},
    )


def read_object(s3, bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    with response["Body"] as body:
        data = body.read(MAX_BUNDLE + 1)
    if len(data) > MAX_BUNDLE:
        raise ValueError("Release object is too large.")
    return data


def current_release(s3, bucket, prefix):
    try:
        return json.loads(read_object(s3, bucket, prefix + "/current.json"))
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"NoSuchKey", "404"}:
            raise
        return None


def check_dashboard_config(endpoint, frontend_url):
    with urlopen(endpoint + "/v1/dashboard-config", timeout=20) as response:
        config = json.load(response)
    auth = config["auth"]
    if (
        frontend_url not in auth["allowed_origins"]
        or auth["callback_url"] != frontend_url + "/auth/callback"
        or "http://localhost:5173" not in auth["allowed_origins"]
    ):
        raise ValueError("Configure backend dashboard origins before publishing.")


def publish(session, cfn, args, backend, frontend):
    values = outputs(frontend)
    endpoint = outputs(backend)["ApiEndpoint"]
    check_dashboard_config(endpoint, values["FrontendUrl"])
    artifact = artifact_bucket(cfn, args, backend)
    s3 = session.client("s3")
    prefix = f"frontend-releases/{args.frontend_stack}"
    previous = current_release(s3, artifact, prefix)
    identity = {
        "account": args.account,
        "region": args.region,
        "backend_stack": args.backend_stack,
        "frontend_stack": args.frontend_stack,
        "api_endpoint": endpoint,
        "frontend_url": values["FrontendUrl"],
    }
    if args.command == "publish":
        for command in (
            ["npm", "ci"],
            ["npm", "run", "generate:check"],
            ["npm", "run", "lint"],
            ["npm", "run", "typecheck"],
            ["npm", "test"],
            ["npm", "run", "test:e2e"],
            ["npm", "audit", "--audit-level=high"],
            ["npm", "run", "build"],
        ):
            subprocess.run(
                command,
                cwd=FRONTEND,
                check=True,
                env={**os.environ, "VITE_API_BASE_URL": endpoint},
            )
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        release = f"{stamp}-{revision[:12]}"
        files = {
            file.relative_to(FRONTEND / "dist").as_posix(): file.read_bytes()
            for file in (FRONTEND / "dist").rglob("*")
            if file.is_file()
        }
        marker = f'<meta name="infralens-release" content="{release}" />'
        files["index.html"] = files["index.html"].replace(
            b"</head>", (marker + "</head>").encode()
        )
        bundle = bundle_files(files)
        release_files(bundle)
        manifest = {
            **identity,
            "release": release,
            "git_revision": revision,
            "git_dirty": bool(
                subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
            ),
            "created_at": datetime.now(UTC).isoformat(),
            "archive_sha256": checksum(bundle),
            "files": {name: checksum(data) for name, data in files.items()},
        }
        for name, data, content_type in (
            ("bundle.tar.gz", bundle, "application/gzip"),
            (
                "manifest.json",
                json.dumps(manifest, indent=2).encode(),
                "application/json",
            ),
        ):
            s3.put_object(
                Bucket=artifact,
                Key=f"{prefix}/{release}/{name}",
                Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
                IfNoneMatch="*",
            )
    else:
        release = args.release
        if release == "previous":
            release = previous.get("previous_release") if previous else None
        if not release or not RELEASE_ID.fullmatch(release):
            raise ValueError("No valid rollback release was selected.")
        manifest = json.loads(
            read_object(s3, artifact, f"{prefix}/{release}/manifest.json")
        )
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("Release belongs to a different deployment.")
        bundle = read_object(s3, artifact, f"{prefix}/{release}/bundle.tar.gz")
        if checksum(bundle) != manifest["archive_sha256"]:
            raise ValueError("Release archive checksum mismatch.")
        files = release_files(bundle)
        if {name: checksum(data) for name, data in files.items()} != manifest["files"]:
            raise ValueError("Release file checksums do not match the manifest.")
    publish_files(s3, values["FrontendBucket"], files)
    # Successful HTML read-back proves the S3 commit point before advancing the pointer.
    actual = read_object(s3, values["FrontendBucket"], "index.html")
    if checksum(actual) != manifest["files"]["index.html"]:
        raise ValueError("Published HTML does not match the selected release.")
    record = {
        **manifest,
        "published_at": datetime.now(UTC).isoformat(),
        "previous_release": previous["release"] if previous else None,
    }
    s3.put_object(
        Bucket=artifact,
        Key=prefix + "/current.json",
        Body=json.dumps(record).encode(),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    print(
        json.dumps(
            {
                "release": release,
                "url": values["FrontendUrl"],
                "previous_release": record["previous_release"],
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["prepare", "configure-backend", "publish", "rollback"]
    )
    parser.add_argument("--account", required=True)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--backend-stack", default="infralens-dev")
    parser.add_argument("--frontend-stack", default="infralens-dev-frontend")
    parser.add_argument("--artifacts-stack", default="infralens-dev-artifacts")
    parser.add_argument("--release", default="previous")
    parser.add_argument(
        "--keep-origin",
        action="store_true",
        help="Configure backend auth while preserving its current primary origin",
    )
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    config = Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 3})
    if (
        session.client("sts", config=config).get_caller_identity()["Account"]
        != args.account
    ):
        raise ValueError("AWS account does not match the requested deployment.")
    cfn = session.client("cloudformation", config=config)
    backend = get_stack(cfn, args.backend_stack)
    tags = {row["Key"]: row["Value"] for row in backend["Tags"]}
    if (
        tags.get("Project") != "infralens"
        or tags.get("Environment") != "dev"
        or tags.get("Deployment") != args.backend_stack
    ):
        raise ValueError(
            "This workflow only publishes an identified InfraLens dev deployment."
        )
    if args.command == "prepare":
        frontend = prepare(cfn, args, backend)
        print(json.dumps(outputs(frontend)), flush=True)
        return
    if args.command == "configure-backend" and args.keep_origin:
        configure_backend(cfn, args, backend)
        return
    frontend = get_stack(cfn, args.frontend_stack)
    frontend_tags = {row["Key"]: row["Value"] for row in frontend["Tags"]}
    if any(frontend_tags.get(key) != value for key, value in tags.items()):
        raise ValueError("Frontend stack does not belong to the selected deployment.")
    if args.command == "configure-backend":
        configure_backend(cfn, args, backend, frontend)
    else:
        publish(session, cfn, args, backend, frontend)


if __name__ == "__main__":
    main()
