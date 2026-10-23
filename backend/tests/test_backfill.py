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
