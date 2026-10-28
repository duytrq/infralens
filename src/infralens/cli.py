"""Command declarations and process entry point."""

import os
import signal
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from infralens.errors import ExitCode, InvalidInput, command_errors, report_unexpected
from infralens.handlers import handle_drift, handle_scan
from infralens.logging import configure_logging, logger
from infralens.options import (
    SEVERITIES,
    DriftFormat,
    DriftOptions,
    ScanFormat,
    ScanOptions,
    UploadOptions,
)
from infralens.validation import (
    drift_output_path,
    drift_priority_threshold,
    failure_threshold,
    optional_text,
    readable_file,
    scan_directory,
    scan_output_path,
    severity_filter,
    terraform_directory,
    trace_lookback,
    variable_files,
)

app = typer.Typer(
    help="Scan Terraform security and inspect infrastructure drift.",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)
cloud_app = typer.Typer(
    help="Upload saved Security or Drift reports.", no_args_is_help=True
)
app.add_typer(cloud_app, name="cloud")


@cloud_app.command("upload")
def upload_saved(
    report: Annotated[Path, typer.Option(help="Saved Security or Drift JSON file.")],
    manifest: Annotated[Path, typer.Option(help="Immutable .upload.json sidecar.")],
    api_url: Annotated[str, typer.Option(help="InfraLens HTTPS API origin.")],
) -> None:
    """Retry a saved upload without rerunning the engine or changing metadata."""
    with command_errors():
        from infralens.cloud import upload_files

        upload_files(
            readable_file(report, "--report"),
            readable_file(manifest, "--manifest"),
            api_url,
        )


def show_version(value: bool) -> None:
    if value:
        typer.echo(f"infralens {version('infralens')}")
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=show_version,
            is_eager=True,
            help="Show the installed version and exit.",
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Log diagnostic steps to stderr.")
    ] = False,
    no_color: Annotated[
        bool, typer.Option("--no-color", help="Disable ANSI color output.")
    ] = False,
) -> None:
    # Plain help/errors avoid ANSI even before eager --help is processed.
    ctx.color = False
    configure_logging(verbose)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


ProjectPath = Annotated[Path, typer.Argument(help="Terraform project directory.")]
ReportOutput = Annotated[Path | None, typer.Option(help="Output path relative to CWD.")]
EngineTimeout = Annotated[int, typer.Option(min=1, help="Engine timeout in seconds.")]
UploadReport = Annotated[
    bool, typer.Option(help="Upload JSON to the InfraLens dashboard.")
]
CloudProject = Annotated[
    str | None, typer.Option(help="Existing cloud project ID; requires --upload.")
]
CloudApiUrl = Annotated[
    str | None, typer.Option(help="InfraLens HTTPS API origin; requires --upload.")
]


def _upload_options(
    upload: bool,
    report_format: str,
    output: Path | None,
    project: str | None,
    api_url: str | None,
    *,
    scope: str | None = None,
    require_scope: bool = False,
) -> UploadOptions | None:
    if not upload:
        if any(value is not None for value in (project, api_url, scope)):
            flags = (
                "--project, --scope and --api-url"
                if require_scope
                else "--project and --api-url"
            )
            raise InvalidInput(f"{flags} require --upload.")
        return None
    if report_format != "json" or output is None or project is None or api_url is None:
        raise InvalidInput(
            "--upload requires --format json, --output, --project and --api-url."
        )
    from infralens.cloud import identifier, manifest_path
    from infralens.cloud_auth import origin

    options = UploadOptions(
        origin(api_url),
        identifier(project, "--project"),
        identifier(scope, "--scope") if require_scope else None,
    )
    saved = manifest_path(output)
    if saved.exists() or saved.is_symlink():
        raise InvalidInput(
            "Manifest exists; retry with cloud upload or use a new output."
        )
    return options


@app.command()
def scan(
    path: ProjectPath,
    format: Annotated[
        ScanFormat, typer.Option("--format", help="Report format.")
    ] = ScanFormat.table,
    output: ReportOutput = None,
    fail_on: Annotated[
        str | None,
        typer.Option(
            help="Inclusive LOW|MEDIUM|HIGH|CRITICAL threshold; ignores --severity."
        ),
    ] = None,
    timeout: EngineTimeout = 300,
    upload: UploadReport = False,
    project: CloudProject = None,
    api_url: CloudApiUrl = None,
    severity: Annotated[
        str,
        typer.Option(help="Comma-separated report severities; upload JSON keeps all."),
    ] = ",".join(SEVERITIES),
) -> None:
    """Scan Terraform misconfigurations using Trivy 0.76.x."""
    with command_errors():
        selected = severity_filter(severity)
        threshold = failure_threshold(fail_on)
        directory, inputs = scan_directory(path)
        destination = scan_output_path(output, inputs)
        cloud_options = _upload_options(
            upload, format.value, destination, project, api_url
        )
        if cloud_options is not None:
            from infralens.cloud import manifest_path

            scan_output_path(manifest_path(destination), inputs + (destination,))
        logger.debug("Scan validation complete")
        handle_scan(
            ScanOptions(
                directory,
                selected,
                format.value,
                destination,
                threshold,
                timeout,
                upload=cloud_options,
            )
        )


@app.command()
def drift(
    path: ProjectPath,
    format: Annotated[
        DriftFormat, typer.Option("--format", help="Report format.")
    ] = DriftFormat.table,
    output: ReportOutput = None,
    fail_on_priority: Annotated[
        str | None,
        typer.Option(
            "--fail-on",
            "--fail-on-priority",
            help="Inclusive MEDIUM|HIGH review-priority threshold.",
        ),
    ] = None,
    timeout: EngineTimeout = 300,
    upload: UploadReport = False,
    project: CloudProject = None,
    api_url: CloudApiUrl = None,
    scope: Annotated[
        str | None,
        typer.Option(
            help="Stable account/workspace/environment ID; requires --upload."
        ),
    ] = None,
    var_file: Annotated[
        list[Path] | None,
        typer.Option("--var-file", help="Repeatable variable file, relative to PATH."),
    ] = None,
    profile: Annotated[str | None, typer.Option(help="AWS profile name.")] = None,
    region: Annotated[str | None, typer.Option(help="AWS region name.")] = None,
    trace: Annotated[
        bool, typer.Option("--trace", help="Look up related AWS CloudTrail events.")
    ] = False,
    lookback_days: Annotated[
        int | None,
        typer.Option(
            min=1,
            max=90,
            help="Lookback in days (1-90); requires --trace (default: 7).",
        ),
    ] = None,
    fail_on_drift: Annotated[
        bool, typer.Option("--fail-on-drift", help="Exit 1 when drift is detected.")
    ] = False,
    fail_on_unknown: Annotated[
        bool,
        typer.Option(
            "--fail-on-unknown", help="Exit 1 for unknown or unassessed priority."
        ),
    ] = False,
    plan_json: Annotated[
        Path | None,
        typer.Option(help="Read plan JSON without Terraform; --trace still calls AWS."),
    ] = None,
) -> None:
    """Detect managed resource drift using a Terraform refresh-only plan."""
    with command_errors():
        days = trace_lookback(trace, lookback_days)
        priority = drift_priority_threshold(fail_on_priority)
        profile = optional_text(profile, "--profile")
        region = optional_text(region, "--region")
        directory, inputs = terraform_directory(path)
        variables = variable_files(var_file or [], directory)
        imported = (
            readable_file(plan_json, "--plan-json") if plan_json is not None else None
        )
        protected = inputs + variables + ((imported,) if imported is not None else ())
        destination = drift_output_path(output, directory, protected)
        cloud_options = _upload_options(
            upload,
            format.value,
            destination,
            project,
            api_url,
            scope=scope,
            require_scope=True,
        )
        if cloud_options is not None:
            from infralens.cloud import manifest_path

            drift_output_path(
                manifest_path(destination), directory, protected + (destination,)
            )
        logger.debug("Drift validation complete")
        handle_drift(
            DriftOptions(
                directory,
                variables,
                format.value,
                destination,
                profile,
                region,
                trace,
                days,
                fail_on_drift,
                timeout,
                imported,
                fail_on_priority=priority,
                fail_on_unknown=fail_on_unknown,
                upload=cloud_options,
            )
        )


def main() -> None:
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")

        def interrupt(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGBREAK, interrupt)
    try:
        app()
    except KeyboardInterrupt:
        raise SystemExit(ExitCode.interrupted) from None
    except Exception as exc:
        report_unexpected(exc)
        raise SystemExit(ExitCode.execution_error) from None
