import io
import json

import pytest

from infralens_backend.findings import normalize_report


def report(items, **result):
    return io.BytesIO(
        json.dumps(
            {
                "SchemaVersion": 2,
                "Results": [
                    {"Misconfigurations": items, "Target": "main.tf", **result}
                ],
            }
        ).encode()
    )


def finding(**extra):
    return {
        "ID": "AVD-AWS-0088",
        "Severity": "HIGH",
        "Title": "Public bucket",
        "Status": "FAIL",
        "Message": "Restrict access",
        **extra,
    }


def test_normalize_suppression_location_and_stable_ids():
    items = [
        finding(
            CauseMetadata={
                "Resource": "aws_s3_bucket.main",
                "StartLine": 4,
                "EndLine": 9,
            }
        ),
        finding(Status="PASS"),
        finding(Status="EXCEPTION"),
        finding(),
    ]
    rows = list(normalize_report(report(items)))
    assert len(rows) == 2
    assert rows[0]["file"] == "main.tf"  # Target can follow Misconfigurations.
    assert rows[0]["start_line"] == 4
    assert rows[0]["resource"] == "aws_s3_bucket.main"
    assert rows[0]["finding_id"] != rows[1]["finding_id"]
    assert rows == list(normalize_report(report(items)))


def test_normalize_unknown_location_and_bounded_fields():
    rows = list(normalize_report(report([finding(Message="é" * 100000)], Target=".")))
    assert rows[0]["file"] is None
    assert rows[0]["start_line"] is None
    assert rows[0]["truncated_fields"] == ["message"]
    assert len(rows[0]["message"].encode()) <= 16384


@pytest.mark.parametrize(
    "extra",
    [{"Severity": "bad"}, {"ID": ""}, {"Status": "OTHER"}, {"CauseMetadata": []}],
)
def test_normalize_rejects_invalid_consumed_fields(extra):
    with pytest.raises(ValueError):
        list(normalize_report(report([finding(**extra)])))


def test_empty_and_multiple_results():
    assert list(normalize_report(io.BytesIO(b'{"SchemaVersion":2}'))) == []
    stream = io.BytesIO(
        json.dumps(
            {
                "SchemaVersion": 2,
                "Results": [
                    {"Target": "a.tf", "Misconfigurations": [finding()]},
                    {
                        "Target": "b.tf",
                        "Misconfigurations": [finding(Severity="CRITICAL")],
                    },
                ],
            }
        ).encode()
    )
    assert [r["file"] for r in normalize_report(stream)] == ["a.tf", "b.tf"]


def test_ignored_nested_payload_cannot_expand_unbounded_in_memory():
    with pytest.raises(ValueError, match="processing bounds"):
        list(normalize_report(report([finding(IgnoredPayload=[{}] * 10000)])))


def test_source_excerpt_is_plain_text_and_bounded():
    code = {
        "Lines": [
            {
                "Number": 10,
                "Content": 'acl = "public-read"',
                "IsCause": True,
                "Highlighted": "<span>unsafe HTML</span>",
            }
        ]
        * 50
    }
    row = list(normalize_report(report([finding(CauseMetadata={"Code": code})])))[0]
    assert len(row["code"]) == 40
    assert row["code"][0] == {
        "number": 10,
        "content": 'acl = "public-read"',
        "is_cause": True,
    }
    assert row["truncated_fields"] == ["code"]
