import hashlib
import json
from datetime import timedelta

import pytest
from test_runs import upload


@pytest.fixture
def completed(api, cloud, scan):
    payload, _ = scan
    report = json.dumps(
        {
            "SchemaVersion": 2,
            "Results": [
                {
                    "Target": "main.tf",
                    "Misconfigurations": [
                        {"ID": "RULE-A", "Severity": "HIGH", "Message": "first"},
                        {"ID": "RULE-A", "Severity": "LOW", "Message": "second"},
                        {"ID": "RULE-B", "Severity": "HIGH", "Message": "third"},
                    ],
                },
                {
                    "Target": "other.tf",
                    "Misconfigurations": [
                        {"ID": "RULE-B", "Severity": "CRITICAL"},
                    ],
                },
            ],
        }
    ).encode()
    payload["artifact"].update(
        size_bytes=len(report), sha256=hashlib.sha256(report).hexdigest()
    )
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, report)
    run = payload["run_id"]
    assert api("POST", f"/v1/runs/{run}/complete")[0] == 200
    return run


def process(cloud, run):
    item = cloud.runs.get("user-a", run)
    cloud.analysis.process(
        "user-a", run, item["generation"], item["data"]["analysis"]["build_id"]
    )


def test_findings_pending_then_filtered_pages_and_detail(api, cloud, completed):
    base = f"/v1/runs/{completed}"
    assert api("GET", base + "/findings")[0] == 409
    process(cloud, completed)
    metadata = api("GET", base)[1]
    assert metadata["analysis"]["status"] == "ready"
    assert metadata["analysis"]["findings"]["total"] == 4
    assert metadata["analysis"]["counts_match"] is False
    assert metadata["result"]["findings"]["total"] == 0
    seen, cursor = [], None
    while True:
        params = {"limit": "1"}
        if cursor:
            params["cursor"] = cursor
        status, page = api("GET", base + "/findings", query=params)
        assert status == 200
        seen += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert [f["severity"] for f in seen] == ["CRITICAL", "HIGH", "HIGH", "LOW"]
    assert len({f["finding_id"] for f in seen}) == 4
    detail = api("GET", base + "/findings/" + seen[0]["finding_id"])[1]
    assert detail["file"] == "other.tf"
    status, filtered = api(
        "GET",
        base + "/findings",
        query={"file": "main.tf", "severity": "HIGH", "rule_id": "RULE-A"},
    )
    assert status == 200
    assert [f["rule_id"] for f in filtered["items"]] == ["RULE-A"]
    for suffix in ("", "/findings", "/findings/" + seen[0]["finding_id"]):
        assert api("GET", base + suffix, user="user-b")[0] == 404


def test_retry_is_idempotent_and_old_worker_cannot_publish(api, cloud, completed):
    run = completed
    before = cloud.runs.get("user-a", run)
    assert api("POST", f"/v1/runs/{run}/analysis/retry")[0] == 202
    assert (
        cloud.runs.get("user-a", run)["data"]["analysis"] == before["data"]["analysis"]
    )
    process(cloud, run)
    assert api("POST", f"/v1/runs/{run}/analysis/retry")[0] == 200
    assert api("DELETE", f"/v1/runs/{run}")[0] == 202
    assert (
        cloud.analysis.process(
            "user-a", run, before["generation"], before["data"]["analysis"]["build_id"]
        )
        == "skipped"
    )
    assert api("GET", f"/v1/runs/{run}/findings")[0] == 404
    cloud.now = lambda: __import__("datetime").datetime(
        2026, 10, 22, tzinfo=__import__("datetime").UTC
    )
    cloud.runs.cleanup()
    cloud.analysis.cleanup()
    assert cloud.analysis.table.scan()["Items"] == []


def test_project_latest_scan_disappears_after_delete(api, cloud, completed):
    params = {"include": "latest_scan"}
    assert (
        api("GET", "/v1/projects/demo", query=params)[1]["latest_scan"]["run_id"]
        == completed
    )
    assert (
        api("GET", "/v1/projects", query=params)[1]["items"][0]["latest_scan"]["run_id"]
        == completed
    )
    assert api("GET", "/v1/projects/demo")[1].get("latest_scan") is None
    api("DELETE", f"/v1/runs/{completed}")
    assert api("GET", "/v1/projects/demo", query=params)[1]["latest_scan"] is None


def test_dashboard_public_config(api):
    status, config = api("GET", "/v1/dashboard-config", user=None)
    assert status == 200
    assert config["auth"]["client_id"] == "dashboard-client"
    assert config["auth"]["callback_url"] == "http://localhost:5173/auth/callback"
    assert api("GET", "/v1/config", user=None)[1]["auth"]["client_id"] == "client"


def test_cursor_is_bound_to_filter_owner_and_build(api, cloud, completed):
    base = f"/v1/runs/{completed}/findings"
    process(cloud, completed)
    cursor = api("GET", base, query={"limit": "1"})[1]["next_cursor"]
    assert api("GET", base, query={"cursor": cursor, "severity": "LOW"})[0] == 422
    assert api("GET", base, query={"cursor": cursor}, user="user-b")[0] == 404
    item = cloud.runs.get("user-a", completed)
    item["data"]["analysis"]["build_id"] = "different-build"
    cloud.table.put_item(Item=item)
    assert api("GET", base, query={"cursor": cursor})[0] == 422


def test_sparse_filter_continues_after_empty_page(api, cloud, completed):
    process(cloud, completed)
    params = {"rule_id": "RULE-B", "file": "main.tf", "limit": "1"}
    status, page = api("GET", f"/v1/runs/{completed}/findings", query=params)
    assert status == 200
    assert page["items"] == []
    assert page["next_cursor"]
    params["cursor"] = page["next_cursor"]
    page = api("GET", f"/v1/runs/{completed}/findings", query=params)[1]
    assert len(page["items"]) == 1
    assert page["items"][0]["file"] == "main.tf"


@pytest.mark.parametrize(
    "query",
    [
        {"severity": "high"},
        {"file": ""},
        {"rule_id": "x" * 1025},
        {"limit": "101"},
        {"search": "bucket"},
        {"cursor": "garbage"},
    ],
)
def test_invalid_filters(api, cloud, completed, query):
    process(cloud, completed)
    assert api("GET", f"/v1/runs/{completed}/findings", query=query)[0] == 422


def test_worker_duplicate_delivery_and_cleanup_keep_ready_data(api, cloud, completed):
    process(cloud, completed)
    before = cloud.analysis.table.scan()["Items"]
    process(cloud, completed)
    assert cloud.analysis.table.scan()["Items"] == before
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(days=1)
    assert cloud.analysis.cleanup()["failed"] == 0
    assert cloud.analysis.table.scan()["Items"] == before
    assert api("GET", f"/v1/runs/{completed}/findings")[0] == 200


def test_worker_expired_then_retry_new_build(api, cloud, completed):
    before = cloud.runs.get("user-a", completed)
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(minutes=21)
    cloud.analysis.cleanup()
    assert api("GET", f"/v1/runs/{completed}")[1]["analysis"]["status"] == "failed"
    assert api("POST", f"/v1/runs/{completed}/analysis/retry")[0] == 202
    after = cloud.runs.get("user-a", completed)
    assert (
        after["data"]["analysis"]["build_id"] != before["data"]["analysis"]["build_id"]
    )
    assert (
        cloud.analysis.process(
            "user-a",
            completed,
            before["generation"],
            before["data"]["analysis"]["build_id"],
        )
        == "skipped"
    )
    process(cloud, completed)
    assert api("GET", f"/v1/runs/{completed}")[1]["analysis"]["status"] == "ready"


def test_failed_normalization_keeps_original_download(
    api, cloud, completed, monkeypatch
):
    import infralens_backend.analysis as module

    def invalid(stream):
        yield {
            "finding_id": "1-" + "a" * 32,
            "severity": "HIGH",
            "rule_id": "A",
            "file": None,
        }
        raise ValueError("Unsupported finding")

    monkeypatch.setattr(module, "normalize_report", invalid)
    process(cloud, completed)
    assert api("GET", f"/v1/runs/{completed}/findings")[0] == 409
    assert api("GET", f"/v1/runs/{completed}/artifacts/json")[0] == 200
    assert api("GET", f"/v1/runs/{completed}")[1]["analysis"]["status"] == "failed"
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(minutes=21)
    cloud.analysis.cleanup()
    assert cloud.analysis.table.scan()["Items"] == []


def test_delete_while_worker_writes_never_publishes(api, cloud, completed, monkeypatch):
    import infralens_backend.analysis as module
    from infralens_backend.findings import normalize_report

    def deleting(stream):
        for n, row in enumerate(normalize_report(stream)):
            if n == 1:
                assert api("DELETE", f"/v1/runs/{completed}")[0] == 202
            yield row

    monkeypatch.setattr(module, "normalize_report", deleting)
    process(cloud, completed)
    assert api("GET", f"/v1/runs/{completed}")[0] == 404
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(hours=1)
    cloud.analysis.cleanup()
    cloud.runs.cleanup()
    assert cloud.analysis.table.scan()["Items"] == []


def test_reused_run_generation_isolated_from_old_processing(api, cloud, completed):
    before = cloud.runs.get("user-a", completed)
    original = json.loads(json.dumps(before["data"], default=int))
    for key in ("analysis", "upload_status", "received_at", "uploaded_at"):
        original.pop(key, None)
    api("DELETE", f"/v1/runs/{completed}")
    initial = cloud.now()
    cloud.now = lambda: initial + timedelta(hours=1)
    cloud.runs.cleanup()
    assert api("POST", "/v1/runs", original)[0] == 201
    assert (
        cloud.analysis.process(
            "user-a",
            completed,
            before["generation"],
            before["data"]["analysis"]["build_id"],
        )
        == "skipped"
    )
    assert api("GET", f"/v1/runs/{completed}")[1]["upload_status"] == "pending"


def test_latest_lookup_has_a_shared_read_budget(api, cloud, monkeypatch):
    api("PUT", "/v1/projects/demo", {"name": "Demo"})
    calls = []

    def stale(*args):
        calls.append(1)
        return {"items": [], "next_cursor": "stale-page"}

    monkeypatch.setattr(cloud.runs, "history", stale)
    status, body = api("GET", "/v1/projects", query={"include": "latest_scan"})
    assert status == 503
    assert body["error"]["code"] == "latest_scan_unavailable"
    assert len(calls) == 120


def test_stream_entrypoint_processes_new_image(api, cloud, completed, monkeypatch):
    from boto3.dynamodb.types import TypeSerializer

    from infralens_backend import handler

    item = cloud.runs.get("user-a", completed)
    serialize = TypeSerializer().serialize
    event = {
        "Records": [
            {"dynamodb": {"NewImage": {k: serialize(v) for k, v in item.items()}}}
        ]
    }
    monkeypatch.setattr(handler, "application", lambda: cloud)
    assert handler.analysis_handler(event, None) == {"processed": 1}
    assert api("GET", f"/v1/runs/{completed}")[1]["analysis"]["status"] == "ready"
    assert handler.analysis_handler(event, None) == {"processed": 1}


def test_transient_worker_dependency_failure_is_retryable(
    api, cloud, completed, monkeypatch
):
    from botocore.exceptions import ClientError

    original = cloud.s3.get_object

    def unavailable(**kwargs):
        raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "GetObject")

    monkeypatch.setattr(cloud.s3, "get_object", unavailable)
    with pytest.raises(ClientError):
        process(cloud, completed)
    assert api("GET", f"/v1/runs/{completed}")[1]["analysis"]["status"] == "pending"
    monkeypatch.setattr(cloud.s3, "get_object", original)
    process(cloud, completed)
    assert api("GET", f"/v1/runs/{completed}/findings")[0] == 200


def test_dashboard_client_allowed_but_other_clients_rejected(cloud):
    def event(client, token_use="access"):
        return {
            "rawPath": "/v1/projects",
            "requestContext": {
                "http": {"method": "GET"},
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "user-a",
                            "iss": cloud.settings.issuer,
                            "client_id": client,
                            "token_use": token_use,
                            "scope": "infralens/api",
                        }
                    }
                },
            },
        }

    assert cloud.handle(event("dashboard-client"))["statusCode"] == 200
    assert cloud.handle(event("client"))["statusCode"] == 200
    assert cloud.handle(event("unknown-client"))["statusCode"] == 401
    assert cloud.handle(event("dashboard-client", "id"))["statusCode"] == 401


def test_long_filters_still_produce_usable_bounded_cursor(api, cloud, completed):
    from infralens_backend.findings import digest

    process(cloud, completed)
    path, rule = "x" * 4096, "R" * 1024
    rows = cloud.analysis.table.scan()["Items"][:2]
    for row in rows:
        row["data"].update(file=path, rule_id=rule)
        row.update(
            file_pk=row["pk"] + "#FILE#" + digest(path),
            rule_pk=row["pk"] + "#RULE#" + digest(rule),
        )
        cloud.analysis.table.put_item(Item=row)
    params = {"file": path, "rule_id": rule, "limit": "1"}
    base = f"/v1/runs/{completed}/findings"
    status, first = api("GET", base, query=params)
    assert status == 200 and first["next_cursor"]
    assert len(first["next_cursor"]) <= 8192
    params["cursor"] = first["next_cursor"]
    assert api("GET", base, query=params)[0] == 200
