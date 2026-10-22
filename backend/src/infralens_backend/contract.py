"""OpenAPI 3.1 contract generated from the runtime request schemas."""

from infralens_backend.schemas import COUNT, PROJECT, RUN, SEVERITIES, TIME, obj


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


STRING = {"type": "string"}
CURSOR = {"type": ["string", "null"], "maxLength": 8192}
NULLABLE_STRING = {"type": ["string", "null"]}
FINDING_COUNTS = obj(
    {"total": COUNT, "by_severity": obj({s: COUNT for s in SEVERITIES})}
)
ANALYSIS = obj(
    {
        "status": {"enum": ["pending", "ready", "failed"]},
        "version": {"type": "integer", "minimum": 1},
        "build_id": {"type": "string", "format": "uuid"},
        "requested_at": TIME,
        "completed_at": {"anyOf": [TIME, {"type": "null"}]},
        "findings": {"anyOf": [FINDING_COUNTS, {"type": "null"}]},
        "counts_match": {"type": ["boolean", "null"]},
        "error_code": NULLABLE_STRING,
    }
)
FINDING_SUMMARY = obj(
    {
        "finding_id": STRING,
        "rule_id": STRING,
        "severity": {"enum": list(SEVERITIES)},
        "title": STRING,
        "file": NULLABLE_STRING,
        "resource": NULLABLE_STRING,
        "start_line": {"type": ["integer", "null"]},
        "end_line": {"type": ["integer", "null"]},
        "truncated_fields": {"type": "array", "items": STRING},
    }
)
FINDING = obj(
    {
        **FINDING_SUMMARY["properties"],
        "message": STRING,
        "description": STRING,
        "resolution": STRING,
        "references": {"type": "array", "items": STRING},
        "code": {
            "type": "array",
            "items": obj(
                {
                    "number": {"type": "integer", "minimum": 1},
                    "content": STRING,
                    "is_cause": {"type": "boolean"},
                }
            ),
        },
    }
)
UPLOAD = obj(
    {
        "url": {"type": "string", "format": "uri"},
        "method": {"const": "PUT"},
        "expires_at": TIME,
        "headers": {"type": "object", "additionalProperties": {"type": "string"}},
    }
)
RUN_ITEM = obj(
    {
        **RUN["properties"],
        "received_at": TIME,
        "uploaded_at": {"anyOf": [TIME, {"type": "null"}]},
        "upload_status": {"enum": ["pending", "ready"]},
        "analysis": ANALYSIS,
    },
    optional=("analysis",),
)
LATEST = obj(
    {
        key: RUN["properties"][key]
        for key in ("run_id", "started_at", "finished_at", "result")
    }
)
PROJECT_ITEM = obj(
    {
        **PROJECT["properties"],
        "project_id": STRING,
        "created_at": TIME,
        "latest_scan": {"anyOf": [LATEST, {"type": "null"}]},
    },
    optional=("latest_scan",),
)
ERROR = obj({"error": obj({"code": STRING, "message": STRING})})

SCHEMAS = {
    "ProjectInput": PROJECT,
    "RunInput": RUN,
    "Project": PROJECT_ITEM,
    "Run": RUN_ITEM,
    "Analysis": ANALYSIS,
    "Finding": FINDING,
    "FindingSummary": FINDING_SUMMARY,
    "FindingPage": obj(
        {
            "items": {"type": "array", "items": ref("FindingSummary")},
            "next_cursor": CURSOR,
        }
    ),
    "ProjectPage": obj(
        {"items": {"type": "array", "items": ref("Project")}, "next_cursor": CURSOR}
    ),
    "RunPage": obj(
        {"items": {"type": "array", "items": ref("Run")}, "next_cursor": CURSOR}
    ),
    "Upload": UPLOAD,
    "Registration": obj(
        {"run": ref("Run"), "upload": {"anyOf": [ref("Upload"), {"type": "null"}]}}
    ),
    "Download": obj({"url": {"type": "string", "format": "uri"}, "expires_at": TIME}),
    "Deletion": obj(
        {"run_id": STRING, "upload_status": {"const": "deleting"}, "delete_after": TIME}
    ),
    "Error": ERROR,
    # API Gateway rejects invalid JWTs before Lambda with its native error body.
    "GatewayError": {"anyOf": [ERROR, obj({"message": STRING})]},
    "Config": obj(
        {
            "schema_version": {"const": 1},
            "api_version": {"const": "v1"},
            "auth": obj(
                {
                    "issuer": STRING,
                    "client_id": STRING,
                    "authorization_endpoint": STRING,
                    "token_endpoint": STRING,
                    "revocation_endpoint": STRING,
                    "callback_url": STRING,
                    "scopes": {"type": "array", "items": STRING},
                    "pkce_method": {"const": "S256"},
                }
            ),
            "upload": obj(
                {
                    "formats": {"const": ["json"]},
                    "max_report_bytes": {"type": "integer", "minimum": 1},
                    "url_expires_seconds": {"type": "integer", "minimum": 1},
                }
            ),
        }
    ),
}
SCHEMAS["DashboardConfig"] = obj(
    {
        **SCHEMAS["Config"]["properties"],
        "auth": obj(
            {
                **SCHEMAS["Config"]["properties"]["auth"]["properties"],
                "logout_url": STRING,
                "logout_endpoint": STRING,
            }
        ),
    }
)


def response(schema, description="Success"):
    return {
        "description": description,
        "content": {"application/json": {"schema": ref(schema)}},
    }


def operation(operation_id, successes, request=None, params=(), public=False):
    result = {
        "operationId": operation_id,
        "responses": {
            str(status): response(schema) if schema else {"description": "Deleted"}
            for status, schema in successes.items()
        },
        "parameters": list(params),
    }
    for status, description in {
        400: "Invalid JSON",
        401: "Invalid or missing access token",
        403: "Access token has insufficient scopes",
        404: "Resource not found",
        409: "Conflict; retry or check upload state",
        413: "Metadata exceeds 64 KiB",
        415: "Unsupported media type",
        422: "Invalid metadata or query",
        429: "Throttled",
        500: "Internal error",
        502: "Gateway integration failed",
        503: "Dependency unavailable; retry later",
        504: "Gateway integration timed out",
    }.items():
        result["responses"][str(status)] = response(
            "GatewayError"
            if status in (401, 403, 413, 429, 500, 502, 504)
            else "Error",
            description,
        )
    if request:
        result["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": ref(request)}},
        }
    if public:
        result["security"] = []
    return result


def parameter(name, schema=STRING, location="query"):
    return {
        "name": name,
        "in": location,
        "required": location == "path",
        "schema": schema,
    }


PAGINATION = (
    parameter(
        "limit", {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
    ),
    parameter("cursor", {"type": "string", "maxLength": 8192}),
)
HISTORY = (
    *PAGINATION,
    parameter("project_id"),
    parameter("from", TIME),
    parameter("to", TIME),
)
INCLUDE_LATEST = (parameter("include", {"enum": ["latest_scan"]}),)
FINDING_FILTERS = (
    *PAGINATION,
    parameter("severity", {"enum": list(SEVERITIES)}),
    parameter("rule_id", {"type": "string", "minLength": 1, "maxLength": 1024}),
    parameter("file", {"type": "string", "minLength": 1, "maxLength": 4096}),
)


def openapi():
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "InfraLens storage API",
            "version": "1.1.0",
            "description": (
                "User-private projects and immutable native Trivy JSON reports. "
                "Caller-reported scan metadata is not independently attested."
            ),
        },
        "security": [{"Cognito": ["infralens/api"]}],
        "components": {
            "securitySchemes": {
                "Cognito": {
                    "type": "oauth2",
                    "flows": {
                        "authorizationCode": {
                            "authorizationUrl": "https://your-cognito-domain/oauth2/authorize",
                            "tokenUrl": "https://your-cognito-domain/oauth2/token",
                            "scopes": {
                                "openid": "OpenID Connect",
                                "infralens/api": "Your own scan history",
                            },
                        }
                    },
                }
            },
            "schemas": SCHEMAS,
        },
        "paths": {
            "/v1/config": {"get": operation("config", {200: "Config"}, public=True)},
            "/v1/dashboard-config": {
                "get": operation(
                    "dashboardConfig", {200: "DashboardConfig"}, public=True
                )
            },
            "/v1/projects": {
                "get": operation(
                    "listProjects",
                    {200: "ProjectPage"},
                    params=(*PAGINATION, *INCLUDE_LATEST),
                )
            },
            "/v1/projects/{project_id}": {
                "parameters": [parameter("project_id", location="path")],
                "put": operation(
                    "createProject", {200: "Project", 201: "Project"}, "ProjectInput"
                ),
                "get": operation("getProject", {200: "Project"}, params=INCLUDE_LATEST),
            },
            "/v1/runs": {
                "post": operation(
                    "registerRun",
                    {200: "Registration", 201: "Registration"},
                    "RunInput",
                ),
                "get": operation("listRuns", {200: "RunPage"}, params=HISTORY),
            },
            "/v1/runs/{run_id}": {
                "parameters": [parameter("run_id", location="path")],
                "get": operation("getRun", {200: "Run"}),
                "delete": operation("deleteRun", {202: "Deletion", 204: None}),
            },
            "/v1/runs/{run_id}/complete": {
                "parameters": [parameter("run_id", location="path")],
                "post": operation("completeRun", {200: "Run"}),
            },
            "/v1/runs/{run_id}/artifacts/json": {
                "parameters": [parameter("run_id", location="path")],
                "get": operation("downloadReport", {200: "Download"}),
            },
            "/v1/runs/{run_id}/findings": {
                "parameters": [parameter("run_id", location="path")],
                "get": operation(
                    "listFindings", {200: "FindingPage"}, params=FINDING_FILTERS
                ),
            },
            "/v1/runs/{run_id}/findings/{finding_id}": {
                "parameters": [
                    parameter("run_id", location="path"),
                    parameter("finding_id", location="path"),
                ],
                "get": operation("getFinding", {200: "Finding"}),
            },
            "/v1/runs/{run_id}/analysis/retry": {
                "parameters": [parameter("run_id", location="path")],
                "post": operation("retryAnalysis", {200: "Run", 202: "Run"}),
            },
        },
    }
