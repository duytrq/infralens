"""Opt-in AWS drift demonstration. Not called by the read-only drift command."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from infralens.errors import ExecutionError
from infralens.options import DriftOptions
from infralens.process import run_process
from infralens.reporting import plain, write_report
from infralens.terraform import terraform_environment


class SandboxError(Exception):
    """A safe error from the explicitly mutating demo program."""


class GuardedEC2:
    """Accept only resources from this run, in the expected account and VPC."""

    def __init__(self, client, sandbox: dict):
        self.client = client
        self.sandbox = sandbox

    def _tags(self, resource: dict) -> None:
        tags = {tag["Key"]: tag["Value"] for tag in resource.get("Tags", [])}
        if any(
            tags.get(key) != value
            for key, value in {
                "Project": "InfraLens",
                "Purpose": "DriftSandbox",
                "RunId": self.sandbox["run_id"],
            }.items()
        ):
            raise SandboxError("Resource ownership tags do not match this sandbox run.")

    def instance(self) -> dict:
        response = self.client.describe_instances(
            InstanceIds=[self.sandbox["instance_id"]]
        )
        instances = [
            item
            for reservation in response["Reservations"]
            for item in reservation["Instances"]
        ]
        if any(
            reservation.get("OwnerId") != self.sandbox["account_id"]
            for reservation in response["Reservations"]
        ):
            raise SandboxError("Instance account does not match the expected account.")
        if len(instances) != 1:
            raise SandboxError("Expected exactly one sandbox instance.")
        instance = instances[0]
        self._tags(instance)
        if (
            instance["VpcId"] != self.sandbox["vpc_id"]
            or instance["SubnetId"] != self.sandbox["subnet_id"]
            or {group["GroupId"] for group in instance["SecurityGroups"]}
            != {self.sandbox["security_group_id"]}
        ):
            raise SandboxError("Instance network does not match the sandbox outputs.")
        return instance

    def group(self) -> dict:
        groups = self.client.describe_security_groups(
            GroupIds=[self.sandbox["security_group_id"]]
        )["SecurityGroups"]
        if len(groups) != 1:
            raise SandboxError("Expected exactly one sandbox security group.")
        group = groups[0]
        self._tags(group)
        if (
            group["VpcId"] != self.sandbox["vpc_id"]
            or group["OwnerId"] != self.sandbox["account_id"]
        ):
            raise SandboxError("Security group account or VPC does not match.")
        return group

    def resize(self, instance_type: str) -> None:
        if instance_type not in ("t3.micro", "t3.small"):
            raise SandboxError("Unsupported instance type for this demo.")
        instance = self.instance()
        if instance["InstanceType"] == instance_type:
            return
        if instance["State"]["Name"] != "running":
            raise SandboxError("Sandbox instance must be running before resize.")
        ids = [self.sandbox["instance_id"]]
        self.client.stop_instances(InstanceIds=ids)
        self.client.get_waiter("instance_stopped").wait(
            InstanceIds=ids, WaiterConfig={"Delay": 5, "MaxAttempts": 60}
        )
        self.instance()
        self.client.modify_instance_attribute(
            InstanceId=ids[0], InstanceType={"Value": instance_type}
        )
        self.client.start_instances(InstanceIds=ids)
        self.client.get_waiter("instance_running").wait(
            InstanceIds=ids, WaiterConfig={"Delay": 5, "MaxAttempts": 60}
        )

    def rule(self, *, remove: bool = False) -> None:
        self.group()
        permission = [
            {
                "IpProtocol": "tcp",
                "FromPort": 8080,
                "ToPort": 8080,
                "IpRanges": [
                    {
                        "CidrIp": "10.241.0.0/24",
                        "Description": "InfraLens isolated drift test",
                    }
                ],
            }
        ]
        operation = (
            self.client.revoke_security_group_ingress
            if remove
            else self.client.authorize_security_group_ingress
        )
        operation(GroupId=self.sandbox["security_group_id"], IpPermissions=permission)

    def terminate(self) -> None:
        instance = self.instance()
        if instance["State"]["Name"] != "running":
            raise SandboxError("Sandbox instance must be running before deletion test.")
        ids = [self.sandbox["instance_id"]]
        self.client.terminate_instances(InstanceIds=ids)
        self.client.get_waiter("instance_terminated").wait(
            InstanceIds=ids, WaiterConfig={"Delay": 5, "MaxAttempts": 60}
        )


def state_fingerprint(project: Path) -> tuple[str, int]:
    state = project / "terraform.tfstate"
    return hashlib.sha256(state.read_bytes()).hexdigest(), state.stat().st_mtime_ns


def verify_cleanup(client, run_id: str) -> None:
    filters = [
        {"Name": "tag:Project", "Values": ["InfraLens"]},
        {"Name": "tag:RunId", "Values": [run_id]},
    ]
    for operation, field in (
        ("describe_vpcs", "Vpcs"),
        ("describe_subnets", "Subnets"),
        ("describe_security_groups", "SecurityGroups"),
        ("describe_volumes", "Volumes"),
    ):
        for page in client.get_paginator(operation).paginate(Filters=filters):
            if page.get(field):
                raise SandboxError("AWS still reports sandbox resources after destroy.")
    for page in client.get_paginator("describe_instances").paginate(Filters=filters):
        if any(
            instance["State"]["Name"] != "terminated"
            for reservation in page.get("Reservations", [])
            for instance in reservation.get("Instances", [])
        ):
            raise SandboxError(
                "AWS still reports an active sandbox instance after destroy."
            )


class Demo:
    def __init__(self, args, session, config):
        self.args = args
        self.session = session
        self.config = config
        self.run_id = uuid.uuid4().hex[:12]
        self.report = {"run_id": self.run_id, "scenarios": [], "cleanup": "not_needed"}
        self.root = args.reports.resolve() / self.run_id
        self.project = self.root / "terraform"
        self.options = DriftOptions(
            self.project,
            (),
            "json",
            None,
            args.profile,
            args.region,
            False,
            None,
            False,
            timeout=300,
        )
        self.env = terraform_environment(self.options)
        self.env = {
            key: value
            for key, value in self.env.items()
            if key.upper() not in ("TF_WORKSPACE", "TF_DATA_DIR")
        }
        self.env.update(
            TF_WORKSPACE="default", TF_DATA_DIR=str(self.project / ".terraform")
        )
        self.variables = {}
        self.binary = None

    def _terraform(self, *arguments: str, timeout: int = 300):
        self.report["phase"] = arguments[0]
        self._save()
        print(f"Terraform: {arguments[0]}", flush=True)
        command = [self.binary, *arguments]
        if arguments[0] in ("apply", "destroy"):
            command.append("-json")
        result = run_process(command, cwd=self.project, env=self.env, timeout=timeout)
        if result.returncode != 0:
            diagnostics = []
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "diagnostic":
                    diagnostic = event.get("diagnostic", {})
                    code = re.search(
                        r"api error ([A-Za-z0-9_.-]+):", diagnostic.get("detail", "")
                    )
                    diagnostics.append(
                        {
                            "summary": plain(diagnostic.get("summary", ""))[:300],
                            "api_code": code[1] if code else None,
                        }
                    )
            self.report["terraform_diagnostics"] = diagnostics
            self._save()
            raise SandboxError(
                f"Terraform {arguments[0]} failed; inspect {self.root}. "
                "Raw diagnostics are withheld because they can contain private values."
            )
        return result.stdout

    def _variables(self, instance_type: str) -> None:
        self.variables["instance_type"] = instance_type
        write_report(
            self.project / "sandbox.auto.tfvars.json",
            json.dumps(self.variables, indent=2) + "\n",
        )

    def _check(
        self,
        name: str,
        address: str | None = None,
        attribute: str | None = None,
        action: str | None = None,
    ) -> dict:
        before = state_fingerprint(self.project)
        result = run_process(
            [
                sys.executable,
                "-m",
                "infralens",
                "drift",
                str(self.project),
                "--format",
                "json",
                "--fail-on-drift",
            ],
            cwd=self.project,
            env=self.env,
            timeout=400,
        )
        if state_fingerprint(self.project) != before:
            raise SandboxError(
                "InfraLens changed the saved state during a drift check."
            )
        if result.returncode in (0, 1):
            observed = json.loads(result.stdout)
            write_report(
                self.root / f"{name}.json", json.dumps(observed, indent=2) + "\n"
            )
        expected = 1 if address is not None else 0
        if result.returncode != expected:
            self.report["check_error"] = plain(result.stderr)[:1000]
            self._save()
            raise SandboxError(
                f"Scenario {name} returned unexpected exit {result.returncode}."
            )
        report = json.loads(result.stdout)
        if report["has_drift"] is not (address is not None):
            raise SandboxError(f"Scenario {name} returned an incorrect drift status.")
        if address is not None:
            matches = [r for r in report["resources"] if r["address"] == address]
            if not matches or (action and action not in matches[0]["actions"]):
                raise SandboxError(
                    f"Scenario {name} did not report the expected resource/action."
                )
            if attribute and not any(
                change["path"] and change["path"][0] == attribute
                for change in matches[0]["attributes"]
            ):
                raise SandboxError(f"Scenario {name} did not report {attribute}.")
        write_report(self.root / f"{name}.json", json.dumps(report, indent=2) + "\n")
        self.report["scenarios"].append(
            {"name": name, "status": "passed", "exit_code": expected}
        )
        self._save()
        print(f"Passed: {name}", flush=True)
        return report

    def _save(self):
        write_report(
            self.root / "summary.json", json.dumps(self.report, indent=2) + "\n"
        )

    def run(self) -> None:
        self.binary = shutil.which(self.args.terraform)
        if self.binary is None:
            raise SandboxError("Terraform executable was not found.")
        self.binary = str(Path(self.binary).resolve())
        inherited_path = next(
            (value for key, value in self.env.items() if key.upper() == "PATH"), ""
        )
        self.env = {
            key: value for key, value in self.env.items() if key.upper() != "PATH"
        }
        self.env["PATH"] = str(Path(self.binary).parent) + os.pathsep + inherited_path
        identity = self.session.client("sts", config=self.config).get_caller_identity()
        if identity["Account"] != self.args.account:
            raise SandboxError(
                "Current AWS identity does not match --account; nothing was created."
            )
        ec2 = self.session.client("ec2", config=self.config)
        ami = self.args.ami
        if ami is None:
            ami = self.session.client("ssm", config=self.config).get_parameter(
                Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
            )["Parameter"]["Value"]
        self.project.mkdir(parents=True, exist_ok=False)
        source = self.args.template.resolve()
        shutil.copyfile(source / "main.tf", self.project / "main.tf")
        if (source / ".terraform.lock.hcl").exists():
            shutil.copyfile(
                source / ".terraform.lock.hcl", self.project / ".terraform.lock.hcl"
            )
        self.variables = {
            "account_id": self.args.account,
            "region": self.args.region,
            "run_id": self.run_id,
            "ami_id": ami,
        }
        self._variables("t3.micro")
        self.report.update(
            account_id=self.args.account,
            region=self.args.region,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._save()
        print(f"Sandbox evidence and state: {self.root}", flush=True)
        applied = False
        try:
            self._terraform("init", "-input=false", "-no-color", timeout=600)
            # Mark cleanup necessary BEFORE apply: a failed apply can create resources.
            applied = True
            self.report["cleanup"] = "pending"
            self._save()
            self._terraform(
                "apply", "-auto-approve", "-input=false", "-no-color", timeout=600
            )
            sandbox = json.loads(self._terraform("output", "-json", "sandbox"))
            if any(
                sandbox.get(key) != value
                for key, value in {
                    "account_id": self.args.account,
                    "region": self.args.region,
                    "run_id": self.run_id,
                }.items()
            ):
                raise SandboxError("Terraform outputs do not match this sandbox run.")
            guard = GuardedEC2(ec2, sandbox)
            guard.instance()
            guard.group()
            self._check("01-baseline")
            self._variables("t3.small")
            self._check("02-code-only")
            self._variables("t3.micro")
            guard.resize("t3.small")
            self._check("03-ec2-change", "aws_instance.demo", "instance_type", "update")
            guard.resize("t3.micro")
            guard.rule()
            self._check(
                "04-security-group", "aws_security_group.demo", "ingress", "update"
            )
            guard.rule(remove=True)
            self._variables("t3.small")
            guard.rule()
            report = self._check(
                "05-code-and-aws", "aws_security_group.demo", "ingress", "update"
            )
            if any(
                resource["address"] == "aws_instance.demo"
                and any(
                    change["path"] == ["instance_type"]
                    for change in resource["attributes"]
                )
                for resource in report["resources"]
            ):
                raise SandboxError(
                    "Pending instance code changes were misreported as drift."
                )
            guard.rule(remove=True)
            self._variables("t3.micro")
            guard.terminate()
            self._check("06-resource-deleted", "aws_instance.demo", action="delete")
            self.report["status"] = "passed"
        except BaseException as error:
            self.report["failure_type"] = type(error).__name__
            if isinstance(error, (SandboxError, ExecutionError)):
                self.report["failure_message"] = str(error)
            operation = getattr(error, "operation_name", None)
            if isinstance(operation, str):
                self.report["failure_operation"] = operation
            self._save()
            raise
        finally:
            scenarios_passed = self.report.get("status") == "passed"
            self.report["status"] = "failed"
            if applied and not self.args.keep_resources:
                print("Cleaning up this sandbox with Terraform destroy...", flush=True)
                self.report["cleanup"] = "failed"
                self._save()
                self._terraform(
                    "destroy", "-auto-approve", "-input=false", "-no-color", timeout=600
                )
                remaining = self._terraform("state", "list").strip()
                if remaining:
                    raise SandboxError(
                        "Terraform state still contains resources after cleanup."
                    )
                verify_cleanup(ec2, self.run_id)
                self.report["cleanup"] = "completed"
            elif applied:
                self.report["cleanup"] = "kept_by_request"
            if scenarios_passed:
                self.report["status"] = "passed"
            self._save()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Create, mutate and remove an isolated AWS drift sandbox"
    )
    parser.add_argument(
        "--account", required=True, help="Expected 12-digit AWS account"
    )
    parser.add_argument("--region", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--ami", help="Optional x86_64 Amazon Linux AMI in this region")
    parser.add_argument(
        "--terraform", default="terraform", help="Executable name or absolute path"
    )
    parser.add_argument(
        "--template", type=Path, default=Path("examples/aws-drift-sandbox")
    )
    parser.add_argument("--reports", type=Path, default=Path("reports/aws-drift"))
    parser.add_argument(
        "--keep-resources", action="store_true", help="Keep resources after the run"
    )
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d{12}", args.account):
        parser.error("--account must contain exactly 12 digits")
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        print(
            "From checkout, install: pip install -e '.[aws-demo]'",
            file=sys.stderr,
        )
        return 3
    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        config = Config(
            connect_timeout=5,
            read_timeout=20,
            retries={"total_max_attempts": 3, "mode": "standard"},
        )
        demo = Demo(args, session, config)
        demo.run()
        print(f"Evidence: {demo.root}")
        return 0
    except (BotoCoreError, ClientError):
        print(
            "AWS request failed. Check login, account, region and permissions. "
            "Raw payload withheld.",
            file=sys.stderr,
        )
        return 3
    except (SandboxError, ExecutionError, OSError, ValueError) as error:
        message = (
            str(error)
            if isinstance(error, (SandboxError, ExecutionError))
            else "Local demo input or I/O failed."
        )
        print(f"Demo failed: {message}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print(
            "Interrupted. Check the run's cleanup status before leaving resources.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
