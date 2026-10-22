"""Queue missing/failed scan indexes in an existing deployment; dry-run by default."""

import argparse
import json

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config

from infralens_backend.app import Application
from infralens_backend.errors import ApiError
from infralens_backend.settings import Settings


def backfill(app, apply=False, include_failed=False, maximum=100):
    counts = {"eligible": 0, "queued": 0, "conflicts": 0}
    cursor = None
    while counts["eligible"] < maximum:
        kwargs = {"ExclusiveStartKey": cursor} if cursor else {}
        page = app.table.scan(
            FilterExpression=Attr("data.upload_status").eq("ready"),
            Limit=100,
            **kwargs,
        )
        for item in page.get("Items", []):
            status = item["data"].get("analysis", {}).get("status")
            if status is not None and not (include_failed and status == "failed"):
                continue
            counts["eligible"] += 1
            if apply:
                try:
                    code, _ = app.analysis.retry(
                        item["pk"].removeprefix("USER#"), item["data"]["run_id"]
                    )
                    counts["queued"] += code == 202
                except ApiError as exc:
                    if exc.status not in (404, 409):
                        raise
                    counts["conflicts"] += 1
            if counts["eligible"] >= maximum:
                break
        cursor = page.get("LastEvaluatedKey")
        if not cursor:
            break
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--stack", default="infralens-dev")
    parser.add_argument("--maximum", type=int, default=100)
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.maximum <= 10000:
        parser.error("maximum must be between 1 and 10000")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    if session.client("sts").get_caller_identity()["Account"] != args.account:
        raise SystemExit("AWS account does not match the expected account.")
    stack = session.client("cloudformation").describe_stacks(StackName=args.stack)[
        "Stacks"
    ][0]
    outputs = {row["OutputKey"]: row["OutputValue"] for row in stack["Outputs"]}
    config = Config(
        connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 3}
    )
    db = session.resource("dynamodb", config=config)
    settings = Settings(
        table_name=outputs["StorageTable"],
        bucket=outputs["ReportsBucket"],
        issuer="operator",
        client_id="operator",
        auth_domain="operator",
    )
    app = Application(
        settings,
        db.Table(settings.table_name),
        session.client("s3", config=config),
        db.Table(outputs["FindingsTable"]),
    )
    result = backfill(app, args.apply, args.include_failed, args.maximum)
    print(json.dumps({"apply": args.apply, **result}))


if __name__ == "__main__":
    main()
