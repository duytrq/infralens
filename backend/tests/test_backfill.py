import importlib.util
from pathlib import Path

from test_dashboard import completed  # noqa: F401

spec = importlib.util.spec_from_file_location(
    "backfill_analysis", Path(__file__).parents[1] / "scripts/backfill_analysis.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_backfill_is_dry_by_default_and_only_changes_unindexed_runs(cloud, request):
    run = request.getfixturevalue("completed")
    key = cloud.runs.key("user-a", run)
    item = cloud.table.get_item(Key=key)["Item"]
    del item["data"]["analysis"]
    cloud.table.put_item(Item=item)
    assert module.backfill(cloud) == {"eligible": 1, "queued": 0, "conflicts": 0}
    assert "analysis" not in cloud.table.get_item(Key=key)["Item"]["data"]
    assert module.backfill(cloud, apply=True)["queued"] == 1
    assert (
        cloud.table.get_item(Key=key)["Item"]["data"]["analysis"]["status"] == "pending"
    )
    assert module.backfill(cloud, apply=True)["eligible"] == 0


def test_backfill_entrypoint_initializes_without_cli_cognito(monkeypatch, capsys):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    outputs = {
        "StorageTable": "table",
        "ReportsBucket": "bucket",
        "FindingsTable": "findings",
    }
    session = Mock()

    def client(service, **kwargs):
        if service == "sts":
            return SimpleNamespace(get_caller_identity=lambda: {"Account": "123"})
        if service == "cloudformation":
            return SimpleNamespace(
                describe_stacks=lambda **k: {
                    "Stacks": [
                        {
                            "Outputs": [
                                {"OutputKey": key, "OutputValue": value}
                                for key, value in outputs.items()
                            ]
                        }
                    ]
                }
            )
        return Mock()

    session.client.side_effect = client
    session.resource.return_value.Table.return_value.scan.return_value = {"Items": []}
    monkeypatch.setattr(module.boto3, "Session", lambda **kwargs: session)
    monkeypatch.setattr("sys.argv", ["backfill", "--account", "123"])
    module.main()
    assert json.loads(capsys.readouterr().out) == {
        "apply": False,
        "eligible": 0,
        "queued": 0,
        "conflicts": 0,
    }
