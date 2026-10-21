"""Prepare a verified scanner for an explicit release-wheel build (stdlib only)."""

import argparse
import hashlib
import json
import os
import shutil
import struct
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "vendor" / "trivy.json"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def configuration(target: str) -> tuple[dict, dict]:
    config = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if target not in config["platforms"]:
        raise ValueError(f"Unsupported bundle platform: {target}")
    return config, config["platforms"][target]


def validate_binary(binary: Path, target: str) -> None:
    with binary.open("rb") as stream:
        header = stream.read(64)
        if target == "linux_x86_64":
            valid = header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\x3e\x00"
        else:
            valid = header[:2] == b"MZ" and len(header) == 64
            if valid:
                stream.seek(struct.unpack_from("<I", header, 60)[0])
                valid = stream.read(6) == b"PE\x00\x00\x64\x86"
    if not valid:
        raise ValueError(f"Executable is not a {target} binary")


def validate_stage(directory: Path, target: str) -> dict:
    config, asset = configuration(target)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest["platform"] != target
        or manifest["version"] != config["version"]
        or manifest["executable"] != asset["executable"]
        or manifest["archive_sha256"] != asset["sha256"]
    ):
        raise ValueError("Staged manifest does not match pinned release")
    binary = directory / asset["executable"]
    if binary.is_symlink() or digest(binary) != manifest["sha256"]:
        raise ValueError("Staged executable checksum mismatch")
    validate_binary(binary, target)
    if "Apache License" not in (directory / "LICENSE").read_text(encoding="utf-8"):
        raise ValueError("Trivy license missing from staged bundle")
    return manifest


def stage(target: str, destination: Path, *, archive: Path | None = None) -> dict:
    config, asset = configuration(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".trivy-", dir=destination.parent) as work:
        temporary = Path(work)
        if archive is None:
            archive = temporary / "download"
            request = urllib.request.Request(
                asset["url"], headers={"User-Agent": "InfraLens-build"}
            )
            with (
                urllib.request.urlopen(request, timeout=120) as source,
                archive.open("wb") as output,
            ):
                shutil.copyfileobj(source, output)
        if digest(archive) != asset["sha256"]:
            raise ValueError("Trivy archive checksum mismatch; refusing extraction")
        names = [asset["executable"], "LICENSE"]
        if target == "win_amd64":
            with zipfile.ZipFile(archive) as package:
                for name in names:
                    with (
                        package.open(name) as source,
                        (temporary / name).open("wb") as output,
                    ):
                        shutil.copyfileobj(source, output)
        else:
            with tarfile.open(archive, "r:gz") as package:
                for name in names:
                    member = package.getmember(name)
                    if not member.isfile():
                        raise ValueError("Archive member is not a regular file")
                    with (
                        package.extractfile(member) as source,
                        (temporary / name).open("wb") as output,
                    ):
                        shutil.copyfileobj(source, output)
        binary = temporary / asset["executable"]
        binary.chmod(0o755)
        manifest = {
            "platform": target,
            "version": config["version"],
            "executable": asset["executable"],
            "sha256": digest(binary),
            "archive_sha256": asset["sha256"],
            "source": asset["url"],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        validate_stage(temporary, target)
        destination.mkdir(parents=True, exist_ok=True)
        # Manifest is published last; interrupted staging fails build validation.
        for name in [*names, "manifest.json"]:
            os.replace(temporary / name, destination / name)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=["linux_x86_64", "win_amd64"])
    parser.add_argument(
        "--archive", type=Path, help="Use an already downloaded pinned archive"
    )
    args = parser.parse_args()
    destination = ROOT / "build" / "trivy" / args.platform
    result = stage(args.platform, destination, archive=args.archive)
    print(f"Staged Trivy {result['version']} for {args.platform}: {destination}")


if __name__ == "__main__":
    main()
