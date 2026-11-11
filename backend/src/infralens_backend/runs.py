"""Immutable report upload and user-owned run state."""

import base64
import hashlib
import json
import logging
from datetime import timedelta
from uuid import uuid4

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from infralens_backend import validation as v
from infralens_backend.errors import ApiError, conflict, not_found
from infralens_backend.reports import validate_report

logger = logging.getLogger(__name__)


def conditional(exc):
    return exc.response["Error"]["Code"] == "ConditionalCheckFailedException"


class Runs:
    def __init__(self, settings, table, s3, now):
        self.settings = settings
        self.table = table
        self.s3 = s3
        self.now = now
        self.analysis = None

    def key(self, owner, run):
        return {"pk": f"USER#{owner}", "sk": f"RUN#{run}"}

    def get(self, owner, run):
        item = self.table.get_item(Key=self.key(owner, run), ConsistentRead=True).get(
            "Item"
        )
        if item is None or item["data"]["upload_status"] == "deleting":
            raise not_found()
        return item

    def object_key(self, owner, item):
        data = item["data"]
        return (
            f"users/{owner}/projects/{data['project_id']}/runs/"
            f"{data['run_id']}/{item['generation']}/report.json"
        )

    def replace(self, item, previous_revision):
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="#rev = :revision AND #gen = :generation",
                ExpressionAttributeNames={"#rev": "revision", "#gen": "generation"},
                ExpressionAttributeValues={
                    ":revision": previous_revision,
                    ":generation": item["generation"],
                },
            )
        except ClientError as exc:
            if conditional(exc):
                raise conflict() from None
            raise

    def register(self, owner, payload):
        now = self.now()
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        data = {
            **payload,
            "upload_status": "pending",
            "received_at": v.iso(now),
            "uploaded_at": None,
        }
        expires = now + timedelta(seconds=self.settings.pending_seconds)
        item = {
            **self.key(owner, payload["run_id"]),
            "data": data,
            "fingerprint": fingerprint,
            "revision": 0,
            "generation": str(uuid4()),
            "cleanup_pk": "PENDING",
            "cleanup_sk": v.iso(expires),
            "upload_valid_until": v.iso(
                now + timedelta(seconds=self.settings.upload_seconds)
            ),
        }
        status = 201
        try:
            self.table.put_item(
                Item=item, ConditionExpression="attribute_not_exists(pk)"
            )
        except ClientError as exc:
            if not conditional(exc):
                raise
            item = self.get(owner, payload["run_id"])
            if item["fingerprint"] != fingerprint:
                raise conflict(
                    "Run ID is already registered with different metadata."
                ) from None
            if item["data"]["upload_status"] == "ready":
                return 200, {"run": item["data"], "upload": None}
            if item["cleanup_sk"] <= v.iso(now):
                raise conflict("Upload session expired; start a new scan.") from None
            revision = item["revision"]
            item["revision"] = revision + 1
            item["upload_valid_until"] = max(
                item["upload_valid_until"],
                min(
                    v.iso(now + timedelta(seconds=self.settings.upload_seconds)),
                    item["cleanup_sk"],
                ),
            )
            self.replace(item, revision)
            status = 200
        remaining = int((v.timestamp(item["cleanup_sk"]) - now).total_seconds())
        lifetime = min(self.settings.upload_seconds, remaining)
        if lifetime < 1:
            raise conflict("Upload session expired; start a new scan.")
        advertised_expiry = v.iso(now + timedelta(seconds=lifetime))
        artifact = payload["artifact"]
        checksum = base64.b64encode(bytes.fromhex(artifact["sha256"])).decode()
        params = {
            "Bucket": self.settings.bucket,
            "Key": self.object_key(owner, item),
            "ContentType": "application/json",
            "ContentLength": artifact["size_bytes"],
            "ChecksumSHA256": checksum,
            "ChecksumAlgorithm": "SHA256",
            "IfNoneMatch": "*",
            "Tagging": "state=pending",
        }
        url = self.s3.generate_presigned_url(
            "put_object", Params=params, ExpiresIn=lifetime
        )
        return status, {
            "run": item["data"],
            "upload": {
                "url": url,
                "method": "PUT",
                "expires_at": advertised_expiry,
                "headers": {
                    "content-type": "application/json",
                    "content-length": str(artifact["size_bytes"]),
                    "x-amz-checksum-sha256": checksum,
                    "x-amz-tagging": "state=pending",
                    "x-amz-sdk-checksum-algorithm": "SHA256",
                    "if-none-match": "*",
                },
            },
        }

    def complete(self, owner, run):
        item = self.get(owner, run)
        data = item["data"]
        if data["upload_status"] == "ready":
            return data
        if item["cleanup_sk"] <= v.iso(self.now()):
            raise conflict("Upload session expired; start a new scan.")
        try:
            head = self.s3.head_object(
                Bucket=self.settings.bucket,
                Key=self.object_key(owner, item),
                ChecksumMode="ENABLED",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                raise ApiError(
                    409, "artifact_missing", "Upload the report before completing."
                ) from None
            raise
        artifact = data["artifact"]
        checksum = base64.b64encode(bytes.fromhex(artifact["sha256"])).decode()
        if (
            head.get("ContentLength") != artifact["size_bytes"]
            or head.get("ContentType") != "application/json"
            or head.get("ChecksumSHA256") != checksum
        ):
            raise ApiError(
                409,
                "artifact_mismatch",
                "Report does not match the registered manifest.",
            )
        try:
            response = self.s3.get_object(
                Bucket=self.settings.bucket,
                Key=self.object_key(owner, item),
                ChecksumMode="ENABLED",
            )
            with response["Body"] as stream:
                if data["run_type"] == "drift":
                    from infralens_backend.drift import (
                        validate_report as validate_drift,
                    )

                    validate_drift(stream, data)
                else:
                    validate_report(stream)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                raise conflict("Report was deleted while completing upload.") from None
            raise
        # A late PUT that finishes after deletion remains tagged pending and is
        # expired by S3 lifecycle. Only verified reports are retained indefinitely.
        try:
            self.s3.put_object_tagging(
                Bucket=self.settings.bucket,
                Key=self.object_key(owner, item),
                Tagging={"TagSet": [{"Key": "state", "Value": "ready"}]},
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                raise conflict("Report was deleted while completing upload.") from None
            raise
        revision = item["revision"]
        item["revision"] = revision + 1
        data["upload_status"] = "ready"
        data["uploaded_at"] = v.iso(self.now())
        if self.analysis is not None and data["run_type"] == "security_scan":
            data["analysis"] = self.analysis.pending()
            self.analysis.ensure_job(item)
        item["history_pk"] = item["pk"]
        item["project_pk"] = f"{item['pk']}#PROJECT#{data['project_id']}"
        item["history_sk"] = f"{data['started_at']}#{run}"
        del item["cleanup_pk"], item["cleanup_sk"]
        try:
            self.replace(item, revision)
        except ApiError as exc:
            if exc.status != 409:
                raise
            current = self.table.get_item(
                Key=self.key(owner, run),
                ConsistentRead=True,
            ).get("Item")
            if (
                current
                and current["generation"] == item["generation"]
                and current["data"]["upload_status"] == "ready"
            ):
                return current["data"]
            raise
        return data

    def history(self, owner, event):
        params = v.query(
            event,
            [
                "project_id",
                "from",
                "to",
                "limit",
                "cursor",
                "run_type",
                "scope",
                "gate_status",
            ],
        )
        run_type = params.get("run_type", "security_scan")
        if run_type not in ("security_scan", "drift"):
            raise v.invalid("Unsupported run type.")
        if run_type != "drift" and ("scope" in params or "gate_status" in params):
            raise v.invalid("Drift filters require run_type=drift.")
        drift_scope = v.project_id(params["scope"]) if "scope" in params else None
        gate = params.get("gate_status")
        if gate is not None and gate not in (
            "disabled",
            "passed",
            "failed",
            "incomplete",
        ):
            raise v.invalid("Unsupported gate status.")
        project = v.project_id(params["project_id"]) if "project_id" in params else None
        start = v.iso(v.timestamp(params.get("from", "1970-01-01T00:00:00Z")))
        finish = v.iso(v.timestamp(params.get("to", "9999-12-31T23:59:59.999999Z")))
        if start > finish:
            raise v.invalid("'from' must not be later than 'to'.")
        scope = {"owner": owner, "project_id": project, "from": start, "to": finish}
        if run_type != "security_scan":
            scope.update(run_type=run_type, scope=drift_scope, gate_status=gate)
        index = "ProjectHistoryIndex" if project else "HistoryIndex"
        attribute = "project_pk" if project else "history_pk"
        partition = f"USER#{owner}" + (f"#PROJECT#{project}" if project else "")
        cursor = v.decode_cursor(
            params.get("cursor"),
            scope,
            {
                "pk": f"USER#{owner}",
                "sk": None,
                attribute: partition,
                "history_sk": None,
            },
        )
        if cursor and not cursor["sk"].startswith("RUN#"):
            raise v.invalid("Invalid run cursor.")
        kwargs = {"ExclusiveStartKey": cursor} if cursor else {}
        page = self.table.query(
            IndexName=index,
            KeyConditionExpression=Key(attribute).eq(partition)
            & Key("history_sk").between(f"{start}#", f"{finish}#~"),
            ScanIndexForward=False,
            Limit=v.page_limit(params),
            **kwargs,
        )
        items = []
        # GSIs are eventually consistent. Recheck ownership/state in the base table
        # so an old index entry cannot republish deleted metadata.
        for entry in page.get("Items", []):
            item = self.table.get_item(
                Key={"pk": entry["pk"], "sk": entry["sk"]},
                ConsistentRead=True,
            ).get("Item")
            if (
                item
                and item["data"]["upload_status"] == "ready"
                and item["generation"] == entry["generation"]
                and item.get(attribute) == entry.get(attribute)
                and item.get("history_sk") == entry.get("history_sk")
                and item["data"]["run_type"] == run_type
                and (drift_scope is None or item["data"].get("scope") == drift_scope)
                and (gate is None or item["data"]["result"].get("gate_status") == gate)
            ):
                items.append(item["data"])
        return {
            "items": items,
            "next_cursor": v.encode_cursor(page.get("LastEvaluatedKey"), scope),
        }

    def download(self, owner, run):
        item = self.get(owner, run)
        data = item["data"]
        if data["upload_status"] != "ready":
            raise conflict("Report upload has not completed.")
        url = self.s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.settings.bucket,
                "Key": self.object_key(owner, item),
                "ResponseContentType": "application/json",
                "ResponseContentDisposition": f'attachment; filename="{run}.json"',
            },
            ExpiresIn=self.settings.download_seconds,
        )
        return {
            "url": url,
            "expires_at": v.iso(
                self.now() + timedelta(seconds=self.settings.download_seconds)
            ),
        }

    def claim_deletion(self, item):
        if item["data"]["upload_status"] == "deleting":
            return item
        revision = item["revision"]
        item["revision"] = revision + 1
        item["data"]["upload_status"] = "deleting"
        for attribute in ("history_pk", "history_sk", "project_pk"):
            item.pop(attribute, None)
        item["cleanup_pk"] = "DELETING"
        item["cleanup_sk"] = v.iso(self.now())
        if "analysis" in item["data"]:
            # Any already-running worker is bounded by its 600-second timeout.
            item["analysis_delete_after"] = v.iso(
                v.timestamp(item["data"]["analysis"]["requested_at"])
                + timedelta(minutes=16)
            )
        self.replace(item, revision)
        return item

    def finish_deletion(self, item):
        owner = item["pk"].removeprefix("USER#")
        self.s3.delete_object(
            Bucket=self.settings.bucket, Key=self.object_key(owner, item)
        )
        # Keep a tombstone until every upload URL has expired. The extra minute
        # covers time spent signing after recording its lifetime in DynamoDB.
        safe_after = v.timestamp(item["upload_valid_until"]) + timedelta(minutes=1)
        if "analysis_delete_after" in item:
            safe_after = max(safe_after, v.timestamp(item["analysis_delete_after"]))
        if self.now() < safe_after:
            revision = item["revision"]
            item["revision"] = revision + 1
            item["cleanup_sk"] = v.iso(safe_after)
            self.replace(item, revision)
            return False
        try:
            self.table.delete_item(
                Key={"pk": item["pk"], "sk": item["sk"]},
                ConditionExpression="#rev = :revision AND #gen = :generation",
                ExpressionAttributeNames={"#rev": "revision", "#gen": "generation"},
                ExpressionAttributeValues={
                    ":revision": item["revision"],
                    ":generation": item["generation"],
                },
            )
        except ClientError as exc:
            if conditional(exc):
                raise conflict() from None
            raise
        return True

    def delete(self, owner, run):
        item = self.table.get_item(Key=self.key(owner, run), ConsistentRead=True).get(
            "Item"
        )
        if not item:
            raise not_found()
        item = self.claim_deletion(item)
        if self.finish_deletion(item):
            return 204, None
        return 202, {
            "upload_status": "deleting",
            "run_id": run,
            "delete_after": item["cleanup_sk"],
        }

    def cleanup(self):
        counts = {"deleted": 0, "deferred": 0, "failed": 0}
        # Bound work per invocation. Remaining due entries stay indexed for the
        # next schedule, including operations interrupted after an S3 delete.
        for state in ("PENDING", "DELETING"):
            page = self.table.query(
                IndexName="CleanupIndex",
                KeyConditionExpression=Key("cleanup_pk").eq(state)
                & Key("cleanup_sk").lte(v.iso(self.now())),
                Limit=100,
            )
            for entry in page.get("Items", []):
                try:
                    item = self.table.get_item(
                        Key={"pk": entry["pk"], "sk": entry["sk"]},
                        ConsistentRead=True,
                    ).get("Item")
                    if (
                        not item
                        or item.get("cleanup_pk") != state
                        or item.get("cleanup_sk", "~") > v.iso(self.now())
                    ):
                        continue
                    item = self.claim_deletion(item)
                    result = self.finish_deletion(item)
                    counts["deleted" if result else "deferred"] += 1
                except ApiError as exc:
                    if exc.status != 409:
                        raise
                    counts["deferred"] += 1
                except ClientError as exc:
                    logger.error("cleanup_dependency_error type=%s", type(exc).__name__)
                    counts["failed"] += 1
        logger.info(
            "cleanup_result deleted=%d deferred=%d failed=%d",
            counts["deleted"],
            counts["deferred"],
            counts["failed"],
        )
        return counts
