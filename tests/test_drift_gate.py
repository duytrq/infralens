import json
from copy import deepcopy
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from infralens.cli import app
from infralens.drift import REVIEW_POLICY, AttributeChange, DriftResult, ResourceDrift
from infralens.drift_gate import evaluate_gate, render_gate
from infralens.errors import ExecutionError

SECRET = "PRIVATE_GATE_VALUE"
runner = CliRunner()


def reviewed(priorities):
    return DriftResult(
        "1.16.5",
        tuple(
            ResourceDrift(
                f"aws_instance.example_{index}",
                "aws_instance",
                ("update",),
                (
                    AttributeChange(
                        ("password",), {"status": "sensitive"}, {"status": "sensitive"}
                    ),
                ),
                assessment={
                    "policy": REVIEW_POLICY,
                    "priority": priority,
                    "signals": [],
                    "guidance": {"review_steps": [], "choices": []},
                },
            )
            for index, priority in enumerate(priorities)
        ),
        "imported_plan",
        "2026-10-23T00:00:00+00:00",
    )


@pytest.mark.parametrize(
    "priorities,criteria,code,matched",
    [
        ([], {"fail_on_priority": "high"}, 0, []),
        (["medium"], {"fail_on_priority": "high"}, 0, []),
        (["high"], {"fail_on_priority": "high"}, 1, ["high"]),
        (["unknown"], {"fail_on_priority": "high"}, 0, []),
        (
            ["unknown"],
            {"fail_on_priority": "high", "fail_on_unknown": True},
            1,
            ["unknown"],
        ),
        (["medium"], {"fail_on_priority": "medium"}, 1, ["medium"]),
        (["high"], {"fail_on_priority": "medium"}, 1, ["high"]),
        (["unknown"], {"fail_on_priority": "medium"}, 0, []),
        (
            ["medium", "unknown"],
            {"fail_on_priority": "high", "fail_on_unknown": True},
            1,
            ["unknown"],
        ),
        (["high", "medium", "unknown"], {"fail_on_priority": "high"}, 1, ["high"]),
        (
            ["high", "medium", "unknown"],
            {"fail_on_priority": "medium"},
            1,
            ["high", "medium"],
        ),
        (
            ["high", "medium", "unknown"],
            {"fail_on_drift": True},
            1,
            ["high", "medium", "unknown"],
        ),
        (
            ["medium"],
            {"fail_on_drift": True, "fail_on_priority": "high"},
            1,
            ["medium"],
        ),
        (["high"], {"fail_on_unknown": True}, 0, []),
        (["unknown"], {"fail_on_unknown": True}, 1, ["unknown"]),
        ([], {"fail_on_drift": True, "fail_on_unknown": True}, 0, []),
    ],
)
def test_gate_exit_policy_matrix(priorities, criteria, code, matched):
    result = reviewed(priorities)
    snapshot = deepcopy(result.to_dict())
    gate = evaluate_gate(result, **criteria)
    assert gate["exit_code"] == code
    assert gate["status"] == ("failed" if code else "passed")
    assert [r["priority"] for r in gate["matched_resources"]] == matched
    assert gate["matched_count"] == len(matched)
    assert sum(gate["priority_counts"].values()) == len(priorities)
    assert result.to_dict() == snapshot


@pytest.mark.parametrize(
    "assessment",
    [
        None,
        {},
        {"priority": "high"},
        {"policy": "builtin-review-v1", "priority": "high"},
        {"policy": REVIEW_POLICY, "priority": SECRET},
        {"policy": REVIEW_POLICY, "priority": []},
        {"policy": REVIEW_POLICY, "priority": {}},
    ],
)
def test_unassessed_or_unrecognized_priority_is_unknown_without_echoing_data(
    assessment,
):
    r = replace(reviewed(["high"]).resources[0], assessment=assessment)
    gate = evaluate_gate(replace(reviewed([]), resources=(r,)), fail_on_unknown=True)
    assert gate["exit_code"] == 1
    assert gate["priority_counts"] == {"high": 0, "medium": 0, "unknown": 1}
    assert gate["unassessed_resources"] == 1
    assert SECRET not in json.dumps(gate)


def test_unknown_subsignal_does_not_change_effective_high_priority_gate():
    r = reviewed(["high"]).resources[0]
    r = replace(
        r,
        assessment={
            **r.assessment,
            "signals": [{"priority": "unknown", "description": SECRET}],
        },
    )
    gate = evaluate_gate(replace(reviewed([]), resources=(r,)), fail_on_unknown=True)
    assert gate["exit_code"] == 0
    assert SECRET not in json.dumps(gate)


def test_overlapping_criteria_deduplicate_resource_and_record_reasons():
    gate = evaluate_gate(
        reviewed(["high", "unknown"]),
        fail_on_drift=True,
        fail_on_priority="high",
        fail_on_unknown=True,
    )
    assert gate["matched_count"] == 2
    assert gate["matched_resources"][0]["reasons"] == [
        "any_drift",
        "priority_threshold",
    ]
    assert gate["matched_resources"][1]["reasons"] == ["any_drift", "unknown_priority"]


@pytest.mark.parametrize("value", ["low", "unknown", "HIGH", "", SECRET])
def test_invalid_programmatic_threshold_is_rejected(value):
    with pytest.raises(ValueError, match="Unsupported drift gate priority"):
        evaluate_gate(reviewed(["high"]), fail_on_priority=value)


@pytest.mark.parametrize(
    "flag",
    [[], ["--fail-on-drift"], ["--fail-on-priority", "high"], ["--fail-on-unknown"]],
)
def test_execution_error_overrides_gate_and_retains_report(project, monkeypatch, flag):
    result = replace(
        reviewed(["high", "unknown"]), trace={"status": "error", "has_errors": True}
    )
    monkeypatch.setattr("infralens.handlers.collect_drift", lambda options: result)
    response = runner.invoke(app, ["drift", str(project), "--format", "json", *flag])
    assert response.exit_code == 3
    report = json.loads(response.stdout)
    assert len(report["resources"]) == 2
    if flag:
        assert report["gate"]["status"] == "incomplete"
        assert report["gate"]["exit_code"] == 3
        assert report["gate"]["reason_codes"] == ["cloudtrail_incomplete"]
    else:
        assert "gate" not in report


def test_partial_trace_without_execution_error_does_not_invent_exit_3():
    result = replace(
        reviewed(["medium"]), trace={"status": "partial", "has_errors": False}
    )
    assert evaluate_gate(result, fail_on_priority="high")["exit_code"] == 0


@pytest.mark.parametrize(
    "threshold", ["bad", "low", "unknown", "high,medium", "", "   "]
)
def test_invalid_cli_gate_precedes_collection_and_output_creation(
    project, tmp_path, monkeypatch, threshold
):
    monkeypatch.setattr(
        "infralens.handlers.collect_drift",
        lambda options: pytest.fail("Invalid gate started collection"),
    )
    output = tmp_path / "new" / "report.json"
    response = runner.invoke(
        app,
        [
            "drift",
            str(project),
            "--fail-on-priority",
            threshold,
            "--output",
            str(output),
        ],
    )
    assert response.exit_code == 2
    assert "--fail-on-priority" in response.stderr
    assert response.stdout == "" and not output.parent.exists()


def test_cli_normalizes_priority_and_passes_flags_to_handler(project, monkeypatch):
    received = []
    monkeypatch.setattr("infralens.cli.handle_drift", received.append)
    response = runner.invoke(
        app,
        ["drift", str(project), "--fail-on-priority", " HIGH ", "--fail-on-unknown"],
    )
    assert response.exit_code == 0
    assert received[0].fail_on_priority == "high"
    assert received[0].fail_on_unknown is True


def imported_plan(resources):
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.5",
        "planned_values": {},
        "resource_drift": resources,
    }


def entry(kind, name, before, after, **change):
    return {
        "address": f"{kind}.{name}",
        "type": kind,
        "mode": "managed",
        "change": {"actions": ["update"], "before": before, "after": after, **change},
    }


def fixture_resources():
    return [
        entry(
            "aws_instance",
            "high",
            {"instance_type": "t3.micro"},
            None,
            actions=["delete"],
        ),
        entry(
            "aws_instance",
            "medium",
            {"instance_type": "t3.micro"},
            {"instance_type": "t3.small"},
        ),
        entry(
            "aws_instance",
            "unknown",
            {"tags": {"env": SECRET}},
            {"tags": {"env": "new"}},
            before_sensitive={"tags": True},
            after_sensitive={"tags": True},
        ),
    ]


@pytest.mark.parametrize(
    "indices,flags,expected,matched",
    [
        ([], ["--fail-on-priority", "high", "--fail-on-unknown"], 0, 0),
        ([1], ["--fail-on-priority", "high"], 0, 0),
        ([1], ["--fail-on-priority", "medium"], 1, 1),
        ([2], ["--fail-on-priority", "high"], 0, 0),
        ([2], ["--fail-on-priority", "high", "--fail-on-unknown"], 1, 1),
        ([0, 1, 2], ["--fail-on-priority", "high"], 1, 1),
        ([0, 1, 2], ["--fail-on-priority", "high", "--fail-on-unknown"], 1, 2),
        ([0, 1, 2], ["--fail-on-priority", "medium"], 1, 2),
        ([1, 2], ["--fail-on-drift", "--fail-on-priority", "high"], 1, 2),
    ],
)
def test_cli_import_gates_without_filtering_or_aws(
    project, tmp_path, monkeypatch, indices, flags, expected, matched
):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline gate started Terraform/AWS")

    monkeypatch.setattr("infralens.drift_service.Terraform", forbidden)
    monkeypatch.setattr("infralens.cloudtrail._session", forbidden)
    resources = fixture_resources()
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(imported_plan([resources[i] for i in indices])))
    response = runner.invoke(
        app,
        ["drift", str(project), "--plan-json", str(source), "--format", "json", *flags],
    )
    assert response.exit_code == expected, response.output
    report = json.loads(response.stdout)
    assert len(report["resources"]) == len(indices)
    assert report["has_drift"] == bool(indices)
    assert report["gate"]["exit_code"] == expected
    assert report["gate"]["matched_count"] == matched
    assert SECRET not in response.output
    assert response.stderr == ""


def test_default_report_has_no_gate_metadata(project, monkeypatch):
    result = reviewed(["high"])
    monkeypatch.setattr("infralens.handlers.collect_drift", lambda options: result)
    response = runner.invoke(app, ["drift", str(project), "--format", "json"])
    assert response.exit_code == 0
    assert json.loads(response.stdout) == json.loads(json.dumps(result.to_dict()))


def test_output_is_saved_before_policy_failure_and_stdout_remains_table(
    project, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "infralens.handlers.collect_drift",
        lambda options: reviewed(["medium", "high", "unknown"]),
    )
    output = tmp_path / "reports" / "gate.json"
    response = runner.invoke(
        app,
        [
            "drift",
            str(project),
            "--format",
            "json",
            "--output",
            str(output),
            "--fail-on-priority",
            "high",
        ],
    )
    assert response.exit_code == 1
    report = json.loads(output.read_text())
    assert report["gate"]["matched_count"] == 1
    assert len(report["resources"]) == 3
    assert "CI gate: failed" in response.stdout
    assert "aws_instance.example_0" in response.stdout
    assert "aws_instance.example_2" in response.stdout


def test_io_failure_is_exit_3_and_does_not_replace_existing_report(
    project, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "infralens.handlers.collect_drift", lambda options: reviewed(["high"])
    )

    def failing_write(*args):
        raise OSError(SECRET)

    monkeypatch.setattr("infralens.handlers.write_report", failing_write)
    output = tmp_path / "gate.json"
    output.write_text("old report")
    response = runner.invoke(
        app,
        ["drift", str(project), "--output", str(output), "--fail-on-priority", "high"],
    )
    assert response.exit_code == 3
    assert output.read_text() == "old report"
    assert response.stdout == "" and SECRET not in response.stderr


def test_engine_failure_does_not_publish_gate_success(project, tmp_path, monkeypatch):
    def failed(*args):
        raise ExecutionError("Engine failed.")

    monkeypatch.setattr("infralens.handlers.collect_drift", failed)
    output = tmp_path / "new" / "gate.json"
    response = runner.invoke(
        app, ["drift", str(project), "--output", str(output), "--fail-on-unknown"]
    )
    assert response.exit_code == 3
    assert response.stdout == "" and not output.exists()


def test_table_gate_sanitizes_terminal_sequences_and_uses_no_attribute_values():
    result = reviewed(["high"])
    r = replace(
        result.resources[0],
        address="aws_instance.\x1b[31mexample\nunsafe",
        attributes=(
            AttributeChange(
                ("private",),
                {"status": "known", "value": SECRET},
                {"status": "known", "value": "new"},
            ),
        ),
    )
    gate = evaluate_gate(replace(result, resources=(r,)), fail_on_priority="high")
    text = render_gate(gate)
    assert "\x1b" not in text
    assert SECRET not in text + json.dumps(gate)


def test_help_explains_new_gate_options():
    response = runner.invoke(app, ["drift", "--help"])
    assert response.exit_code == 0
    assert (
        "--fail-on-priority" in response.stdout
        and "--fail-on-unknown" in response.stdout
    )
