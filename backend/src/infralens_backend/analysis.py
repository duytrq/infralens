"""Idempotent report indexing, private query APIs and deferred cleanup."""

import json
import logging
import time
from datetime import timedelta
from uuid import uuid4

import ijson
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from infralens_backend import validation as v
from infralens_backend.errors import ApiError, invalid, not_found
from infralens_backend.findings import VERSION, digest, finding_id, normalize_report
from infralens_backend.schemas import SEVERITIES

logger = logging.getLogger(__name__)
SUMMARY_FIELDS = (
    "finding_id",
    "rule_id",
    "severity",
    "title",
    "file",
    "resource",
    "start_line",
    "end_line",
    "truncated_fields",
)


class Analysis:
    def __init__(self, runs, table):
        self.runs = runs
        self.table = table

    def pending(self):
        return {
            "status": "pending",
            "version": VERSION,
            "build_id": str(uuid4()),
            "requested_at": v.iso(self.runs.now()),
            "completed_at": None,
            "findings": None,
            "counts_match": None,
            "error_code": None,
        }

    def partition(self, owner, run, generation, build):
        return f"USER#{owner}#RUN#{run}#GEN#{generation}#BUILD#{build}"

    def ensure_job(self, item):
        analysis = item["data"]["analysis"]
        run = item["data"]["run_id"]
        job = {
            "pk": item["pk"],
            "sk": f"ANALYSIS#{run}#{item['generation']}#{analysis['build_id']}",
            "run_id": run,
            "generation": item["generation"],
            "build_id": analysis["build_id"],
            "cleanup_pk": "ANALYSIS",
            "cleanup_sk": v.iso(self.runs.now() + timedelta(minutes=20)),
        }
        try:
            self.runs.table.put_item(
                Item=job, ConditionExpression="attribute_not_exists(pk)"
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def current(self, owner, run, generation, build, pending=False):
        item = self.runs.table.get_item(
            Key=self.runs.key(owner, run), ConsistentRead=True
        ).get("Item")
        if (
            not item
            or item["generation"] != generation
            or item["data"]["upload_status"] != "ready"
            or item["data"]["run_type"] != "security_scan"
        ):
            return None
        analysis = item["data"].get("analysis", {})
        if analysis.get("build_id") != build or (
            pending and analysis.get("status") != "pending"
        ):
            return None
        return item

    def process(self, owner, run, generation, build):
        item = self.current(owner, run, generation, build, pending=True)
        if item is None:
            return "skipped"
        # Do not start old deliveries indefinitely; this also bounds deletion's
        # worker grace period (five minutes to start + ten minutes runtime).
        if self.runs.now() > v.timestamp(
            item["data"]["analysis"]["requested_at"]
        ) + timedelta(minutes=5):
            self.finish(
                owner, run, generation, build, "failed", error="processing_expired"
            )
            return "failed"
        self.ensure_job(item)  # Durable cleanup record precedes every derived write.
        partition = self.partition(owner, run, generation, build)
        counts = dict.fromkeys(SEVERITIES, 0)
        started = time.monotonic()
        try:
            response = self.runs.s3.get_object(
                Bucket=self.runs.settings.bucket,
                Key=self.runs.object_key(owner, item),
                ChecksumMode="ENABLED",
            )
            with response["Body"] as stream, self.table.batch_writer() as batch:
                for ordinal, finding in enumerate(normalize_report(stream)):
                    if ordinal % 25 == 0:
                        if time.monotonic() - started > 500:
                            raise ValueError("Processing limit exceeded")
                        if (
                            self.current(owner, run, generation, build, pending=True)
                            is None
                        ):
                            return "skipped"
                    counts[finding["severity"]] += 1
                    sk = "F#" + finding["finding_id"]
                    row = {
                        "pk": partition,
                        "sk": sk,
                        "data": finding,
                        "rule_pk": partition + "#RULE#" + digest(finding["rule_id"]),
                    }
                    if finding["file"] is not None:
                        row["file_pk"] = partition + "#FILE#" + digest(finding["file"])
                    batch.put_item(Item=row)
        except (ValueError, ijson.JSONError, UnicodeError):
            self.finish(
                owner, run, generation, build, "failed", error="artifact_unsupported"
            )
            return "failed"
        self.finish(owner, run, generation, build, "ready", counts=counts)
        logger.info(
            "analysis_result status=ready findings=%d duration_ms=%d",
            sum(counts.values()),
            int((time.monotonic() - started) * 1000),
        )
        return "ready"

    def finish(self, owner, run, generation, build, status, counts=None, error=None):
        item = self.current(owner, run, generation, build, pending=True)
        if item is None:
            return
        analysis = item["data"]["analysis"]
        analysis.update(
            status=status, completed_at=v.iso(self.runs.now()), error_code=error
        )
        if counts is not None:
            analysis["findings"] = {
                "total": sum(counts.values()),
                "by_severity": counts,
            }
            analysis["counts_match"] = (
                analysis["findings"] == item["data"]["result"]["findings"]
            )
        revision = item["revision"]
        item["revision"] += 1
        try:
            self.runs.replace(item, revision)
        except ApiError as exc:
            if exc.status != 409:
                raise
            # A concurrent delete/retry/worker wins. Never overwrite its state.

    def retry(self, owner, run):
        item = self.runs.get(owner, run)
        if item["data"]["run_type"] != "security_scan":
            raise ApiError(
                409, "unsupported_run_type", "Indexing requires a security scan."
            )
        if item["data"]["upload_status"] != "ready":
            raise ApiError(409, "artifact_pending", "Complete the report upload first.")
        status = item["data"].get("analysis", {}).get("status")
        if status in ("pending", "ready"):
            return (202 if status == "pending" else 200), item["data"]
        item["data"]["analysis"] = self.pending()
        self.ensure_job(item)
        revision = item["revision"]
        item["revision"] += 1
        self.runs.replace(item, revision)
        return 202, item["data"]

    def readable(self, owner, run):
        item = self.runs.get(owner, run)
        if item["data"]["run_type"] != "security_scan":
            raise ApiError(
                409, "unsupported_run_type", "Findings require a security scan."
            )
        analysis = item["data"].get("analysis", {})
        if (
            item["data"]["upload_status"] != "ready"
            or analysis.get("status") != "ready"
        ):
            raise ApiError(
                409,
                "analysis_" + analysis.get("status", "unavailable"),
                "Scan details are not ready; check the run's analysis status.",
            )
        return item, self.partition(
            owner, run, item["generation"], analysis["build_id"]
        )

    def page(self, owner, run, event):
        item, partition = self.readable(owner, run)
        params = v.query(event, ["severity", "rule_id", "file", "limit", "cursor"])
        filters = {
            key: params[key] for key in ("severity", "rule_id", "file") if key in params
        }
        if "severity" in filters and filters["severity"] not in SEVERITIES:
            raise invalid("Invalid severity.")
        if any(
            not value or len(value.encode()) > (1024 if key == "rule_id" else 4096)
            for key, value in filters.items()
        ):
            raise invalid("Invalid finding filter.")
        attribute, index, key_value = "pk", None, partition
        for name, field, selected in (
            ("rule_id", "rule_pk", "RuleIndex"),
            ("file", "file_pk", "FileIndex"),
        ):
            if name in filters:
                attribute, index = field, selected
                key_value = (
                    partition
                    + ("#RULE#" if name == "rule_id" else "#FILE#")
                    + digest(filters[name])
                )
                break
        scope = {
            "owner": owner,
            "run": run,
            "partition": partition,
            "filters": digest(
                json.dumps(filters, sort_keys=True, separators=(",", ":"))
            ),
        }
        required = {"pk": partition, "sk": None}
        if index:
            required[attribute] = key_value
        cursor = v.decode_cursor(params.get("cursor"), scope, required)
        if cursor and not re_finding_key(cursor["sk"]):
            raise invalid("Invalid finding cursor.")
        condition = Key(attribute).eq(key_value)
        kwargs = {"IndexName": index} if index else {"ConsistentRead": True}
        if "severity" in filters:
            from infralens_backend.findings import RANK

            condition &= Key("sk").begins_with(f"F#{RANK[filters['severity']]}-")
        expression = None
        for name, value in filters.items():
            term = Attr("data." + name).eq(value)
            expression = term if expression is None else expression & term
        if expression is not None:
            kwargs["FilterExpression"] = expression
        if cursor:
            kwargs["ExclusiveStartKey"] = cursor
        page = self.table.query(
            KeyConditionExpression=condition, Limit=v.page_limit(params), **kwargs
        )
        # Recheck publication/ownership after reading an eventually consistent index.
        current, current_partition = self.readable(owner, run)
        if current_partition != partition:
            raise ApiError(
                409, "analysis_changed", "Analysis changed; restart pagination."
            )
        return {
            "items": [
                {k: row["data"][k] for k in SUMMARY_FIELDS}
                for row in page.get("Items", [])
            ],
            "next_cursor": v.encode_cursor(page.get("LastEvaluatedKey"), scope),
        }

    def detail(self, owner, run, identifier):
        _, partition = self.readable(owner, run)
        row = self.table.get_item(
            Key={"pk": partition, "sk": "F#" + finding_id(identifier)},
            ConsistentRead=True,
        ).get("Item")
        _, current = self.readable(owner, run)
        if current != partition or row is None:
            raise not_found()
        return row["data"]

    def purge(self, partition):
        """Bound cleanup per invocation; the durable job remains until exhausted."""
        page = self.table.query(
            KeyConditionExpression=Key("pk").eq(partition),
            ProjectionExpression="pk, sk",
            Limit=500,
            ConsistentRead=True,
        )
        with self.table.batch_writer() as batch:
            for row in page.get("Items", []):
                batch.delete_item(Key=row)
        return not page.get("LastEvaluatedKey")

    def cleanup(self):
        result = {"deleted": 0, "deferred": 0, "failed": 0}
        jobs = self.runs.table.query(
            IndexName="CleanupIndex",
            KeyConditionExpression=Key("cleanup_pk").eq("ANALYSIS")
            & Key("cleanup_sk").lte(v.iso(self.runs.now())),
            Limit=100,
        )
        for entry in jobs.get("Items", []):
            try:
                key = {"pk": entry["pk"], "sk": entry["sk"]}
                job = self.runs.table.get_item(Key=key, ConsistentRead=True).get("Item")
                if not job or job["cleanup_sk"] > v.iso(self.runs.now()):
                    continue
                owner = job["pk"].removeprefix("USER#")
                item = self.current(
                    owner, job["run_id"], job["generation"], job["build_id"]
                )
                if item and item["data"]["analysis"]["status"] == "pending":
                    self.finish(
                        owner,
                        job["run_id"],
                        job["generation"],
                        job["build_id"],
                        "failed",
                        error="processing_expired",
                    )
                    # A racing ready publisher may have won; re-read before purging.
                    item = self.current(
                        owner, job["run_id"], job["generation"], job["build_id"]
                    )
                if item and item["data"]["analysis"]["status"] == "ready":
                    self.runs.table.update_item(
                        Key=key,
                        UpdateExpression="SET cleanup_sk = :due",
                        ConditionExpression="attribute_exists(pk)",
                        ExpressionAttributeValues={
                            ":due": v.iso(self.runs.now() + timedelta(hours=1))
                        },
                    )
                    result["deferred"] += 1
                    continue
                partition = self.partition(
                    owner, job["run_id"], job["generation"], job["build_id"]
                )
                if self.purge(partition):
                    self.runs.table.delete_item(Key=key)
                    result["deleted"] += 1
                else:
                    result["deferred"] += 1
            except (ClientError, ApiError):
                logger.error("analysis_cleanup_dependency_error")
                result["failed"] += 1
        return result


def re_finding_key(value):
    import re

    from infralens_backend.findings import ID_PATTERN

    return re.fullmatch("F#" + ID_PATTERN, value) is not None
