"""SQLite queue and normalized report history with short, per-operation connections."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone


class StoreConflict(Exception):
    """A controlled state conflict."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def public_run(row):
    result = {
        key: row[key]
        for key in (
            "id",
            "sequence",
            "project_id",
            "mode",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "error_code",
        )
    }
    result.update(
        cancel_requested=bool(row["cancel_requested"]),
        has_report=row["report_json"] is not None,
        has_drift=bool(row["has_drift"]) if row["has_drift"] is not None else None,
        request=json.loads(row["request_json"]),
    )
    gate = (
        json.loads(row["report_json"]).get("gate")
        if row["report_json"] is not None
        else None
    )
    result["gate"] = (
        {key: gate[key] for key in ("status", "exit_code", "matched_count")}
        if gate is not None
        else None
    )
    return result


class Store:
    def __init__(self, path):
        self.path = path.resolve()

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                yield connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as c:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise StoreConflict("unsupported_database_version")
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    request_json TEXT NOT NULL,
                    input_json TEXT,
                    report_json TEXT,
                    has_drift INTEGER,
                    error_code TEXT,
                    idempotency_key TEXT,
                    fingerprint TEXT NOT NULL,
                    UNIQUE(project_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS runs_project_history
                    ON runs(project_id, sequence DESC);
                CREATE INDEX IF NOT EXISTS runs_queue ON runs(status, sequence);
                PRAGMA user_version=1;
            """)

    def recover(self):
        with self.connection() as c:
            c.execute(
                """UPDATE runs SET
                status=CASE WHEN cancel_requested=1 THEN 'cancelled'
                    ELSE 'interrupted' END,
                finished_at=?, error_code='worker_interrupted', input_json=NULL
                WHERE status='running'""",
                (utc_now(),),
            )

    def enqueue(self, project, request, normalized=None, key=None, max_pending=100):
        comparable = dict(normalized) if normalized is not None else None
        if comparable is not None:
            comparable.pop("checked_at", None)
        fingerprint = hashlib.sha256(
            json.dumps(
                [project.scope_key(), request, comparable],
                sort_keys=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            if key is not None:
                old = c.execute(
                    "SELECT * FROM runs WHERE project_id=? AND idempotency_key=?",
                    (project.id, key),
                ).fetchone()
                if old is not None:
                    if old["fingerprint"] != fingerprint:
                        raise StoreConflict("idempotency_conflict")
                    return dict(old), False
            pending = c.execute(
                "SELECT COUNT(*) FROM runs WHERE status IN ('queued','running')"
            ).fetchone()[0]
            if pending >= max_pending:
                raise StoreConflict("queue_full")
            identity = uuid.uuid4().hex
            c.execute(
                """INSERT INTO runs
                (id,project_id,scope_key,mode,status,created_at,request_json,input_json,
                 idempotency_key,fingerprint) VALUES (?,?,?,?,'queued',?,?,?,?,?)""",
                (
                    identity,
                    project.id,
                    project.scope_key(),
                    request["mode"],
                    utc_now(),
                    json.dumps(request),
                    json.dumps(normalized) if normalized is not None else None,
                    key,
                    fingerprint,
                ),
            )
            return dict(
                c.execute("SELECT * FROM runs WHERE id=?", (identity,)).fetchone()
            ), True

    def claim(self):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT * FROM runs WHERE status='queued' ORDER BY sequence LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            c.execute(
                "UPDATE runs SET status='running',started_at=? WHERE id=?",
                (utc_now(), row["id"]),
            )
            return dict(
                c.execute("SELECT * FROM runs WHERE id=?", (row["id"],)).fetchone()
            )

    def get(self, identity):
        with self.connection() as c:
            row = c.execute("SELECT * FROM runs WHERE id=?", (identity,)).fetchone()
            return dict(row) if row is not None else None

    def history(self, project_id, limit=20, before=None, status=None, gate_status=None):
        clauses, params = ["project_id=?"], [project_id]
        if before is not None:
            clauses.append("sequence<?")
            params.append(before)
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        # Filter before pagination so each cursor walks matching rows only.
        # Request metadata distinguishes a disabled gate from an enabled gate
        # which has not produced a decision. Old requests have no gate key.
        if gate_status in ("passed", "failed", "incomplete"):
            clauses.append("json_extract(report_json, '$.gate.status')=?")
            params.append(gate_status)
        elif gate_status == "disabled":
            clauses.append("json_extract(request_json, '$.gate') IS NULL")
        elif gate_status in ("pending", "unavailable"):
            clauses.extend(
                [
                    "json_extract(request_json, '$.gate') IS NOT NULL",
                    "json_extract(report_json, '$.gate.status') IS NULL",
                    "status IN ('queued','running')"
                    if gate_status == "pending"
                    else "status NOT IN ('queued','running')",
                ]
            )
        elif gate_status is not None:
            raise ValueError("Unsupported gate history filter.")
        with self.connection() as c:
            rows = c.execute(
                "SELECT * FROM runs WHERE "
                + " AND ".join(clauses)
                + " ORDER BY sequence DESC LIMIT ?",
                (*params, limit + 1),
            ).fetchall()
        return {
            "items": [public_run(row) for row in rows[:limit]],
            "next_before": rows[limit - 1]["sequence"] if len(rows) > limit else None,
        }

    def finish(self, identity, status, report=None, error_code=None):
        with self.connection() as c:
            # Cancellation and completion race on this row. Decide in the same
            # UPDATE, so an accepted cancel cannot retain a successful gate or
            # stale execution error after the worker's last checkpoint.
            c.execute(
                """UPDATE runs SET
                status=CASE WHEN cancel_requested=1 THEN 'cancelled' ELSE ? END,
                report_json=CASE WHEN cancel_requested=1 THEN NULL ELSE ? END,
                has_drift=CASE WHEN cancel_requested=1 THEN NULL ELSE ? END,
                error_code=CASE WHEN cancel_requested=1 THEN 'cancel_requested'
                    ELSE ? END,
                finished_at=?, input_json=NULL
                WHERE id=? AND status='running'""",
                (
                    status,
                    json.dumps(report, allow_nan=False) if report is not None else None,
                    int(report["has_drift"]) if report is not None else None,
                    error_code,
                    utc_now(),
                    identity,
                ),
            )

    def cancel(self, identity):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM runs WHERE id=?", (identity,)).fetchone()
            if row is None:
                return None
            if row["status"] not in ("queued", "running"):
                raise StoreConflict("run_already_finished")
            if row["status"] == "queued":
                c.execute(
                    """UPDATE runs SET status='cancelled',cancel_requested=1,
                    finished_at=?,input_json=NULL WHERE id=?""",
                    (utc_now(), identity),
                )
            else:
                c.execute("UPDATE runs SET cancel_requested=1 WHERE id=?", (identity,))
            return dict(
                c.execute("SELECT * FROM runs WHERE id=?", (identity,)).fetchone()
            )

    def baseline(self, row):
        with self.connection() as c:
            previous = c.execute(
                """SELECT * FROM runs
                WHERE project_id=? AND scope_key=? AND mode=? AND sequence<?
                AND status='succeeded' AND report_json IS NOT NULL
                ORDER BY sequence DESC LIMIT 1""",
                (row["project_id"], row["scope_key"], row["mode"], row["sequence"]),
            ).fetchone()
            return dict(previous) if previous is not None else None
