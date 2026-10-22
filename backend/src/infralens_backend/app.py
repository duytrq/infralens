"""Small HTTP API dispatcher for AWS API Gateway payload version 2.0."""

import json
import logging
import re
import time
from datetime import UTC, datetime
from decimal import Decimal

from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from infralens_backend import validation as v
from infralens_backend.analysis import Analysis
from infralens_backend.errors import ApiError, conflict, not_found
from infralens_backend.runs import Runs
from infralens_backend.schemas import PROJECT, RUN

logger = logging.getLogger(__name__)


def serialize(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError


def conditional(exc):
    return exc.response["Error"]["Code"] == "ConditionalCheckFailedException"


class Application:
    def __init__(self, settings, table, s3, findings_table=None):
        self.settings = settings
        self.table = table
        self.s3 = s3
        self.now = lambda: datetime.now(UTC)
        self.runs = Runs(settings, table, s3, lambda: self.now())
        self.analysis = (
            Analysis(self.runs, findings_table) if findings_table is not None else None
        )
        self.runs.analysis = self.analysis

    def identity(self, event):
        claims = (
            event.get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
        )
        owner = claims.get("sub", "")
        scope = claims.get("scope")
        if (
            not isinstance(owner, str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", owner)
            or claims.get("iss") != self.settings.issuer
            or claims.get("client_id")
            not in {
                self.settings.client_id,
                self.settings.dashboard_client_id or self.settings.client_id,
            }
            or claims.get("token_use") != "access"
            or not isinstance(scope, str)
            or self.settings.scope not in scope.split()
        ):
            raise ApiError(401, "unauthorized", "A valid access token is required.")
        return owner

    def handle(self, event):
        status = 500
        try:
            status, value = self.route(event)
        except ApiError as exc:
            status = exc.status
            value = {"error": {"code": exc.code, "message": exc.message}}
        except (ClientError, BotoCoreError) as exc:
            logger.error("aws_dependency_error type=%s", type(exc).__name__)
            status = 503
            value = {
                "error": {
                    "code": "service_unavailable",
                    "message": "Service unavailable; retry later.",
                }
            }
        except Exception as exc:
            logger.error("unhandled_error type=%s", type(exc).__name__)
            value = {
                "error": {"code": "internal_error", "message": "Internal server error."}
            }
        # Do not log events, request bodies, JWTs or presigned URLs.
        logger.info("api_response status=%d", status)
        return {
            "statusCode": status,
            "headers": {
                "content-type": "application/json; charset=utf-8",
                "cache-control": "no-store",
                "x-content-type-options": "nosniff",
                "strict-transport-security": "max-age=31536000",
            },
            "body": "" if status == 204 else json.dumps(value, default=serialize),
        }

    def route(self, event):
        method = event.get("requestContext", {}).get("http", {}).get("method")
        path = event.get("rawPath", "")
        if method == "GET" and path == "/v1/config":
            v.query(event, [])
            return 200, self.settings.public()
        if method == "GET" and path == "/v1/dashboard-config":
            v.query(event, [])
            if not self.settings.dashboard_client_id:
                raise ApiError(
                    503, "dashboard_unavailable", "Dashboard is not configured."
                )
            return 200, self.settings.dashboard()
        owner = self.identity(event)
        match = re.fullmatch(
            r"/v1/runs/([^/]+)/(findings(?:/([^/]+))?|analysis/retry)", path
        )
        if match:
            run = v.run_id(match[1])
            if self.analysis is None:
                raise ApiError(
                    503, "analysis_unavailable", "Analysis is not configured."
                )
            if match[2] == "analysis/retry" and method == "POST":
                v.query(event, [])
                return self.analysis.retry(owner, run)
            if match[2].startswith("findings") and method == "GET":
                if match[3]:
                    v.query(event, [])
                    return 200, self.analysis.detail(owner, run, match[3])
                return 200, self.analysis.page(owner, run, event)
        if path == "/v1/runs" and method == "POST":
            v.query(event, [])
            payload = v.scan(v.body(event, RUN), self.settings.max_report_bytes)
            self.project(owner, payload["project_id"])
            return self.runs.register(owner, payload)
        if path == "/v1/runs" and method == "GET":
            return 200, self.runs.history(owner, event)
        match = re.fullmatch(r"/v1/runs/([^/]+)(/complete)?", path)
        if match:
            run = v.run_id(match[1])
            v.query(event, [])
            if match[2] and method == "POST":
                return 200, self.runs.complete(owner, run)
            if not match[2] and method == "GET":
                return 200, self.runs.get(owner, run)["data"]
            if not match[2] and method == "DELETE":
                return self.runs.delete(owner, run)
        match = re.fullmatch(r"/v1/runs/([^/]+)/artifacts/json", path)
        if match and method == "GET":
            v.query(event, [])
            return 200, self.runs.download(owner, v.run_id(match[1]))
        if method == "GET" and path == "/v1/projects":
            return 200, self.projects(owner, event)
        match = re.fullmatch(r"/v1/projects/([^/]+)", path)
        if match:
            project = v.project_id(match[1])
            if method == "PUT":
                v.query(event, [])
                payload = v.body(event, PROJECT)
                return self.create_project(owner, project, payload)
            if method == "GET":
                include = self.project_query(event)
                return 200, self.project_data(
                    owner, self.project(owner, project)["data"], include
                )
        raise not_found()

    def project(self, owner, project):
        item = self.table.get_item(
            Key={"pk": f"USER#{owner}", "sk": f"PROJECT#{project}"},
            ConsistentRead=True,
        ).get("Item")
        if item is None:
            raise not_found()
        return item

    def create_project(self, owner, project, payload):
        data = {
            "project_id": project,
            "name": payload["name"],
            "created_at": v.iso(self.now()),
        }
        try:
            self.table.put_item(
                Item={"pk": f"USER#{owner}", "sk": f"PROJECT#{project}", "data": data},
                ConditionExpression="attribute_not_exists(pk)",
            )
            return 201, data
        except ClientError as exc:
            if not conditional(exc):
                raise
            existing = self.project(owner, project)["data"]
            if existing["name"] != payload["name"]:
                raise conflict(
                    "Project ID already exists with a different name."
                ) from None
            return 200, existing

    def projects(self, owner, event):
        params = v.query(event, ["limit", "cursor", "include"])
        include = self.project_query(event, pagination=True)
        scope = {"owner": owner, "type": "projects"}
        cursor = v.decode_cursor(
            params.get("cursor"), scope, {"pk": f"USER#{owner}", "sk": None}
        )
        if cursor and not cursor["sk"].startswith("PROJECT#"):
            raise v.invalid("Invalid project cursor.")
        kwargs = {"ExclusiveStartKey": cursor} if cursor else {}
        page = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"USER#{owner}")
            & Key("sk").begins_with("PROJECT#"),
            ConsistentRead=True,
            Limit=v.page_limit(params),
            **kwargs,
        )
        budget = {"pages": 120, "deadline": time.monotonic() + 8}
        return {
            "items": [
                self.project_data(owner, item["data"], include, budget)
                for item in page.get("Items", [])
            ],
            "next_cursor": v.encode_cursor(page.get("LastEvaluatedKey"), scope),
        }

    def project_query(self, event, pagination=False):
        params = v.query(
            event, ["include", "limit", "cursor"] if pagination else ["include"]
        )
        if "include" in params and params["include"] != "latest_scan":
            raise v.invalid("Only include=latest_scan is supported.")
        return "include" in params

    def project_data(self, owner, data, include, budget=None):
        if not include:
            return data
        # Reuse history's strong state/generation checks, including empty GSI pages.
        cursor = None
        budget = (
            budget
            if budget is not None
            else {"pages": 120, "deadline": time.monotonic() + 8}
        )
        while True:
            if budget["pages"] <= 0 or time.monotonic() >= budget["deadline"]:
                raise ApiError(
                    503,
                    "latest_scan_unavailable",
                    "Latest-scan lookup is busy; retry later.",
                )
            budget["pages"] -= 1
            params = {"project_id": data["project_id"], "limit": "5" if cursor else "1"}
            if cursor:
                params["cursor"] = cursor
            page = self.runs.history(owner, {"queryStringParameters": params})
            if page["items"]:
                run = page["items"][0]
                summary = {
                    key: run[key]
                    for key in ("run_id", "started_at", "finished_at", "result")
                }
                return {**data, "latest_scan": summary}
            cursor = page["next_cursor"]
            if not cursor:
                return {**data, "latest_scan": None}
