"""One background consumer of the durable SQLite queue."""

import json
import threading

from infralens.drift import AttributeChange, DriftResult, ResourceDrift
from infralens.drift_gate import evaluate_gate
from infralens.drift_service import collect_drift
from infralens.errors import ExecutionCancelled
from infralens.options import DriftOptions


def restore_imported(report):
    """Rehydrate only the normalized model previously produced by parse_plan."""
    return DriftResult(
        report["terraform_version"],
        tuple(
            ResourceDrift(
                r["address"],
                r["resource_type"],
                tuple(r["actions"]),
                tuple(
                    AttributeChange(tuple(a["path"]), a["before"], a["after"])
                    for a in r["attributes"]
                ),
                r.get("identifiers", {}),
                network_context=r.get("network_context"),
            )
            for r in report["resources"]
        ),
        report["input_mode"],
        report["checked_at"],
        tuple(report["notes"]),
        tuple(report.get("normalizations", [])),
    )


class Worker:
    def __init__(self, settings, store, executor=collect_drift):
        self.settings, self.store, self.executor = settings, store, executor
        self.stop_event, self.wake = threading.Event(), threading.Event()
        self.lock = threading.Lock()
        self.active = None
        self.thread = threading.Thread(
            target=self._loop, name="drift-worker", daemon=True
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wake.set()
        with self.lock:
            if self.active:
                self.active[1].set()
        self.thread.join()

    def cancel(self, identity):
        with self.lock:
            if self.active and self.active[0] == identity:
                self.active[1].set()

    def _loop(self):
        while not self.stop_event.is_set():
            job = self.store.claim()
            if job is None:
                self.wake.wait(0.2)
                self.wake.clear()
                continue
            cancel = threading.Event()
            with self.lock:
                self.active = (job["id"], cancel)
            try:
                latest = self.store.get(job["id"])
                if self.stop_event.is_set() or latest["cancel_requested"]:
                    raise ExecutionCancelled
                project = self.settings.projects.get(job["project_id"])
                if project is None or project.scope_key() != job["scope_key"]:
                    self.store.finish(
                        job["id"], "failed", error_code="project_configuration_changed"
                    )
                    continue
                request = json.loads(job["request_json"])
                if (
                    request["trace"]
                    and not project.allow_trace
                    or request["mode"] == "refresh"
                    and not project.allow_refresh
                    or request["mode"] == "import"
                    and not project.allow_import
                    or request["timeout"] > project.max_timeout
                ):
                    self.store.finish(
                        job["id"], "failed", error_code="project_configuration_changed"
                    )
                    continue
                initial = (
                    restore_imported(json.loads(job["input_json"]))
                    if job["input_json"]
                    else None
                )
                options = DriftOptions(
                    project.path,
                    project.var_files,
                    "json",
                    None,
                    project.profile,
                    project.region,
                    request["trace"],
                    request["lookback_days"] if request["trace"] else None,
                    False,
                    timeout=request["timeout"],
                    workspace=project.workspace,
                    data_dir=project.data_dir or project.path / ".terraform",
                    cancel=cancel,
                )
                result = self.executor(options, initial)
                if cancel.is_set():
                    raise ExecutionCancelled
                report = result.to_dict()
                gate = request.get("gate")
                if gate:
                    report["gate"] = evaluate_gate(
                        result,
                        fail_on_drift=gate["any_drift"],
                        fail_on_priority=gate["minimum_priority"],
                        fail_on_unknown=gate["unknown_priority"],
                    )
                failed = result.trace and result.trace.get("has_errors")
                self.store.finish(
                    job["id"],
                    "failed" if failed else "succeeded",
                    report,
                    "cloudtrail_incomplete" if failed else None,
                )
            except ExecutionCancelled:
                self.store.finish(
                    job["id"],
                    "interrupted" if self.stop_event.is_set() else "cancelled",
                    error_code="worker_stopped"
                    if self.stop_event.is_set()
                    else "cancel_requested",
                )
            except Exception:
                # Do not persist or log SDK/tool exception payloads.
                self.store.finish(job["id"], "failed", error_code="execution_failed")
            finally:
                with self.lock:
                    self.active = None
