"""Terraform fixture executable. Never accesses a cloud or mutates state."""

import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
mode = os.environ.get("FAKE_TERRAFORM_MODE", "clean")
with Path(os.environ["FAKE_TERRAFORM_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(
        json.dumps(
            {
                "args": args,
                "cwd": os.getcwd(),
                "env": {
                    key: value
                    for key, value in os.environ.items()
                    if key.upper().startswith(("TF_CLI_ARGS", "TF_LOG"))
                    or key
                    in (
                        "AWS_PROFILE",
                        "AWS_REGION",
                        "AWS_DEFAULT_REGION",
                        "TF_VAR_DEMO",
                        "TF_WORKSPACE",
                    )
                },
            }
        )
        + "\n"
    )
if args == ["version", "-json"]:
    version = "0.15.4" if mode == "old-version" else "1.16.5"
    print(json.dumps({"terraform_version": version}))
elif args[0] == "plan":
    if mode == "timeout":
        time.sleep(60)
    if mode == "plan-fail":
        print("SECRET_PROVIDER_ERROR", file=sys.stderr)
        sys.exit(1)
    output = next(arg[5:] for arg in args if arg.startswith("-out="))
    Path(output).write_text("temporary binary plan fixture", encoding="utf-8")
    print("Terraform human output must not appear in the report")
    sys.exit(2 if mode in ("drift", "delete", "output-only") else 0)
elif args[0] == "show":
    if mode == "show-fail":
        print("SECRET_STATE_ERROR", file=sys.stderr)
        sys.exit(1)
    if mode == "invalid-json":
        print("SECRET_INVALID_JSON")
        sys.exit(0)
    plan = {
        "format_version": "1.2",
        "terraform_version": "1.16.5",
        "planned_values": {},
        "resource_drift": [],
        # A proposed code change must never be interpreted as observed drift.
        "resource_changes": [{"change": {"actions": ["create"]}}],
        "variables": {"private": {"value": "SECRET_RAW_VARIABLE"}},
    }
    if mode == "incomplete":
        plan["complete"] = False
    if mode in ("drift", "delete"):
        plan["resource_drift"] = [
            {
                "address": 'module.app.aws_instance.web["demo"]',
                "mode": "managed",
                "type": "aws_instance",
                "change": {
                    "actions": ["delete"] if mode == "delete" else ["update"],
                    "before": {"instance_type": "t3.micro", "password": "SECRET_OLD"},
                    "after": None
                    if mode == "delete"
                    else {"instance_type": "t3.small", "password": "SECRET_NEW"},
                    "before_sensitive": {"password": True},
                    "after_sensitive": {"password": True}
                    if mode != "delete"
                    else False,
                },
            }
        ]
    print(json.dumps(plan))
else:
    sys.exit(9)
