"""Command declarations and process entry point."""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from infralens.errors import ExitCode, command_errors, report_unexpected
from infralens.handlers import handle_drift, handle_scan
from infralens.logging import configure_logging, logger
from infralens.options import (
    SEVERITIES,
    DriftFormat,
    DriftOptions,
    ScanFormat,
    ScanOptions,
)
from infralens.validation import (
    failure_threshold,
    optional_text,
    output_path,
    severity_filter,
    terraform_directory,
    trace_lookback,
    variable_files,
)

app = typer.Typer(
    help="Inspect Terraform security and drift (engines not yet implemented).",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
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
        bool, typer.Option("--verbose", help="Log validation steps to stderr.")
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


@app.command()
def scan(
    path: Annotated[Path, typer.Argument(help="Terraform project directory.")],
    severity: Annotated[
        str, typer.Option(help="Comma-separated report severities.")
    ] = ",".join(SEVERITIES),
    format: Annotated[
        ScanFormat, typer.Option("--format", help="Report format.")
    ] = ScanFormat.table,
    output: Annotated[
        Path | None, typer.Option(help="Output path relative to CWD.")
    ] = None,
    fail_on: Annotated[
        str | None,
        typer.Option(
            help="Inclusive LOW|MEDIUM|HIGH|CRITICAL threshold; ignores --severity."
        ),
    ] = None,
) -> None:
    """Validate a security scan request (engine not yet implemented)."""
    with command_errors():
        selected = severity_filter(severity)
        threshold = failure_threshold(fail_on)
        directory, inputs = terraform_directory(path)
        destination = output_path(output, inputs)
        logger.debug("Scan validation complete")
        handle_scan(
            ScanOptions(directory, selected, format.value, destination, threshold)
        )


@app.command()
def drift(
    path: Annotated[Path, typer.Argument(help="Terraform project directory.")],
    var_file: Annotated[
        list[Path] | None,
        typer.Option("--var-file", help="Repeatable variable file, relative to PATH."),
    ] = None,
    format: Annotated[
        DriftFormat, typer.Option("--format", help="Report format.")
    ] = DriftFormat.table,
    output: Annotated[
        Path | None, typer.Option(help="Output path relative to CWD.")
    ] = None,
    profile: Annotated[str | None, typer.Option(help="AWS profile name.")] = None,
    region: Annotated[str | None, typer.Option(help="AWS region name.")] = None,
    trace: Annotated[
        bool, typer.Option("--trace", help="Request CloudTrail trace.")
    ] = False,
    lookback_days: Annotated[
        int | None,
        typer.Option(
            min=1, help="Positive lookback; requires --trace (default with trace: 7)."
        ),
    ] = None,
    fail_on_drift: Annotated[
        bool, typer.Option("--fail-on-drift", help="Reserve exit 1 for detected drift.")
    ] = False,
) -> None:
    """Validate a drift request (engine and trace not yet implemented)."""
    with command_errors():
        days = trace_lookback(trace, lookback_days)
        profile = optional_text(profile, "--profile")
        region = optional_text(region, "--region")
        directory, inputs = terraform_directory(path)
        variables = variable_files(var_file or [], directory)
        destination = output_path(output, inputs + variables)
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
            )
        )


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        raise SystemExit(ExitCode.interrupted) from None
    except Exception as exc:
        report_unexpected(exc)
        raise SystemExit(ExitCode.execution_error) from None
