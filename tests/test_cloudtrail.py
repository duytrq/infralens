import builtins
import json
import time
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import boto3
import pytest
from botocore.stub import ANY, Stubber
from typer.testing import CliRunner

from infralens import cloudtrail
from infralens.cli import app
from infralens.drift import AttributeChange, DriftResult, ResourceDrift
from infralens.drift_reporting import render_drift
from infralens.options import DriftOptions

ACCOUNT = "123456789012"
REGION = "ap-southeast-2"
ID = "i-0123456789abcdef0"
ARN = f"arn:aws:ec2:{REGION}:{ACCOUNT}:instance/{ID}"
NOW = datetime.now(timezone.utc)
START, END = NOW - timedelta(days=7), NOW + timedelta(minutes=1)
SECRET = "PRIVATE_REQUEST_VALUE"


def resource():
    return ResourceDrift(
        "aws_instance.demo",
        "aws_instance",
        ("update",),
        (
            AttributeChange(
                ("instance_type",),
                {"status": "known", "value": "t3.micro"},
                {"status": "known", "value": "t3.small"},
            ),
        ),
        {
            "id": {"status": "known", "value": ID, "source": "observed"},
            "arn": {"status": "known", "value": ARN, "source": "observed"},
        },
    )


def result(resources=None):
    return DriftResult(
        "1.16.5", tuple(resources or [resource()]), "imported_plan", NOW.isoformat()
    )


def options(tmp_path):
    return DriftOptions(tmp_path, (), "json", None, "sandbox", REGION, True, 7, True)


def event(event_id="event-1", **changes):
    raw = {
        "eventID": event_id,
        "eventTime": (NOW - timedelta(hours=1)).isoformat(),
        "eventName": "ModifyInstanceAttribute",
        "eventSource": "ec2.amazonaws.com",
        "awsRegion": REGION,
        "recipientAccountId": ACCOUNT,
        "readOnly": False,
        "requestParameters": {
            "instanceId": ID,
            "instanceType": {"value": "t3.small"},
            "private": SECRET,
        },
        "responseElements": {"private": SECRET},
        "userIdentity": {
            "type": "AssumedRole",
            "arn": "arn:aws:sts::123456789012:assumed-role/Demo/session",
            "accessKeyId": SECRET,
            "sessionContext": {
                "sessionIssuer": {"arn": "arn:aws:iam::123456789012:role/Demo"}
            },
        },
        **changes,
    }
    return {
        "EventId": event_id,
        "EventName": raw["eventName"],
        "Resources": [{"ResourceName": ID, "ResourceType": "AWS::EC2::Instance"}],
        "CloudTrailEvent": json.dumps(raw),
    }


@pytest.fixture
def aws(monkeypatch):
    session = boto3.Session(
        aws_access_key_id="test", aws_secret_access_key="test", region_name=REGION
    )
    client = session.client("cloudtrail")
    sts = session.client("sts")
    session = SimpleNamespace(
        region_name=REGION,
        client=lambda name, **kwargs: sts if name == "sts" else client,
    )
    monkeypatch.setattr(cloudtrail, "_session", lambda options: session)
    with Stubber(client) as trail_stub, Stubber(sts) as sts_stub:
        yield client, trail_stub, sts_stub
        trail_stub.assert_no_pending_responses()
        sts_stub.assert_no_pending_responses()


def identity(stub):
    stub.add_response(
        "get_caller_identity",
        {
            "Account": ACCOUNT,
            "Arn": f"arn:aws:iam::{ACCOUNT}:user/demo",
            "UserId": "demo",
        },
    )


def lookup_params(token=None):
    params = {
        "LookupAttributes": [{"AttributeKey": "ResourceName", "AttributeValue": ID}],
        "StartTime": ANY,
        "EndTime": ANY,
        "MaxResults": 50,
    }
    if token:
        params["NextToken"] = token
    return params


def test_pagination_deduplication_and_allowlisted_output(aws):
    client, stub, _ = aws
    stub.add_response(
        "lookup_events", {"Events": [event()], "NextToken": "page2"}, lookup_params()
    )
    stub.add_response(
        "lookup_events", {"Events": [event(), event("event-2")]}, lookup_params("page2")
    )
    trace = cloudtrail.lookup_resource(
        client, resource(), (ID, REGION, ACCOUNT), START, END, time.monotonic() + 60
    )
    assert trace["status"] == "matched"
    assert len(trace["events"]) == 2
    assert trace["pages_scanned"] == 2
    assert SECRET not in json.dumps(trace)
    assert trace["events"][0]["actor"]["session_issuer_arn"].endswith("role/Demo")
    assert trace["events"][0]["relation"] == "candidate"


@pytest.mark.parametrize(
    "changes",
    [
        {"readOnly": True},
        {"readOnly": 0},
        {"errorCode": "AccessDenied"},
        {"awsRegion": "us-east-1"},
        {"recipientAccountId": "999999999999"},
        {"eventSource": "iam.amazonaws.com"},
        {"eventName": "DescribeInstances"},
        {"eventTime": "bad-date"},
        {"eventTime": "2020-01-01T00:00:00Z"},
        {"eventCategory": "Data"},
        {"managementEvent": False},
        {"requestParameters": {"disableApiTermination": {"value": True}}},
    ],
)
def test_nonmatching_failed_or_read_events_are_excluded(aws, changes):
    client, stub, _ = aws
    stub.add_response("lookup_events", {"Events": [event(**changes)]})
    trace = cloudtrail.lookup_resource(
        client, resource(), (ID, REGION, ACCOUNT), START, END, time.monotonic() + 60
    )
    assert trace["events"] == []


def test_exact_resource_reference_is_required(aws):
    client, stub, _ = aws
    candidate = event()
    candidate["Resources"][0]["ResourceName"] = "i-aaaaaaaaaaaaaaaaa"
    stub.add_response("lookup_events", {"Events": [candidate]})
    trace = cloudtrail.lookup_resource(
        client, resource(), (ID, REGION, ACCOUNT), START, END, time.monotonic() + 60
    )
    assert not trace["events"]


def test_page_limit_and_invalid_payload_are_visible(aws, monkeypatch):
    client, stub, _ = aws
    candidate = event()
    candidate["CloudTrailEvent"] = SECRET
    monkeypatch.setattr(cloudtrail, "MAX_PAGES", 1)
    stub.add_response("lookup_events", {"Events": [candidate], "NextToken": "more"})
    trace = cloudtrail.lookup_resource(
        client, resource(), (ID, REGION, ACCOUNT), START, END, time.monotonic() + 60
    )
    assert trace["status"] == "partial"
    assert trace["truncated"] is True
    assert trace["malformed_events"] == 1
    assert SECRET not in json.dumps(trace)


def test_enrichment_uses_verified_scope_and_renders_actor(aws, tmp_path):
    _, stub, sts = aws
    identity(sts)
    stub.add_response("lookup_events", {"Events": [event()]}, lookup_params())
    traced = cloudtrail.enrich_trace(result(), options(tmp_path))
    assert traced.trace["status"] == "complete"
    assert traced.trace["account_id"] == ACCOUNT
    assert traced.trace["region"] == REGION
    table = render_drift(traced)
    assert "Candidate" in table and "ModifyInstanceAttribute" in table
    assert "assumed-role/Demo/session" in table
    assert SECRET not in table


@pytest.mark.parametrize(
    "region,account", [("us-east-1", ACCOUNT), (REGION, "999999999999")]
)
def test_other_account_or_region_is_skipped_without_lookup(
    aws, tmp_path, region, account
):
    _, _, sts = aws
    identity(sts)
    r = resource()
    ids = deepcopy(r.identifiers)
    ids["arn"]["value"] = f"arn:aws:ec2:{region}:{account}:instance/{ID}"
    traced = cloudtrail.enrich_trace(
        result([replace(r, identifiers=ids)]), options(tmp_path)
    )
    assert traced.trace["status"] == "partial"
    assert traced.resources[0].trace["reason"] == "scope_mismatch"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"identifiers": {}}, "missing_identifiers"),
        ({"identifiers": {"id": {"status": "sensitive"}}}, "sensitive_identifiers"),
        ({"resource_type": "aws_s3_bucket"}, "unsupported_resource"),
        ({"attributes": ()}, "unsupported_change"),
        (
            {
                "identifiers": {
                    "id": {"status": "known", "value": "fake"},
                    "arn": {"status": "known", "value": ARN},
                }
            },
            "invalid_identifiers",
        ),
    ],
)
def test_ineligible_resources_never_initialize_aws(
    tmp_path, monkeypatch, change, reason
):
    def forbidden(*args):
        pytest.fail("Ineligible resource triggered AWS access")

    monkeypatch.setattr(cloudtrail, "_session", forbidden)
    traced = cloudtrail.enrich_trace(
        result([replace(resource(), **change)]), options(tmp_path)
    )
    assert traced.resources[0].trace["reason"] == reason
    assert not traced.trace["has_errors"]


def test_resource_cap_is_explicit(aws, tmp_path, monkeypatch):
    _, stub, sts = aws
    identity(sts)
    monkeypatch.setattr(cloudtrail, "MAX_RESOURCES", 1)
    stub.add_response("lookup_events", {"Events": []}, lookup_params())
    traced = cloudtrail.enrich_trace(
        result([resource(), replace(resource(), address="aws_instance.other")]),
        options(tmp_path),
    )
    assert traced.resources[0].trace["status"] == "no_events"
    assert traced.resources[1].trace["reason"] == "resource_limit"
    assert traced.trace["status"] == "partial"


@pytest.mark.parametrize("module", ["botocore.config", "boto3"])
def test_missing_sdk_dependency_requests_reinstall(tmp_path, monkeypatch, module):
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == module:
            raise ImportError(SECRET)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    traced = cloudtrail.enrich_trace(result(), options(tmp_path))
    assert traced.trace["has_errors"]
    assert traced.resources[0].trace["reason"] == "dependency_missing"
    assert "Reinstall InfraLens" in traced.trace["message"]
    assert "aws-trace extra" not in traced.trace["message"]
    assert SECRET not in json.dumps(traced.to_dict())


def test_aws_failure_keeps_drift_report_and_cli_returns_3(
    aws, tmp_path, project, monkeypatch, fake_terraform
):
    _, stub, sts = aws
    identity(sts)
    stub.add_client_error(
        "lookup_events",
        service_error_code="AccessDeniedException",
        service_message=SECRET,
    )
    monkeypatch.setattr(
        "infralens.drift_service.Terraform.drift", lambda self: result()
    )
    output = tmp_path / "trace.json"
    cli = CliRunner().invoke(
        app,
        [
            "drift",
            str(project),
            "--trace",
            "7",
            "--format",
            "json",
            "--fail-on",
            "ANY",
            "--output",
            str(output),
        ],
    )
    assert cli.exit_code == 3
    report = json.loads(output.read_text())
    assert report["has_drift"] is True
    assert report["trace"]["has_errors"] is True
    assert report["resources"][0]["trace"]["reason"] == "aws_lookup_failed"
    assert SECRET not in output.read_text() + cli.output


def test_throttle_paces_calls_and_obeys_budget(monkeypatch):
    clock = [0.0]
    delays = []
    monkeypatch.setattr(cloudtrail.time, "monotonic", lambda: clock[0])

    def sleep(delay):
        delays.append(delay)
        clock[0] += delay

    monkeypatch.setattr(cloudtrail.time, "sleep", sleep)
    throttle = cloudtrail.LookupThrottle(1)
    throttle()
    throttle()
    assert delays == [0.55]
    with pytest.raises(cloudtrail.TraceBudgetExceeded):
        throttle()


@pytest.mark.parametrize(
    "kind,name,key,prefix",
    [
        ("aws_instance", "TerminateInstances", "instance", "i"),
        ("aws_security_group", "DeleteSecurityGroup", "security-group", "sg"),
    ],
)
def test_deleted_resources_trace_saved_identity(aws, tmp_path, kind, name, key, prefix):
    _, stub, sts = aws
    identity(sts)
    r = resource()
    resource_id = prefix + ID[1:]
    ids = {
        "id": {"status": "known", "value": resource_id, "source": "saved"},
        "arn": {
            "status": "known",
            "value": f"arn:aws:ec2:{REGION}:{ACCOUNT}:{key}/{resource_id}",
            "source": "saved",
        },
    }
    candidate = event(eventName=name)
    candidate["Resources"][0]["ResourceName"] = resource_id
    stub.add_response("lookup_events", {"Events": [candidate]})
    traced = cloudtrail.enrich_trace(
        result([replace(r, resource_type=kind, actions=("delete",), identifiers=ids)]),
        options(tmp_path),
    )
    assert traced.resources[0].trace["events"][0]["event_name"] == name


def test_no_trace_leaves_json_contract_unchanged():
    report = result().to_dict()
    assert "trace" not in report
    assert "trace" not in report["resources"][0]


def test_events_from_completed_pages_survive_later_api_failure(aws, tmp_path):
    _, stub, sts = aws
    identity(sts)
    stub.add_response("lookup_events", {"Events": [event()], "NextToken": "page2"})
    stub.add_client_error(
        "lookup_events",
        service_error_code="ThrottlingException",
        service_message=SECRET,
    )
    traced = cloudtrail.enrich_trace(result(), options(tmp_path))
    trace = traced.resources[0].trace
    assert trace["status"] == "error"
    assert len(trace["events"]) == 1
    assert traced.trace["has_errors"]
    assert SECRET not in json.dumps(traced.to_dict())


def test_mixed_supported_and_unsupported_changes_have_partial_coverage(aws, tmp_path):
    _, stub, sts = aws
    identity(sts)
    stub.add_response("lookup_events", {"Events": [event()]})
    r = resource()
    r = replace(
        r,
        attributes=r.attributes
        + (
            AttributeChange(
                ("root_block_device",),
                {"status": "known", "value": []},
                {"status": "unknown"},
            ),
        ),
    )
    traced = cloudtrail.enrich_trace(result([r]), options(tmp_path))
    assert traced.trace["status"] == "partial"
    assert traced.resources[0].trace["unsupported_attributes"] == [
        ["root_block_device"]
    ]
    assert len(traced.resources[0].trace["events"]) == 1


def test_trace_window_ends_when_drift_was_checked(aws, tmp_path):
    _, stub, sts = aws
    identity(sts)
    checked_at = NOW - timedelta(minutes=30)
    params = lookup_params()
    params["EndTime"] = checked_at
    params["StartTime"] = checked_at - timedelta(days=7)
    stub.add_response(
        "lookup_events",
        {"Events": [event("earlier"), event("later", eventTime=NOW.isoformat())]},
        params,
    )
    traced = cloudtrail.enrich_trace(
        replace(result(), checked_at=checked_at.isoformat()), options(tmp_path)
    )
    assert [e["event_id"] for e in traced.resources[0].trace["events"]] == ["earlier"]


@pytest.mark.parametrize("fail_on,exit_code", [(False, 0), (True, 1)])
def test_imported_plan_trace_calls_aws_without_terraform(
    aws, project, tmp_path, monkeypatch, fail_on, exit_code
):
    _, stub, sts = aws
    identity(sts)
    stub.add_response("lookup_events", {"Events": [event()]})

    def forbidden(*args, **kwargs):
        pytest.fail("Imported plans must not run Terraform")

    monkeypatch.setattr("infralens.drift_service.Terraform", forbidden)
    imported = tmp_path / "plan.json"
    imported.write_text(
        json.dumps(
            {
                "format_version": "1.2",
                "terraform_version": "1.16.5",
                "planned_values": {},
                "resource_drift": [
                    {
                        "address": "aws_instance.demo",
                        "type": "aws_instance",
                        "mode": "managed",
                        "change": {
                            "actions": ["update"],
                            "before": {
                                "id": ID,
                                "arn": ARN,
                                "instance_type": "t3.micro",
                            },
                            "after": {
                                "id": ID,
                                "arn": ARN,
                                "instance_type": "t3.small",
                            },
                        },
                    }
                ],
            }
        )
    )
    cli = CliRunner().invoke(
        app,
        [
            "drift",
            str(project),
            "--trace",
            "7",
            "--plan-json",
            str(imported),
            "--format",
            "json",
            *(["--fail-on", "ANY"] if fail_on else []),
        ],
    )
    assert cli.exit_code == exit_code, cli.output
    report = json.loads(cli.stdout)
    assert report["trace"]["status"] == "complete"
    assert report["input_mode"] == "imported_plan"
    assert SECRET not in cli.output
