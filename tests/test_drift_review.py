import json
from copy import deepcopy
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from infralens.cli import app
from infralens.drift import AttributeChange, DriftResult, ResourceDrift
from infralens.drift_reporting import render_drift
from infralens.drift_review import assess_resource, enrich_review

SECRET = "PRIVATE_REVIEW_VALUE"


def value(data):
    return {"status": "known", "value": data}


def change(path, before, after):
    return AttributeChange(tuple(path), value(before), value(after))


def resource(attributes=(), kind="aws_security_group", actions=("update",)):
    return ResourceDrift(f"{kind}.demo", kind, actions, tuple(attributes))


def rule(start=22, end=None, protocol="tcp", cidr="0.0.0.0/0", family=4, **extra):
    return {
        "protocol": protocol,
        "from_port": start,
        "to_port": start if end is None else end,
        "cidr_blocks": [cidr] if family == 4 else [],
        "ipv6_cidr_blocks": [cidr] if family == 6 else [],
        **extra,
    }


def codes(assessment):
    return {signal["code"] for signal in assessment["signals"]}


@pytest.mark.parametrize(
    "cidr,family,protocol",
    [
        ("0.0.0.0/0", 4, "tcp"),
        ("::/0", 6, "tcp"),
        ("0:0:0:0:0:0:0:0/0", 6, "udp"),
        ("0.0.0.0/0", 4, "-1"),
        ("0.0.0.0/0", 4, "6"),
        ("0.0.0.0/0", 4, "17"),
    ],
)
def test_new_world_ingress_is_high(cidr, family, protocol):
    assessment = assess_resource(
        resource(
            [
                change(
                    ["ingress"], [], [rule(protocol=protocol, cidr=cidr, family=family)]
                )
            ]
        )
    )
    assert assessment["priority"] == "high"
    assert "world_ingress_added_or_expanded" in codes(assessment)


@pytest.mark.parametrize(
    "old,new",
    [
        ([rule()], [rule(22, 23)]),
        ([rule()], [rule(protocol="udp")]),
        ([rule()], [rule(cidr="::/0", family=6)]),
        ([rule()], [rule(protocol="-1")]),
    ],
)
def test_wider_port_protocol_or_address_family_requires_high_review(old, new):
    assessment = assess_resource(resource([change(["ingress"], old, new)]))
    assert assessment["priority"] == "high"


@pytest.mark.parametrize(
    "old,new",
    [
        ([rule(0, 65535)], [rule()]),
        ([rule(protocol="-1")], [rule()]),
        ([rule()], [rule(description="description changed")]),
        ([rule(22), rule(23)], [rule(22, 23)]),
        ([rule()], []),
        ([], [rule(cidr="10.241.0.0/24")]),
    ],
)
def test_narrowing_reordering_and_descriptions_do_not_invent_new_exposure(old, new):
    assessment = assess_resource(resource([change(["ingress"], old, new)]))
    assert assessment["priority"] == "medium"
    assert "world_ingress_added_or_expanded" not in codes(assessment)


def test_egress_is_not_misclassified_as_public_ingress():
    assessment = assess_resource(resource([change(["egress"], [], [rule()])]))
    assert assessment["priority"] == "medium"
    assert codes(assessment) == {"network_rules_changed"}


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        [None],
        [rule(protocol="icmp")],
        [rule(protocol={})],
        [rule(start=True)],
        [rule(40, 20)],
        [rule(-1, 22)],
        [rule(0, 70000)],
        [rule(cidr="invalid")],
        [rule(cidr="::/0", family=4)],
        [rule(cidr_blocks="0.0.0.0/0")],
    ],
)
def test_unrecognized_network_details_require_manual_review(bad):
    assessment = assess_resource(resource([change(["ingress"], [], bad)]))
    assert assessment["priority"] == "unknown"
    assert codes(assessment) == {"network_details_unavailable"}


@pytest.mark.parametrize("status", ["sensitive", "unknown", "absent"])
def test_unavailable_values_are_not_used_even_if_a_value_is_present(status):
    attribute = AttributeChange(
        ("ingress",), value([]), {"status": status, "value": [rule(description=SECRET)]}
    )
    assessment = assess_resource(resource([attribute]))
    assert assessment["priority"] == "unknown"
    assert codes(assessment) == {"values_unavailable"}
    assert SECRET not in json.dumps(assessment)


@pytest.mark.parametrize("kind", ["aws_instance", "aws_db_instance", "local_file"])
def test_missing_resource_is_high_and_needs_recovery_review(kind):
    assessment = assess_resource(resource(kind=kind, actions=("delete",)))
    assert assessment["priority"] == "high"
    assert codes(assessment) == {"resource_missing"}
    assert any("recovery" in step for step in assessment["guidance"]["review_steps"])


def test_instance_type_change_has_medium_priority_without_guessing_cost():
    assessment = assess_resource(
        resource(
            [change(["instance_type"], "t3.micro", "t3.small")], kind="aws_instance"
        )
    )
    assert assessment["priority"] == "medium"
    assert codes(assessment) == {"instance_type_changed"}


@pytest.mark.parametrize("path", [["tags", "env"], ["tags_all"], ["size"], []])
def test_tags_and_unsupported_changes_are_not_assumed_low_risk(path):
    assessment = assess_resource(resource([change(path, "old", "new")]))
    assert assessment["priority"] == "unknown"


def test_empty_visible_delta_still_requires_review():
    assessment = assess_resource(resource())
    assert assessment["priority"] == "unknown"


def test_unknown_change_is_not_hidden_by_a_medium_signal():
    assessment = assess_resource(
        resource(
            [
                change(["instance_type"], "t3.micro", "t3.small"),
                AttributeChange(
                    ("password",), {"status": "sensitive"}, {"status": "sensitive"}
                ),
            ],
            kind="aws_instance",
        )
    )
    assert assessment["priority"] == "unknown"
    assert codes(assessment) == {"instance_type_changed", "values_unavailable"}


def test_high_signal_remains_visible_alongside_unknown_changes():
    assessment = assess_resource(
        resource([change(["ingress"], [], [rule()]), change(["unsupported"], 1, 2)])
    )
    assert assessment["priority"] == "high"
    assert "unclassified_change" in codes(assessment)


def test_guidance_preserves_two_choices_and_does_not_copy_input_values():
    r = resource(
        [change(["instance_type"], SECRET, "$(malicious-command)")], kind="aws_instance"
    )
    r = replace(r, trace={"status": "matched", "events": [{"actor": SECRET}]})
    assessment = assess_resource(r)
    assert {choice["id"] for choice in assessment["guidance"]["choices"]} == {
        "restore_approved_configuration",
        "adopt_approved_external_change",
    }
    assert any(
        "candidate CloudTrail" in step
        for step in assessment["guidance"]["review_steps"]
    )
    text = json.dumps(assessment)
    assert SECRET not in text
    assert "malicious-command" not in text
    assert "state-only refresh does not update code" in text


def test_enrichment_is_pure_and_preserves_trace_source_and_drift_counts():
    first = replace(resource(actions=("delete",)), source={"status": "unavailable"})
    second = resource(
        [change(["instance_type"], "t3.micro", "t3.small")], kind="aws_instance"
    )
    third = replace(
        resource([change(["tags"], {}, {"x": 1})]), address="aws_security_group.other"
    )
    original = DriftResult(
        "1.16.5",
        (first, second, third),
        "refresh_only",
        "now",
        trace={"status": "complete", "has_errors": False},
    )
    snapshot = deepcopy(original.to_dict())
    reviewed = enrich_review(original)
    report = reviewed.to_dict()
    assert original.to_dict() == snapshot
    assert reviewed.trace == original.trace
    assert reviewed.resources[0].source == original.resources[0].source
    assert report["summary"] == snapshot["summary"]
    assert report["has_drift"] == snapshot["has_drift"]
    assert report["review_summary"]["priority_counts"] == {
        "high": 1,
        "medium": 1,
        "unknown": 1,
    }
    table = render_drift(reviewed)
    assert "Review priorities: high=1, medium=1, unknown=1" in table
    assert "review a normal Terraform plan" in table


def test_clean_result_has_no_synthetic_assessment():
    original = DriftResult("1.16.5", (), "refresh_only", "now")
    assert enrich_review(original) is original
    assert "review_summary" not in original.to_dict()


@pytest.mark.parametrize("fail_on,exit_code", [(False, 0), (True, 1)])
def test_cli_advice_never_writes_state_or_runs_terraform_for_imported_plan(
    project, tmp_path, monkeypatch, fail_on, exit_code
):
    def forbidden(*args, **kwargs):
        pytest.fail("Review must not execute Terraform or call AWS")

    monkeypatch.setattr("infralens.drift_service.Terraform", forbidden)
    monkeypatch.setattr("infralens.cloudtrail._session", forbidden)
    state = project / "terraform.tfstate"
    state.write_text(SECRET)
    fingerprint = state.read_bytes(), state.stat().st_mtime_ns
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
                            "before": {"tags": {"env": "old"}},
                            "after": {"tags": {"env": "new"}},
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
            "--plan-json",
            str(imported),
            "--format",
            "json",
            *(["--fail-on-drift"] if fail_on else []),
        ],
    )
    assert cli.exit_code == exit_code, cli.output
    report = json.loads(cli.stdout)
    assert report["has_drift"] is True
    assert report["resources"][0]["assessment"]["priority"] == "unknown"
    assert fingerprint == (state.read_bytes(), state.stat().st_mtime_ns)
    assert SECRET not in cli.output
