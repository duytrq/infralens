"""Validate paths and options without reading input contents or writing files."""

import errno
import os
from pathlib import Path

from infralens.errors import InvalidInput
from infralens.logging import logger
from infralens.options import SEVERITIES


def resolve_path(path: Path, parameter: str) -> Path:
    try:
        try:
            # Strict resolution detects symlink loops on all supported Pythons.
            return path.resolve(strict=True)
        except FileNotFoundError:
            # Output destinations may have parents that do not exist yet.
            return path.resolve()
    except (RuntimeError, ValueError):
        raise InvalidInput(f"{parameter}: cannot resolve path {str(path)!r}.") from None
    except OSError as exc:
        if exc.errno not in (
            errno.ELOOP,
            errno.ENOTDIR,
            errno.ENAMETOOLONG,
            errno.EACCES,
            errno.EPERM,
        ):
            raise
        raise InvalidInput(f"{parameter}: cannot access path {str(path)!r}.") from None


def terraform_directory(path: Path) -> tuple[Path, tuple[Path, ...]]:
    path = resolve_path(path, "PATH")
    logger.debug("Validating Terraform directory %r", str(path))
    if not path.is_dir():
        raise InvalidInput(f"PATH: {str(path)!r} must be an existing directory.")
    if not os.access(path, os.R_OK | os.X_OK):
        raise InvalidInput(f"PATH: directory {str(path)!r} is not readable.")
    files = tuple(
        file
        for file in path.iterdir()
        if file.name.endswith((".tf", ".tf.json")) and file.is_file()
    )
    if not files:
        raise InvalidInput(f"PATH: {str(path)!r} has no direct .tf or .tf.json files.")
    for file in files:
        readable_file(file, "PATH")
    return path, files


def readable_file(path: Path, parameter: str) -> Path:
    path = resolve_path(path, parameter)
    if not path.is_file() or not os.access(path, os.R_OK):
        raise InvalidInput(f"{parameter}: {str(path)!r} must be a readable file.")
    return path


def output_path(path: Path | None, inputs: tuple[Path, ...]) -> Path | None:
    if path is None:
        return None
    path = resolve_path(path, "--output")
    logger.debug("Validating output destination %r", str(path))
    if path.exists() and not path.is_file():
        raise InvalidInput(f"--output: {str(path)!r} must be a file destination.")
    for source in inputs:
        if path == source.resolve() or (path.exists() and path.samefile(source)):
            raise InvalidInput(f"--output: {str(path)!r} overlaps an input file.")
    if path.exists() and not os.access(path, os.W_OK):
        raise InvalidInput(f"--output: file {str(path)!r} is not writable.")
    ancestor = path.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if not ancestor.is_dir() or not os.access(ancestor, os.W_OK | os.X_OK):
        raise InvalidInput(f"--output: parent {str(ancestor)!r} is not writable.")
    return path


def severity_filter(value: str) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(part.strip().upper() for part in value.split(",")))
    if any(part not in SEVERITIES for part in selected):
        raise InvalidInput(
            "--severity: use a nonempty comma-separated list of "
            + ",".join(SEVERITIES)
            + "."
        )
    return selected


def failure_threshold(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().upper()
    if value not in SEVERITIES[1:]:
        raise InvalidInput("--fail-on: use one of LOW, MEDIUM, HIGH, CRITICAL.")
    return value


def optional_text(value: str | None, parameter: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise InvalidInput(f"{parameter}: must not be blank.")
    return value


def trace_lookback(trace: bool, days: int | None) -> int | None:
    if days is not None and (not trace or days <= 0):
        raise InvalidInput("--lookback-days: requires --trace and a positive integer.")
    return (7 if days is None else days) if trace else None


def variable_files(paths: list[Path], directory: Path) -> tuple[Path, ...]:
    logger.debug("Validating %d variable file paths", len(paths))
    return tuple(readable_file(directory / path, "--var-file") for path in paths)
