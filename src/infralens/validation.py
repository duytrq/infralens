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
        # Windows symlink loops raise ERROR_CANT_RESOLVE_FILENAME (1921),
        # which Python maps to EINVAL rather than POSIX ELOOP.
        if getattr(exc, "winerror", None) == 1921:
            raise InvalidInput(
                f"{parameter}: cannot resolve path {str(path)!r}."
            ) from None
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


def _scan_input(name: str) -> bool:
    return (
        name.endswith((".tf", ".tf.json", ".tfvars", ".tfvars.json", ".tfstate"))
        or ".tfstate." in name
        or name in (".terraform.lock.hcl", ".trivyignore")
    )


def scan_directory(path: Path) -> tuple[Path, tuple[Path, ...]]:
    """Discover source and protect auxiliary inputs; do not follow directory links."""
    path = resolve_path(path, "PATH")
    logger.debug("Validating recursive Terraform directory %r", str(path))
    if not path.is_dir():
        raise InvalidInput(f"PATH: {str(path)!r} must be an existing directory.")
    sources = []
    # Resolve the consumed root policy even on case-insensitive filesystems.
    ignorefile = path / ".trivyignore"
    protected = [ignorefile] if ignorefile.is_file() else []

    def walk_error(error: OSError) -> None:
        raise InvalidInput("PATH: cannot enumerate a project directory.") from None

    for directory, names, files in os.walk(path, onerror=walk_error):
        current = Path(directory)
        if not os.access(current, os.R_OK | os.X_OK):
            raise InvalidInput(f"PATH: directory {str(current)!r} is not readable.")
        names[:] = sorted(name for name in names if name not in (".git", ".terraform"))
        for name in sorted(files):
            file = current / name
            if name.endswith((".tf", ".tf.json")) and file.is_symlink():
                raise InvalidInput(
                    f"PATH: Terraform source {str(file)!r} is a symlink; "
                    "Trivy cannot reliably scan symlinked source files."
                )
            if _scan_input(name) and file.is_file():
                protected.append(file)
                if name.endswith((".tf", ".tf.json")):
                    sources.append(readable_file(file, "PATH"))
    if not sources:
        raise InvalidInput(
            f"PATH: {str(path)!r} has no .tf or .tf.json files in the project tree."
        )
    return path, tuple(protected)


def scan_output_path(path: Path | None, inputs: tuple[Path, ...]) -> Path | None:
    destination = output_path(path, inputs)
    if destination is not None and (
        _scan_input(destination.name) or destination.name.lower() == ".trivyignore"
    ):
        raise InvalidInput(
            "--output: must not use a Terraform source, variable, "
            "lock, state or .trivyignore filename."
        )
    return destination


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


def drift_output_path(
    path: Path | None, directory: Path, inputs: tuple[Path, ...]
) -> Path | None:
    if path is None:
        return None
    protected = list(inputs)
    configured_data = Path(os.environ.get("TF_DATA_DIR") or ".terraform")
    active_data = resolve_path(directory / configured_data, "TF_DATA_DIR")
    for data_directory in {directory / ".terraform", active_data}:
        for metadata in (
            data_directory / "terraform.tfstate",
            data_directory / "modules" / "modules.json",
        ):
            if metadata.is_file():
                protected.append(metadata)

    def walk_error(error: OSError) -> None:
        raise InvalidInput("PATH: cannot enumerate files to protect drift inputs.")

    for root, names, files in os.walk(directory, onerror=walk_error):
        names[:] = [name for name in names if name not in (".git", ".terraform")]
        for name in files:
            source = Path(root) / name
            if _scan_input(name) and source.is_file():
                protected.append(source)
    destination = scan_output_path(path, tuple(protected))
    if destination is not None and destination.is_relative_to(active_data):
        raise InvalidInput("--output: must not be inside the Terraform data directory.")
    if destination is not None and any(
        name.lower() in (".terraform", ".git") for name in destination.parts
    ):
        raise InvalidInput("--output: must not be inside .terraform or .git.")
    return destination


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


def drift_priority_threshold(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    if value not in ("high", "medium"):
        raise InvalidInput("--fail-on-priority: use high or medium.")
    return value


def optional_text(value: str | None, parameter: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise InvalidInput(f"{parameter}: must not be blank.")
    return value


def trace_lookback(trace: bool, days: int | None) -> int | None:
    if days is not None and (not trace or not 1 <= days <= 90):
        raise InvalidInput(
            "--lookback-days: requires --trace and an integer from 1 to 90."
        )
    return (7 if days is None else days) if trace else None


def variable_files(paths: list[Path], directory: Path) -> tuple[Path, ...]:
    logger.debug("Validating %d variable file paths", len(paths))
    return tuple(readable_file(directory / path, "--var-file") for path in paths)
