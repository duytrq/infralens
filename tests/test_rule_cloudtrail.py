import json
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
from infralens.drift import parse_plan
from infralens.drift_reporting import render_drift
from infralens.options import DriftOptions

ACCOUNT, REGION = "123456789012", "ap-southeast-2"
GROUP = "sg-0123456789abcdef0"
RULE = "sgr-0123456789abcdef0"
OTHER = "sgr-1123456789abcdef0"
ARN = f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group-rule/{RULE}"
INGRESS = "aws_vpc_security_group_ingress_rule"
EGRESS = "aws_vpc_security_group_egress_rule"
NOW = datetime.now(timezone.utc)
SECRET = "PRIVATE_RULE_CLOUDTRAIL_PAYLOAD"


def plan(kind=INGRESS, action="update", field="to_port", **masks):
    before = {
        "id": RULE,
        "arn": ARN,
        "security_group_rule_id": RULE,
        "security_group_id": GROUP,
        "ip_protocol": "tcp",
        "from_port": 22,
        "to_port": 22,
        "cidr_ipv4": "0.0.0.0/0",
    }
    after = {**before, field: "new description" if field == "description" else 23}
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.5",
        "planned_values": {},
        "resource_drift": [
            {
                "address": kind + ".demo",
                "type": kind,
                "mode": "managed",
                "change": {
                    "actions": [action],
                    "before": before,
                    "after": None if action == "delete" else after,
                    **masks,
                },
            }
        ],
    }


def result(payload=None):
    return replace(
        parse_plan(json.dumps(payload or plan())), checked_at=NOW.isoformat()
    )


def options(tmp_path):
    return DriftOptions(tmp_path, (), "json", None, "sandbox", REGION, True, 7, True)


def event(
    name="ModifySecurityGroupRules",
    identity=RULE,
    request=None,
    event_id="rule-event-1",
    **changes,
):
    if request is None:
        if name.startswith("Revoke"):
            body = {"GroupId": GROUP, "SecurityGroupRuleId": [identity]}
        elif name.startswith("UpdateSecurityGroupRuleDescriptions"):
            body = {
                "GroupId": GROUP,
                "SecurityGroupRuleDescription": {
                    "SecurityGroupRuleId": identity,
                    "Description": SECRET,
                },
            }
        else:
            body = {
                "GroupId": GROUP,
                "SecurityGroupRule": {
                    "SecurityGroupRuleId": identity,
                    "SecurityGroupRule": {"ToPort": 23, "private": SECRET},
                },
            }
        request = {name + "Request": body}
    raw = {
        "eventID": event_id,
        "eventName": name,
        "eventTime": (NOW - timedelta(hours=1)).isoformat(),
        "eventSource": "ec2.amazonaws.com",
        "awsRegion": REGION,
        "recipientAccountId": ACCOUNT,
        "readOnly": False,
        "requestParameters": request,
        "responseElements": {"private": SECRET},
        "sourceIPAddress": SECRET,
        "userIdentity": {
            "type": "AssumedRole",
            "arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/NetworkAdmin/demo",
            "accessKeyId": SECRET,
        },
        **changes,
    }
    return {
        "EventId": event_id,
        "EventName": name,
        "Resources": [
            {"ResourceName": GROUP, "ResourceType": "AWS::EC2::SecurityGroup"}
        ],
        "CloudTrailEvent": json.dumps(raw),
    }


def params(token=None):
    expected = {
        "LookupAttributes": [{"AttributeKey": "ResourceName", "AttributeValue": GROUP}],
        "StartTime": ANY,
        "EndTime": ANY,
        "MaxResults": 50,
    }
    if token:
        expected["NextToken"] = token
    return expected


@pytest.fixture
def aws(monkeypatch):
    session = boto3.Session(
        aws_access_key_id="test", aws_secret_access_key="test", region_name=REGION
    )
    trail = session.client("cloudtrail")
    sts = session.client("sts")
    monkeypatch.setattr(
        cloudtrail,
        "_session",
        lambda options: SimpleNamespace(
            region_name=REGION,
            client=lambda name, **kwargs: sts if name == "sts" else trail,
        ),
    )
    with Stubber(trail) as stub, Stubber(sts) as identity:
        yield stub, identity
        stub.assert_no_pending_responses()
        identity.assert_no_pending_responses()


def caller(stub):
    stub.add_response(
        "get_caller_identity",
        {
            "Account": ACCOUNT,
            "Arn": f"arn:aws:iam::{ACCOUNT}:user/demo",
            "UserId": "demo",
        },
    )


@pytest.mark.parametrize("kind", [INGRESS, EGRESS])
@pytest.mark.parametrize(
    "shape", ["wrapped_single", "wrapped_list", "sdk_list", "camel_set"]
)
def test_modification_requires_exact_rule_and_records_only_safe_metadata(
    aws, tmp_path, kind, shape
):
    stub, sts = aws
    caller(sts)
    request = {
        "GroupId": GROUP,
        "SecurityGroupRule": {
            "SecurityGroupRuleId": RULE,
            "SecurityGroupRule": {"ToPort": 23, "private": SECRET},
        },
    }
    if shape == "wrapped_single":
        request = {"ModifySecurityGroupRulesRequest": request}
    elif shape == "wrapped_list":
        request["SecurityGroupRule"] = [request["SecurityGroupRule"]]
        request = {"ModifySecurityGroupRulesRequest": request}
    elif shape == "sdk_list":
        request["SecurityGroupRules"] = [request.pop("SecurityGroupRule")]
    else:
        request = {
            "groupId": GROUP,
            "securityGroupRuleSet": {
                "items": [
                    {"securityGroupRuleId": RULE, "securityGroupRule": {"toPort": 23}}
                ]
            },
        }
    stub.add_response(
        "lookup_events",
        {"Events": [event(request=request), event(identity=OTHER, event_id="other")]},
        params(),
    )
    traced = cloudtrail.enrich_trace(result(plan(kind)), options(tmp_path))
    trace = traced.resources[0].trace
    assert trace["status"] == "matched"
    assert trace["correlation"] == "exact_rule_id"
    assert trace["lookup_scope"] == "parent_security_group"
    assert trace["unresolved_rule_events"] == 0
    assert [e["event_id"] for e in trace["events"]] == ["rule-event-1"]
    assert trace["events"][0]["matched_attributes"] == ["to_port"]
    assert trace["events"][0]["relation"] == "candidate"
    assert SECRET not in json.dumps(traced.to_dict()) + render_drift(traced)
    assert traced.trace["status"] == "complete"


@pytest.mark.parametrize(
    "reference",
    [GROUP, f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/{GROUP}", RULE, ARN],
)
def test_parent_or_rule_resource_reference_is_accepted_with_exact_request_id(
    aws, tmp_path, reference
):
    stub, sts = aws
    caller(sts)
    candidate = event()
    candidate["Resources"][0]["ResourceName"] = reference
    stub.add_response("lookup_events", {"Events": [candidate]}, params())
    assert (
        cloudtrail.enrich_trace(result(), options(tmp_path))
        .resources[0]
        .trace["status"]
        == "matched"
    )


@pytest.mark.parametrize("kind,suffix", [(INGRESS, "Ingress"), (EGRESS, "Egress")])
def test_deleted_rule_uses_saved_scoped_identity_and_directional_revoke(
    aws, tmp_path, kind, suffix
):
    stub, sts = aws
    caller(sts)
    stub.add_response(
        "lookup_events",
        {
            "Events": [
                event("RevokeSecurityGroup" + suffix),
                event(
                    "RevokeSecurityGroup"
                    + ("Egress" if suffix == "Ingress" else "Ingress"),
                    event_id="wrong-direction",
                ),
            ]
        },
        params(),
    )
    r = result(plan(kind, "delete"))
    assert r.resources[0].identifiers["security_group_id"]["source"] == "saved"
    trace = cloudtrail.enrich_trace(r, options(tmp_path)).resources[0].trace
    assert trace["status"] == "matched" and len(trace["events"]) == 1
    assert trace["events"][0]["event_name"] == "RevokeSecurityGroup" + suffix


@pytest.mark.parametrize("kind,suffix", [(INGRESS, "Ingress"), (EGRESS, "Egress")])
def test_description_api_requires_rule_id(aws, tmp_path, kind, suffix):
    stub, sts = aws
    caller(sts)
    stub.add_response(
        "lookup_events",
        {"Events": [event("UpdateSecurityGroupRuleDescriptions" + suffix)]},
        params(),
    )
    trace = (
        cloudtrail.enrich_trace(
            result(plan(kind, field="description")), options(tmp_path)
        )
        .resources[0]
        .trace
    )
    assert trace["status"] == "matched"
    assert trace["events"][0]["matched_attributes"] == ["description"]


@pytest.mark.parametrize(
    "request_payload",
    [
        None,
        {},
        {"groupId": GROUP, "ipPermissions": {"items": []}},
        {"ModifySecurityGroupRulesRequest": {"GroupId": GROUP}},
        {
            "ModifySecurityGroupRulesRequest": {
                "GroupId": GROUP,
                "SecurityGroupRule": {"SecurityGroupRuleId": RULE},
            }
        },
        {
            "ModifySecurityGroupRulesRequest": {
                "GroupId": GROUP,
                "SecurityGroupRule": {
                    "SecurityGroupRuleId": "bad",
                    "SecurityGroupRule": {"ToPort": 23},
                },
            }
        },
    ],
)
def test_unresolved_schema_is_partial_not_an_assertion_of_no_events(
    aws, tmp_path, request_payload
):
    stub, sts = aws
    caller(sts)
    candidate = event()
    raw = json.loads(candidate["CloudTrailEvent"])
    raw["requestParameters"] = request_payload
    candidate["CloudTrailEvent"] = json.dumps(raw)
    stub.add_response("lookup_events", {"Events": [candidate, candidate]}, params())
    traced = cloudtrail.enrich_trace(result(), options(tmp_path))
    trace = traced.resources[0].trace
    assert trace["status"] == "partial" and trace["unresolved_rule_events"] == 1
    assert trace["events"] == []
    assert not traced.trace["has_errors"]


@pytest.mark.parametrize(
    "change",
    [
        "other_rule",
        "other_group",
        "wrong_field",
        "no_reference",
        "read",
        "error",
        "scope",
        "time",
        "decoy",
    ],
)
def test_unrelated_or_untrusted_events_do_not_match(aws, tmp_path, change):
    stub, sts = aws
    caller(sts)
    candidate = event(identity=OTHER if change in ("other_rule", "decoy") else RULE)
    raw = json.loads(candidate["CloudTrailEvent"])
    body = raw["requestParameters"]["ModifySecurityGroupRulesRequest"]
    if change == "other_group":
        body["GroupId"] = "sg-1123456789abcdef0"
    elif change == "wrong_field":
        body["SecurityGroupRule"]["SecurityGroupRule"] = {"Description": SECRET}
    elif change == "no_reference":
        candidate["Resources"] = []
    elif change == "read":
        raw["readOnly"] = True
    elif change == "error":
        raw["errorCode"] = "AccessDenied"
    elif change == "scope":
        raw["recipientAccountId"] = "999999999999"
    elif change == "time":
        raw["eventTime"] = (NOW + timedelta(hours=1)).isoformat()
    elif change == "decoy":
        body["SecurityGroupRule"]["SecurityGroupRule"]["Description"] = RULE
        raw["responseElements"]["securityGroupRuleId"] = RULE
    candidate["CloudTrailEvent"] = json.dumps(raw)
    stub.add_response("lookup_events", {"Events": [candidate]}, params())
    trace = cloudtrail.enrich_trace(result(), options(tmp_path)).resources[0].trace
    assert trace["status"] == "no_events" and not trace["events"]


@pytest.mark.parametrize(
    "field", ["id", "arn", "security_group_id", "security_group_rule_id"]
)
@pytest.mark.parametrize(
    "mask", ["before_sensitive", "after_sensitive", "after_unknown"]
)
def test_masked_identity_never_triggers_aws_access(tmp_path, monkeypatch, field, mask):
    monkeypatch.setattr(
        cloudtrail,
        "_session",
        lambda options: pytest.fail("Masked identity triggered AWS access"),
    )
    traced = cloudtrail.enrich_trace(
        result(plan(**{mask: {field: True}})), options(tmp_path)
    )
    assert traced.resources[0].trace["status"] == "skipped"
    assert not traced.trace["has_errors"]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("id", "bad", "invalid_identifiers"),
        ("arn", ARN.replace(RULE, OTHER), "invalid_identifiers"),
        ("security_group_id", "bad", "invalid_parent_group"),
        ("security_group_rule_id", OTHER, "conflicting_rule_identifiers"),
    ],
)
def test_invalid_or_conflicting_identity_never_triggers_aws(
    tmp_path, monkeypatch, field, value, reason
):
    monkeypatch.setattr(
        cloudtrail,
        "_session",
        lambda options: pytest.fail("Invalid identity triggered AWS access"),
    )
    payload = plan()
    for side in ("before", "after"):
        payload["resource_drift"][0]["change"][side][field] = value
    traced = cloudtrail.enrich_trace(result(payload), options(tmp_path))
    assert traced.resources[0].trace["reason"] == reason


def test_missing_parent_never_uses_unmasked_network_context_as_a_fallback(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        cloudtrail,
        "_session",
        lambda options: pytest.fail("Missing parent triggered AWS access"),
    )
    r = result()
    resource = r.resources[0]
    identifiers = deepcopy(resource.identifiers)
    identifiers.pop("security_group_id")
    traced = cloudtrail.enrich_trace(
        replace(r, resources=(replace(resource, identifiers=identifiers),)),
        options(tmp_path),
    )
    assert traced.resources[0].trace["reason"] == "missing_parent_group"


def test_mixed_unsupported_attributes_still_report_partial_coverage(aws, tmp_path):
    stub, sts = aws
    caller(sts)
    payload = plan()
    payload["resource_drift"][0]["change"]["after"]["tags"] = {"env": "test"}
    stub.add_response("lookup_events", {"Events": [event()]}, params())
    trace = (
        cloudtrail.enrich_trace(result(payload), options(tmp_path)).resources[0].trace
    )
    assert trace["status"] == "partial"
    assert trace["unsupported_attributes"] == [["tags", "env"]]
    assert len(trace["events"]) == 1


def test_rule_event_from_completed_page_survives_later_aws_error(aws, tmp_path):
    stub, sts = aws
    caller(sts)
    stub.add_response(
        "lookup_events", {"Events": [event()], "NextToken": "page2"}, params()
    )
    stub.add_client_error(
        "lookup_events",
        service_error_code="AccessDeniedException",
        service_message=SECRET,
        expected_params=params("page2"),
    )
    traced = cloudtrail.enrich_trace(result(), options(tmp_path))
    assert traced.trace["has_errors"]
    assert traced.resources[0].trace["status"] == "error"
    assert len(traced.resources[0].trace["events"]) == 1
    assert SECRET not in json.dumps(traced.to_dict())


def test_cli_import_trace_uses_new_matcher_without_terraform(
    aws, tmp_path, monkeypatch, project
):
    stub, sts = aws
    caller(sts)
    stub.add_response("lookup_events", {"Events": [event()]}, params())
    monkeypatch.setattr(
        "infralens.drift_service.Terraform",
        lambda options: pytest.fail("Import ran Terraform"),
    )
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(plan()))
    response = CliRunner().invoke(
        app,
        [
            "drift",
            str(project),
            "--plan-json",
            str(source),
            "--trace",
            "--region",
            REGION,
            "--format",
            "json",
            "--fail-on-drift",
        ],
    )
    assert response.exit_code == 1, response.output
    report = json.loads(response.stdout)
    assert report["resources"][0]["trace"]["events"][0]["matched_attributes"] == [
        "to_port"
    ]
    assert report["resources"][0]["assessment"]["priority"] == "high"
    assert SECRET not in response.stdout


@pytest.mark.parametrize(
    "region,account", [("us-east-1", ACCOUNT), (REGION, "999999999999")]
)
def test_rule_scope_mismatch_never_looks_up_events(aws, tmp_path, region, account):
    _, sts = aws
    caller(sts)
    payload = plan()
    for side in ("before", "after"):
        payload["resource_drift"][0]["change"][side]["arn"] = (
            f"arn:aws:ec2:{region}:{account}:security-group-rule/{RULE}"
        )
    trace = (
        cloudtrail.enrich_trace(result(payload), options(tmp_path)).resources[0].trace
    )
    assert trace["status"] == "skipped" and trace["reason"] == "scope_mismatch"


@pytest.mark.parametrize("missing", ["id", "arn", "security_group_id"])
def test_missing_rule_identifiers_never_create_session(tmp_path, monkeypatch, missing):
    monkeypatch.setattr(
        cloudtrail,
        "_session",
        lambda options: pytest.fail("Incomplete identity triggered AWS access"),
    )
    payload = plan()
    for side in ("before", "after"):
        payload["resource_drift"][0]["change"][side].pop(missing)
    trace = (
        cloudtrail.enrich_trace(result(payload), options(tmp_path)).resources[0].trace
    )
    assert trace["status"] == "skipped"


def test_legacy_composite_rule_is_explicitly_unsupported(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cloudtrail,
        "_session",
        lambda options: pytest.fail("Legacy rule triggered AWS access"),
    )
    trace = (
        cloudtrail.enrich_trace(
            result(plan("aws_security_group_rule")), options(tmp_path)
        )
        .resources[0]
        .trace
    )
    assert trace["reason"] == "unsupported_resource"


@pytest.mark.parametrize(
    "name,kind,action,field",
    [
        ("RevokeSecurityGroupIngress", INGRESS, "delete", "to_port"),
        ("RevokeSecurityGroupEgress", EGRESS, "delete", "to_port"),
        (
            "UpdateSecurityGroupRuleDescriptionsIngress",
            INGRESS,
            "update",
            "description",
        ),
        ("UpdateSecurityGroupRuleDescriptionsEgress", EGRESS, "update", "description"),
    ],
)
def test_camel_case_rule_id_collections(aws, tmp_path, name, kind, action, field):
    stub, sts = aws
    caller(sts)
    key = (
        "securityGroupRuleIdSet"
        if action == "delete"
        else "securityGroupRuleDescriptionSet"
    )
    request_payload = {
        "groupId": GROUP,
        key: {"items": [{"securityGroupRuleId": RULE}]},
    }
    stub.add_response(
        "lookup_events", {"Events": [event(name, request=request_payload)]}, params()
    )
    trace = (
        cloudtrail.enrich_trace(result(plan(kind, action, field)), options(tmp_path))
        .resources[0]
        .trace
    )
    assert trace["status"] == "matched"


def test_backend_worker_uses_rule_trace_and_persists_only_normalized_event(
    aws, tmp_path
):
    import time

    from fastapi.testclient import TestClient

    from infralens.backend.api import create_app
    from infralens.backend.config import Project, Settings

    stub, sts = aws
    caller(sts)
    stub.add_response("lookup_events", {"Events": [event()]}, params())
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.tf").write_text(f'resource "{INGRESS}" "demo" {{}}')
    token = "fake_backend_rule_trace_test_token_123456"
    auth = {"Authorization": "Bearer " + token}
    settings = Settings(
        {
            "demo": Project(
                "demo",
                "Demo",
                root,
                region=REGION,
                allow_refresh=False,
                allow_trace=True,
            )
        },
        tmp_path / "history.sqlite3",
        token,
    )
    payload = plan()
    for side in ("before", "after"):
        payload["resource_drift"][0]["change"][side]["unused_secret"] = SECRET
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/projects/demo/runs",
            headers=auth,
            json={"mode": "import", "trace": True, "plan": payload},
        )
        assert response.status_code == 202
        run_id = response.json()["run"]["id"]
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            row = client.get(f"/api/v1/runs/{run_id}", headers=auth).json()
            if row["status"] not in ("running", "queued"):
                break
            time.sleep(0.01)
        assert row["status"] == "succeeded"
        response = client.get(f"/api/v1/runs/{run_id}/report", headers=auth)
        assert response.json()["resources"][0]["trace"]["status"] == "matched"
        assert SECRET not in response.text
    for name in ("history.sqlite3", "history.sqlite3-wal", "history.sqlite3-shm"):
        path = tmp_path / name
        if path.exists():
            assert SECRET.encode() not in path.read_bytes()
    with TestClient(create_app(settings)) as client:
        assert (
            client.get(f"/api/v1/runs/{run_id}/report", headers=auth).json()
            == response.json()
        )
