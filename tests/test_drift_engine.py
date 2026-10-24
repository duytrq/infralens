import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens.cli import app
from infralens.drift import parse_plan
from infralens.drift_reporting import render_drift
from infralens.errors import ExecutionError
from infralens.options import DriftOptions
from infralens.terraform import terraform_environment

runner = CliRunner()


def plan(resources=None, **extra):
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.5",
        "planned_values": {},
        "resource_drift": resources or [],
        **extra,
    }


def resource(before=None, after=None, **extra):
    return {
        "address": "module.app.aws_instance.web[0]",
        "type": "aws_instance",
        "mode": "managed",
        "change": {
            "actions": ["update"],
            "before": {"instance_type": "t3.micro"} if before is None else before,
            "after": {"instance_type": "t3.small"} if after is None else after,
            **extra,
        },
    }


def parse(resources=None, **extra):
    return parse_plan(json.dumps(plan(resources, **extra)))


def test_saved_to_observed_direction():
    report = parse([resource()]).to_dict()
    assert report["has_drift"] is True
    change = report["resources"][0]["attributes"][0]
    assert change["path"] == ("instance_type",)
    assert change["before"] == {"status": "known", "value": "t3.micro"}
    assert change["after"] == {"status": "known", "value": "t3.small"}


def test_configuration_changes_and_root_outputs_are_not_resource_drift():
    result = parse(resource_changes=[resource()], output_changes={"x": {"after": 5}})
    assert result.resources == ()


@pytest.mark.parametrize("actions,mode", [(["no-op"], "managed"), (["update"], "data")])
def test_noops_and_data_sources_are_not_managed_drift(actions, mode):
    entry = resource(actions=actions)
    entry["mode"] = mode
    assert parse([entry]).resources == ()


def test_deleted_resource_reports_saved_values_and_absent_attributes():
    entry = resource(actions=["delete"])
    entry["change"]["after"] = None
    result = parse([entry])
    assert result.resources[0].actions == ("delete",)
    assert result.resources[0].attributes[0].after == {"status": "absent"}


def test_null_missing_unknown_and_map_keys_are_distinct():
    result = parse(
        [
            resource(
                {"tags": {"a.b": None}, "id": None},
                {"tags": {}, "id": None},
                after_unknown={"id": True},
            )
        ]
    )
    changes = {change.path: change for change in result.resources[0].attributes}
    assert changes[("id",)].after == {"status": "unknown"}
    assert changes[("tags", "a.b")].before == {"status": "known", "value": None}
    assert changes[("tags", "a.b")].after == {"status": "absent"}


@pytest.mark.parametrize("delete", [False, True])
def test_nested_sensitive_values_are_never_exported(delete):
    entry = resource(
        {"auth": {"token": "SECRET_OLD"}, "rules": [{"key": "SECRET_COLLECTION"}]},
        {"auth": {"token": "SECRET_NEW"}, "rules": []},
        before_sensitive={"auth": {"token": True}, "rules": [{"key": True}]},
        after_sensitive={"auth": {"token": True}},
    )
    if delete:
        entry["change"].update(actions=["delete"], after=None)
    output = json.dumps(parse([entry]).to_dict())
    assert "SECRET" not in output
    assert "sensitive" in output


def test_change_of_sensitivity_masks_both_sides():
    change = (
        parse(
            [
                resource(
                    {"token": "SECRET"},
                    {"token": "new"},
                    after_sensitive={"token": True},
                )
            ]
        )
        .resources[0]
        .attributes[0]
    )
    assert change.before == change.after == {"status": "sensitive"}


def test_container_type_change_with_sensitive_child_is_fully_masked():
    change = (
        parse(
            [
                resource(
                    {"value": {"key": "SECRET"}},
                    {"value": []},
                    before_sensitive={"value": {"key": True}},
                )
            ]
        )
        .resources[0]
        .attributes[0]
    )
    assert change.before == change.after == {"status": "sensitive"}


def test_arrays_are_atomic_and_empty_objects_are_not_lost():
    changes = (
        parse([resource({"rules": [22], "tags": {}}, {"rules": [443]})])
        .resources[0]
        .attributes
    )
    assert {c.path for c in changes} == {("rules",), ("tags",)}


@pytest.mark.parametrize(
    "alter",
    [
        {"format_version": "2.0"},
        {"planned_values": None},
        {"errored": True},
        {"complete": False},
        {"resource_drift": None},
        {"deferred_changes": [{}]},
        {"terraform_version": "unknown"},
    ],
)
def test_rejects_unusable_plan(alter):
    with pytest.raises(ExecutionError, match="plan JSON"):
        parse(**alter)


@pytest.mark.parametrize(
    "change",
    [
        {"actions": ["create"]},
        {"before": None},
        {"after_sensitive": "SECRET"},
        {"after_unknown": {"id": "wrong"}},
        {"before_sensitive": [True]},
        {"after_unknown": [True]},
        {"after": []},
    ],
)
def test_malformed_resource_cannot_produce_a_clean_report(change):
    entry = resource()
    entry["change"].update(change)
    with pytest.raises(ExecutionError):
        parse([entry])


@pytest.mark.parametrize(
    "payload",
    [
        "SECRET_INVALID_JSON",
        "[]",
        '{"format_version":"1.2","format_version":"1.2"}',
        '{"format_version":"1.2","planned_values":NaN}',
        '{"format_version":"1.2","values":{}}',
    ],
)
def test_parser_errors_never_include_payload(payload):
    with pytest.raises(ExecutionError) as exc:
        parse_plan(payload)
    assert "SECRET" not in str(exc.value)


def test_duplicate_resources_fail_closed():
    entry = resource()
    with pytest.raises(ExecutionError):
        parse([entry, deepcopy(entry)])


def test_raw_state_variables_and_outputs_are_not_exported():
    output = json.dumps(
        parse(
            variables={"secret": "SECRET"},
            prior_state={"private": "SECRET"},
            output_changes={"private": "SECRET"},
        ).to_dict()
    )
    assert "SECRET" not in output


@pytest.mark.parametrize(
    "mode,expected", [("clean", 0), ("drift", 1), ("delete", 1), ("output-only", 0)]
)
def test_cli_with_real_executable_boundary(
    project, fake_terraform, monkeypatch, mode, expected
):
    monkeypatch.setenv("FAKE_TERRAFORM_MODE", mode)
    result = runner.invoke(
        app, ["drift", str(project), "--format", "json", "--fail-on-drift"]
    )
    assert result.exit_code == expected, result.output
    report = json.loads(result.stdout)
    assert report["has_drift"] is (expected == 1)
    assert report["input_mode"] == "refresh_only"
    assert "SECRET" not in result.output
    assert result.stderr == ""
    calls = [json.loads(line) for line in fake_terraform.read_text().splitlines()]
    assert [call["args"][0] for call in calls] == ["version", "plan", "show"]
    assert "-refresh-only" in calls[1]["args"]
    assert "-input=false" in calls[1]["args"]
    assert "-lock=false" not in calls[1]["args"]
    temporary = Path(
        next(arg[5:] for arg in calls[1]["args"] if arg.startswith("-out="))
    )
    assert not temporary.parent.exists()


@pytest.mark.parametrize(
    "mode",
    ["old-version", "plan-fail", "show-fail", "invalid-json", "incomplete", "timeout"],
)
def test_failures_do_not_leak_or_publish(
    project, tmp_path, fake_terraform, monkeypatch, mode
):
    monkeypatch.setenv("FAKE_TERRAFORM_MODE", mode)
    output = tmp_path / "reports" / "drift.json"
    result = runner.invoke(
        app,
        ["--verbose", "drift", str(project), "--output", str(output), "--timeout", "1"],
    )
    assert result.exit_code == 3, result.output
    assert "SECRET" not in result.output
    assert result.stdout == ""
    assert not output.exists()
    calls = [json.loads(line) for line in fake_terraform.read_text().splitlines()]
    for call in calls:
        for arg in call["args"]:
            if arg.startswith("-out="):
                assert not Path(arg[5:]).parent.exists()


def test_missing_terraform_is_actionable(project, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "missing-bin"))
    result = runner.invoke(app, ["drift", str(project)])
    assert result.exit_code == 3
    assert "Terraform" in result.stderr and "PATH" in result.stderr


def test_environment_and_var_file_order(project, fake_terraform, monkeypatch):
    variables = project / "dev vars.tfvars"
    variables.write_text('demo = "SECRET"')
    monkeypatch.setenv("TF_CLI_ARGS_plan", "-target=aws_instance.other -out=unsafe")
    monkeypatch.setenv("TF_LOG", "TRACE")
    monkeypatch.setenv("TF_LOG_PATH", "unsafe.log")
    monkeypatch.setenv("TF_VAR_DEMO", "synthetic-variable")
    monkeypatch.setenv("TF_WORKSPACE", "demo")
    result = runner.invoke(
        app,
        [
            "drift",
            str(project),
            "--var-file",
            variables.name,
            "--var-file",
            variables.name,
            "--profile",
            "dev",
            "--region",
            "us-east-1",
        ],
    )
    assert result.exit_code == 0, result.output
    calls = [json.loads(line) for line in fake_terraform.read_text().splitlines()]
    assert calls[1]["args"][-2:] == [f"-var-file={variables}"] * 2
    assert calls[1]["cwd"] == str(project)
    assert calls[1]["env"] == {
        "AWS_PROFILE": "dev",
        "AWS_REGION": "us-east-1",
        "AWS_DEFAULT_REGION": "us-east-1",
        "TF_VAR_DEMO": "synthetic-variable",
        "TF_WORKSPACE": "demo",
    }
    assert not (project / "unsafe.log").exists()


def test_json_file_written_before_findings_exit(
    project, tmp_path, fake_terraform, monkeypatch
):
    monkeypatch.setenv("FAKE_TERRAFORM_MODE", "drift")
    output = tmp_path / "reports" / "drift.json"
    result = runner.invoke(
        app,
        [
            "drift",
            str(project),
            "--format",
            "json",
            "--output",
            str(output),
            "--fail-on-drift",
        ],
    )
    assert result.exit_code == 1, result.output
    assert json.loads(output.read_text())["has_drift"] is True
    assert "Infrastructure drift" in result.stdout
    assert "SECRET" not in result.output + output.read_text()


def test_imported_plan_does_not_require_binary(project, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "missing-bin"))
    imported = tmp_path / "plan.json"
    imported.write_text(json.dumps(plan([resource()])), encoding="utf-8-sig")
    result = runner.invoke(
        app, ["drift", str(project), "--plan-json", str(imported), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["input_mode"] == "imported_plan"
    assert any("unverified" in note for note in report["notes"])


@pytest.mark.parametrize(
    "target",
    [
        "terraform.tfstate",
        "dev.tfvars",
        ".terraform.lock.hcl",
        "module/main.tf",
        ".terraform/report.json",
    ],
)
def test_output_protects_sources_state_and_backend_metadata(project, target):
    output = project / target
    output.parent.mkdir(exist_ok=True)
    output.write_text("SECRET_ORIGINAL")
    result = runner.invoke(app, ["drift", str(project), "--output", str(output)])
    assert result.exit_code == 2, result.output
    assert output.read_text() == "SECRET_ORIGINAL"


@pytest.mark.parametrize("alias", ["hardlink", "symlink"])
def test_report_alias_cannot_overwrite_state(project, tmp_path, alias, symlink):
    state = project / "terraform.tfstate"
    state.write_text("SECRET_STATE")
    output = tmp_path / "report.json"
    if alias == "symlink":
        symlink(output, state)
    else:
        output.hardlink_to(state)
    result = runner.invoke(app, ["drift", str(project), "--output", str(output)])
    assert result.exit_code == 2
    assert state.read_text() == "SECRET_STATE"


@pytest.mark.parametrize("timeout", ["0", "-1", "1.5"])
def test_invalid_timeout_precedes_external_work(project, timeout):
    assert (
        runner.invoke(app, ["drift", str(project), "--timeout", timeout]).exit_code == 2
    )


def test_output_cannot_replace_imported_plan(project, tmp_path):
    imported = tmp_path / "plan.json"
    imported.write_text(json.dumps(plan()))
    result = runner.invoke(
        app,
        [
            "drift",
            str(project),
            "--plan-json",
            str(imported),
            "--output",
            str(imported),
        ],
    )
    assert result.exit_code == 2


def test_terminal_control_characters_are_sanitized(project, tmp_path):
    entry = resource()
    entry["address"] = "aws_instance.\x1b[31mweb"
    imported = tmp_path / "plan.json"
    imported.write_text(json.dumps(plan([entry])))
    result = runner.invoke(app, ["drift", str(project), "--plan-json", str(imported)])
    assert result.exit_code == 0
    assert "\x1b" not in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows environment casing")
def test_windows_preserves_mixed_case_tf_variable_names_and_unicode(project):
    name = "TF_VAR_infralensMixedCaseFixture"
    os.putenv(name, "synthetic Unicode \U0001f30f value")
    try:
        options = DriftOptions(
            project, (), "json", None, None, None, False, None, False
        )
        env = terraform_environment(options)
        assert env[name] == "synthetic Unicode \U0001f30f value"
    finally:
        os.unsetenv(name)


def test_backend_metadata_hardlink_is_protected(project, tmp_path):
    backend = project / ".terraform" / "terraform.tfstate"
    backend.parent.mkdir()
    backend.write_text("SECRET_METADATA")
    output = tmp_path / "alias.json"
    output.hardlink_to(backend)
    result = runner.invoke(app, ["drift", str(project), "--output", str(output)])
    assert result.exit_code == 2
    assert backend.read_text() == "SECRET_METADATA"


def test_imported_non_utf8_has_a_controlled_error(project, tmp_path):
    imported = tmp_path / "plan.json"
    imported.write_bytes(b"\xffSECRET")
    result = runner.invoke(app, ["drift", str(project), "--plan-json", str(imported)])
    assert result.exit_code == 3
    assert "UTF-8" in result.stderr
    assert "SECRET" not in result.output


def test_non_finite_exponent_is_not_exported_as_invalid_json():
    payload = json.dumps(plan([resource()])).replace('"t3.small"', "1e9999")
    with pytest.raises(ExecutionError):
        parse_plan(payload)


def test_resource_identifiers_are_available_without_attribute_changes():
    entry = resource(
        {
            "id": "i-demo",
            "arn": "arn:aws:ec2:region:account:instance/i-demo",
            "size": 1,
        },
        {
            "id": "i-demo",
            "arn": "arn:aws:ec2:region:account:instance/i-demo",
            "size": 2,
        },
    )
    result = parse([entry]).resources[0]
    assert result.identifiers["id"] == {
        "status": "known",
        "value": "i-demo",
        "source": "observed",
    }
    assert result.identifiers["arn"]["source"] == "observed"
    assert [change.path for change in result.attributes] == [("size",)]


def test_deleted_resource_keeps_saved_identifier():
    entry = resource({"id": "i-deleted"}, actions=["delete"])
    entry["change"]["after"] = None
    assert parse([entry]).resources[0].identifiers["id"] == {
        "status": "known",
        "value": "i-deleted",
        "source": "saved",
    }


@pytest.mark.parametrize("mask", [{"id": True, "arn": True}, True])
def test_sensitive_resource_identifiers_never_leak(mask):
    entry = resource(
        {"id": "SECRET_ID_OLD", "arn": "SECRET_ARN_OLD"},
        {"id": "SECRET_ID_NEW", "arn": "SECRET_ARN_NEW"},
        after_sensitive=mask,
    )
    output = json.dumps(parse([entry]).to_dict())
    assert "SECRET" not in output
    assert parse([entry]).resources[0].identifiers["id"] == {"status": "sensitive"}


def test_unknown_identity_uses_labelled_saved_value():
    entry = resource({"id": "i-saved"}, {"id": None}, after_unknown={"id": True})
    assert parse([entry]).resources[0].identifiers["id"]["source"] == "saved"


def aws_resource(before, after, resource_type="aws_instance"):
    entry = resource(before, after)
    entry.update(
        type=resource_type, provider_name="registry.terraform.io/hashicorp/aws"
    )
    return entry


def test_aws_empty_tags_are_reported_as_representation_normalization():
    entry = aws_resource(
        {"id": "sg-demo", "tags": None, "tags_all": {"Project": "demo"}},
        {"id": "sg-demo", "tags": {}, "tags_all": {"Project": "demo"}},
        "aws_security_group",
    )
    result = parse([entry])
    assert result.resources == ()
    assert result.normalizations[0]["path"] == ["tags"]
    assert result.to_dict()["has_drift"] is False


def test_root_volume_empty_tag_map_does_not_create_false_drift():
    old = {"root_block_device": [{"tags": None, "volume_size": 8}]}
    new = {"root_block_device": [{"tags": {}, "volume_size": 8}]}
    result = parse([aws_resource(old, new)])
    assert result.resources == ()
    assert result.normalizations[0]["path"] == ["root_block_device", 0, "tags"]


def test_empty_tags_do_not_hide_an_unknown_attribute():
    entry = aws_resource({"tags": None, "id": "i-demo"}, {"tags": {}, "id": "i-demo"})
    entry["change"]["after_unknown"] = {"id": True}
    result = parse([entry])
    assert len(result.resources) == 1
    assert result.resources[0].attributes[0].after == {"status": "unknown"}


def test_table_explains_normalized_fields_even_without_drift():
    result = parse([aws_resource({"tags": None}, {"tags": {}})])
    table = render_drift(result)
    assert "Resources with drift: 0" in table
    assert 'Normalized module.app.aws_instance.web[0] ["tags"]:' in table
    assert "null versus {}" in table


@pytest.mark.parametrize(
    "old,new",
    [(None, {"env": "dev"}), ({"env": "dev"}, {}), ({"env": "dev"}, {"env": "prod"})],
)
def test_real_tag_changes_are_always_drift(old, new):
    result = parse([aws_resource({"tags": old}, {"tags": new})])
    assert len(result.resources) == 1
    assert result.normalizations == ()


def test_real_volume_change_survives_tag_map_normalization():
    old = {"root_block_device": [{"tags": None, "volume_size": 8}]}
    new = {"root_block_device": [{"tags": {}, "volume_size": 16}]}
    result = parse([aws_resource(old, new)])
    assert len(result.resources) == 1
    assert result.resources[0].attributes[0].path == ("root_block_device",)


@pytest.mark.parametrize(
    "provider,resource_type,key",
    [
        ("custom/aws", "aws_instance", "tags"),
        ("registry.terraform.io/hashicorp/aws", "aws_instance", "metadata"),
        ("registry.terraform.io/hashicorp/aws", "custom_resource", "tags"),
    ],
)
def test_unrelated_null_empty_objects_remain_distinct(provider, resource_type, key):
    entry = resource({key: None}, {key: {}})
    entry.update(provider_name=provider, type=resource_type)
    result = parse([entry])
    assert len(result.resources) == 1
    assert result.normalizations == ()
