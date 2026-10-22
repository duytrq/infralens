"""AWS Lambda entry points. API Gateway is the JWT verification boundary."""

import logging
from functools import lru_cache

import boto3
from botocore.config import Config

from infralens_backend.app import Application
from infralens_backend.settings import Settings

logging.getLogger().setLevel(logging.INFO)


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
        ):
            continue
        service.process(
            item["pk"].removeprefix("USER#"),
            item["data"]["run_id"],
            item["generation"],
            analysis["build_id"],
        )
    return {"processed": len(event.get("Records", []))}
