"""Check SAM's rendered CloudFormation offline using the pinned SAM tool environment.

No AWS client is created. Local CodeUri values are replaced with illustrative S3
locations, and the AWS-managed execution policy map is supplied without IAM calls.
"""

import copy
import json
import os
from pathlib import Path
from unittest.mock import patch

from samtranslator.translator.transform import transform
from samtranslator.yaml_helper import yaml_parse

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "put", "post", "delete"}


class StaticPolicies:
    def load(self):
        return {
            "AWSLambdaBasicExecutionRole": (
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
            )
        }


def verify(environment, reserve):
    template = yaml_parse((ROOT / "infra/template.yaml").read_text(encoding="utf-8"))
    for resource in template["Resources"].values():
        if resource["Type"] == "AWS::Serverless::Function":
            resource["Properties"]["CodeUri"] = {
                "Bucket": "offline-artifact-bucket",
                "Key": "function.zip",
            }
    rendered = transform(
        copy.deepcopy(template),
        {
            "Environment": environment,
            "CallbackUrl": "http://localhost:8765/callback",
            "ReserveConcurrency": reserve,
        },
        StaticPolicies(),
    )
    resources = rendered["Resources"]
    expected_tags = {
        "Project": "infralens",
        "Environment": {"Ref": "Environment"},
        "ManagedBy": "cloudformation",
        "Deployment": {"Ref": "AWS::StackName"},
    }
    tagged_types = {
        "AWS::Lambda::Function",
        "AWS::IAM::Role",
        "AWS::Logs::LogGroup",
        "AWS::S3::Bucket",
        "AWS::DynamoDB::Table",
        "AWS::Events::Rule",
        "AWS::Cognito::UserPool",
        "AWS::ApiGatewayV2::Stage",
        "AWS::Lambda::EventSourceMapping",
    }
    for name, resource in resources.items():
        if resource["Type"] in tagged_types:
            props = resource["Properties"]
            tags = props.get("Tags", props.get("UserPoolTags"))
            if isinstance(tags, list):
                tags = {tag["Key"]: tag["Value"] for tag in tags}
            assert tags is not None, name
            assert all(tags.get(k) == v for k, v in expected_tags.items()), name
    body = resources["HttpApi"]["Properties"]["Body"]
    api_tags = {
        tag["name"]: tag["x-amazon-apigateway-tag-value"] for tag in body["tags"]
    }
    assert all(api_tags.get(k) == v for k, v in expected_tags.items())
    contract = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))
    expected = {
        (method, path)
        for path, methods in contract["paths"].items()
        for method in methods
        if method in METHODS
    }
    routes = {
        (method, path): operation
        for path, methods in body["paths"].items()
        for method, operation in methods.items()
        if method in METHODS
    }
    assert set(routes) == expected
    for (method, path), operation in routes.items():
        expected_security = (
            [{"NONE": []}]
            if method == "get" and path in ("/v1/config", "/v1/dashboard-config")
            else [{"CognitoJwt": ["infralens/api"]}]
        )
        assert operation["security"] == expected_security, (method, path)
        assert (
            operation["x-amazon-apigateway-integration"]["payloadFormatVersion"]
            == "2.0"
        )
    jwt = body["components"]["securitySchemes"]["CognitoJwt"][
        "x-amazon-apigateway-authorizer"
    ]
    assert jwt["type"] == "jwt"
    assert jwt["jwtConfiguration"]["audience"] == [
        {"Ref": "CliClient"},
        {"Ref": "DashboardClient"},
    ]
    for name, log_group in (
        ("ApiFunction", "ApiLogGroup"),
        ("CleanupFunction", "CleanupLogGroup"),
    ):
        props = resources[name]["Properties"]
        logging = props["LoggingConfig"]
        assert logging["LogGroup"] == {"Ref": log_group}
        assert logging["LogFormat"] == "JSON"
        assert logging["ApplicationLogLevel"] == "INFO"
        assert props["Environment"]["Variables"]["COGNITO_CLIENT_ID"] == {
            "Ref": "CliClient"
        }
        assert "VpcConfig" not in props
        assert "ProvisionedConcurrencyConfig" not in props
        reserved = 10 if name == "ApiFunction" else 1
        assert props["ReservedConcurrentExecutions"] == {
            "Fn::If": ["UseReservedConcurrency", reserved, {"Ref": "AWS::NoValue"}]
        }
    assert rendered["Conditions"]["UseReservedConcurrency"] == {
        "Fn::Equals": [{"Ref": "ReserveConcurrency"}, "true"]
    }
    assert not any(r["Type"] == "AWS::Lambda::Url" for r in resources.values())
    assert resources["StorageTable"]["Properties"]["StreamSpecification"] == {
        "StreamViewType": "NEW_IMAGE"
    }
    worker = resources["AnalysisFunction"]["Properties"]
    assert worker["Timeout"] == 600
    assert worker["LoggingConfig"]["LogGroup"] == {"Ref": "AnalysisLogGroup"}
    mapping = resources["AnalysisStream"]["Properties"]
    assert mapping["BatchSize"] == 1 and mapping["MaximumRetryAttempts"] == 3
    assert mapping["MaximumRecordAgeInSeconds"] == 900
    assert "DestinationConfig" not in mapping
    assert not any(r["Type"] == "AWS::SQS::Queue" for r in resources.values())
    pattern = json.loads(mapping["FilterCriteria"]["Filters"][0]["Pattern"])
    assert pattern["dynamodb"]["NewImage"]["data"]["M"]["analysis"]["M"]["status"][
        "S"
    ] == ["pending"]
    origins = resources["HttpApi"]["Properties"]["Body"]["x-amazon-apigateway-cors"][
        "allowOrigins"
    ]
    assert origins[0] == "http://localhost:5173"
    assert origins[1] == {
        "Fn::If": [
            "UseLocalDashboard",
            "http://localhost:5173",
            {"Ref": "AWS::NoValue"},
        ]
    }
    assert rendered["Conditions"]["UseLocalDashboard"]["Fn::And"][:2] == [
        {"Fn::Equals": [{"Ref": "Environment"}, "dev"]},
        {"Fn::Equals": [{"Ref": "EnableLocalDashboard"}, "true"]},
    ]
    print(
        json.dumps(
            {
                "environment": environment,
                "rendered_routes": len(routes),
                "jwt_scopes": "verified",
                "logging_and_environment": "verified",
                "resource_tags": "verified",
                "reserve_concurrency": reserve,
            }
        )
    )


if __name__ == "__main__":
    os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-1")
    with patch(
        "boto3.session.Session.client",
        side_effect=AssertionError("AWS calls forbidden"),
    ):
        for stage, reserve in (("dev", "false"), ("prod", "true")):
            verify(stage, reserve)
