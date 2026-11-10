"""AWS Lambda entry points for API, API-key authorization and background work."""

import logging
import os
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from infralens_backend.app import Application
from infralens_backend.settings import Settings

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def application():
    settings = Settings.from_env()
    config = Config(
        connect_timeout=3,
        read_timeout=5,
        retries={"mode": "standard", "total_max_attempts": 3},
    )
    table = boto3.resource("dynamodb", config=config).Table(settings.table_name)
    # Sign the regional virtual-host endpoint: a new bucket's global endpoint
    # can return 307, and following a redirect would change the signed host.
    s3 = boto3.client(
        "s3",
        config=config.merge(
            Config(
                signature_version="s3v4",
                s3={
                    "addressing_style": "virtual",
                    "us_east_1_regional_endpoint": "regional",
                },
            )
        ),
    )
    findings = (
        boto3.resource("dynamodb", config=config).Table(settings.findings_table_name)
        if settings.findings_table_name
        else None
    )
    return Application(settings, table, s3, findings)


def api_handler(event, context):
    return application().handle(event)


@lru_cache(maxsize=1)
def api_key_table():
    config = Config(
        connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 3}
    )
    return boto3.resource("dynamodb", config=config).Table(os.environ["TABLE_NAME"])


@lru_cache(maxsize=1)
def api_key_cognito():
    # Cache the connection only; user status must be checked on every request.
    return boto3.client(
        "cognito-idp",
        config=Config(
            connect_timeout=2,
            read_timeout=3,
            retries={"mode": "standard", "total_max_attempts": 2},
        ),
    )


def api_key_authorizer(event, context):
    from infralens_backend.api_keys import authenticate, owner_is_enabled

    header = event.get("headers", {}).get("authorization", "")
    credential = (
        header.removeprefix("Bearer ")
        if isinstance(header, str) and header.startswith("Bearer ")
        else ""
    )
    try:
        owner = authenticate(api_key_table(), credential)
        if owner is None or not owner_is_enabled(
            api_key_cognito(), os.environ["COGNITO_USER_POOL_ID"], owner
        ):
            return {"isAuthorized": False}
    except (BotoCoreError, ClientError):
        # Fail closed and surface an authorizer failure without logging credentials
        # or Cognito response data. An outage must never grant access.
        logger.error("api_key_authorization_dependency_failed")
        raise RuntimeError("API key verification is unavailable.") from None
    return {"isAuthorized": True, "context": {"owner": owner, "auth_type": "api_key"}}


def cleanup_handler(event, context):
    result = application().runs.cleanup()
    if application().analysis is not None:
        extra = application().analysis.cleanup()
        result = {k: result[k] + extra[k] for k in result}
    if result["failed"]:
        # Surface partial failures in Lambda Errors and EventBridge retry handling.
        raise RuntimeError(
            "Cleanup dependencies unavailable; remaining work is indexed."
        )
    return result


def analysis_handler(event, context):
    """Batch size one, bounded retries; metadata supports manual recovery."""
    from boto3.dynamodb.types import TypeDeserializer

    deserialize = TypeDeserializer().deserialize
    service = application().analysis
    if service is None:
        raise RuntimeError("Analysis is not configured")
    for record in event.get("Records", []):
        image = record.get("dynamodb", {}).get("NewImage", {})
        if not image:
            continue
        item = {k: deserialize(value) for k, value in image.items()}
        analysis = item.get("data", {}).get("analysis", {})
        if (
            analysis.get("status") != "pending"
            or item["data"].get("upload_status") != "ready"
            or item["data"].get("run_type") != "security_scan"
        ):
            continue
        service.process(
            item["pk"].removeprefix("USER#"),
            item["data"]["run_id"],
            item["generation"],
            analysis["build_id"],
        )
    return {"processed": len(event.get("Records", []))}
