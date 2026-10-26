"""Command orchestration and finding policies."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import typer

from infralens.drift_gate import evaluate_gate, render_gate
from infralens.drift_reporting import render_drift
from infralens.drift_service import collect_drift
from infralens.errors import ExitCode
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
    started = datetime.now(timezone.utc)
    result = collect_drift(options)
    finished = datetime.now(timezone.utc)
    gate = None
    if (
        options.fail_on_drift
        or options.fail_on_priority is not None
        or options.fail_on_unknown
    ):
        gate = evaluate_gate(
            result,
            fail_on_drift=options.fail_on_drift,
            fail_on_priority=options.fail_on_priority,
            fail_on_unknown=options.fail_on_unknown,
        )
    table = render_drift(result)
    if gate is not None:
        table += render_gate(gate)
    data = result.to_dict()
    if gate is not None:
        data["gate"] = gate
    if options.upload is not None:
        from infralens.cloud import cloud_report

        data = cloud_report(data, options.path)
    report = (
        json.dumps(data, ensure_ascii=True, indent=2) + "\n"
        if options.format == "json"
        else table
    )
    if options.output is not None:
        write_report(options.output, report)
        typer.echo(table, nl=False)
        typer.echo(f"Report saved to {str(options.output)!r}.", err=True)
    else:
        typer.echo(report, nl=False)
    if options.upload is not None:
        from infralens import cloud

        saved = cloud.save_manifest(data, report, options, started, finished)
        typer.echo(f"Upload manifest saved to {str(saved)!r}.", err=True)
        cloud.upload_files(options.output, saved, options.upload.api_url)
    if result.trace and result.trace["has_errors"]:
        typer.echo(
            "Error: CloudTrail trace incomplete; see trace details in the report.",
            err=True,
        )
        raise typer.Exit(ExitCode.execution_error)
    if gate is not None and gate["exit_code"] == 1:
        raise typer.Exit(ExitCode.findings)
