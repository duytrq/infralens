"""Plain terminal rendering and atomic report publication."""

import os
import tempfile
from collections import Counter
from pathlib import Path

from infralens.options import SEVERITIES
from infralens.trivy import ScanResult


def plain(value: str) -> str:
    """Keep engine-controlled fields from injecting terminal control sequences."""
    return " ".join("".join(c if c.isprintable() else " " for c in value).split())


def render_table(result: ScanResult, severity: tuple[str, ...]) -> str:
    counts = Counter(f.severity for f in result.findings)
    visible = sorted(
        (f for f in result.findings if f.severity in severity),
        key=lambda f: (
            -SEVERITIES.index(f.severity),
            f.file or "",
            f.start_line or 0,
            f.rule_id,
        ),
    )
    lines = [
        f"Security scan (Trivy {plain(result.engine_version or 'unknown')})",
        f"Findings: {len(result.findings)} | Displayed: {len(visible)}",
        "Severities (all): "
        + ", ".join(f"{level}: {counts[level]}" for level in reversed(SEVERITIES)),
    ]
    if not result.findings:
        lines.append(
            "No security findings reported; see scan warnings."
            if result.diagnostics
            else "No security findings found."
        )
    elif not visible:
        lines.append("No findings match the selected severities.")
    else:
        lines.extend(["", "SEVERITY | RULE | LOCATION | RESOURCE | WARNING"])
        for finding in visible:
            location = finding.file or "unknown location"
            if finding.file and finding.start_line:
                location += f":{finding.start_line}"
                if finding.end_line and finding.end_line > finding.start_line:
                    location += f"-{finding.end_line}"
            lines.append(
                " | ".join(
                    plain(value)
                    for value in (
                        finding.severity,
                        finding.rule_id,
                        location,
                        finding.resource or "-",
                        finding.message,
                    )
                )
            )
    return "\n".join(lines) + "\n"


def write_report(destination: Path, content: str) -> None:
    """An interrupted write must not truncate an existing report."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=".infralens-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
