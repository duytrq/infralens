import base64
import copy
import hashlib
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest


@pytest.fixture
def scan(api):
    assert api("PUT", "/v1/projects/demo", {"name": "Demo"})[0] == 201
    report = json.dumps({"SchemaVersion": 2, "Results": []}).encode()
    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "project_id": "demo",
        "run_type": "security_scan",
        "started_at": "2026-10-21T11:59:00Z",
        "finished_at": "2026-10-21T11:59:02Z",
        "duration_ms": 2000,
        "source": {"relative_path": "."},
        "tool": {
            "infralens_version": "0.1.0",
            "engine": "trivy",
            "engine_version": "0.76.0",
        },
        "scan_options": {"fail_on": None, "severity": ["HIGH"], "ignore_sha256": None},
        "result": {
            "scan_status": "completed",
            "threshold_status": "not_evaluated",
            "findings": {
                "total": 0,
                "by_severity": {
                    "UNKNOWN": 0,
                    "LOW": 0,
                    "MEDIUM": 0,
                    "HIGH": 0,
                    "CRITICAL": 0,
                },
            },
            "warnings": [],
        },
        "artifact": {
            "format": "json",
            "content_type": "application/json",
            "size_bytes": len(report),
            "sha256": hashlib.sha256(report).hexdigest(),
            "schema_version": 2,
        },
    }, report


def upload(cloud, payload, report, owner="user-a"):
    item = cloud.table.get_item(Key=cloud.runs.key(owner, payload["run_id"]))["Item"]
    key = cloud.runs.object_key(owner, item)
    cloud.s3.put_object(
        Bucket=cloud.settings.bucket,
        Key=key,
        Body=report,
        ContentType="application/json",
        IfNoneMatch="*",
        ChecksumSHA256=base64.b64encode(hashlib.sha256(report).digest()).decode(),
        ChecksumAlgorithm="SHA256",
        Tagging="state=pending",
    )
    return key


def test_registration_binds_url_and_idempotency_to_entire_payload(api, scan):
    payload, report = scan
    status, created = api("POST", "/v1/runs", payload)
    assert status == 201
    assert created["run"]["upload_status"] == "pending"
    assert created["upload"]["headers"]["if-none-match"] == "*"
    assert created["upload"]["headers"]["content-length"] == str(len(report))
    assert created["upload"]["headers"]["x-amz-checksum-sha256"] == (
        base64.b64encode(hashlib.sha256(report).digest()).decode()
    )
    params = parse_qs(urlsplit(created["upload"]["url"]).query)
    signed = params["X-Amz-SignedHeaders"][0].split(";")
    assert set(created["upload"]["headers"]) <= set(signed)
    status, retry = api("POST", "/v1/runs", copy.deepcopy(payload))
    assert status == 200
    assert retry["run"] == created["run"]
    changed = copy.deepcopy(payload)
    changed["tool"]["engine_version"] = "0.76.1"
    assert api("POST", "/v1/runs", changed)[0] == 409


def test_complete_publishes_only_after_report_is_verified(api, cloud, scan):
    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    assert api("GET", "/v1/runs")[1]["items"] == []
    assert api("POST", f"/v1/runs/{run}/complete")[0] == 409
    upload(cloud, payload, report)
    status, completed = api("POST", f"/v1/runs/{run}/complete")
    assert status == 200
    assert completed["upload_status"] == "ready"
    assert completed["uploaded_at"].endswith("Z")
    assert api("POST", f"/v1/runs/{run}/complete")[1] == completed
    assert api("POST", "/v1/runs", payload)[1]["upload"] is None
    assert api("GET", "/v1/runs")[1]["items"] == [completed]
    assert api("GET", f"/v1/runs/{run}")[1] == completed
    status, download = api("GET", f"/v1/runs/{run}/artifacts/json")
    assert status == 200
    assert "X-Amz-Signature=" in download["url"]
    assert api("GET", f"/v1/runs/{run}/artifacts/sarif")[0] == 404


def test_run_access_is_scoped_to_authenticated_user(api, cloud, scan):
    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    for method, suffix in [
        ("GET", ""),
        ("DELETE", ""),
        ("POST", "/complete"),
        ("GET", "/artifacts/json"),
    ]:
        assert api(method, f"/v1/runs/{run}{suffix}", user="user-b")[0] == 404
    assert api("GET", "/v1/runs", user="user-b")[1]["items"] == []
    assert api("POST", f"/v1/runs/{run}/complete")[0] == 200


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(owner_id="other"),
        lambda p: p["artifact"].update(format="sarif"),
        lambda p: p["artifact"].update(size_bytes=50 * 1024 * 1024 + 1),
        lambda p: p["artifact"].update(sha256="wrong"),
        lambda p: p["source"].update(relative_path="/home/private/infra"),
        lambda p: p["source"].update(relative_path="C:\\Users\\private"),
        lambda p: p["source"].update(relative_path="../infra"),
        lambda p: p["result"]["findings"].update(total=1),
        lambda p: p["result"].update(threshold_status="failed"),
        lambda p: p.update(finished_at="2026-10-21T11:58:00Z"),
    ],
)
def test_invalid_run_metadata_is_rejected(api, scan, change):
    payload, _ = scan
    change(payload)
    assert api("POST", "/v1/runs", payload)[0] == 422


def test_missing_project_is_not_created_implicitly(api, scan):
    payload, _ = scan
    payload["project_id"] = "missing"
    assert api("POST", "/v1/runs", payload)[0] == 404


def test_complete_rejects_different_checksum_even_when_size_matches(api, cloud, scan):
    payload, report = scan
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, b"x" * len(report))
    status, data = api("POST", f"/v1/runs/{payload['run_id']}/complete")
    assert status == 409
    assert data["error"]["code"] == "artifact_mismatch"
    assert api("GET", "/v1/runs")[1]["items"] == []


def test_history_is_newest_first_paginated_and_project_scoped(api, cloud, scan):
    payload, report = scan
    assert api("PUT", "/v1/projects/other", {"name": "Other"})[0] == 201
    ids = []
    for minute in (1, 3, 2):
        p = copy.deepcopy(payload)
        p.update(
            run_id=str(uuid4()),
            started_at=f"2026-10-21T10:0{minute}:00Z",
            finished_at=f"2026-10-21T10:0{minute}:02Z",
        )
        if minute == 2:
            p["project_id"] = "other"
        ids.append(p["run_id"])
        assert api("POST", "/v1/runs", p)[0] == 201
        upload(cloud, p, report)
        assert api("POST", f"/v1/runs/{p['run_id']}/complete")[0] == 200
    found, cursor = [], None
    for _ in range(4):
        params = {"limit": "1"}
        if cursor:
            params["cursor"] = cursor
        status, page = api("GET", "/v1/runs", query=params)
        assert status == 200
        found += [r["run_id"] for r in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert found == [ids[1], ids[2], ids[0]]
    status, page = api("GET", "/v1/runs", query={"project_id": "demo"})
    assert status == 200
    assert [r["run_id"] for r in page["items"]] == [ids[1], ids[0]]
    page = api(
        "GET",
        "/v1/runs",
        query={"from": "2026-10-21T10:02:00Z", "to": "2026-10-21T10:02:00Z"},
    )[1]
    assert [r["run_id"] for r in page["items"]] == [ids[2]]


def test_history_validates_cursor_owner_filters_and_limit(api, cloud, scan):
    payload, report = scan
    for _ in range(2):
        p = {**payload, "run_id": str(uuid4())}
        assert api("POST", "/v1/runs", p)[0] == 201
        upload(cloud, p, report)
        assert api("POST", f"/v1/runs/{p['run_id']}/complete")[0] == 200
    cursor = api("GET", "/v1/runs", query={"limit": "1"})[1]["next_cursor"]
    assert cursor
    assert api("GET", "/v1/runs", user="user-b", query={"cursor": cursor})[0] == 422
    assert (
        api("GET", "/v1/runs", query={"cursor": cursor, "project_id": "demo"})[0] == 422
    )
    for params in [
        {"limit": "101"},
        {"cursor": "invalid"},
        {"from": "bad"},
        {"status": "pending"},
        {"from": "2027-01-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
    ]:
        assert api("GET", "/v1/runs", query=params)[0] == 422


def test_deletion_sweeps_late_uploads_after_presigned_url_expiry(api, cloud, scan):
    from botocore.exceptions import ClientError

    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    key = upload(cloud, payload, report)
    assert api("POST", f"/v1/runs/{run}/complete")[0] == 200
    assert api("DELETE", f"/v1/runs/{run}")[0] == 202
    assert api("GET", f"/v1/runs/{run}")[0] == 404
    assert api("GET", "/v1/runs")[1]["items"] == []
    # Simulate the already issued URL being used after the first deletion.
    upload(cloud, payload, report)
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(minutes=17)
    result = cloud.runs.cleanup()
    assert result["deleted"] == 1
    with pytest.raises(ClientError):
        cloud.s3.head_object(Bucket=cloud.settings.bucket, Key=key)
    assert cloud.table.get_item(Key=cloud.runs.key("user-a", run)).get("Item") is None


def test_cleanup_expires_pending_but_preserves_completed_runs(api, cloud, scan):
    payload, report = scan
    assert api("POST", "/v1/runs", payload)[0] == 201
    pending_key = upload(cloud, payload, report)
    ready = {**payload, "run_id": str(uuid4())}
    assert api("POST", "/v1/runs", ready)[0] == 201
    upload(cloud, ready, report)
    assert api("POST", f"/v1/runs/{ready['run_id']}/complete")[0] == 200
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(days=8)
    assert cloud.runs.cleanup()["deleted"] == 1
    assert api("GET", f"/v1/runs/{payload['run_id']}")[0] == 404
    assert api("GET", f"/v1/runs/{ready['run_id']}")[0] == 200
    assert pending_key not in [
        o["Key"]
        for o in cloud.s3.list_objects_v2(Bucket=cloud.settings.bucket).get(
            "Contents", []
        )
    ]


def test_complete_cannot_resurrect_a_concurrently_deleted_run(
    api, cloud, scan, monkeypatch
):
    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    original = cloud.s3.head_object

    def racing_head(**kwargs):
        head = original(**kwargs)
        assert api("DELETE", f"/v1/runs/{run}")[0] == 202
        return head

    monkeypatch.setattr(cloud.s3, "head_object", racing_head)
    assert api("POST", f"/v1/runs/{run}/complete")[0] == 409
    assert api("GET", f"/v1/runs/{run}")[0] == 404
    assert api("GET", "/v1/runs")[1]["items"] == []


def test_uploads_are_staged_and_complete_marks_report_for_indefinite_retention(
    api, cloud, scan
):
    payload, report = scan
    status, registered = api("POST", "/v1/runs", payload)
    assert status == 201
    assert registered["upload"]["headers"]["x-amz-tagging"] == "state=pending"
    key = upload(cloud, payload, report)
    assert api("POST", f"/v1/runs/{payload['run_id']}/complete")[0] == 200
    assert cloud.s3.get_object_tagging(Bucket=cloud.settings.bucket, Key=key)[
        "TagSet"
    ] == [
        {"Key": "state", "Value": "ready"},
    ]


def test_failed_delete_stays_hidden_and_scheduled_cleanup_retries(
    api, cloud, scan, monkeypatch
):
    from botocore.exceptions import ClientError

    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    original = cloud.s3.delete_object

    def unavailable(**kwargs):
        raise ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "internal"}},
            "DeleteObject",
        )

    monkeypatch.setattr(cloud.s3, "delete_object", unavailable)
    assert api("DELETE", f"/v1/runs/{run}")[0] == 503
    assert api("GET", f"/v1/runs/{run}")[0] == 404
    assert cloud.runs.cleanup()["failed"] == 1
    monkeypatch.setattr(cloud.s3, "delete_object", original)
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(minutes=17)
    assert cloud.runs.cleanup()["deleted"] == 1


def test_cleanup_cannot_delete_a_run_completed_after_index_read(
    api, cloud, scan, monkeypatch
):
    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(days=8)
    original = cloud.runs.replace
    raced = False

    def racing_replace(item, revision):
        nonlocal raced
        if not raced and item["data"]["upload_status"] == "deleting":
            raced = True
            # A completion that started before expiry wins its conditional write.
            current = cloud.table.get_item(Key=cloud.runs.key("user-a", run))["Item"]
            current["revision"] += 1
            current["data"]["upload_status"] = "ready"
            current.pop("cleanup_pk")
            current.pop("cleanup_sk")
            cloud.table.put_item(Item=current)
        return original(item, revision)

    monkeypatch.setattr(cloud.runs, "replace", racing_replace)
    assert cloud.runs.cleanup()["deferred"] == 1
    assert api("GET", f"/v1/runs/{run}")[1]["upload_status"] == "ready"


def test_float_integer_input_returns_validation_error_instead_of_storage_failure(
    api, scan
):
    payload, _ = scan
    payload["duration_ms"] = 2000.0
    assert api("POST", "/v1/runs", payload)[0] == 422


def test_renewed_upload_url_cannot_outlive_the_pending_session(api, cloud, scan):
    payload, _ = scan
    assert api("POST", "/v1/runs", payload)[0] == 201
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(days=7, seconds=-60)
    status, renewed = api("POST", "/v1/runs", payload)
    assert status == 200
    assert parse_qs(urlsplit(renewed["upload"]["url"]).query)["X-Amz-Expires"] == ["60"]
    from infralens_backend.validation import timestamp

    assert timestamp(renewed["upload"]["expires_at"]) <= initial + timedelta(days=7)


def test_concurrent_completion_returns_the_already_completed_run(
    api, cloud, scan, monkeypatch
):
    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    original = cloud.runs.replace
    raced = False
    completed = None

    def racing_replace(item, revision):
        nonlocal raced, completed
        if not raced and item["data"]["upload_status"] == "ready":
            raced = True
            status, completed = api("POST", f"/v1/runs/{run}/complete")
            assert status == 200
        return original(item, revision)

    monkeypatch.setattr(cloud.runs, "replace", racing_replace)
    status, result = api("POST", f"/v1/runs/{run}/complete")
    assert status == 200
    assert result == completed


def test_stale_deletion_cannot_remove_a_new_run_reusing_the_same_id(api, cloud, scan):
    from infralens_backend.errors import ApiError

    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(minutes=17)
    deleting = cloud.runs.claim_deletion(cloud.runs.get("user-a", run))
    stale_worker = copy.deepcopy(deleting)
    assert cloud.runs.finish_deletion(deleting)
    assert api("POST", "/v1/runs", payload)[0] == 201
    new_key = upload(cloud, payload, report)
    with pytest.raises(ApiError, match="retry"):
        cloud.runs.finish_deletion(stale_worker)
    assert cloud.s3.head_object(Bucket=cloud.settings.bucket, Key=new_key)[
        "ContentLength"
    ] == len(report)
    assert api("GET", f"/v1/runs/{run}")[1]["upload_status"] == "pending"


def test_old_completion_cannot_overwrite_a_new_generation(
    api, cloud, scan, monkeypatch
):
    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(minutes=17)
    original = cloud.runs.replace
    raced = False

    def racing_replace(item, revision):
        nonlocal raced
        if not raced and item["data"]["upload_status"] == "ready":
            raced = True
            assert api("DELETE", f"/v1/runs/{run}")[0] == 204
            assert api("POST", "/v1/runs", payload)[0] == 201
            upload(cloud, payload, report)
        return original(item, revision)

    monkeypatch.setattr(cloud.runs, "replace", racing_replace)
    assert api("POST", f"/v1/runs/{run}/complete")[0] == 409
    assert api("GET", f"/v1/runs/{run}")[1]["upload_status"] == "pending"


@pytest.mark.parametrize(
    "report",
    [
        b"not JSON",
        b"[]",
        b'{"SchemaVersion": 3}',
        b'{"SchemaVersion": 2,"Results": {}}',
        b'{"SchemaVersion": 2,"Results": [7]}',
        b'{"SchemaVersion": 2,"SchemaVersion": 2}',
        b'{"SchemaVersion": 2,"extra":' + b"[" * 70 + b"0" + b"]" * 70 + b"}",
    ],
)
def test_completion_requires_a_valid_native_json_envelope(api, cloud, scan, report):
    payload, _ = scan
    payload["artifact"].update(
        size_bytes=len(report), sha256=hashlib.sha256(report).hexdigest()
    )
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    status, result = api("POST", f"/v1/runs/{payload['run_id']}/complete")
    assert status == 409
    assert result["error"]["code"] == "artifact_invalid"
    assert api("GET", "/v1/runs")[1]["items"] == []


def test_history_does_not_mix_reused_run_generations_from_stale_index_entries(
    api, cloud, scan, monkeypatch
):
    payload, report = scan
    run = payload["run_id"]
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    assert api("POST", f"/v1/runs/{run}/complete")[0] == 200
    old_entry = cloud.table.get_item(Key=cloud.runs.key("user-a", run))["Item"]
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(minutes=17)
    assert api("DELETE", f"/v1/runs/{run}")[0] == 204
    assert api("PUT", "/v1/projects/other", {"name": "Other"})[0] == 201
    newer = copy.deepcopy(payload)
    newer.update(
        project_id="other",
        started_at="2027-01-01T00:00:00Z",
        finished_at="2027-01-01T00:00:02Z",
    )
    assert api("POST", "/v1/runs", newer)[0] == 201
    upload(cloud, newer, report)
    assert api("POST", f"/v1/runs/{run}/complete")[0] == 200
    new_entry = cloud.table.get_item(Key=cloud.runs.key("user-a", run))["Item"]
    monkeypatch.setattr(cloud.table, "query", lambda **kwargs: {"Items": [old_entry]})
    assert api("GET", "/v1/runs", query={"project_id": "demo"})[1]["items"] == []
    assert (
        api("GET", "/v1/runs", query={"to": "2026-12-31T00:00:00Z"})[1]["items"] == []
    )
    monkeypatch.setattr(
        cloud.table, "query", lambda **kwargs: {"Items": [old_entry, new_entry]}
    )
    assert len(api("GET", "/v1/runs")[1]["items"]) == 1
