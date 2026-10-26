"""Drift uploads use the same private storage boundary as security scans."""

import copy
import hashlib
import json
from uuid import uuid4

import pytest
from test_runs import upload


def report_fixture():
    return {
        "schema_version": "1.0",
        "kind": "drift",
        "terraform_version": "1.16.5",
        "input_mode": "refresh_only",
        "checked_at": "2026-10-21T11:59:02Z",
        "has_drift": True,
        "summary": {"resources": 1, "attributes": 1},
        "resources": [
            {
                "address": "aws_instance.demo",
                "resource_type": "aws_instance",
                "actions": ["update"],
                "identifiers": {},
                "attributes": [
                    {
                        "path": ["instance_type"],
                        "before": {"status": "known", "value": "t3.micro"},
                        "after": {"status": "known", "value": "t3.small"},
                    }
                ],
                "source": {
                    "status": "located",
                    "context": "current_configuration",
                    "block_address": "aws_instance.demo",
                    "locations": [
                        {
                            "file": "main.tf",
                            "start_line": 1,
                            "end_line": 4,
                            "syntax": "hcl",
                        }
                    ],
                },
            }
        ],
        "normalizations": [],
        "notes": [],
    }


def manifest(report):
    data = json.dumps(report).encode()
    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "project_id": "demo",
        "run_type": "drift",
        "started_at": "2026-10-21T11:59:00Z",
        "finished_at": "2026-10-21T11:59:02Z",
        "duration_ms": 2000,
        "source": {"relative_path": "."},
        "tool": {
            "infralens_version": "0.1.0",
            "engine": "terraform",
            "engine_version": "1.16.5",
        },
        "scope": "dev-default",
        "drift_options": {
            "input_mode": report["input_mode"],
            "trace": False,
            "lookback_days": None,
            "gate": {
                "any_drift": False,
                "minimum_priority": None,
                "unknown_priority": False,
            },
        },
        "result": {
            "collection_status": "completed",
            "has_drift": report["has_drift"],
            "summary": report["summary"],
            "priority_counts": {"high": 0, "medium": 0, "unknown": 1},
            "gate_status": "disabled",
            "trace_status": "disabled",
        },
        "artifact": {
            "format": "json",
            "content_type": "application/json",
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "schema_version": "1.0",
        },
    }, data


@pytest.fixture
def drift(api):
    assert api("PUT", "/v1/projects/demo", {"name": "Demo"})[0] == 201
    return manifest(report_fixture())


def ready(api, cloud, payload, data):
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, data)
    status, response = api("POST", f"/v1/runs/{payload['run_id']}/complete")
    assert status == 200, response
    return response


def test_drift_upload_report_history_and_security_isolation(api, cloud, drift):
    payload, data = drift
    run = payload["run_id"]
    assert (
        api("GET", "/v1/config")[1]["upload"]["max_drift_report_bytes"] == 2 * 1024**2
    )
    assert api("POST", "/v1/runs", payload)[0] == 201
    assert api("GET", f"/v1/runs/{run}/drift/report")[0] == 409
    upload(cloud, payload, data)
    status, completed = api("POST", f"/v1/runs/{run}/complete")
    assert status == 200, completed
    assert "analysis" not in completed
    assert api("GET", f"/v1/runs/{run}/drift/report")[1] == json.loads(data)
    assert api("GET", "/v1/runs")[1]["items"] == []
    assert api("GET", "/v1/runs", query={"run_type": "drift"})[1]["items"] == [
        completed
    ]
    project = api(
        "GET", "/v1/projects/demo", query={"include": "latest_scan,latest_drift"}
    )[1]
    assert project["latest_scan"] is None
    assert project["latest_drift"]["scope"] == "dev-default"
    assert api("POST", f"/v1/runs/{run}/analysis/retry")[0] == 409
    assert api("GET", f"/v1/runs/{run}/findings")[0] == 409
    assert api("POST", "/v1/runs", payload)[1]["upload"] is None
    assert api("POST", f"/v1/runs/{run}/complete")[1] == completed
    assert api("GET", f"/v1/runs/{run}/artifacts/json")[0] == 200


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("GET", "/drift/report"),
        ("GET", "/drift/comparison"),
        ("POST", "/complete"),
        ("GET", "/artifacts/json"),
        ("DELETE", ""),
    ],
)
def test_drift_owner_boundary(api, cloud, drift, method, suffix):
    payload, data = drift
    ready(api, cloud, payload, data)
    assert api(method, f"/v1/runs/{payload['run_id']}{suffix}", user="user-b")[0] == 404


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["resources"][0]["source"]["locations"][0].update(
            file="/home/private/main.tf"
        ),
        lambda r: r["resources"][0]["source"]["locations"][0].update(
            file="C:\\private\\main.tf"
        ),
        lambda r: r["resources"][0]["source"]["locations"][0].update(file="../main.tf"),
        lambda r: r["resources"][0]["attributes"][0].update(
            before={"status": "sensitive", "value": "secret"}
        ),
        lambda r: r["resources"].append(copy.deepcopy(r["resources"][0])),
        lambda r: r.update(has_drift=False),
        lambda r: r["summary"].update(attributes=5),
        lambda r: r.update(variables={"secret": "raw plan"}),
        lambda r: r.update(schema_version="2.0"),
    ],
)
def test_invalid_drift_content_is_not_published(api, cloud, drift, change):
    report = report_fixture()
    change(report)
    payload, data = manifest(report)
    assert api("POST", "/v1/runs", payload)[0] in (201, 422)
    if cloud.table.get_item(Key=cloud.runs.key("user-a", payload["run_id"])).get(
        "Item"
    ):
        upload(cloud, payload, data)
        assert api("POST", f"/v1/runs/{payload['run_id']}/complete")[0] == 409
    assert api("GET", "/v1/runs", query={"run_type": "drift"})[1]["items"] == []


def test_drift_size_limit_and_metadata_summary_consistency(api, cloud, drift):
    payload, data = drift
    oversized = copy.deepcopy(payload)
    oversized["artifact"]["size_bytes"] = 2 * 1024**2 + 1
    assert api("POST", "/v1/runs", oversized)[0] == 422
    payload["result"]["priority_counts"] = {"high": 1, "medium": 0, "unknown": 0}
    assert api("POST", "/v1/runs", payload)[0] == 201
    upload(cloud, payload, data)
    assert api("POST", f"/v1/runs/{payload['run_id']}/complete")[0] == 409


def test_drift_delete_hides_report_and_comparison(api, cloud, drift):
    payload, data = drift
    ready(api, cloud, payload, data)
    run = payload["run_id"]
    assert api("DELETE", f"/v1/runs/{run}")[0] in (202, 204)
    assert api("GET", f"/v1/runs/{run}/drift/report")[0] == 404
    assert api("GET", f"/v1/runs/{run}/drift/comparison")[0] == 404


def test_comparison_baseline_scope_pagination_and_hidden_values(api, cloud, drift):
    old, data = drift
    ready(api, cloud, old, data)
    report = report_fixture()
    report["resources"][0]["attributes"][0]["after"]["value"] = "PRIVATE_CHANGED"
    added = copy.deepcopy(report["resources"][0])
    added["address"] = "aws_instance.new"
    report["resources"].append(added)
    report["summary"] = {"resources": 2, "attributes": 2}
    current, data = manifest(report)
    current.update(
        started_at="2026-10-21T12:00:00Z", finished_at="2026-10-21T12:00:02Z"
    )
    current["result"]["priority_counts"]["unknown"] = 2
    ready(api, cloud, current, data)
    path = f"/v1/runs/{current['run_id']}/drift/comparison"
    status, page = api("GET", path, query={"limit": "1"})
    assert status == 200, page
    assert page["baseline_run_id"] == old["run_id"]
    assert page["summary"]["changed"] == 1
    assert page["summary"]["new"] == 1
    assert page["next_cursor"]
    assert "PRIVATE_CHANGED" not in json.dumps(page)
    assert page["resources"][0]["changed_paths"] == [["instance_type"]]
    second = api(
        "GET", path, query={"baseline_id": old["run_id"], "cursor": page["next_cursor"]}
    )[1]
    assert second["resources"][0]["status"] == "new"
    assert second["next_cursor"] is None
    assert api("GET", path, query={"baseline_id": current["run_id"]})[0] == 422
    foreign, data = manifest(report_fixture())
    foreign["scope"] = "prod-default"
    ready(api, cloud, foreign, data)
    assert api("GET", path, query={"baseline_id": foreign["run_id"]})[0] == 422
    assert (
        api("GET", path, user="user-b", query={"baseline_id": old["run_id"]})[0] == 404
    )


def test_comparison_uncertainty_and_baseline_missing(api, cloud, drift):
    old, data = drift
    ready(api, cloud, old, data)
    path = f"/v1/runs/{old['run_id']}/drift/comparison"
    assert api("GET", path)[1]["status"] == "baseline_missing"
    report = report_fixture()
    report["resources"][0]["attributes"][0]["after"] = {"status": "sensitive"}
    current, data = manifest(report)
    ready(api, cloud, current, data)
    page = api(
        "GET",
        f"/v1/runs/{current['run_id']}/drift/comparison",
        query={"baseline_id": old["run_id"]},
    )[1]
    assert page["resources"][0]["status"] == "indeterminate"
    assert page["resources"][0]["changed_paths"] == []


def test_history_filters_bind_cursor_and_allow_empty_pages(api, cloud, drift):
    first, data = drift
    ready(api, cloud, first, data)
    other = copy.deepcopy(first)
    other.update(run_id=str(uuid4()), scope="prod-default")
    ready(api, cloud, other, data)
    params = {"run_type": "drift", "limit": "1", "scope": "dev-default"}
    page = api("GET", "/v1/runs", query=params)[1]
    assert page["next_cursor"]
    assert (
        api(
            "GET",
            "/v1/runs",
            query={**params, "cursor": page["next_cursor"], "scope": "prod-default"},
        )[0]
        == 422
    )
    assert (
        api("GET", "/v1/runs", query={"run_type": "drift", "gate_status": "failed"})[1][
            "items"
        ]
        == []
    )


def test_trace_error_is_stored_as_partial_and_gate_incomplete(api, cloud, drift):
    from infralens_backend.drift import summarize

    report = report_fixture()
    report["trace"] = {"status": "error", "has_errors": True}
    report["resources"][0]["trace"] = {
        "status": "error",
        "reason": "aws_lookup_failed",
        "events": [],
    }
    criteria = {"any_drift": True, "minimum_priority": None, "unknown_priority": False}
    result, gate = summarize(report, criteria)
    report["gate"] = gate
    payload, data = manifest(report)
    payload["drift_options"].update(trace=True, lookback_days=7, gate=criteria)
    payload["result"] = result
    completed = ready(api, cloud, payload, data)
    assert completed["result"]["collection_status"] == "partial"
    assert completed["result"]["gate_status"] == "incomplete"
    assert api("GET", f"/v1/runs/{payload['run_id']}/drift/report")[1] == report


def test_duplicate_and_nonfinite_json_and_deep_values_are_rejected(api, cloud, drift):
    valid = json.dumps(report_fixture())
    for data in (
        valid.replace('"has_drift": true', '"has_drift": true, "has_drift": true'),
        valid.replace('"t3.small"', "NaN"),
        valid.replace('"t3.small"', "1e999"),
        valid.replace('"t3.small"', "[" * 70 + "null" + "]" * 70),
    ):
        payload, _ = manifest(report_fixture())
        data = data.encode()
        payload["artifact"].update(
            size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest()
        )
        assert api("POST", "/v1/runs", payload)[0] == 201
        upload(cloud, payload, data)
        assert api("POST", f"/v1/runs/{payload['run_id']}/complete")[0] == 409


def test_security_backfill_skips_drift_reports(api, cloud, drift):
    import importlib.util
    from pathlib import Path

    payload, data = drift
    ready(api, cloud, payload, data)
    spec = importlib.util.spec_from_file_location(
        "drift_backfill_test",
        Path(__file__).parents[1] / "scripts/backfill_analysis.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.backfill(cloud, apply=True, include_failed=True, maximum=10)
    assert result["eligible"] == 0
    assert result["queued"] == 0
