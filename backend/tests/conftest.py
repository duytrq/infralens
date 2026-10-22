import json
import re
from datetime import UTC, datetime

import boto3
import pytest
from botocore.config import Config
from jsonschema import Draft202012Validator
from moto import mock_aws


@pytest.fixture
def cloud(monkeypatch):
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "ap-southeast-1",
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(key, value)
    with mock_aws():
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.create_table(
            TableName="runs",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": n, "AttributeType": "S"}
                for n in [
                    "pk",
                    "sk",
                    "history_pk",
                    "project_pk",
                    "history_sk",
                    "cleanup_pk",
                    "cleanup_sk",
                ]
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": name,
                    "KeySchema": [
                        {"AttributeName": pk, "KeyType": "HASH"},
                        {"AttributeName": sk, "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
                for name, pk, sk in [
                    ("HistoryIndex", "history_pk", "history_sk"),
                    ("ProjectHistoryIndex", "project_pk", "history_sk"),
                    ("CleanupIndex", "cleanup_pk", "cleanup_sk"),
                ]
            ],
        )
        s3 = boto3.client("s3", config=Config(signature_version="s3v4"))
        s3.create_bucket(
            Bucket="infralens-test-reports",
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-1"},
        )
        from infralens_backend.app import Application
        from infralens_backend.settings import Settings

        settings = Settings(
            table_name="runs",
            bucket="infralens-test-reports",
            issuer="https://cognito-idp.ap-southeast-1.amazonaws.com/pool",
            client_id="client",
            auth_domain="https://example.auth.ap-southeast-1.amazoncognito.com",
        )
        app = Application(settings, table, s3)
        app.now = lambda: datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
        yield app


@pytest.fixture
def api(cloud):
    def call(method, path, body=None, user="user-a", query=None):
        event = {
            "version": "2.0",
            "rawPath": path,
            "requestContext": {
                "requestId": "test-request",
                "http": {"method": method},
            },
            "headers": {"content-type": "application/json"},
            "queryStringParameters": query or {},
        }
        if user is not None:
            event["requestContext"]["authorizer"] = {
                "jwt": {
                    "claims": {
                        "sub": user,
                        "iss": cloud.settings.issuer,
                        "client_id": "client",
                        "token_use": "access",
                        "scope": "openid infralens/api",
                    }
                }
            }
        if body is not None:
            event["body"] = json.dumps(body)
        response = cloud.handle(event)
        data = json.loads(response["body"]) if response.get("body") else None
        from infralens_backend.contract import openapi

        spec = openapi()
        for pattern, methods in spec["paths"].items():
            if re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", pattern), path):
                operation = methods.get(method.lower())
                if operation:
                    contract_response = operation["responses"][
                        str(response["statusCode"])
                    ]
                    if data is not None:
                        schema = {
                            **contract_response["content"]["application/json"][
                                "schema"
                            ],
                            "components": spec["components"],
                        }
                        Draft202012Validator(schema).validate(data)
                break
        return response["statusCode"], data

    return call
