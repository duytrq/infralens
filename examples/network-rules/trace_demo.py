"""Offline CloudTrail rule demo. Stubber intercepts every SDK request."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from infralens.drift import parse_plan
from infralens.drift_reporting import render_drift
from infralens.drift_service import collect_drift
from infralens.options import DriftOptions

ACCOUNT, REGION = "123456789012", "ap-southeast-2"


def main():
    parser = argparse.ArgumentParser(
        description="Offline CloudTrail demo with fake AWS events"
    )
    parser.add_argument("--format", choices=("table", "json"), default="table")
    args = parser.parse_args()
    try:
        import boto3
        from botocore.stub import ANY, Stubber
    except ImportError:
        print("Reinstall InfraLens to restore its AWS SDK dependency.", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent
    payload = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    keep = {"widen_ports", "widen_egress", "hidden_context", "legacy_direction"}
    payload["resource_drift"] = [
        r for r in payload["resource_drift"] if r["address"].split(".")[-1] in keep
    ]
    for index, resource in enumerate(payload["resource_drift"], 1):
        if resource["type"] == "aws_security_group_rule":
            continue
        change = resource["change"]
        if resource["address"].endswith(".widen_egress"):
            change.update(actions=["delete"], after=None)
        rule_id = f"sgr-{index:017x}"
        for side in ("before", "after"):
            if isinstance(change[side], dict):
                change[side].update(
                    id=rule_id,
                    security_group_rule_id=rule_id,
                    arn=f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group-rule/{rule_id}",
                )
    normalized = parse_plan(json.dumps(payload))
    session = boto3.Session(
        aws_access_key_id="test", aws_secret_access_key="test", region_name=REGION
    )
    sts, trail = session.client("sts"), session.client("cloudtrail")
    fake_session = SimpleNamespace(
        region_name=REGION,
        client=lambda name, **kwargs: sts if name == "sts" else trail,
    )
    with Stubber(sts) as sts_stub, Stubber(trail) as trail_stub:
        sts_stub.add_response(
            "get_caller_identity",
            {
                "Account": ACCOUNT,
                "Arn": f"arn:aws:iam::{ACCOUNT}:user/offline-demo",
                "UserId": "offline-demo",
            },
        )
        for index, resource in enumerate(normalized.resources):
            if resource.resource_type == "aws_security_group_rule":
                continue
            group = resource.identifiers["security_group_id"]["value"]
            rule_id = resource.identifiers["id"]["value"]
            deleted = resource.actions == ("delete",)
            name = (
                "RevokeSecurityGroupEgress" if deleted else "ModifySecurityGroupRules"
            )
            body = {"GroupId": group}
            if deleted:
                body["SecurityGroupRuleId"] = [rule_id]
            elif not resource.address.endswith(".hidden_context"):
                body["SecurityGroupRule"] = {
                    "SecurityGroupRuleId": rule_id,
                    "SecurityGroupRule": {"ToPort": 23},
                }
            event_id = f"offline-rule-event-{index}"
            raw = {
                "eventID": event_id,
                "eventName": name,
                "eventTime": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).isoformat(),
                "eventSource": "ec2.amazonaws.com",
                "awsRegion": REGION,
                "recipientAccountId": ACCOUNT,
                "readOnly": False,
                "requestParameters": {name + "Request": body},
                "userIdentity": {
                    "type": "AssumedRole",
                    "arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/OfflineDemo/demo",
                },
            }
            event = {
                "EventId": event_id,
                "EventName": name,
                "Resources": [{"ResourceName": group}],
                "CloudTrailEvent": json.dumps(raw),
            }
            trail_stub.add_response(
                "lookup_events",
                {"Events": [event]},
                {
                    "LookupAttributes": [
                        {"AttributeKey": "ResourceName", "AttributeValue": group}
                    ],
                    "StartTime": ANY,
                    "EndTime": ANY,
                    "MaxResults": 50,
                },
            )
        options = DriftOptions(
            root, (), args.format, None, None, REGION, True, 7, False
        )
        with patch("infralens.cloudtrail._session", return_value=fake_session):
            reviewed = collect_drift(options, normalized)
        sts_stub.assert_no_pending_responses()
        trail_stub.assert_no_pending_responses()
    print(
        "OFFLINE DEMO: synthetic plan and AWS identity/events; no AWS requests sent.",
        file=sys.stderr,
    )
    print(
        json.dumps(reviewed.to_dict(), indent=2)
        if args.format == "json"
        else render_drift(reviewed),
        end="\n" if args.format == "json" else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
