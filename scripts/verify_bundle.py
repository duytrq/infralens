"""Install a wheel in an isolated uv tool environment and scan without PATH Trivy."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def verify(wheel: Path, uv: str) -> None:
    with zipfile.ZipFile(wheel) as package:
        manifest = json.loads(package.read("infralens/_bundle.json"))
        prefix = "infralens/_vendor/trivy/"
        expected = {
            prefix + name
            for name in (
                manifest["executable"],
                "LICENSE",
                "manifest.json",
                "README.md",
            )
        }
        assert {
            name for name in package.namelist() if name.startswith(prefix)
        } == expected
        binary = package.read(prefix + manifest["executable"])
        assert hashlib.sha256(binary).hexdigest() == manifest["sha256"]
        assert b"Apache License" in package.read(prefix + "LICENSE")
        metadata = package.read(
            next(
                name for name in package.namelist() if name.endswith(".dist-info/WHEEL")
            )
        ).decode()
        assert "Root-Is-Purelib: false" in metadata
        assert f"Tag: py3-none-{manifest['platform']}" in metadata
    with tempfile.TemporaryDirectory(prefix="infralens-wheel-") as work:
        root = Path(work)
        env = {
            **os.environ,
            "UV_TOOL_DIR": str(root / "tools"),
            "UV_TOOL_BIN_DIR": str(root / "bin"),
            "PYTHONUTF8": "1",
        }
        subprocess.run(
            [
                uv,
                "tool",
                "install",
                "--with",
                "pytest>=8,<10",
                "--link-mode",
                "copy",
                "--python",
                sys.executable,
                str(wheel.resolve()),
            ],
            env=env,
            cwd=root,
            check=True,
        )
        executable = (
            root / "bin" / ("infralens.exe" if os.name == "nt" else "infralens")
        )
        tool_python = (
            root
            / "tools"
            / "infralens"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        # Copies keep deliberate tampering isolated from uv's shared package cache.
        # Run lifecycle and atomic-I/O tests against the installed wheel's code.
        subprocess.run(
            [
                str(tool_python),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                str(ROOT / "tests" / "test_process.py"),
                str(ROOT / "tests" / "test_report_io.py"),
                "--basetemp",
                str(root / "process-tests"),
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=90,
        )
        env["PATH"] = ""
        env.pop("INFRALENS_ACCESS_TOKEN", None)
        env["TRIVY_CACHE_DIR"] = os.environ.get("TRIVY_CACHE_DIR", str(root / "cache"))

        def run(*arguments, code=0):
            scan_env = {**env}
            # Exercise Windows redirected UTF-8 without an environment opt-in.
            scan_env.pop("PYTHONUTF8", None)
            completed = subprocess.run(
                [str(executable), *arguments],
                cwd=root,
                env=scan_env,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
            assert completed.returncode == code, (
                arguments,
                completed.stdout,
                completed.stderr,
            )
            return completed

        run("--help")
        run("--version")
        drift_project = root / "drift project Việt"
        shutil.copytree(ROOT / "examples" / "drift-review", drift_project)
        observed = json.loads(
            run(
                "drift",
                str(drift_project),
                "--plan-json",
                str(drift_project / "plan.json"),
                "--format",
                "json",
                "--fail-on-priority",
                "high",
                "--fail-on-unknown",
                code=1,
            ).stdout
        )
        assert observed["kind"] == "drift"
        assert observed["summary"]["resources"] == 4
        assert observed["gate"]["status"] == "failed"
        output = root / "reports Việt" / "drift.json"
        failed_upload = run(
            "drift",
            str(drift_project),
            "--plan-json",
            str(drift_project / "plan.json"),
            "--format",
            "json",
            "--output",
            str(output),
            "--upload",
            "--project",
            "demo",
            "--scope",
            "dev-default",
            "--api-url",
            "https://api.example.com",
            code=3,
        )
        assert "Noninteractive upload requires" in failed_upload.stderr
        saved = json.loads(
            Path(str(output) + ".upload.json").read_text(encoding="utf-8")
        )
        assert (
            saved["manifest"]["artifact"]["sha256"]
            == hashlib.sha256(output.read_bytes()).hexdigest()
        )
        assert saved["manifest"]["artifact"]["size_bytes"] == len(output.read_bytes())
        assert str(drift_project) not in output.read_text(encoding="utf-8")
        project = root / "Terraform project Việt"
        shutil.copytree(ROOT / "tests" / "fixtures" / "unsafe", project)
        source = project / "hạ tầng.tf"
        (project / "main.tf").rename(source)
        before = source.read_bytes(), source.stat().st_mtime_ns
        table = run("--verbose", "scan", str(project), "--fail-on", "HIGH", code=1)
        assert "source=bundle version=0.76.0" in table.stderr
        assert "AWS-0107" in table.stdout
        assert source.name in table.stdout
        for format in ("json", "sarif"):
            output = root / "reports Việt" / f"scan.{format}"
            run(
                "scan",
                str(project),
                "--format",
                format,
                "--output",
                str(output),
                "--fail-on",
                "HIGH",
                code=1,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
            if format == "json":
                assert report["SchemaVersion"] == 2
                assert any(
                    f["ID"] == "AWS-0107"
                    for r in report["Results"]
                    for f in r.get("Misconfigurations", [])
                )
            else:
                schema = json.loads(
                    (ROOT / "tests" / "fixtures" / "sarif-schema-2.1.0.json").read_text(
                        encoding="utf-8"
                    )
                )
                jsonschema.Draft7Validator(schema).validate(report)
        output = root / "reports Việt" / "security-upload.json"
        security_upload = run(
            "scan",
            str(project),
            "--format",
            "json",
            "--output",
            str(output),
            "--severity",
            "LOW",
            "--fail-on",
            "HIGH",
            "--upload",
            "--project",
            "demo",
            "--api-url",
            "https://api.example.com",
            code=3,
        )
        assert "Noninteractive upload requires" in security_upload.stderr
        report = json.loads(output.read_text(encoding="utf-8"))
        saved_path = Path(str(output) + ".upload.json")
        original_manifest = saved_path.read_bytes()
        metadata = json.loads(original_manifest)["manifest"]
        assert metadata["run_type"] == "security_scan"
        assert metadata["result"]["threshold_status"] == "failed"
        assert metadata["result"]["findings"]["by_severity"]["HIGH"] > 0
        assert any(
            f["ID"] == "AWS-0107"
            for result in report["Results"]
            for f in result.get("Misconfigurations", [])
        )
        assert (
            metadata["artifact"]["sha256"]
            == hashlib.sha256(output.read_bytes()).hexdigest()
        )
        assert (
            "Noninteractive upload requires"
            in run(
                "cloud",
                "upload",
                "--report",
                str(output),
                "--manifest",
                str(saved_path),
                "--api-url",
                "https://api.example.com",
                code=3,
            ).stderr
        )
        assert saved_path.read_bytes() == original_manifest
        filtered = json.loads(
            run(
                "scan",
                str(project),
                "--format",
                "json",
                "--severity",
                "LOW",
                "--fail-on",
                "HIGH",
                code=1,
            ).stdout
        )
        assert {
            f["Severity"]
            for r in filtered["Results"]
            for f in r.get("Misconfigurations", [])
        } == {"LOW"}
        (project / ".trivyignore").write_text("AWS-0107\n", encoding="utf-8")
        run("scan", str(project), "--fail-on", "HIGH")
        assert before == (source.read_bytes(), source.stat().st_mtime_ns)
        clean = root / "clean"
        shutil.copytree(ROOT / "tests" / "fixtures" / "clean", clean)
        assert "Findings: 0" in run("scan", str(clean)).stdout
        invalid = root / "invalid"
        invalid.mkdir()
        (invalid / "Falling back to embedded checks.tf").write_text(
            'resource "aws_s3_bucket" "bad" {\n broken = [\n', encoding="utf-8"
        )
        assert not run("scan", str(invalid), code=3).stdout
        bundle_path = Path(
            subprocess.check_output(
                [
                    str(tool_python),
                    "-c",
                    "from infralens.executable import BUNDLE; print(BUNDLE)",
                ],
                cwd=root,
                env=env,
                text=True,
                encoding="utf-8",
            ).strip()
        )
        assert bundle_path.is_relative_to(root / "tools" / "infralens")
        installed_binary = bundle_path / manifest["executable"]
        with installed_binary.open("r+b") as stream:
            original = stream.read(1)
            stream.seek(0)
            stream.write(bytes([original[0] ^ 1]))
        try:
            assert "Reinstall" in run("scan", str(clean), code=3).stderr
        finally:
            with installed_binary.open("r+b") as stream:
                stream.write(original)
        marker = bundle_path.parent.parent / "_bundle.json"
        original_marker = marker.read_bytes()
        marker.unlink()
        try:
            assert "Reinstall" in run("scan", str(clean), code=3).stderr
        finally:
            marker.write_bytes(original_marker)
        print(
            f"Verified installed {manifest['platform']} wheel without Trivy on PATH: "
            f"{wheel.name}"
        )
        print(
            f"Wheel: {wheel.stat().st_size} bytes; bundled binary: {len(binary)} bytes"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--uv", default=shutil.which("uv"))
    args = parser.parse_args()
    if not args.uv:
        parser.error("uv is required; pass --uv with its absolute executable path")
    verify(args.wheel.resolve(), args.uv)


if __name__ == "__main__":
    main()
