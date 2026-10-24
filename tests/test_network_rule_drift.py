import json
import time
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from infralens.backend.api import create_app
from infralens.backend.comparison import compare_runs
from infralens.backend.config import Project, Settings
from infralens.backend.worker import restore_imported
from infralens.cli import app
from infralens.drift import NETWORK_RULE_FIELDS, parse_plan
from infralens.drift_reporting import render_drift
from infralens.drift_review import enrich_review

INGRESS = "aws_vpc_security_group_ingress_rule"
EGRESS = "aws_vpc_security_group_egress_rule"
LEGACY = "aws_security_group_rule"
SECRET = "PRIVATE_UNCHANGED_RULE_CONTEXT"
TOKEN = "local_network_rule_test_token_12345678"
AUTH = {"Authorization": "Bearer " + TOKEN}


def entry(kind=INGRESS, old=None, new=None, **masks):
    before = {
        "security_group_id": "sg-0123456789abcdef0",
        "region": "ap-southeast-2",
        "from_port": 22,
        "to_port": 22,
        **(
            {"protocol": "tcp", "type": "ingress", "cidr_blocks": ["0.0.0.0/0"]}
            if kind == LEGACY
            else {"ip_protocol": "tcp", "cidr_ipv4": "0.0.0.0/0"}
        ),
        **(old or {}),
    }
    return {
        "address": f"{kind}.demo",
        "type": kind,
        "mode": "managed",
        "change": {
            "actions": ["update"],
            "before": before,
            "after": {**before, **(new or {"to_port": 23})},
            **masks,
        },
    }


def plan(item):
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.5",
        "planned_values": {},
        "resource_drift": [item],
    }


def parsed(item):
    return parse_plan(json.dumps(plan(item)))


def assessment(item):
    return enrich_review(parsed(item)).resources[0].assessment


@pytest.mark.parametrize(
    "kind,old,new,priority",
    [
        (INGRESS, {}, {"to_port": 23}, "high"),
        (INGRESS, {"cidr_ipv4": "10.0.0.0/24"}, {"cidr_ipv4": "0.0.0.0/0"}, "high"),
        (
            INGRESS,
            {"cidr_ipv4": None, "cidr_ipv6": "2001:db8::/64"},
            {"cidr_ipv6": "::/0"},
            "high",
        ),
        (INGRESS, {}, {"cidr_ipv4": None, "cidr_ipv6": "::/0"}, "high"),
        (INGRESS, {}, {"ip_protocol": "udp"}, "high"),
        (
            INGRESS,
            {},
            {"ip_protocol": "-1", "from_port": None, "to_port": None},
            "high",
        ),
        (INGRESS, {}, {"security_group_id": "sg-1123456789abcdef0"}, "high"),
        (INGRESS, {}, {"region": "us-east-1"}, "high"),
        (INGRESS, {"to_port": 23}, {"to_port": 22}, "medium"),
        (
            INGRESS,
            {"ip_protocol": "-1", "from_port": None, "to_port": None},
            {"ip_protocol": "tcp", "from_port": 22, "to_port": 22},
            "medium",
        ),
        (INGRESS, {}, {"ip_protocol": "6"}, "medium"),
        (INGRESS, {"ip_protocol": "udp"}, {"ip_protocol": "17"}, "medium"),
        (INGRESS, {}, {"description": "approved description"}, "medium"),
        (INGRESS, {}, {"cidr_ipv4": "10.0.0.0/24"}, "medium"),
        (INGRESS, {"cidr_ipv4": "10.0.0.0/24"}, {"cidr_ipv4": "10.0.0.0/16"}, "medium"),
        (EGRESS, {}, {"to_port": 23}, "medium"),
        (EGRESS, {"cidr_ipv4": "10.0.0.0/24"}, {"cidr_ipv4": "0.0.0.0/0"}, "medium"),
        (LEGACY, {}, {"to_port": 23}, "high"),
        (
            LEGACY,
            {"cidr_blocks": ["10.0.0.0/24"]},
            {"cidr_blocks": ["0.0.0.0/0"]},
            "high",
        ),
        (LEGACY, {"type": "egress"}, {"type": "ingress"}, "high"),
        (LEGACY, {}, {"type": "egress"}, "medium"),
        (LEGACY, {}, {"protocol": "all"}, "high"),
        (LEGACY, {"protocol": "all"}, {"protocol": "tcp"}, "medium"),
        (LEGACY, {}, {"cidr_blocks": [], "ipv6_cidr_blocks": ["::/0"]}, "high"),
        (
            LEGACY,
            {"cidr_blocks": ["10.0.0.0/24", "10.0.1.0/24"]},
            {"cidr_blocks": ["10.0.1.0/24", "10.0.0.0/24"]},
            "medium",
        ),
    ],
)
def test_network_rule_review_uses_complete_context(kind, old, new, priority):
    result = assessment(entry(kind, old, new))
    assert result["priority"] == priority
    codes = {signal["code"] for signal in result["signals"]}
    assert ("world_ingress_added_or_expanded" in codes) == (priority == "high")
    assert "network_rules_changed" in codes


@pytest.mark.parametrize(
    "kind,old,new",
    [
        (INGRESS, {"ip_protocol": "icmp"}, {}),
        (INGRESS, {"ip_protocol": {}}, {}),
        (INGRESS, {"to_port": True}, {}),
        (INGRESS, {}, {"to_port": 70000}),
        (INGRESS, {}, {"from_port": 50, "to_port": 22}),
        (INGRESS, {}, {"cidr_ipv4": "::/0"}),
        (INGRESS, {}, {"cidr_ipv4": None}),
        (INGRESS, {}, {"cidr_ipv4": None, "prefix_list_id": "pl-example"}),
        (
            INGRESS,
            {"cidr_ipv4": None, "referenced_security_group_id": "sg-example"},
            {"cidr_ipv4": "0.0.0.0/0", "referenced_security_group_id": None},
        ),
        (INGRESS, {}, {"cidr_ipv6": "::/0"}),
        (INGRESS, {"security_group_id": None}, {}),
        (INGRESS, {"region": 4}, {}),
        (LEGACY, {"type": "invalid"}, {}),
        (LEGACY, {"cidr_blocks": []}, {}),
        (LEGACY, {"cidr_blocks": "0.0.0.0/0"}, {}),
        (LEGACY, {"prefix_list_ids": ["pl-example"]}, {}),
        (LEGACY, {"source_security_group_id": "sg-example"}, {}),
        (LEGACY, {"self": True}, {}),
    ],
)
def test_unsupported_or_invalid_semantics_are_unknown(kind, old, new):
    result = assessment(entry(kind, old, new))
    assert result["priority"] == "unknown"
    assert "network_details_unavailable" in {s["code"] for s in result["signals"]}


@pytest.mark.parametrize(
    "mask", ["before_sensitive", "after_sensitive", "after_unknown"]
)
@pytest.mark.parametrize("root", [False, True])
def test_unchanged_masked_context_is_not_inferred_or_leaked(mask, root):
    item = entry(
        old={"security_group_id": SECRET},
        **{mask: True if root else {"security_group_id": True}},
    )
    result = enrich_review(parsed(item))
    context = result.resources[0].network_context
    assert context["after"]["security_group_id"]["status"] in ("sensitive", "unknown")
    assert result.resources[0].assessment["priority"] == "unknown"
    if mask != "after_unknown":
        assert SECRET not in json.dumps(result.to_dict())
        assert SECRET not in render_drift(result)
    else:
        # The known saved value is allowed; it must never be used as observed.
        assert "value" not in context["after"]["security_group_id"]


def test_nested_collection_sensitivity_redacts_entire_context_field():
    item = entry(
        LEGACY, {"cidr_blocks": [SECRET]}, before_sensitive={"cidr_blocks": [True]}
    )
    result = enrich_review(parsed(item))
    assert result.resources[0].network_context["before"]["cidr_blocks"] == {
        "status": "sensitive"
    }
    assert SECRET not in json.dumps(result.to_dict())
    assert result.resources[0].assessment["priority"] == "unknown"


def test_context_is_allowlisted_and_does_not_inflate_drift_counts():
    item = entry(old={"password": SECRET, "description": SECRET})
    result = parsed(item)
    r = result.resources[0]
    assert [c.path for c in r.attributes] == [("to_port",)]
    assert set(r.network_context["before"]) == set(NETWORK_RULE_FIELDS[INGRESS])
    assert result.to_dict()["summary"] == {"resources": 1, "attributes": 1}
    assert SECRET not in json.dumps(result.to_dict())
    restored = restore_imported(result.to_dict())
    assert restored.to_dict() == result.to_dict()
    assert enrich_review(restored).resources[0].assessment["priority"] == "high"
    reviewed = enrich_review(restored).to_dict()
    assert reviewed["review_summary"]["policy"] == "builtin-review-v2"
    assert reviewed["resources"][0]["assessment"]["policy"] == "builtin-review-v2"


def test_missing_protocol_and_context_do_not_default_to_a_network_verdict():
    item = entry()
    for side in ("before", "after"):
        item["change"][side].pop("ip_protocol")
    assert assessment(item)["priority"] == "unknown"
    old_report = parsed(entry()).to_dict()
    old_report["resources"][0].pop("network_context")
    restored = restore_imported(old_report)
    assert restored.resources[0].network_context is None
    assert enrich_review(restored).resources[0].assessment["priority"] == "unknown"


def test_sensitive_description_still_requires_review_when_network_is_known():
    result = assessment(
        entry(new={"description": SECRET}, after_sensitive={"description": True})
    )
    assert result["priority"] == "unknown"


@pytest.mark.parametrize("kind", [INGRESS, EGRESS, LEGACY])
def test_deleted_rule_remains_high_without_snapshot(kind):
    item = entry(kind)
    item["change"].update(actions=["delete"], after=None)
    result = enrich_review(parsed(item))
    assert result.resources[0].network_context is None
    assert result.resources[0].assessment["priority"] == "high"


def compared(old, new):
    return compare_runs(
        {"id": "new", "report_json": json.dumps(new)},
        {"id": "old", "report_json": json.dumps(old)},
    )


def test_comparison_detects_unchanged_context_changes_without_emitting_values():
    old = parsed(entry()).to_dict()
    new = parsed(entry(old={"cidr_ipv4": "10.0.0.0/24"})).to_dict()
    assert old["resources"][0]["attributes"] == new["resources"][0]["attributes"]
    result = compared(old, new)
    assert result["resources"][0]["status"] == "changed"
    assert result["resources"][0]["changed_paths"] == [["cidr_ipv4"]]
    assert "10.0.0.0/24" not in json.dumps(result)


@pytest.mark.parametrize("change", ["missing", "sensitive", "unknown"])
def test_comparison_cannot_claim_context_is_unchanged_if_unavailable(change):
    old = parsed(entry()).to_dict()
    new = deepcopy(old)
    if change == "missing":
        old["resources"][0].pop("network_context")
    else:
        new["resources"][0]["network_context"]["after"]["cidr_ipv4"] = {
            "status": change
        }
    assert compared(old, new)["resources"][0]["status"] == "indeterminate"


def test_comparison_with_identical_known_rule_context_is_unchanged():
    report = parsed(entry()).to_dict()
    assert compared(report, report)["resources"][0]["status"] == "unchanged"


def test_cli_import_keeps_context_and_never_runs_tools(project, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Imported rule review must not call Terraform or AWS")

    monkeypatch.setattr("infralens.drift_service.Terraform", forbidden)
    monkeypatch.setattr("infralens.cloudtrail._session", forbidden)
    source = tmp_path / "rule-plan.json"
    source.write_text(json.dumps(plan(entry())))
    response = CliRunner().invoke(
        app,
        [
            "drift",
            str(project),
            "--plan-json",
            str(source),
            "--format",
            "json",
            "--fail-on-drift",
        ],
    )
    assert response.exit_code == 1, response.output
    report = json.loads(response.stdout)
    assert report["resources"][0]["assessment"]["priority"] == "high"
    assert (
        report["resources"][0]["network_context"]["after"]["cidr_ipv4"]["value"]
        == "0.0.0.0/0"
    )


def test_backend_persists_context_reassesses_and_compares(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    settings = Settings(
        {"demo": Project("demo", "Demo", root, allow_refresh=False)},
        tmp_path / "history.sqlite3",
        TOKEN,
    )
    with TestClient(create_app(settings)) as client:
        reports = []
        for item in (
            entry(),
            entry(old={"cidr_ipv4": "10.0.0.0/24", "password": SECRET}),
        ):
            response = client.post(
                "/api/v1/projects/demo/runs",
                headers=AUTH,
                json={"mode": "import", "plan": plan(item)},
            )
            assert response.status_code == 202
            identity = response.json()["run"]["id"]
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                row = client.get(f"/api/v1/runs/{identity}", headers=AUTH).json()
                if row["status"] not in ("queued", "running"):
                    break
                time.sleep(0.01)
            assert row["status"] == "succeeded"
            report = client.get(f"/api/v1/runs/{identity}/report", headers=AUTH).json()
            reports.append(report)
        assert reports[0]["resources"][0]["assessment"]["priority"] == "high"
        assert reports[1]["resources"][0]["assessment"]["priority"] == "medium"
        comparison = client.get(
            f"/api/v1/runs/{identity}/comparison", headers=AUTH
        ).json()
        assert comparison["summary"]["changed"] == 1
        assert comparison["resources"][0]["changed_paths"] == [["cidr_ipv4"]]
    with TestClient(create_app(settings)) as client:
        response = client.get(f"/api/v1/runs/{identity}/report", headers=AUTH)
        assert response.json() == reports[1]
        assert SECRET not in response.text
