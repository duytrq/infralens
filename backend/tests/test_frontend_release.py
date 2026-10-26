import importlib.util
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

PATH = Path(__file__).resolve().parents[2] / "infra/frontend_release.py"
SPEC = importlib.util.spec_from_file_location("frontend_release", PATH)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def test_release_roundtrip_preserves_exact_bytes():
    files = {"index.html": b"<html>release</html>", "assets/app-hash.js": b"export{}"}
    assert release.release_files(release.bundle_files(files)) == files


@pytest.mark.parametrize(
    "name",
    ["../outside", "/index.html", "assets/../secret", "assets\\secret", "secret.txt"],
)
def test_release_rejects_paths_outside_the_public_build(name):
    bundle = release.bundle_files(
        {"index.html": b"ok", "assets/app.js": b"ok", name: b"bad"}
    )
    with pytest.raises(ValueError, match="Unsafe release"):
        release.release_files(bundle)


def test_release_rejects_links_and_expanded_size_limits(monkeypatch):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        member = tarfile.TarInfo("index.html")
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc/passwd"
        archive.addfile(member)
    with pytest.raises(ValueError, match="Unsafe release"):
        release.release_files(output.getvalue())
    bundle = release.bundle_files({"index.html": b"x" * 20_000, "assets/app.js": b"ok"})
    monkeypatch.setattr(release, "MAX_BUNDLE", 1024)
    with pytest.raises(ValueError, match="Expanded release"):
        release.release_files(bundle)


def test_publish_writes_html_last_and_preserves_existing_assets():
    s3 = Mock()
    files = {"index.html": b"new", "assets/z.js": b"z", "assets/a.css": b"a"}
    release.publish_files(s3, "frontend", files)
    calls = s3.put_object.call_args_list
    assert [call.kwargs["Key"] for call in calls] == [
        "assets/z.js",
        "assets/a.css",
        "index.html",
    ]
    assert calls[-1].kwargs["CacheControl"] == "no-store"
    assert all("immutable" in call.kwargs["CacheControl"] for call in calls[:-1])
    s3.delete_object.assert_not_called()
    s3.delete_objects.assert_not_called()


def test_asset_upload_failure_never_publishes_new_html():
    s3 = Mock()
    s3.put_object.side_effect = RuntimeError("Unavailable")
    with pytest.raises(RuntimeError):
        release.publish_files(
            s3, "frontend", {"index.html": b"new", "assets/app.js": b"js"}
        )
    assert s3.put_object.call_args.kwargs["Key"] == "assets/app.js"


def test_release_requires_both_html_and_assets():
    with pytest.raises(ValueError, match="HTML and bundled assets"):
        release.release_files(release.bundle_files({"index.html": b"empty"}))


@pytest.mark.parametrize("corruption", [None, "identity", "archive", "files"])
def test_rollback_checks_identity_and_integrity_before_restoring(
    corruption, monkeypatch
):
    args = SimpleNamespace(
        command="rollback",
        release="previous",
        account="123",
        region="region",
        backend_stack="backend",
        frontend_stack="frontend",
        artifacts_stack="artifacts",
    )
    identity = {
        "account": "123",
        "region": "region",
        "backend_stack": "backend",
        "frontend_stack": "frontend",
        "api_endpoint": "https://api.example.com",
        "frontend_url": "https://frontend.example.com",
    }
    files = {"index.html": b"old html", "assets/old.js": b"old js"}
    bundle = release.bundle_files(files)
    manifest = {
        **identity,
        "release": "old",
        "archive_sha256": release.checksum(bundle),
        "files": {name: release.checksum(data) for name, data in files.items()},
    }
    if corruption == "identity":
        manifest["account"] = "other-account"
    if corruption == "archive":
        bundle += b"tampered"
    if corruption == "files":
        manifest["files"]["index.html"] = "wrong"
    prefix = "frontend-releases/frontend"
    storage = {
        ("archive", prefix + "/current.json"): json.dumps(
            {"release": "new", "previous_release": "old"}
        ).encode(),
        ("archive", prefix + "/old/manifest.json"): json.dumps(manifest).encode(),
        ("archive", prefix + "/old/bundle.tar.gz"): bundle,
        ("public", "index.html"): b"new html",
        ("public", "assets/new.js"): b"new js",
    }
    s3 = Mock()
    s3.put_object.side_effect = lambda **kw: storage.update(
        {(kw["Bucket"], kw["Key"]): kw["Body"]}
    )
    session = SimpleNamespace(client=lambda name: s3)
    monkeypatch.setattr(release, "check_dashboard_config", lambda *args: None)
    monkeypatch.setattr(release, "artifact_bucket", lambda *args: "archive")
    monkeypatch.setattr(
        release, "read_object", lambda client, bucket, key: storage[(bucket, key)]
    )
    backend = {
        "Outputs": [
            {"OutputKey": "ApiEndpoint", "OutputValue": identity["api_endpoint"]}
        ]
    }
    frontend = {
        "Outputs": [
            {"OutputKey": "FrontendUrl", "OutputValue": identity["frontend_url"]},
            {"OutputKey": "FrontendBucket", "OutputValue": "public"},
        ]
    }
    if corruption:
        with pytest.raises(ValueError):
            release.publish(session, None, args, backend, frontend)
        s3.put_object.assert_not_called()
    else:
        release.publish(session, None, args, backend, frontend)
        assert storage[("public", "index.html")] == b"old html"
        assert storage[("public", "assets/new.js")] == b"new js"
        assert (
            json.loads(storage[("archive", prefix + "/current.json")])["release"]
            == "old"
        )


@pytest.mark.parametrize("status", ["CREATE_IN_PROGRESS", "ROLLBACK_COMPLETE"])
def test_prepare_resumes_live_work_or_refuses_failed_creation(status, monkeypatch):
    tags = [
        {"Key": "Project", "Value": "infralens"},
        {"Key": "Environment", "Value": "dev"},
    ]
    backend = {
        "Tags": tags,
        "Outputs": [
            {"OutputKey": "ApiEndpoint", "OutputValue": "https://api.example.com"},
            {"OutputKey": "AuthDomain", "OutputValue": "https://login.example.com"},
        ],
    }
    existing = {"Tags": tags, "StackStatus": status}
    monkeypatch.setattr(release, "get_stack", lambda *args: existing)
    wait = Mock(return_value=existing)
    monkeypatch.setattr(release, "wait_stack", wait)
    cfn = Mock()
    args = SimpleNamespace(
        backend_stack="backend", frontend_stack="frontend", region="region"
    )
    if status.endswith("IN_PROGRESS"):
        assert release.prepare(cfn, args, backend) == existing
        wait.assert_called_once()
    else:
        with pytest.raises(ValueError, match="previous creation rolled back"):
            release.prepare(cfn, args, backend)
    cfn.update_stack.assert_not_called()
    cfn.create_stack.assert_not_called()
