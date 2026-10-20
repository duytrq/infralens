"""Command orchestration and finding policies."""

import json
import tempfile
from pathlib import Path

import typer

from infralens.errors import ExitCode, FeatureUnavailable
from infralens.options import SEVERITIES, DriftOptions, ScanOptions
from infralens.reporting import render_table, write_report
from infralens.trivy import Trivy


def handle_scan(options: ScanOptions) -> None:
    engine = Trivy(options.path)
    result = engine.scan(options.timeout)
    for diagnostic in result.diagnostics:
        typer.echo(f"Warning: {diagnostic}", err=True)
    table = render_table(result, options.severity)
    report = table
    if options.format != "table":
        with tempfile.TemporaryDirectory(prefix="infralens-") as directory:
            source = Path(directory) / "scan.json"
            source.write_text(json.dumps(result.raw), encoding="utf-8")
            report = engine.convert(source, options.format, options.severity)
    if options.output is not None:
        write_report(options.output, report)
        typer.echo(table, nl=False)
        typer.echo(f"Report saved to {str(options.output)!r}.", err=True)
    else:
        typer.echo(report, nl=not report.endswith("\n"))
    if options.fail_on is not None and any(
        SEVERITIES.index(f.severity) >= SEVERITIES.index(options.fail_on)
        for f in result.findings
    ):
        raise typer.Exit(ExitCode.findings)


def handle_drift(options: DriftOptions) -> None:
    if options.trace:
        raise FeatureUnavailable("CloudTrail trace is not supported yet.")
    raise FeatureUnavailable("Drift engine is not implemented.")
