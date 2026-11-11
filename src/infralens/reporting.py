"""Readable terminal findings and atomic, unstyled report publication."""

import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

import typer

from infralens.options import SEVERITIES
from infralens.trivy import ScanResult


def plain(value: str) -> str:
    """Keep engine-controlled fields from injecting terminal control sequences."""
    return " ".join("".join(c if c.isprintable() else " " for c in value).split())


def color_enabled(no_color: bool = False) -> bool:
    if no_color or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return bool(sys.stdout.isatty())


def _severity(text: str, level: str, color: bool, *, dim: bool = False) -> str:
    if not color:
        return text
    colors = {
        "CRITICAL": {"fg": "red"},
        "HIGH": {"fg": 208},
        "MEDIUM": {"fg": "yellow"},
        "LOW": {"fg": "cyan"},
        "UNKNOWN": {"fg": "magenta"},
    }
    emphasis = {"dim": True} if dim else {"bold": True}
    return typer.style(text, **colors[level], **emphasis)


def _source_excerpt(finding, color: bool) -> list[str]:
    if not finding.code:
        return ["  Source excerpt unavailable in scanner report."]
    code = finding.code
    first_cause = next((i for i, line in enumerate(code) if line.cause), 0)
    start = max(0, first_cause - 2)
    selected = code[start : start + 9]
    width = max(len(str(line.number)) for line in selected)
    output = ["  ..."] if start else []
    previous = None
    for line in selected:
        if line.truncated:
            output.append("  ...")
            previous = None
            continue
        if previous is not None and line.number > previous + 1:
            output.append("  ...")
        # Ignore native Highlighted fields; preserve indentation, strip controls.
        content = "".join(c for c in line.content.expandtabs(4) if c.isprintable())
        if len(content) > 180:
            content = content[:180] + "..."
        text = f"  {'>' if line.cause else ' '} {line.number:>{width}} | {content}"
        output.append(_severity(text, finding.severity, color) if line.cause else text)
        previous = line.number
    if start + len(selected) < len(code):
        output.append("  ...")
    return output


def render_table(
    result: ScanResult, severity: tuple[str, ...], *, color: bool = False
) -> str:
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
        f"Findings: {len(result.findings)} | Displayed: {len(visible)}",
        "Severity (all): "
        + " ".join(
            _severity(
                f"[{level}: {counts[level]}]", level, color, dim=not counts[level]
            )
            for level in reversed(SEVERITIES)
        ),
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
        for finding in visible:
            location = finding.file or "unknown location"
            if finding.file and finding.start_line:
                location += f":{finding.start_line}"
                if finding.end_line and finding.end_line > finding.start_line:
                    location += f"-{finding.end_line}"
            lines.extend(
                [
                    "",
                    _severity(f"[{finding.severity}]", finding.severity, color)
                    + f" {plain(finding.rule_id)}",
                    f"  {plain(location)} | {plain(finding.resource or '-')}",
                    f"  {plain(finding.message)}",
                    "",
                    *_source_excerpt(finding, color),
                ]
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
