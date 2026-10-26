"""Validated options passed to command handlers."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event

SEVERITIES = ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL")


class ScanFormat(str, Enum):
    table = "table"
    json = "json"
    sarif = "sarif"


class DriftFormat(str, Enum):
    table = "table"
    json = "json"


@dataclass(frozen=True)
class ScanOptions:
    path: Path
    severity: tuple[str, ...]
    format: str
    output: Path | None
    # Inclusive threshold across ALL findings, independent of the report filter.
    fail_on: str | None
    timeout: int = 300


@dataclass(frozen=True)
class DriftOptions:
    path: Path
    var_files: tuple[Path, ...]
    format: str
    output: Path | None
    profile: str | None
    region: str | None
    trace: bool
    lookback_days: int | None
    fail_on_drift: bool
    timeout: int = 300
    plan_json: Path | None = None
    workspace: str | None = None
    data_dir: Path | None = None
    cancel: Event | None = None
    fail_on_priority: str | None = None
    fail_on_unknown: bool = False
