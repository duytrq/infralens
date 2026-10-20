"""Test executable, not a replacement engine or integration fixture."""

import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["FAKE_TRIVY_LOG"]).open("a") as stream:
    stream.write(json.dumps(args) + "\n")
mode = os.environ.get("FAKE_TRIVY_MODE", "normal")
if "--version" in args:
    print("Version: " + ("0.75.0" if mode == "version" else "0.76.0"))
    sys.exit()
if mode == "fail":
    print("PRIVATE_ENGINE_PAYLOAD", file=sys.stderr)
    sys.exit(7)
if mode == "timeout":
    time.sleep(30)
if mode == "broken":
    print("PRIVATE_NOT_JSON")
    sys.exit()
if mode == "parse":
    print("time\tERROR\t[terraform parser] Error parsing PRIVATE", file=sys.stderr)
if "config" in args:
    findings = (
        []
        if mode == "clean"
        else [
            {
                "ID": f"TEST-{severity}",
                "Severity": severity,
                "Status": "FAIL",
                "Title": f"{severity} configuration",
                "Message": f"Fix {severity} issue",
                "Resolution": "Restrict access",
                "CauseMetadata": {
                    "Resource": "aws_security_group.public",
                    "StartLine": 7,
                    "EndLine": 8,
                },
            }
            for severity in ("LOW", "HIGH", "CRITICAL", "UNKNOWN")
        ]
    )
    print(
        json.dumps(
            {
                "SchemaVersion": 2,
                "Trivy": {"Version": "0.76.0"},
                "Results": [
                    {
                        "Target": "main.tf",
                        "Class": "config",
                        "Type": "terraform",
                        "Misconfigurations": findings,
                    }
                ],
            }
        )
    )
else:
    if mode == "convert":
        print("PRIVATE_CONVERSION_ERROR", file=sys.stderr)
        sys.exit(8)
    report = json.loads(Path(args[-1]).read_text())
    levels = args[args.index("--severity") + 1].split(",")
    for result in report["Results"]:
        result["Misconfigurations"] = [
            f for f in result["Misconfigurations"] if f["Severity"] in levels
        ]
    if args[args.index("--format") + 1] == "sarif":
        report = {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": "Trivy"}},
                    "results": [
                        {"ruleId": f["ID"], "message": {"text": f["Message"]}}
                        for r in report["Results"]
                        for f in r["Misconfigurations"]
                    ],
                }
            ],
        }
    print(json.dumps(report))
