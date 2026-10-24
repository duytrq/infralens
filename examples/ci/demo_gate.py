"""Exercise the installed CLI gate with fake plans. No Terraform or AWS calls."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Offline CI gate demonstration")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    project = root / "examples" / "drift-review"
    fixture = json.loads((project / "plan.json").read_text(encoding="utf-8"))
    resources = fixture["resource_drift"]
    medium = [r for r in resources if r["address"] == "aws_instance.resized"]
    unknown = [r for r in resources if r["address"] == "aws_instance.tagged"]
    high = [r for r in resources if r["address"] == "aws_instance.missing"]
    cases = [
        ("clean", [], ["--fail-on-priority", "high", "--fail-on-unknown"], 0, 0),
        ("medium_allowed", medium, ["--fail-on-priority", "high"], 0, 0),
        ("medium_blocked", medium, ["--fail-on-priority", "medium"], 1, 1),
        ("unknown_allowed", unknown, ["--fail-on-priority", "high"], 0, 0),
        (
            "unknown_blocked",
            unknown,
            ["--fail-on-priority", "high", "--fail-on-unknown"],
            1,
            1,
        ),
        ("high_blocked", high, ["--fail-on-priority", "high"], 1, 1),
        ("mixed", resources, ["--fail-on-priority", "high", "--fail-on-unknown"], 1, 3),
        (
            "any_drift_overrides",
            unknown,
            ["--fail-on-drift", "--fail-on-priority", "high"],
            1,
            1,
        ),
    ]
    evidence = []
    with tempfile.TemporaryDirectory(prefix="infralens-gate-demo-") as directory:
        for name, selected, flags, expected, matched in cases:
            source = Path(directory) / (name + ".json")
            source.write_text(
                json.dumps({**fixture, "resource_drift": selected}), encoding="utf-8"
            )
            command = [
                sys.executable,
                "-m",
                "infralens",
                "drift",
                str(project),
                "--plan-json",
                str(source),
                "--format",
                "json",
                *flags,
            ]
            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                stdin=subprocess.DEVNULL,
                timeout=30,
            )
            try:
                report = json.loads(completed.stdout)
                valid = (
                    completed.returncode == expected
                    and report["gate"]["exit_code"] == expected
                    and report["gate"]["matched_count"] == matched
                    and len(report["resources"]) == len(selected)
                    and report["has_drift"] == bool(selected)
                )
                gate = report["gate"]
            except (ValueError, KeyError, TypeError):
                valid, gate = False, None
            row = {
                "scenario": name,
                "expected_exit": expected,
                "actual_exit": completed.returncode,
                "valid": valid,
                "gate": gate,
            }
            evidence.append(row)
            if args.format == "table":
                print(
                    f"{name}: {'OK' if valid else 'FAILED'} "
                    f"(exit {completed.returncode}; expected {expected})",
                    flush=True,
                )
    success = all(row["valid"] for row in evidence)
    if args.format == "json":
        print(
            json.dumps(
                {"offline": True, "success": success, "cases": evidence}, indent=2
            )
        )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
