import json

from infralens.drift import AttributeChange, DriftResult, ResourceDrift
from infralens.drift_code import source_excerpts
from infralens.drift_reporting import render_drift
from infralens.source_locations import enrich_source_locations


def report(
    root, text, path=("instance_type",), before=None, after=None, filename="main.tf"
):
    (root / filename).write_text(text)
    change = AttributeChange(
        path,
        before or {"status": "known", "value": "t3.micro"},
        after or {"status": "known", "value": "t3.small"},
    )
    result = DriftResult(
        "1.15.7",
        (ResourceDrift("aws_instance.demo", "aws_instance", ("update",), (change,)),),
        "refresh_only",
        "now",
    )
    result = enrich_source_locations(result, root)
    return result, source_excerpts(result, root)


def test_code_marks_changed_field_without_unrelated_secret(tmp_path):
    result, excerpts = report(
        tmp_path,
        'resource "aws_instance" "demo" {\n  instance_type = "t3.micro"\n'
        '  password = "PRIVATE_NEIGHBOR"\n}\n',
    )
    text = render_drift(result, excerpts=excerpts)
    assert 'instance_type = "t3.micro"' in text and "> 2 |" in text
    assert "PRIVATE_NEIGHBOR" not in text
    assert "Current configuration" in text
    assert "Current configuration" not in json.dumps(result.to_dict())


def test_same_line_attributes_are_extracted_by_span_not_whole_line(tmp_path):
    result, excerpts = report(
        tmp_path,
        'resource "aws_instance" "demo" { instance_type = "t3.micro" '
        'password = "PRIVATE_NEIGHBOR" }',
    )
    text = render_drift(result, excerpts=excerpts)
    assert 'instance_type = "t3.micro"' in text and "PRIVATE_NEIGHBOR" not in text


def test_sensitive_current_source_is_masked_even_when_literal(tmp_path):
    result, excerpts = report(
        tmp_path,
        'resource "aws_instance" "demo" { password = "PRIVATE_LITERAL" }',
        path=("password",),
        before={"status": "sensitive"},
        after={"status": "sensitive"},
    )
    text = render_drift(result, excerpts=excerpts)
    assert "PRIVATE_LITERAL" not in text and "[sensitive]" in text


def test_nested_tag_excerpt_does_not_expose_neighbor_tag(tmp_path):
    result, excerpts = report(
        tmp_path,
        'resource "aws_instance" "demo" {\n tags = { ReviewOwner = "old" '
        'Password = "PRIVATE_TAG" }\n}',
        path=("tags", "ReviewOwner"),
    )
    text = render_drift(result, excerpts=excerpts)
    assert 'ReviewOwner = "old"' in text and "PRIVATE_TAG" not in text


def test_json_field_excerpt_does_not_copy_other_properties(tmp_path):
    result, excerpts = report(
        tmp_path,
        json.dumps(
            {
                "resource": {
                    "aws_instance": {
                        "demo": {
                            "instance_type": "t3.micro",
                            "password": "PRIVATE_JSON",
                        }
                    }
                }
            },
            indent=2,
        ),
        filename="main.tf.json",
    )
    text = render_drift(result, excerpts=excerpts)
    assert '"instance_type": "t3.micro"' in text and "PRIVATE_JSON" not in text


def test_forged_location_never_reads_outside_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "private.tf"
    outside.write_text(
        'resource "aws_instance" "demo" { instance_type = "PRIVATE_OUTSIDE" }'
    )
    result = DriftResult(
        "1.15.7",
        (
            ResourceDrift(
                "aws_instance.demo",
                "aws_instance",
                ("update",),
                (),
                source={
                    "status": "located",
                    "locations": [
                        {"file": str(outside), "start_line": 1, "end_line": 1}
                    ],
                },
            ),
        ),
        "refresh_only",
        "now",
    )
    text = render_drift(result, excerpts=source_excerpts(result, root))
    assert "PRIVATE_OUTSIDE" not in text and "unavailable" in text


def test_excerpts_do_not_change_normalized_report(tmp_path):
    result, excerpts = report(
        tmp_path, 'resource "aws_instance" "demo" { instance_type = "t3.micro" }'
    )
    before = json.dumps(result.to_dict(), sort_keys=True)
    source_excerpts(result, tmp_path, color=True)
    assert json.dumps(result.to_dict(), sort_keys=True) == before


def test_list_excerpt_excludes_unchanged_neighbor_literal(tmp_path):
    result, excerpts = report(
        tmp_path,
        'resource "aws_instance" "demo" { values = ["old", "PRIVATE_NEIGHBOR"] }',
        path=("values", 0),
    )
    text = render_drift(result, excerpts=excerpts)
    assert "PRIVATE_NEIGHBOR" not in text and '"old"' in text
