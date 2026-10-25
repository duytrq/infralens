import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from filelock import Timeout

from infralens.backend.api import create_app
from infralens.backend.comparison import compare_runs
from infralens.backend.config import Project, Settings, load_projects
from infralens.backend.store import Store, StoreConflict
from infralens.drift import parse_plan
from infralens.errors import ExecutionCancelled

TOKEN = "backend_test_token_not_a_real_secret_123456"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SECRET = "PRIVATE_BACKEND_PAYLOAD"


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/", "text/html"),
        ("/dashboard/app.js", "javascript"),
        ("/dashboard/app.css", "text/css"),
        ("/dashboard/demo-plan.json", "application/json"),
    ],
)
def test_dashboard_public_assets_do_not_expose_token_or_project_paths(
    settings, path, content_type
):
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert content_type in response.headers["content-type"]
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert TOKEN not in response.text
        assert str(settings.database) not in response.text
        assert str(settings.projects["demo"].path) not in response.text
        assert client.get("/api/v1/projects").status_code == 401


def test_dashboard_cannot_serve_arbitrary_backend_or_history_files(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        for path in (
            "/dashboard/api.py",
            "/dashboard/history.sqlite3",
            "/dashboard/%2e%2e%2fapi.py",
            "/dashboard/%2e%2e%5capi.py",
        ):
            response = client.get(path)
            assert response.status_code == 404
            assert TOKEN not in response.text


def plan(resources=None):
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.5",
        "planned_values": {},
        "resource_drift": resources or [],
    }


def entry(after="t3.small", sensitive=False, address="aws_instance.demo"):
    change = {
        "actions": ["update"],
        "before": {"instance_type": "t3.micro"},
        "after": {"instance_type": after},
    }
    if sensitive:
        change["after_sensitive"] = {"instance_type": True}
    return {
        "address": address,
        "type": "aws_instance",
        "mode": "managed",
        "change": change,
    }


@pytest.fixture
def settings(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.tf").write_text('resource "aws_instance" "demo" {}')
    return Settings(
        {"demo": Project("demo", "Demo", root, allow_refresh=False)},
        tmp_path / "history.sqlite3",
        TOKEN,
    )


def submit(client, payload=None, headers=None, project="demo"):
    return client.post(
        f"/api/v1/projects/{project}/runs",
        headers={**AUTH, **(headers or {})},
        json=payload or {"mode": "import", "plan": plan([entry()])},
    )


def wait(client, identity):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{identity}", headers=AUTH)
        assert response.status_code == 200, response.text
        row = response.json()
        if row["status"] not in ("queued", "running"):
            return row
        time.sleep(0.01)
    pytest.fail("Backend worker did not finish within test deadline")


def test_submit_status_report_and_history_are_persisted(settings):
    with TestClient(create_app(settings)) as client:
        submitted = submit(client)
        assert submitted.status_code == 202, submitted.text
        identity = submitted.json()["run"]["id"]
        row = wait(client, identity)
        assert row["status"] == "succeeded" and row["has_drift"] is True
        response = client.get(f"/api/v1/runs/{identity}/report", headers=AUTH)
        assert response.headers["cache-control"] == "no-store"
        report = response.json()
        assert report["resources"][0]["source"]["status"] == "located"
        assert report["resources"][0]["assessment"]["priority"] == "medium"
    with TestClient(create_app(settings)) as client:
        assert (
            client.get(f"/api/v1/runs/{identity}/report", headers=AUTH).json() == report
        )
        history = client.get("/api/v1/projects/demo/runs", headers=AUTH).json()
        assert history["items"][0]["id"] == identity
        assert history["items"][0]["request"]["mode"] == "import"


@pytest.mark.parametrize(
    "gate,entries,status,matched",
    [
        ({"minimum_priority": "high"}, [entry()], "passed", 0),
        ({"minimum_priority": "medium"}, [entry()], "failed", 1),
        ({"any_drift": True}, [entry()], "failed", 1),
        ({"unknown_priority": True}, [entry()], "passed", 0),
        ({"unknown_priority": True}, [entry(SECRET, sensitive=True)], "failed", 1),
        ({"minimum_priority": "high"}, [entry(SECRET, sensitive=True)], "passed", 0),
        (
            {"minimum_priority": "high", "unknown_priority": True},
            [entry(SECRET, sensitive=True)],
            "failed",
            1,
        ),
        (
            {"any_drift": True, "minimum_priority": "medium"},
            [entry()],
            "failed",
            1,
        ),
        ({"any_drift": True, "unknown_priority": True}, [], "passed", 0),
    ],
)
def test_backend_gate_keeps_execution_success_and_all_findings(
    settings, gate, entries, status, matched
):
    with TestClient(create_app(settings)) as client:
        identity = submit(
            client, {"mode": "import", "plan": plan(entries), "gate": gate}
        ).json()["run"]["id"]
        row = wait(client, identity)
        assert row["status"] == "succeeded" and row["error_code"] is None
        assert row["gate"] == {
            "status": status,
            "exit_code": 1 if status == "failed" else 0,
            "matched_count": matched,
        }
        report = client.get(f"/api/v1/runs/{identity}/report", headers=AUTH).json()
        assert report["gate"]["policy"] == "drift-gate-v1"
        assert len(report["resources"]) == len(entries)
        assert len(report["gate"]["matched_resources"]) == matched
        assert SECRET not in json.dumps(report)
        # A blocked gate remains a usable completed observation.
        compared = client.get(f"/api/v1/runs/{identity}/comparison", headers=AUTH)
        assert compared.status_code == 200


@pytest.mark.parametrize(
    "gate",
    [
        None,
        {},
        {"any_drift": False, "minimum_priority": None, "unknown_priority": False},
    ],
)
def test_disabled_gate_replays_pre_gate_queue_fingerprint(settings, gate):
    store = Store(settings.database)
    store.initialize()
    raw = plan([entry()])
    request = {"mode": "import", "trace": False, "lookback_days": 7, "timeout": 120}
    original, _ = store.enqueue(
        settings.projects["demo"],
        request,
        parse_plan(json.dumps(raw)).to_dict(),
        "old-request",
    )
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = submit(
            client,
            {"mode": "import", "plan": raw, "gate": gate},
            {"Idempotency-Key": "old-request"},
        )
        assert response.status_code == 202, response.text
        assert response.json()["created"] is False
        assert response.json()["run"]["id"] == original["id"]
        assert "gate" not in response.json()["run"]["request"]
    with TestClient(create_app(settings)) as client:
        assert wait(client, original["id"])["gate"] is None
        report = client.get(
            f"/api/v1/runs/{original['id']}/report", headers=AUTH
        ).json()
        assert "gate" not in report


def test_gate_queue_persistence_idempotency_and_history(settings):
    raw = plan([entry()])
    payload = {"mode": "import", "plan": raw, "gate": {"minimum_priority": "medium"}}
    headers = {"Idempotency-Key": "gate-request"}
    with TestClient(create_app(settings, start_worker=False)) as client:
        first = submit(client, payload, headers).json()["run"]
        assert first["gate"] is None and first["request"]["gate"] == {
            "any_drift": False,
            "minimum_priority": "medium",
            "unknown_priority": False,
        }
        explicit = {**payload, "gate": first["request"]["gate"]}
        assert submit(client, explicit, headers).json()["created"] is False
        for changed in (None, {"minimum_priority": "high"}, {"unknown_priority": True}):
            assert (
                submit(client, {**payload, "gate": changed}, headers).status_code == 409
            )
    with TestClient(create_app(settings)) as client:
        row = wait(client, first["id"])
        assert row["gate"]["status"] == "failed"
        # Different gate criteria do not invalidate an otherwise compatible baseline.
        second = submit(
            client, {**payload, "gate": {"minimum_priority": "high"}}
        ).json()["run"]
        assert wait(client, second["id"])["gate"]["status"] == "passed"
        comparison = client.get(
            f"/api/v1/runs/{second['id']}/comparison", headers=AUTH
        ).json()
        assert comparison["baseline_run_id"] == first["id"]
        assert comparison["summary"]["unchanged"] == 1
    with TestClient(create_app(settings, start_worker=False)) as client:
        rows = client.get(
            "/api/v1/projects/demo/runs?status=succeeded", headers=AUTH
        ).json()["items"]
        assert [row["gate"]["status"] for row in rows] == ["passed", "failed"]
        assert all(
            set(row["gate"]) == {"status", "exit_code", "matched_count"} for row in rows
        )


@pytest.mark.parametrize(
    "gate",
    [
        "PRIVATE_BACKEND_PAYLOAD",
        [],
        True,
        {"minimum_priority": "low"},
        {"minimum_priority": "HIGH"},
        {"minimum_priority": 1},
        {"any_drift": "true"},
        {"any_drift": 1},
        {"unknown_priority": None},
        {"unknown_priority": "false"},
        {"command": SECRET},
    ],
)
def test_invalid_gate_is_rejected_before_queue_without_echo(settings, gate):
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = submit(client, {"mode": "import", "plan": plan(), "gate": gate})
        assert response.status_code == 422 and SECRET not in response.text
        assert (
            client.get("/api/v1/projects/demo/runs", headers=AUTH).json()["items"] == []
        )


def test_gate_trace_incomplete_and_execution_failure_take_precedence(settings):
    def partial(options, initial):
        return replace(initial, trace={"status": "partial", "has_errors": True})

    payload = {"mode": "import", "plan": plan([entry()]), "gate": {"any_drift": True}}
    with TestClient(create_app(settings, executor=partial)) as client:
        identity = submit(client, payload).json()["run"]["id"]
        row = wait(client, identity)
        assert (
            row["status"] == "failed" and row["error_code"] == "cloudtrail_incomplete"
        )
        assert row["gate"] == {
            "status": "incomplete",
            "exit_code": 3,
            "matched_count": 1,
        }
        report = client.get(f"/api/v1/runs/{identity}/report", headers=AUTH).json()
        assert report["gate"]["reason_codes"] == ["cloudtrail_incomplete"]

    def broken(options, initial):
        raise RuntimeError(SECRET)

    with TestClient(create_app(settings, executor=broken)) as client:
        identity = submit(client, payload).json()["run"]["id"]
        row = wait(client, identity)
        assert row["status"] == "failed" and row["gate"] is None
        assert row["has_report"] is False and SECRET not in json.dumps(row)


def test_cancelled_gate_run_does_not_claim_passed(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        payload = {"mode": "import", "plan": plan(), "gate": {"any_drift": True}}
        identity = submit(client, payload).json()["run"]["id"]
        row = client.post(f"/api/v1/runs/{identity}/cancel", headers=AUTH).json()
        assert row["status"] == "cancelled" and row["gate"] is None
        assert row["has_report"] is False


@pytest.mark.parametrize("decision", ["passed", "failed", "incomplete"])
def test_cancel_wins_between_engine_completion_and_report_commit(
    settings, monkeypatch, decision
):
    ready, release = threading.Event(), threading.Event()

    def execute(options, initial):
        return (
            replace(initial, trace={"status": "partial", "has_errors": True})
            if decision == "incomplete"
            else initial
        )

    app = create_app(settings, executor=execute)
    finish = app.state.store.finish

    def delayed_finish(identity, status, report=None, error_code=None):
        if report is not None:
            assert report["gate"]["status"] == decision
            ready.set()
            assert release.wait(8)
        return finish(identity, status, report, error_code)

    monkeypatch.setattr(app.state.store, "finish", delayed_finish)
    with TestClient(app) as client:
        payload = {
            "mode": "import",
            "plan": plan([] if decision == "passed" else [entry()]),
            "gate": {"any_drift": True},
        }
        identity = submit(client, payload).json()["run"]["id"]
        try:
            assert ready.wait(8)
            response = client.post(f"/api/v1/runs/{identity}/cancel", headers=AUTH)
            assert response.status_code == 202
            assert response.json()["cancel_requested"] is True
        finally:
            release.set()
        row = wait(client, identity)
        assert row["status"] == "cancelled"
        assert row["error_code"] == "cancel_requested"
        assert row["gate"] is None and row["has_drift"] is None
        assert row["has_report"] is False
        assert (
            client.get(f"/api/v1/runs/{identity}/report", headers=AUTH).status_code
            == 404
        )
        stored = app.state.store.get(identity)
        assert stored["input_json"] is None and stored["report_json"] is None


@pytest.mark.parametrize("status", ["succeeded", "failed", "interrupted"])
def test_cancel_wins_over_late_error_without_report(settings, status):
    store = Store(settings.database)
    store.initialize()
    request = {"mode": "import", "trace": False, "lookback_days": 7, "timeout": 120}
    queued, _ = store.enqueue(settings.projects["demo"], request)
    store.claim()
    store.cancel(queued["id"])
    store.finish(queued["id"], status, error_code="execution_failed")
    row = store.get(queued["id"])
    assert row["status"] == "cancelled" and row["error_code"] == "cancel_requested"
    assert row["report_json"] is None and row["has_drift"] is None


def test_completed_run_wins_before_cancel_and_keeps_report(settings):
    with TestClient(create_app(settings)) as client:
        identity = submit(
            client, {"mode": "import", "plan": plan(), "gate": {"any_drift": True}}
        ).json()["run"]["id"]
        before = wait(client, identity)
        assert before["gate"]["status"] == "passed"
        assert (
            client.post(f"/api/v1/runs/{identity}/cancel", headers=AUTH).status_code
            == 409
        )
        assert client.get(f"/api/v1/runs/{identity}", headers=AUTH).json() == before


def test_queue_survives_restart_and_stale_running_work_is_interrupted(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        stale = submit(client).json()["run"]["id"]
        client.app.state.store.claim()
        queued = submit(client).json()["run"]["id"]
    with TestClient(create_app(settings)) as client:
        assert wait(client, queued)["status"] == "succeeded"
        row = client.get(f"/api/v1/runs/{stale}", headers=AUTH).json()
        assert row["status"] == "interrupted"
        assert row["error_code"] == "worker_interrupted"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic something"}],
)
def test_api_requires_authentication(settings, headers):
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = client.get("/api/v1/projects", headers=headers)
        assert response.status_code == 401
        assert TOKEN not in response.text
        assert client.get("/health").status_code == 200
        schema = client.get("/openapi.json").json()
        assert "HTTPBearer" in schema["components"]["securitySchemes"]


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "import", "plan": "PRIVATE_BACKEND_PAYLOAD"},
        {"mode": "import", "plan": {}, "command": SECRET},
        {"mode": "import", "plan": {}, "path": SECRET},
        {"mode": "import", "plan": {}, "profile": SECRET},
        {"mode": "import", "plan": {}, "timeout": True},
        {"mode": "import", "plan": {}, "lookback_days": 91},
        {"mode": "import", "plan": {}, "trace": "true"},
    ],
)
def test_validation_errors_do_not_echo_private_request_values(settings, payload):
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = submit(client, payload)
        assert response.status_code == 422
        assert SECRET not in response.text


def test_invalid_raw_json_and_large_chunked_requests_are_safe(settings):
    settings = replace(settings, max_body_bytes=1024)
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = client.post(
            "/api/v1/projects/demo/runs",
            headers=AUTH,
            content='{"plan":"PRIVATE_BACKEND_PAYLOAD"',
        )
        assert response.status_code == 422 and SECRET not in response.text
        response = client.post(
            "/api/v1/projects/demo/runs",
            headers=AUTH,
            content=(b"x" * 700 for _ in range(3)),
        )
        assert response.status_code == 413


def test_raw_plan_and_credentials_are_not_persisted(settings):
    raw = plan([entry(SECRET, sensitive=True)])
    raw["variables"] = {"password": {"value": SECRET}}
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = submit(client, {"mode": "import", "plan": raw})
        assert response.status_code == 202
        identity = response.json()["run"]["id"]
        stored = client.app.state.store.get(identity)
        assert SECRET not in stored["input_json"] + stored["request_json"]
        assert TOKEN not in stored["input_json"] + stored["request_json"]
        assert "sensitive" in stored["input_json"]
        for suffix in ("", "-wal", "-shm"):
            file = settings.database.with_name(settings.database.name + suffix)
            if file.is_file():
                assert SECRET.encode() not in file.read_bytes()


def test_invalid_plan_is_rejected_before_enqueuing(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = submit(client, {"mode": "import", "plan": {"private": SECRET}})
        assert response.status_code == 422 and SECRET not in response.text
        assert (
            client.get("/api/v1/projects/demo/runs", headers=AUTH).json()["items"] == []
        )


def test_mode_trace_and_project_permissions_are_enforced(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert submit(client, {"mode": "refresh"}).status_code == 403
        assert (
            submit(
                client, {"mode": "import", "plan": plan(), "trace": True}
            ).status_code
            == 403
        )
        assert submit(client, project="unknown").status_code == 404
        assert submit(client, {"mode": "import"}).status_code == 400
        assert (
            submit(
                client, {"mode": "import", "plan": plan(), "timeout": 500}
            ).status_code
            == 400
        )


def test_idempotency_replay_conflict_and_queue_backpressure(settings):
    settings = replace(settings, max_pending=1)
    with TestClient(create_app(settings, start_worker=False)) as client:
        headers = {"Idempotency-Key": "example-key"}
        first = submit(client, headers=headers).json()
        replay = submit(client, headers=headers).json()
        assert replay["run"]["id"] == first["run"]["id"] and replay["created"] is False
        assert submit(client).status_code == 429
        different = {"mode": "import", "plan": plan([entry("t3.large")])}
        assert submit(client, different, headers).status_code == 409


def test_queued_cancel_clears_staged_payload(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        identity = submit(client).json()["run"]["id"]
        response = client.post(f"/api/v1/runs/{identity}/cancel", headers=AUTH)
        assert response.status_code == 202 and response.json()["status"] == "cancelled"
        assert client.app.state.store.get(identity)["input_json"] is None
        assert (
            client.post(f"/api/v1/runs/{identity}/cancel", headers=AUTH).status_code
            == 409
        )


def test_running_job_can_be_cancelled(settings):
    started = threading.Event()

    def execute(options, initial):
        started.set()
        assert options.cancel.wait(5)
        raise ExecutionCancelled

    with TestClient(create_app(settings, executor=execute)) as client:
        identity = submit(client).json()["run"]["id"]
        assert started.wait(3)
        assert (
            client.post(f"/api/v1/runs/{identity}/cancel", headers=AUTH).status_code
            == 202
        )
        assert wait(client, identity)["status"] == "cancelled"


def test_graceful_shutdown_interrupts_active_job(settings):
    started = threading.Event()

    def execute(options, initial):
        started.set()
        assert options.cancel.wait(5)
        raise ExecutionCancelled

    with TestClient(create_app(settings, executor=execute)) as client:
        identity = submit(client).json()["run"]["id"]
        assert started.wait(3)
    assert Store(settings.database).get(identity)["status"] == "interrupted"


def test_worker_errors_hide_payload_and_failed_trace_keeps_report(settings, caplog):
    def broken(options, initial):
        raise RuntimeError(SECRET)

    with TestClient(create_app(settings, executor=broken)) as client:
        identity = submit(client).json()["run"]["id"]
        row = wait(client, identity)
        assert row["status"] == "failed" and row["error_code"] == "execution_failed"
        assert SECRET not in json.dumps(row) + caplog.text

    def trace_error(options, initial):
        return replace(initial, trace={"status": "partial", "has_errors": True})

    with TestClient(create_app(settings, executor=trace_error)) as client:
        identity = submit(client).json()["run"]["id"]
        row = wait(client, identity)
        assert row["status"] == "failed" and row["has_report"]
        assert row["error_code"] == "cloudtrail_incomplete"
        assert (
            client.get(f"/api/v1/runs/{identity}/report", headers=AUTH).status_code
            == 200
        )
        assert (
            client.get(f"/api/v1/runs/{identity}/comparison", headers=AUTH).status_code
            == 409
        )


def test_only_one_worker_owner_can_open_a_database(settings):
    with TestClient(create_app(settings, start_worker=False)):
        with pytest.raises(Timeout):
            with TestClient(create_app(settings, start_worker=False)):
                pytest.fail("Second worker owner must be rejected")


def test_history_pagination_and_comparison_use_project_scope(settings):
    with TestClient(create_app(settings)) as client:
        first = submit(client).json()["run"]["id"]
        wait(client, first)
        assert (
            client.get(f"/api/v1/runs/{first}/comparison", headers=AUTH).json()[
                "status"
            ]
            == "baseline_missing"
        )
        second = submit(
            client, {"mode": "import", "plan": plan([entry("t3.large")])}
        ).json()["run"]["id"]
        wait(client, second)
        compared = client.get(f"/api/v1/runs/{second}/comparison", headers=AUTH).json()
        assert compared["baseline_run_id"] == first
        assert compared["summary"]["changed"] == 1
        third = submit(client, {"mode": "import", "plan": plan()}).json()["run"]["id"]
        wait(client, third)
        compared = client.get(f"/api/v1/runs/{third}/comparison", headers=AUTH).json()
        assert compared["summary"]["no_longer_reported"] == 1
        assert "does not prove repair" in compared["notes"][0]
        page = client.get("/api/v1/projects/demo/runs?limit=2", headers=AUTH).json()
        assert [row["id"] for row in page["items"]] == [third, second]
        rest = client.get(
            f"/api/v1/projects/demo/runs?before={page['next_before']}", headers=AUTH
        ).json()
        assert [row["id"] for row in rest["items"]] == [first]
        assert (
            client.get(
                f"/api/v1/runs/{first}/comparison?baseline_id={third}", headers=AUTH
            ).status_code
            == 409
        )


def test_project_change_does_not_execute_stale_queued_work(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        identity = submit(client).json()["run"]["id"]
    changed = replace(
        settings,
        projects={"demo": replace(settings.projects["demo"], workspace="another")},
    )
    with TestClient(create_app(changed)) as client:
        row = wait(client, identity)
        assert (
            row["status"] == "failed"
            and row["error_code"] == "project_configuration_changed"
        )


def test_refresh_runs_shared_engine_with_fixed_workspace(
    settings, fake_terraform, monkeypatch
):
    project = replace(
        settings.projects["demo"], allow_refresh=True, workspace="backend-test"
    )
    settings = replace(settings, projects={"demo": project})
    monkeypatch.setenv("TF_WORKSPACE", "unrelated")
    with TestClient(create_app(settings)) as client:
        identity = submit(client, {"mode": "refresh"}).json()["run"]["id"]
        assert wait(client, identity)["status"] == "succeeded"
    calls = [json.loads(line) for line in fake_terraform.read_text().splitlines()]
    assert [call["args"][0] for call in calls] == ["version", "plan", "show"]
    assert all(call["env"].get("TF_WORKSPACE") == "backend-test" for call in calls)
    assert "-refresh-only" in calls[1]["args"]


def test_atomic_claims_and_queue_replay_under_contention(settings):
    store = Store(settings.database)
    store.initialize()
    request = {"mode": "refresh", "trace": False, "lookback_days": 7, "timeout": 5}
    for _ in range(10):
        store.enqueue(settings.projects["demo"], request)
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows = list(pool.map(lambda _: store.claim(), range(10)))
    assert len({row["id"] for row in rows}) == 10
    assert store.claim() is None
    with pytest.raises(StoreConflict, match="queue_full"):
        store.enqueue(settings.projects["demo"], request, max_pending=10)


@pytest.mark.parametrize(
    "old,new,expected",
    [
        (entry(), entry(), "unchanged"),
        (entry(), entry("t3.large"), "changed"),
        (
            entry(SECRET, sensitive=True),
            entry("other", sensitive=True),
            "indeterminate",
        ),
        (entry(SECRET), entry("other", sensitive=True), "indeterminate"),
    ],
)
def test_comparison_does_not_copy_values_or_claim_hidden_changes_are_unchanged(
    old, new, expected
):
    before = parse_plan(json.dumps(plan([old]))).to_dict()
    after = parse_plan(json.dumps(plan([new]))).to_dict()
    before["resources"][0]["source"] = {"file": "old.tf", "start_line": 1}
    after["resources"][0]["trace"] = {"actor": "different actor"}
    compared = compare_runs(
        {"id": "new", "report_json": json.dumps(after)},
        {"id": "old", "report_json": json.dumps(before)},
    )
    assert compared["resources"][0]["status"] == expected
    assert SECRET not in json.dumps(compared)


def test_comparison_keeps_null_absent_and_literal_map_key_paths_distinct():
    old = parse_plan(json.dumps(plan([entry()]))).to_dict()
    new = deepcopy(old)
    old["resources"][0]["attributes"] = [
        {
            "path": ["tags", "a.b"],
            "before": {"status": "known", "value": None},
            "after": {"status": "absent"},
        }
    ]
    new["resources"][0]["attributes"] = [
        {
            "path": ["tags", "a", "b"],
            "before": {"status": "known", "value": None},
            "after": {"status": "known", "value": None},
        }
    ]
    compared = compare_runs(
        {"id": "new", "report_json": json.dumps(new)},
        {"id": "old", "report_json": json.dumps(old)},
    )
    assert compared["resources"][0]["status"] == "changed"
    assert len(compared["resources"][0]["changed_paths"]) == 2


def test_registry_resolves_paths_and_rejects_duplicate_project_ids(tmp_path):
    root = tmp_path / "infra"
    root.mkdir()
    (root / "main.tf").write_text('resource "aws_instance" "demo" {}')
    config = tmp_path / "projects.json"
    project = {"id": "demo", "name": "Demo", "path": "infra"}
    config.write_text(json.dumps({"projects": [project]}))
    assert load_projects(config)["demo"].path == root.resolve()
    config.write_text(json.dumps({"projects": [project, project]}))
    with pytest.raises(ValueError):
        load_projects(config)


def test_database_cannot_overlap_terraform_metadata(settings):
    data = settings.projects["demo"].path / "cache"
    data.mkdir()
    project = replace(settings.projects["demo"], data_dir=data)
    with pytest.raises(ValueError, match="outside"):
        replace(
            settings, projects={"demo": project}, database=data / "history.sqlite3"
        ).validate()


@pytest.mark.parametrize("difference", ["mode", "workspace", "project"])
def test_comparison_rejects_incompatible_baselines(settings, difference):
    store = Store(settings.database)
    store.initialize()
    request = {"mode": "import", "trace": False, "lookback_days": 7, "timeout": 5}
    project = settings.projects["demo"]
    old_project = (
        replace(project, workspace="other")
        if difference == "workspace"
        else replace(project, id="other")
        if difference == "project"
        else project
    )
    old_request = {**request, "mode": "refresh"} if difference == "mode" else request
    old, _ = store.enqueue(old_project, old_request)
    store.claim()
    report = parse_plan(json.dumps(plan([entry()]))).to_dict()
    store.finish(old["id"], "succeeded", report)
    current, _ = store.enqueue(project, request)
    store.claim()
    store.finish(current["id"], "succeeded", report)
    with TestClient(create_app(settings, start_worker=False)) as client:
        prefix = f"/api/v1/runs/{current['id']}/comparison"
        assert client.get(prefix, headers=AUTH).json()["status"] == "baseline_missing"
        response = client.get(prefix + f"?baseline_id={old['id']}", headers=AUTH)
        assert response.status_code == 409


def test_cancelling_refresh_reaps_actual_terraform_process(
    settings, fake_terraform, monkeypatch
):
    project = replace(settings.projects["demo"], allow_refresh=True)
    settings = replace(settings, projects={"demo": project})
    monkeypatch.setenv("FAKE_TERRAFORM_MODE", "timeout")
    with TestClient(create_app(settings)) as client:
        identity = submit(client, {"mode": "refresh"}).json()["run"]["id"]
        # On Windows the distlib launcher and venv redirector start two Python
        # processes before plan. Allow cold-start overhead before testing cancel.
        deadline = time.monotonic() + 20
        calls = []
        while time.monotonic() < deadline:
            if fake_terraform.exists():
                calls = [
                    json.loads(line) for line in fake_terraform.read_text().splitlines()
                ]
            if any(call["args"][0] == "plan" for call in calls):
                break
            time.sleep(0.01)
        assert any(call["args"][0] == "plan" for call in calls)
        response = client.post(f"/api/v1/runs/{identity}/cancel", headers=AUTH)
        assert response.status_code == 202
        assert wait(client, identity)["status"] == "cancelled"
