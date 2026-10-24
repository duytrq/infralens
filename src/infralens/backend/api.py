"""Local authenticated API over a durable queue and normalized drift history."""

import asyncio
import json
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

from infralens.backend.comparison import compare_runs
from infralens.backend.config import Settings
from infralens.backend.store import Store, StoreConflict, public_run
from infralens.backend.worker import Worker
from infralens.drift import parse_plan
from infralens.errors import ExecutionError

RunStatus = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "interrupted"
]


class GateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    any_drift: bool = False
    minimum_priority: Literal["high", "medium"] | None = None
    unknown_priority: bool = False

    def enabled(self):
        return (
            self.any_drift or self.minimum_priority is not None or self.unknown_priority
        )


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["refresh", "import"] = "refresh"
    plan: dict[str, Any] | None = None
    trace: bool = False
    lookback_days: int = Field(default=7, ge=1, le=90)
    timeout: int | None = Field(default=None, ge=1, le=600)
    gate: GateRequest | None = None


def fail(status, code, message):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


class RequestGuard:
    """Bound actual body bytes, avoid caching reports, and hide raw error payloads."""

    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def guarded_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        async def respond(status, code, message):
            response = JSONResponse(
                {"error": {"code": code, "message": message}}, status_code=status
            )
            await response(scope, receive, guarded_send)

        try:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.limit:
                    return await respond(
                        413,
                        "body_too_large",
                        "Request body exceeds the configured limit.",
                    )
                if not message.get("more_body", False):
                    break
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {
                        "type": "http.request",
                        "body": bytes(body),
                        "more_body": False,
                    }
                return await receive()

            await self.app(scope, buffered_receive, guarded_send)
        except sqlite3.Error:
            if not started:
                await respond(
                    503,
                    "history_unavailable",
                    "History storage is temporarily unavailable.",
                )
        except Exception:
            if not started:
                await respond(
                    500, "internal_error", "The request could not be completed."
                )


def create_app(settings: Settings, *, executor=None, start_worker=True):
    settings.validate()
    store = Store(settings.database)
    worker = Worker(settings, store, **({"executor": executor} if executor else {}))
    ownership = FileLock(str(settings.database.resolve()) + ".worker.lock")

    @asynccontextmanager
    async def lifespan(app):
        settings.database.resolve().parent.mkdir(parents=True, exist_ok=True)
        ownership.acquire(timeout=0)
        try:
            store.initialize()
            store.recover()
            if start_worker:
                worker.start()
            yield
        finally:
            if start_worker and worker.thread.ident is not None:
                await asyncio.to_thread(worker.stop)
            ownership.release()

    app = FastAPI(title="InfraLens Drift API", version="1.0.0", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker
    scheme = HTTPBearer(auto_error=False)

    def authorize(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Security(scheme)],
    ):
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or not secrets.compare_digest(
                credentials.credentials.encode(), settings.api_token.encode()
            )
        ):
            fail(401, "unauthorized", "A valid bearer token is required.")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Pydantic's default error response can contain private request values.
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed; check the API schema.",
                }
            },
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse({"error": error.detail}, status_code=error.status_code)

    def project_for(identity):
        project = settings.projects.get(identity)
        if project is None:
            fail(404, "project_not_found", "Project is not registered.")
        return project

    def run_for(identity):
        if not re.fullmatch(r"[0-9a-f]{32}", identity):
            fail(404, "run_not_found", "Run was not found.")
        row = store.get(identity)
        if row is None:
            fail(404, "run_not_found", "Run was not found.")
        return row

    authenticated = [Depends(authorize)]

    # Only these bundled files are public. Reports and project data stay behind
    # bearer authentication; no filesystem path is accepted from the browser.
    dashboard = Path(__file__).with_name("static")
    dashboard_headers = {
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'; object-src 'none'"
        ),
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
    }

    @app.get("/", include_in_schema=False)
    def dashboard_page():
        return FileResponse(dashboard / "index.html", headers=dashboard_headers)

    @app.get("/dashboard/{asset}", include_in_schema=False)
    def dashboard_asset(asset: str):
        if asset not in {"app.js", "app.css", "demo-plan.json"}:
            fail(404, "asset_not_found", "Dashboard asset was not found.")
        return FileResponse(dashboard / asset, headers=dashboard_headers)

    @app.get("/health")
    def health():
        alive = worker.thread.is_alive() if start_worker else False
        return {
            "status": "ok" if alive or not start_worker else "degraded",
            "worker_alive": alive,
        }

    @app.get("/api/v1/projects", dependencies=authenticated)
    def projects():
        return {
            "items": [
                {
                    "id": p.id,
                    "name": p.name,
                    "workspace": p.workspace,
                    "allow_refresh": p.allow_refresh,
                    "allow_import": p.allow_import,
                    "allow_trace": p.allow_trace,
                    "max_timeout": p.max_timeout,
                }
                for p in settings.projects.values()
            ]
        }

    @app.post(
        "/api/v1/projects/{project_id}/runs",
        status_code=202,
        dependencies=authenticated,
    )
    def submit(
        project_id: str,
        request: RunRequest,
        idempotency_key: Annotated[str | None, Header()] = None,
    ):
        project = project_for(project_id)
        if start_worker and not worker.thread.is_alive():
            fail(503, "worker_unavailable", "The worker is unavailable.")
        if idempotency_key is not None and not re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}", idempotency_key
        ):
            fail(
                400,
                "invalid_idempotency_key",
                "Use 1-128 letters, digits, underscores or hyphens.",
            )
        if (
            request.mode == "refresh"
            and not project.allow_refresh
            or request.mode == "import"
            and not project.allow_import
        ):
            fail(403, "mode_not_allowed", "This run mode is disabled for the project.")
        if request.trace and not project.allow_trace:
            fail(
                403,
                "trace_not_allowed",
                "CloudTrail lookup is disabled for the project.",
            )
        timeout = (
            request.timeout
            if request.timeout is not None
            else min(120, project.max_timeout)
        )
        if timeout > project.max_timeout:
            fail(400, "timeout_exceeded", "Timeout exceeds the project's limit.")
        normalized = None
        if request.mode == "import":
            if request.plan is None:
                fail(400, "plan_required", "Import mode requires Terraform plan JSON.")
            try:
                normalized = parse_plan(
                    json.dumps(request.plan, allow_nan=False)
                ).to_dict()
            except (ExecutionError, ValueError, TypeError, RecursionError):
                fail(
                    422, "invalid_plan", "The Terraform plan is invalid or unsupported."
                )
        elif request.plan is not None:
            fail(400, "unexpected_plan", "Refresh mode does not accept a plan payload.")
        payload = {
            "mode": request.mode,
            "trace": request.trace,
            "lookback_days": request.lookback_days,
            "timeout": timeout,
        }
        # Omit disabled criteria so replays of pre-gate requests keep their
        # original fingerprint, including after a queue/database restart.
        if request.gate is not None and request.gate.enabled():
            payload["gate"] = request.gate.model_dump()
        try:
            row, created = store.enqueue(
                project, payload, normalized, idempotency_key, settings.max_pending
            )
        except StoreConflict as error:
            code = str(error)
            fail(
                429 if code == "queue_full" else 409,
                code,
                "The request conflicts with queue or idempotency state.",
            )
        worker.wake.set()
        return {"run": public_run(row), "created": created}

    @app.get("/api/v1/projects/{project_id}/runs", dependencies=authenticated)
    def history(
        project_id: str,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        before: Annotated[int | None, Query(ge=1)] = None,
        status: RunStatus | None = None,
    ):
        project_for(project_id)
        return store.history(project_id, limit, before, status)

    @app.get("/api/v1/runs/{run_id}", dependencies=authenticated)
    def get_run(run_id: str):
        return public_run(run_for(run_id))

    @app.get("/api/v1/runs/{run_id}/report", dependencies=authenticated)
    def get_report(run_id: str):
        row = run_for(run_id)
        if row["report_json"] is None:
            fail(
                409 if row["status"] in ("queued", "running") else 404,
                "report_unavailable",
                "This run has no report available yet.",
            )
        return json.loads(row["report_json"])

    @app.post(
        "/api/v1/runs/{run_id}/cancel", status_code=202, dependencies=authenticated
    )
    def cancel_run(run_id: str):
        run_for(run_id)
        try:
            row = store.cancel(run_id)
        except StoreConflict:
            fail(409, "run_already_finished", "The run has already finished.")
        worker.cancel(run_id)
        return public_run(row)

    @app.get("/api/v1/runs/{run_id}/comparison", dependencies=authenticated)
    def comparison(run_id: str, baseline_id: str | None = None):
        current = run_for(run_id)
        if current["status"] != "succeeded":
            fail(
                409,
                "run_not_successful",
                "Comparison requires a successful completed run.",
            )
        baseline = (
            run_for(baseline_id) if baseline_id is not None else store.baseline(current)
        )
        if baseline is not None and (
            baseline["project_id"] != current["project_id"]
            or baseline["scope_key"] != current["scope_key"]
            or baseline["mode"] != current["mode"]
            or baseline["sequence"] >= current["sequence"]
            or baseline["status"] != "succeeded"
        ):
            fail(
                409,
                "baseline_incompatible",
                "Choose an earlier successful run in the same project, mode and scope.",
            )
        return compare_runs(current, baseline)

    app.add_middleware(RequestGuard, limit=settings.max_body_bytes)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )
    return app
