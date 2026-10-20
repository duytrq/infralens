"""Exit codes and safe presentation of command failures."""

import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from enum import IntEnum

import typer

from infralens.logging import logger


class ExitCode(IntEnum):
    success = 0
    findings = 1
    invalid_input = 2
    execution_error = 3
    unavailable = 4
    interrupted = 130


class InvalidInput(Exception):
    """A controlled, user-facing validation message."""


class FeatureUnavailable(Exception):
    """A declared feature has no implementation yet."""


class ExecutionError(Exception):
    """A safe, controlled failure while running an engine or exporting a report."""


def report_unexpected(exc: Exception) -> None:
    typer.echo(
        "Error: Unexpected execution error. Use --verbose for stack frames.", err=True
    )
    # Do not format the exception, source lines, chained exceptions or locals.
    for frame, line in traceback.walk_tb(exc.__traceback__):
        logger.debug(
            "Frame %r:%d in %s", frame.f_code.co_filename, line, frame.f_code.co_name
        )


@contextmanager
def command_errors() -> Iterator[None]:
    try:
        yield
    except InvalidInput as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(ExitCode.invalid_input) from None
    except FeatureUnavailable as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(ExitCode.unavailable) from None
    except ExecutionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(ExitCode.execution_error) from None
    except KeyboardInterrupt:
        typer.echo("Error: Interrupted.", err=True)
        raise typer.Exit(ExitCode.interrupted) from None
    except OSError as exc:
        location = f" for {str(exc.filename)!r}" if exc.filename else ""
        typer.echo(f"Error: I/O operation failed{location}.", err=True)
        raise typer.Exit(ExitCode.execution_error) from None
    except (typer.Exit, typer.BadParameter):
        raise
    except Exception as exc:
        report_unexpected(exc)
        raise typer.Exit(ExitCode.execution_error) from None
