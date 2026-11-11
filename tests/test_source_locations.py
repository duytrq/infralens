import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from infralens import source_locations as sources
from infralens.cli import app
from infralens.drift import DriftResult, ResourceDrift
from infralens.drift_reporting import render_drift

SECRET = "PRIVATE_SOURCE_VALUE"


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def resource(address="aws_instance.demo", resource_type="aws_instance"):
    return ResourceDrift(address, resource_type, ("update",), ())


def locate(root, address="aws_instance.demo", data_dir=None):
    return sources.SourceLocator(root, data_dir).locate(resource(address))


def test_hcl_block_ranges_ignore_comments_heredocs_and_nested_blocks(tmp_path):
    path = write(
        tmp_path,
        "main.tf",
        """# resource "aws_instance" "demo" {}
/* resource "aws_instance" "demo" {} */
locals {
  text = <<-EOF
resource "aws_instance" "demo" { private = "PRIVATE_SOURCE_VALUE" }
EOF
}
resource "aws_instance" "demo" {
  instance_type = "t3.micro"
  lifecycle { ignore_changes = [tags] }
}
""",
    )
    source = locate(tmp_path)
    assert source["status"] == "located"
    assert source["locations"] == [
        {"file": str(path.resolve()), "start_line": 8, "end_line": 11, "syntax": "hcl"}
    ]
    assert SECRET not in json.dumps(source)


@pytest.mark.parametrize(
    "address",
    [
        "aws_instance.demo[0]",
        "aws_instance.demo[123]",
        'aws_instance.demo["a.b]\\"quoted"]',
        'aws_instance.demo["日本語"]',
    ],
)
def test_instance_selectors_share_the_resource_declaration(tmp_path, address):
    write(tmp_path, "main.tf", 'resource "aws_instance" "demo" {}')
    source = locate(tmp_path, address)
    assert source["status"] == "located"
    assert source["block_address"] == "aws_instance.demo"


@pytest.mark.parametrize(
    "address",
    [
        "aws_instance.demo[-1]",
        "aws_instance.demo[true]",
        "aws_instance.demo[1.5]",
        'aws_instance.demo["missing]',
        "aws_instance.demo[0].extra",
        "data.aws_instance.demo",
        "aws_instance",
        "aws_instance.demo[01]",
    ],
)
def test_unsupported_addresses_do_not_guess(tmp_path, address):
    source = locate(tmp_path, address)
    assert source["reason"] == "unsupported_address"


def test_nested_local_modules_with_selectors_and_sibling_paths(tmp_path):
    write(tmp_path, "main.tf", 'module "app" { source = "./modules/app" }')
    write(tmp_path, "modules/app/main.tf", 'module "child" { source = "../child" }')
    expected = write(
        tmp_path, "modules/child/network.tf", '\nresource "aws_instance" "demo" {}\n'
    )
    source = locate(
        tmp_path, 'module.app["prod.eu]"].module.child[0].aws_instance.demo["x.y"]'
    )
    assert source["status"] == "located"
    assert source["locations"][0]["file"] == str(expected.resolve())
    assert source["locations"][0]["start_line"] == 2
    assert source["block_address"] == "module.app.module.child.aws_instance.demo"


def test_same_resource_name_in_unrelated_module_is_not_used(tmp_path):
    write(tmp_path, "main.tf", 'module "app" { source = "./app" }')
    write(tmp_path, "other/main.tf", 'resource "aws_instance" "demo" {}')
    write(tmp_path, "app/main.tf", 'resource "aws_instance" "different" {}')
    assert (
        locate(tmp_path, "module.app.aws_instance.demo")["reason"]
        == "resource_not_declared"
    )
    assert (
        locate(tmp_path, "module.old.aws_instance.demo")["reason"]
        == "module_not_declared"
    )


def test_installed_module_manifest_supports_custom_data_dir(tmp_path):
    write(
        tmp_path,
        "main.tf",
        'module "app" { source = "registry.example.com/org/app/aws" }',
    )
    expected = write(
        tmp_path, "cache/modules/app/compute.tf", 'resource "aws_instance" "demo" {}'
    )
    write(
        tmp_path,
        "cache/modules/modules.json",
        json.dumps(
            {
                "Modules": [
                    {"Key": "", "Dir": "PRIVATE_IGNORED_ROOT", "Source": ""},
                    {"Key": "app", "Dir": "cache/modules/app", "Source": SECRET},
                ]
            }
        ),
    )
    source = locate(tmp_path, "module.app.aws_instance.demo", "cache")
    assert source["status"] == "located"
    assert source["locations"][0]["file"] == str(expected.resolve())
    assert SECRET not in json.dumps(source)


def test_missing_remote_module_does_not_search_other_directories(tmp_path):
    write(tmp_path, "main.tf", 'module "app" { source = "org/app/aws" }')
    write(tmp_path, "unrelated/main.tf", 'resource "aws_instance" "demo" {}')
    assert (
        locate(tmp_path, "module.app.aws_instance.demo")["reason"]
        == "module_not_installed"
    )


@pytest.mark.parametrize(
    "manifest",
    [
        SECRET,
        "{}",
        '{"Modules":null}',
        '{"Modules":[{"Key":"app","Dir":"one"},{"Key":"app","Dir":"two"}]}',
    ],
)
def test_invalid_module_metadata_is_safe(tmp_path, manifest):
    write(tmp_path, "main.tf", 'module "app" { source = "org/app/aws" }')
    write(tmp_path, ".terraform/modules/modules.json", manifest)
    source = locate(tmp_path, "module.app.aws_instance.demo")
    assert source["reason"] == "module_manifest_invalid"
    assert SECRET not in json.dumps(source)


@pytest.mark.parametrize(
    "content",
    [
        '{"resource":{"aws_instance":{"demo":{}}}}',
        '{"resource":[{"aws_instance":[{"demo":{}}]}]}',
    ],
)
def test_terraform_json_object_and_array_block_forms(tmp_path, content):
    path = write(tmp_path, "main.tf.json", content)
    source = locate(tmp_path)
    assert source["status"] == "located"
    assert source["locations"] == [
        {"file": str(path.resolve()), "start_line": 1, "end_line": 1, "syntax": "json"}
    ]


def test_json_lines_follow_key_spans_not_strings_containing_fake_blocks(tmp_path):
    write(
        tmp_path,
        "main.tf.json",
        """{
  "//": "resource aws_instance demo {PRIVATE_SOURCE_VALUE}",
  "resource": {
    "aws_instance": {
      "demo": {
        "tags": {"nested": "resource", "quote": "\\\"}"}
      }
    }
  }
}""",
    )
    source = locate(tmp_path)
    assert source["status"] == "located"
    assert source["locations"][0]["start_line"] == 5
    assert source["locations"][0]["end_line"] == 7
    assert SECRET not in json.dumps(source)


def test_json_module_sources_can_resolve_to_hcl_children(tmp_path):
    write(tmp_path, "main.tf.json", '{"module":[{"app":{"source":"./child"}}]}')
    write(tmp_path, "child/main.tf", 'resource "aws_instance" "demo" {}')
    assert locate(tmp_path, "module.app.aws_instance.demo")["status"] == "located"


@pytest.mark.parametrize(
    "name,text",
    [
        ("main.tf", 'resource "aws_instance" "demo" { PRIVATE_SOURCE_VALUE = '),
        ("main.tf.json", '{"resource":PRIVATE_SOURCE_VALUE}'),
        ("main.tf.json", '{"resource":{},"resource":{"aws_instance":{"demo":{}}}}'),
    ],
)
def test_parser_diagnostics_and_source_values_are_never_exposed(tmp_path, name, text):
    write(tmp_path, name, text)
    source = locate(tmp_path)
    assert source["status"] == "unavailable"
    assert source["reason"] == "parse_error"
    assert SECRET not in json.dumps(source)


def test_any_unparseable_file_prevents_a_false_unique_location(tmp_path):
    write(tmp_path, "valid.tf", 'resource "aws_instance" "demo" {}')
    write(tmp_path, "bad.tf", SECRET)
    source = locate(tmp_path)
    assert source["status"] == "unavailable"
    assert source["reason"] == "parse_error"
    assert len(source["locations"]) == 1


def test_duplicate_and_override_declarations_are_explicitly_ambiguous(tmp_path):
    write(tmp_path, "main.tf", 'resource "aws_instance" "demo" {}')
    write(tmp_path, "override.tf", 'resource "aws_instance" "demo" {}')
    source = locate(tmp_path)
    assert source["status"] == "ambiguous"
    assert source["reason"] == "multiple_declarations"
    assert len(source["locations"]) == 2


def test_ambiguous_module_calls_are_not_followed(tmp_path):
    write(tmp_path, "main.tf", 'module "app" { source = "./one" }')
    write(tmp_path, "override.tf", 'module "app" { source = "./two" }')
    assert (
        locate(tmp_path, "module.app.aws_instance.demo")["reason"] == "ambiguous_module"
    )


def test_missing_declarations_and_empty_files_are_normal_results(tmp_path):
    write(tmp_path, "empty.tf", "")
    assert locate(tmp_path)["reason"] == "resource_not_declared"


def test_hidden_files_are_ignored(tmp_path):
    write(tmp_path, "main.tf", 'resource "aws_instance" "demo" {}')
    write(tmp_path, ".hidden.tf", 'resource "aws_instance" "demo" {}')
    assert locate(tmp_path)["status"] == "located"


@pytest.mark.parametrize(
    "limit,value,reason",
    [
        ("MAX_FILE_BYTES", 1, "source_size_limit"),
        ("MAX_TOTAL_BYTES", 1, "source_size_limit"),
        ("MAX_FILES_PER_MODULE", 0, "source_file_limit"),
        ("MAX_MODULES", 0, "module_limit"),
    ],
)
def test_source_scan_limits_do_not_change_drift_verdict(
    tmp_path, monkeypatch, limit, value, reason
):
    write(tmp_path, "main.tf", 'resource "aws_instance" "demo" {}')
    monkeypatch.setattr(sources, limit, value)
    drift = DriftResult("1.16.5", (resource(),), "imported_plan", "now")
    enriched = sources.enrich_source_locations(drift, tmp_path)
    assert enriched.to_dict()["has_drift"]
    assert enriched.resources[0].source["reason"] == reason


def test_unreadable_source_is_reported_without_raw_exception(tmp_path, monkeypatch):
    write(tmp_path, "main.tf", 'resource "aws_instance" "demo" {}')
    original = Path.open

    def fail(path, *args, **kwargs):
        if path.name == "main.tf":
            raise OSError(SECRET)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    source = locate(tmp_path)
    assert source["reason"] == "source_unreadable"
    assert SECRET not in json.dumps(source)


def test_modules_are_parsed_once_for_multiple_instances(tmp_path, monkeypatch):
    write(tmp_path, "main.tf", 'resource "aws_instance" "demo" {}')
    calls = []
    original = sources._hcl_blocks

    def parse(*args):
        calls.append(args[1])
        return original(*args)

    monkeypatch.setattr(sources, "_hcl_blocks", parse)
    locator = sources.SourceLocator(tmp_path)
    assert locator.locate(resource("aws_instance.demo[0]"))["status"] == "located"
    assert locator.locate(resource("aws_instance.demo[1]"))["status"] == "located"
    assert len(calls) == 1


def test_json_and_table_include_locations_without_source_excerpts(tmp_path):
    path = write(
        tmp_path,
        "main.tf",
        'resource "aws_instance" "demo" { secret = "PRIVATE_SOURCE_VALUE" }',
    )
    drift = DriftResult(
        "1.16.5",
        (replace(resource(), trace={"status": "no_events", "events": []}),),
        "refresh_only",
        "now",
    )
    enriched = sources.enrich_source_locations(drift, tmp_path)
    assert enriched.resources[0].trace == drift.resources[0].trace
    assert enriched.to_dict()["resources"][0]["source"]["status"] == "located"
    table = render_drift(enriched)
    assert str(path.resolve()) + ":1-1" in table
    assert SECRET not in table + json.dumps(enriched.to_dict())


def test_imported_plan_cli_maps_current_source_without_terraform(tmp_path, monkeypatch):
    write(tmp_path, "main.tf", '\nresource "aws_instance" "demo" {}\n')
    imported = write(
        tmp_path,
        "plan.json",
        json.dumps(
            {
                "format_version": "1.2",
                "terraform_version": "1.16.5",
                "planned_values": {},
                "resource_drift": [
                    {
                        "address": 'aws_instance.demo["a.b]"]',
                        "type": "aws_instance",
                        "mode": "managed",
                        "change": {
                            "actions": ["update"],
                            "before": {"size": 1},
                            "after": {"size": 2},
                        },
                    }
                ],
            }
        ),
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Source lookup must not run Terraform")

    monkeypatch.setattr("infralens.drift_service.Terraform", forbidden)
    cli = CliRunner().invoke(
        app,
        [
            "drift",
            str(tmp_path),
            "--plan-json",
            str(imported),
            "--format",
            "json",
            "--fail-on",
            "ANY",
        ],
    )
    assert cli.exit_code == 1, cli.output
    source = json.loads(cli.stdout)["resources"][0]["source"]
    assert source["status"] == "located"
    assert source["context"] == "current_configuration"
    assert source["locations"][0]["start_line"] == 2


@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize(
    "target", ["manifest", "manifest-hardlink", "backend-hardlink", "new-report"]
)
def test_output_protects_custom_data_directory_and_metadata_aliases(
    project, tmp_path, monkeypatch, absolute, target
):
    data = tmp_path / "external-cache" if absolute else project / "cache"
    monkeypatch.setenv("TF_DATA_DIR", str(data) if absolute else "cache")
    manifest = write(data, "modules/modules.json", '{"Modules":[]}')
    backend = write(data, "terraform.tfstate", SECRET)
    if target == "manifest":
        output = manifest
    elif target.endswith("hardlink"):
        output = tmp_path / "report.json"
        output.hardlink_to(manifest if target == "manifest-hardlink" else backend)
    else:
        output = data / "new-report.json"
    cli = CliRunner().invoke(app, ["drift", str(project), "--output", str(output)])
    assert cli.exit_code == 2, cli.output
    assert "--output" in cli.stderr
    assert manifest.read_text() == '{"Modules":[]}'
    assert backend.read_text() == SECRET
    assert SECRET not in cli.output


@pytest.mark.parametrize("absolute", [False, True])
def test_cli_uses_custom_data_directory_for_module_source(
    tmp_path, monkeypatch, absolute
):
    data = tmp_path / "external-cache" if absolute else tmp_path / "cache"
    monkeypatch.setenv("TF_DATA_DIR", str(data) if absolute else "cache")
    write(tmp_path, "main.tf", 'module "app" { source = "org/app/aws" }')
    source = write(data, "modules/app/main.tf", 'resource "aws_instance" "demo" {}')
    write(
        data,
        "modules/modules.json",
        json.dumps({"Modules": [{"Key": "app", "Dir": str(data / "modules" / "app")}]}),
    )
    imported = write(
        tmp_path,
        "plan.json",
        json.dumps(
            {
                "format_version": "1.2",
                "terraform_version": "1.16.5",
                "planned_values": {},
                "resource_drift": [
                    {
                        "address": "module.app.aws_instance.demo",
                        "type": "aws_instance",
                        "mode": "managed",
                        "change": {
                            "actions": ["update"],
                            "before": {"size": 1},
                            "after": {"size": 2},
                        },
                    }
                ],
            }
        ),
    )
    cli = CliRunner().invoke(
        app, ["drift", str(tmp_path), "--plan-json", str(imported), "--format", "json"]
    )
    assert cli.exit_code == 0, cli.output
    location = json.loads(cli.stdout)["resources"][0]["source"]
    assert location["status"] == "located"
    assert location["locations"][0]["file"] == str(source.resolve())
