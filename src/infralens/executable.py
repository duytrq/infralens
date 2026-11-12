"""Find the packaged scanner, or a development installation on PATH."""

import hashlib
import json
import os
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from infralens.errors import ExecutionError

BUNDLE = Path(__file__).parent / "_vendor" / "trivy"
EXECUTABLES = {"linux_x86_64": "trivy", "win_amd64": "trivy.exe"}


def current_platform() -> str:
    machine = platform.machine().lower()
    system = platform.system()
    if machine in ("x86_64", "amd64"):
        if system == "Linux":
            return "linux_x86_64"
        if system == "Windows":
            return "win_amd64"
    return f"{system.lower()}_{machine}"


@dataclass(frozen=True)
class Executable:
    path: Path
    source: str
    expected_version: str | None = None


def discover_trivy(bundle: Path = BUNDLE) -> Executable:
    marker = bundle.parent.parent / "_bundle.json"
    if bundle.exists() or marker.exists():
        try:
            manifest = json.loads(
                (bundle / "manifest.json").read_text(encoding="utf-8")
            )
            if json.loads(marker.read_text(encoding="utf-8")) != manifest:
                raise ValueError
            target = current_platform()
            filename = EXECUTABLES[target]
            if (
                manifest["platform"] != target
                or manifest["executable"] != filename
                or not re.fullmatch(r"0\.76\.\d+", manifest["version"])
                or not re.fullmatch(r"[0-9a-f]{64}", manifest["sha256"])
            ):
                raise ValueError
            binary = bundle / filename
            if (
                not binary.is_file()
                or binary.is_symlink()
                or not os.access(binary, os.X_OK)
            ):
                raise ValueError
            checksum = hashlib.sha256()
            with binary.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(block)
            if checksum.hexdigest() != manifest["sha256"]:
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError):
            raise ExecutionError(
                "The bundled Trivy installation is damaged or incompatible. "
                "Reinstall the InfraLens wheel for your operating system and CPU."
            ) from None
        return Executable(binary.resolve(), "bundle", manifest["version"])
    executable = shutil.which("trivy")
    if executable is None:
        raise ExecutionError(
            "Trivy 0.76.x was not found on PATH. Install a bundled InfraLens wheel, "
            "install Trivy for source development, or use the InfraLens Docker image."
        )
    return Executable(Path(executable).resolve(), "PATH")
