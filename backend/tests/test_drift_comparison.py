"""Retain rule-context comparison guarantees from the local drift implementation."""

import copy
import json

import pytest

from infralens_backend.drift_comparison import compare_runs
from infralens_backend.drift_schemas import NETWORK_FIELDS


def rule_report(cidr="10.0.0.0/24"):
    kind = "aws_vpc_security_group_ingress_rule"
    values = {name: {"status": "absent"} for name in NETWORK_FIELDS[kind]}
    values["cidr_ipv4"] = {"status": "known", "value": cidr}
    return {
        "resources": [
            {
                "address": f"{kind}.demo",
                "resource_type": kind,
                "actions": ["update"],
                "attributes": [
                    {
                        "path": ["to_port"],
                        "before": {"status": "known", "value": 22},
                        "after": {"status": "known", "value": 23},
                    }
                ],
                "network_context": {
                    "version": "security-group-rule-v1",
                    "before": values,
                    "after": copy.deepcopy(values),
                },
            }
        ],
    }


def compare(old, new):
    return compare_runs(
        {"id": "new", "report_json": new}, {"id": "old", "report_json": old}
    )


def test_comparison_detects_context_change_without_copying_values():
    old, new = rule_report(), rule_report("0.0.0.0/0")
    assert old["resources"][0]["attributes"] == new["resources"][0]["attributes"]
    result = compare(old, new)
    assert result["resources"][0]["status"] == "changed"
    assert result["resources"][0]["changed_paths"] == [["cidr_ipv4"]]
    assert "10.0.0.0/24" not in json.dumps(result)
    assert "0.0.0.0/0" not in json.dumps(result)


@pytest.mark.parametrize("uncertainty", ["missing", "sensitive", "unknown"])
def test_incomplete_context_cannot_be_reported_unchanged(uncertainty):
    old, new = rule_report(), rule_report()
    if uncertainty == "missing":
        old["resources"][0].pop("network_context")
    else:
        new["resources"][0]["network_context"]["after"]["cidr_ipv4"] = {
            "status": uncertainty
        }
    assert compare(old, new)["resources"][0]["status"] == "indeterminate"


def test_identical_known_rule_context_is_unchanged():
    report = rule_report()
    assert compare(report, report)["resources"][0]["status"] == "unchanged"
