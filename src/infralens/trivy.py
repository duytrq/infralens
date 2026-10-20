"""Trivy 0.76 adapter. Native reports remain the export contract."""

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from infralens.errors import ExecutionError
from infralens.options import SEVERITIES
from infralens.process import run_process


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    title: str
    message: str
    resource: str | None
    file: str | None
    start_line: int | None
    end_line: int | None
    remediation: str
    references: tuple[str, ...]


@dataclass(frozen=True)
class ScanResult:
    engine_version: str | None
    findings: tuple[Finding, ...]
    diagnostics: tuple[str, ...]
    raw: dict


def parse_report(payload: str, diagnostics: tuple[str, ...] = ()) -> ScanResult:
    """Validate consumed fields, tolerating optional and future native fields."""
    try:
        raw = json.loads(payload)
        if not isinstance(raw, dict) or raw.get("SchemaVersion") != 2:
            raise ValueError
        results = raw.get("Results", [])
        if not isinstance(results, list):
            raise ValueError
        findings = []
        for result in results:
            if not isinstance(result, dict):
                raise ValueError
            items = result.get("Misconfigurations", [])
            if not isinstance(items, list):
                raise ValueError
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError
                status = item.get("Status", "FAIL")
                if status in ("PASS", "EXCEPTION"):
                    continue
                if status != "FAIL":
                    raise ValueError
                severity = item.get("Severity")
                rule_id = item.get("ID")
                if (
                    severity not in SEVERITIES
                    or not isinstance(rule_id, str)
                    or not rule_id
                ):
                    raise ValueError
                cause = item.get("CauseMetadata", {})
                if not isinstance(cause, dict):
                    raise ValueError
                references = item.get("References", [])
                if not isinstance(references, list) or any(
                    not isinstance(r, str) for r in references
                ):
                    raise ValueError
                # A root-module result (Target='.') has no concrete source file.
                target = _text(result.get("Target"))
                file = None if target in (None, ".") else target
                findings.append(
                    Finding(
                        rule_id,
                        severity,
                        _text(item.get("Title")) or rule_id,
                        _text(item.get("Message"))
                        or _text(item.get("Title"))
                        or rule_id,
                        _text(cause.get("Resource")),
                        file,
                        _line(cause.get("StartLine")),
                        _line(cause.get("EndLine")),
                        _text(item.get("Resolution")) or "",
                        tuple(references),
                    )
                )
        info = raw.get("Trivy", {})
        if not isinstance(info, dict):
            raise ValueError
        engine_version = _text(info.get("Version"))
    except (ValueError, TypeError, KeyError):
        raise ExecutionError(
            "Trivy returned an invalid or unsupported JSON report (expected schema 2)."
        ) from None
    return ScanResult(engine_version, tuple(findings), diagnostics, raw)


def _text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError
    return value or None


def _line(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def _diagnostics(stderr: str) -> tuple[str, ...]:
    """Never replay engine diagnostics: they may contain source or credentials."""
    messages = []
    for line in stderr.splitlines():
        if "\tERROR\t" in line:
            if "Falling back to embedded checks" in line:
                messages.append(
                    "Trivy used embedded checks because updated checks "
                    "were unavailable."
                )
            else:
                raise ExecutionError(
                    "Trivy could not completely analyze the project. "
                    "Check Terraform syntax, module access and cache permissions."
                )
        elif "\tWARN\t" in line:
            messages.append("Trivy reported a warning; analysis may be incomplete.")
    return tuple(dict.fromkeys(messages))


class Trivy:
    def __init__(self, root: Path):
        self.root = root
        executable = shutil.which("trivy")
        if executable is None:
            raise ExecutionError(
                "Trivy 0.76.x was not found on PATH. "
                "Install Trivy or use the InfraLens Docker image."
            )
        self.executable = executable
        # Parent TRIVY_* values must not override scanner, filtering or outputs.
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("TRIVY_") or key == "TRIVY_CACHE_DIR"
        }
        self.env["NO_COLOR"] = "1"
        self.env["TRIVY_DISABLE_TELEMETRY"] = "true"
        result = self._run(["--version"], timeout=10, step="version check")
        match = re.search(r"^Version:\s*(\S+)", result.stdout, re.MULTILINE)
        if not match or not re.fullmatch(r"0\.76\.\d+", match[1]):
            raise ExecutionError(
                "Unsupported Trivy version. Install Trivy 0.76.x "
                "or use the InfraLens Docker image."
            )
        self.version = match[1]

    def _run(self, arguments: list[str], *, timeout: int, step: str):
        try:
            result = run_process(
                [self.executable, "--config", "", *arguments],
                cwd=self.root,
                timeout=timeout,
                env=self.env,
            )
        except ExecutionError as exc:
            raise ExecutionError(f"Trivy {step} failed: {exc}") from None
        if result.returncode:
            raise ExecutionError(
                f"Trivy {step} failed (exit {result.returncode}). "
                "Check installation, project and network/cache access."
            )
        return result

    def scan(self, timeout: int) -> ScanResult:
        ignorefile = self.root / ".trivyignore"
        result = self._run(
            [
                "config",
                "--misconfig-scanners",
                "terraform",
                "--format",
                "json",
                "--severity",
                ",".join(SEVERITIES),
                "--exit-code",
                "0",
                "--disable-telemetry",
                "--skip-version-check",
                "--ignorefile",
                str(ignorefile) if ignorefile.exists() else "",
                "--timeout",
                f"{timeout}s",
                ".",
            ],
            timeout=timeout,
            step="scan",
        )
        return parse_report(result.stdout, _diagnostics(result.stderr))

    def convert(self, source: Path, format: str, severity: tuple[str, ...]) -> str:
        result = self._run(
            [
                "convert",
                "--format",
                format,
                "--severity",
                ",".join(severity),
                "--exit-code",
                "0",
                "--ignorefile",
                "",
                str(source),
            ],
            timeout=60,
            step="report conversion",
        )
        _diagnostics(result.stderr)
        # Avoid emitting truncated or malformed machine-readable output.
        try:
            report = json.loads(result.stdout)
            if format == "json":
                parse_report(result.stdout)
            elif (
                not isinstance(report, dict)
                or report.get("version") != "2.1.0"
                or not isinstance(report.get("runs"), list)
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise ExecutionError(
                "Trivy report conversion returned invalid JSON/SARIF."
            ) from None
        return result.stdout
