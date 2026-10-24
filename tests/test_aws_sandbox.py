import json
from argparse import Namespace
from copy import deepcopy
from types import SimpleNamespace

import boto3
import pytest
from botocore.stub import Stubber

from infralens.aws_sandbox import Demo, GuardedEC2, SandboxError, verify_cleanup
from infralens.process import ProcessResult

ACCOUNT = "123456789012"
SANDBOX = {
    "account_id": ACCOUNT,
    "region": "ap-southeast-2",
    "run_id": "a" * 12,
    "instance_id": "i-0123456789abcdef0",
    "security_group_id": "sg-0123456789abcdef0",
    "vpc_id": "vpc-0123456789abcdef0",
    "subnet_id": "subnet-0123456789abcdef0",
}
TAGS = [
    {"Key": "Project", "Value": "InfraLens"},
    {"Key": "Purpose", "Value": "DriftSandbox"},
    {"Key": "RunId", "Value": SANDBOX["run_id"]},
]
IDS = [SANDBOX["instance_id"]]


def instances(state="running", instance_type="t3.micro"):
    return {
        "Reservations": [
            {
                "OwnerId": ACCOUNT,
                "Instances": [
                    {
                        "InstanceId": IDS[0],
                        "InstanceType": instance_type,
                        "VpcId": SANDBOX["vpc_id"],
                        "SubnetId": SANDBOX["subnet_id"],
                        "SecurityGroups": [{"GroupId": SANDBOX["security_group_id"]}],
                        "State": {"Name": state},
                        "Tags": deepcopy(TAGS),
                    }
                ],
            }
        ]
    }


def groups():
    return {
        "SecurityGroups": [
            {
                "GroupId": SANDBOX["security_group_id"],
                "VpcId": SANDBOX["vpc_id"],
                "OwnerId": ACCOUNT,
                "Tags": deepcopy(TAGS),
            }
        ]
    }


@pytest.fixture
def client():
    # Synthetic test credentials; Stubber prevents every network request.
    return boto3.client(
        "ec2",
        region_name="ap-southeast-2",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


@pytest.mark.parametrize("field", ["tags", "vpc", "subnet", "group", "owner"])
def test_wrong_instance_scope_blocks_mutation(client, field):
    response = instances()
    item = response["Reservations"][0]["Instances"][0]
    if field == "tags":
        item["Tags"] = []
    elif field == "vpc":
        item["VpcId"] = "vpc-other"
    elif field == "subnet":
        item["SubnetId"] = "subnet-other"
    elif field == "group":
        item["SecurityGroups"] = []
    else:
        response["Reservations"][0]["OwnerId"] = "999999999999"
    with Stubber(client) as stub:
        stub.add_response("describe_instances", response, {"InstanceIds": IDS})
        with pytest.raises(SandboxError):
            GuardedEC2(client, SANDBOX).terminate()
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("field", ["tags", "vpc", "owner"])
def test_wrong_security_group_scope_blocks_rules(client, field):
    response = groups()
    group = response["SecurityGroups"][0]
    group[{"tags": "Tags", "vpc": "VpcId", "owner": "OwnerId"}[field]] = (
        [] if field == "tags" else "different"
    )
    with Stubber(client) as stub:
        stub.add_response(
            "describe_security_groups",
            response,
            {"GroupIds": [SANDBOX["security_group_id"]]},
        )
        with pytest.raises(SandboxError):
            GuardedEC2(client, SANDBOX).rule()
        stub.assert_no_pending_responses()


def test_resize_stops_and_checks_instance_before_changing_type(client):
    with Stubber(client) as stub:
        for state in ("running",):
            stub.add_response(
                "describe_instances", instances(state), {"InstanceIds": IDS}
            )
        stub.add_response("stop_instances", {}, {"InstanceIds": IDS})
        stub.add_response(
            "describe_instances", instances("stopped"), {"InstanceIds": IDS}
        )
        stub.add_response(
            "describe_instances", instances("stopped"), {"InstanceIds": IDS}
        )
        stub.add_response(
            "modify_instance_attribute",
            {},
            {
                "InstanceId": IDS[0],
                "InstanceType": {"Value": "t3.small"},
            },
        )
        stub.add_response("start_instances", {}, {"InstanceIds": IDS})
        stub.add_response(
            "describe_instances", instances("running", "t3.small"), {"InstanceIds": IDS}
        )
        GuardedEC2(client, SANDBOX).resize("t3.small")
        stub.assert_no_pending_responses()


def test_rule_is_private_and_limited_to_demo_group(client):
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
    with Stubber(client) as stub:
        stub.add_response(
            "describe_security_groups",
            groups(),
            {"GroupIds": [SANDBOX["security_group_id"]]},
        )
        stub.add_response(
            "authorize_security_group_ingress",
            {},
            {
                "GroupId": SANDBOX["security_group_id"],
                "IpPermissions": permission,
            },
        )
        GuardedEC2(client, SANDBOX).rule()
        stub.assert_no_pending_responses()


def test_cleanup_verifies_aws_not_only_terraform_state(client):
    filters = [
        {"Name": "tag:Project", "Values": ["InfraLens"]},
        {"Name": "tag:RunId", "Values": [SANDBOX["run_id"]]},
    ]
    with Stubber(client) as stub:
        for operation, field in (
            ("describe_vpcs", "Vpcs"),
            ("describe_subnets", "Subnets"),
            ("describe_security_groups", "SecurityGroups"),
            ("describe_volumes", "Volumes"),
        ):
            stub.add_response(operation, {field: []}, {"Filters": filters})
        stub.add_response(
            "describe_instances", instances("terminated"), {"Filters": filters}
        )
        verify_cleanup(client, SANDBOX["run_id"])
        stub.assert_no_pending_responses()


def test_cleanup_refuses_to_claim_success_when_resource_remains(client):
    filters = [
        {"Name": "tag:Project", "Values": ["InfraLens"]},
        {"Name": "tag:RunId", "Values": [SANDBOX["run_id"]]},
    ]
    with Stubber(client) as stub:
        stub.add_response(
            "describe_vpcs",
            {"Vpcs": [{"VpcId": SANDBOX["vpc_id"]}]},
            {"Filters": filters},
        )
        with pytest.raises(SandboxError, match="still reports"):
            verify_cleanup(client, SANDBOX["run_id"])


def demo_args(tmp_path, *, keep=False):
    template = tmp_path / "template"
    template.mkdir()
    (template / "main.tf").write_text("# Fixture")
    return Namespace(
        account=ACCOUNT,
        region="ap-southeast-2",
        profile=None,
        ami="ami-0123456789abcdef0",
        terraform="terraform",
        reports=tmp_path / "reports",
        template=template,
        keep_resources=keep,
    )


def session(account=ACCOUNT):
    sts = SimpleNamespace(get_caller_identity=lambda: {"Account": account})
    return SimpleNamespace(
        client=lambda name, **kwargs: sts if name == "sts" else object()
    )


def test_account_mismatch_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("infralens.aws_sandbox.shutil.which", lambda _: "terraform")
    demo = Demo(demo_args(tmp_path), session("999999999999"), None)
    with pytest.raises(SandboxError, match="does not match"):
        demo.run()
    assert not demo.root.exists()


@pytest.mark.parametrize("keep", [False, True])
def test_partial_apply_failure_is_recorded_and_cleanup_is_attempted(
    tmp_path, monkeypatch, keep
):
    monkeypatch.setattr("infralens.aws_sandbox.shutil.which", lambda _: "terraform")
    demo = Demo(demo_args(tmp_path, keep=keep), session(), None)
    calls = []

    def terraform(*args, **kwargs):
        calls.append(args[0])
        if args[0] == "apply":
            raise SandboxError("Synthetic partial apply failure")
        return ""

    monkeypatch.setattr(demo, "_terraform", terraform)
    monkeypatch.setattr(
        "infralens.aws_sandbox.verify_cleanup", lambda *args: calls.append("verify")
    )
    with pytest.raises(SandboxError, match="partial apply"):
        demo.run()
    assert calls == (
        ["init", "apply"] if keep else ["init", "apply", "destroy", "state", "verify"]
    )
    assert demo.report["status"] == "failed"
    assert demo.report["cleanup"] == ("kept_by_request" if keep else "completed")


def test_demo_checks_detect_accidental_state_write(tmp_path, monkeypatch):
    demo = Demo(demo_args(tmp_path), session(), None)
    demo.project.mkdir(parents=True)
    state = demo.project / "terraform.tfstate"
    state.write_text("original")

    def execute(*args, **kwargs):
        state.write_text("changed unexpectedly")
        return ProcessResult(0, '{"has_drift":false,"resources":[]}', "")

    monkeypatch.setattr("infralens.aws_sandbox.run_process", execute)
    with pytest.raises(SandboxError, match="changed the saved state"):
        demo._check("baseline")
    assert not (demo.root / "baseline.json").exists()


def test_demo_publishes_only_normalized_successful_check(tmp_path, monkeypatch):
    demo = Demo(demo_args(tmp_path), session(), None)
    demo.project.mkdir(parents=True)
    state = demo.project / "terraform.tfstate"
    state.write_text("original")
    report = {
        "has_drift": True,
        "resources": [
            {
                "address": "aws_instance.demo",
                "actions": ["update"],
                "attributes": [
                    {"path": ["instance_type"], "before": "micro", "after": "small"}
                ],
            }
        ],
    }
    monkeypatch.setattr(
        "infralens.aws_sandbox.run_process",
        lambda *args, **kwargs: ProcessResult(1, json.dumps(report), ""),
    )
    demo._check("resize", "aws_instance.demo", "instance_type", "update")
    assert state.read_text() == "original"
    assert json.loads((demo.root / "resize.json").read_text()) == report
    assert demo.report["scenarios"] == [
        {"name": "resize", "status": "passed", "exit_code": 1}
    ]


def test_demo_failure_does_not_publish_a_passing_report(tmp_path, monkeypatch):
    demo = Demo(demo_args(tmp_path), session(), None)
    demo.project.mkdir(parents=True)
    (demo.project / "terraform.tfstate").write_text("original")
    monkeypatch.setattr(
        "infralens.aws_sandbox.run_process",
        lambda *args, **kwargs: ProcessResult(3, "", "PRIVATE"),
    )
    with pytest.raises(SandboxError) as error:
        demo._check("baseline")
    assert "PRIVATE" not in str(error.value)
    assert not (demo.root / "baseline.json").exists()


def test_demo_never_inherits_another_projects_workspace_or_backend_data(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TF_WORKSPACE", "production")
    monkeypatch.setenv("TF_DATA_DIR", str(tmp_path / "unrelated-backend"))
    demo = Demo(demo_args(tmp_path), session(), None)
    assert demo.env["TF_WORKSPACE"] == "default"
    assert demo.env["TF_DATA_DIR"] == str(demo.project / ".terraform")


def test_failed_cleanup_never_leaves_an_overall_passing_status(tmp_path, monkeypatch):
    monkeypatch.setattr("infralens.aws_sandbox.shutil.which", lambda _: "terraform")
    demo = Demo(demo_args(tmp_path), session(), None)

    def terraform(*args, **kwargs):
        if args[0] == "output":
            return json.dumps({**SANDBOX, "run_id": demo.run_id})
        if args[0] == "destroy":
            raise SandboxError("Synthetic cleanup failure")
        return ""

    guard = SimpleNamespace(
        instance=lambda: None,
        group=lambda: None,
        resize=lambda *args: None,
        rule=lambda **kwargs: None,
        terminate=lambda: None,
    )
    monkeypatch.setattr("infralens.aws_sandbox.GuardedEC2", lambda *args: guard)
    monkeypatch.setattr(demo, "_terraform", terraform)
    monkeypatch.setattr(demo, "_check", lambda *args, **kwargs: {"resources": []})
    with pytest.raises(SandboxError, match="cleanup failure"):
        demo.run()
    summary = json.loads((demo.root / "summary.json").read_text())
    assert summary["status"] == "failed"
    assert summary["cleanup"] == "failed"


def test_unexpected_drift_keeps_normalized_evidence_without_marking_pass(
    tmp_path, monkeypatch
):
    demo = Demo(demo_args(tmp_path), session(), None)
    demo.project.mkdir(parents=True)
    (demo.project / "terraform.tfstate").write_text("original")
    report = {"has_drift": True, "resources": [{"address": "aws_vpc.demo"}]}
    monkeypatch.setattr(
        "infralens.aws_sandbox.run_process",
        lambda *args, **kwargs: ProcessResult(1, json.dumps(report), ""),
    )
    with pytest.raises(SandboxError, match="unexpected exit"):
        demo._check("baseline")
    assert json.loads((demo.root / "baseline.json").read_text()) == report
    assert demo.report["scenarios"] == []
