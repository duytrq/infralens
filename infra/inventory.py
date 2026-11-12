"""Read stack resources and verify deployment tags; never mutate AWS resources.

Keep the JSON output before deleting stacks: retained resources remain billable.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

UNTAGGABLE = {
    "AWS::S3::BucketPolicy": "Owned by its bucket",
    "AWS::Lambda::Permission": "Owned by its Lambda function",
    "AWS::Cognito::UserPoolClient": "Owned by its user pool",
    "AWS::Cognito::UserPoolDomain": "Delete domain before deleting its user pool",
    "AWS::Cognito::UserPoolResourceServer": "Owned by its user pool",
    "AWS::CloudFront::OriginAccessControl": "Stack-managed origin access control",
    "AWS::CloudFront::CachePolicy": "Stack-managed cache policy",
    "AWS::CloudFront::ResponseHeadersPolicy": "Stack-managed response headers policy",
}


def tag_map(tags):
    if isinstance(tags, list):
        return {tag["Key"]: tag["Value"] for tag in tags}
    return tags


def resource_tags(session, kind, physical, account, region, api_id):
    def client(service):
        return session.client(service, config=Config(retries={"max_attempts": 3}))

    if kind == "AWS::S3::Bucket":
        try:
            return tag_map(client("s3").get_bucket_tagging(Bucket=physical)["TagSet"])
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchTagSet":
                return {}
            raise
    if kind == "AWS::Lambda::Function":
        arn = f"arn:aws:lambda:{region}:{account}:function:{physical}"
        return client("lambda").list_tags(Resource=arn)["Tags"]
    if kind == "AWS::Lambda::EventSourceMapping":
        arn = f"arn:aws:lambda:{region}:{account}:event-source-mapping:{physical}"
        return client("lambda").list_tags(Resource=arn)["Tags"]
    if kind == "AWS::DynamoDB::Table":
        arn = f"arn:aws:dynamodb:{region}:{account}:table/{physical}"
        return tag_map(
            client("dynamodb").list_tags_of_resource(ResourceArn=arn)["Tags"]
        )
    if kind == "AWS::IAM::Role":
        return tag_map(client("iam").list_role_tags(RoleName=physical)["Tags"])
    if kind == "AWS::Logs::LogGroup":
        arn = f"arn:aws:logs:{region}:{account}:log-group:{physical}"
        return client("logs").list_tags_for_resource(resourceArn=arn)["tags"]
    if kind == "AWS::Events::Rule":
        arn = f"arn:aws:events:{region}:{account}:rule/{physical}"
        return tag_map(client("events").list_tags_for_resource(ResourceARN=arn)["Tags"])
    if kind == "AWS::Cognito::UserPool":
        pool = client("cognito-idp").describe_user_pool(UserPoolId=physical)["UserPool"]
        return pool.get("UserPoolTags", {})
    if kind in {"AWS::CloudFront::Distribution", "AWS::CloudFront::Function"}:
        resource = "distribution" if kind.endswith("Distribution") else "function"
        arn = (
            physical
            if physical.startswith("arn:")
            else f"arn:aws:cloudfront::{account}:{resource}/{physical}"
        )
        return tag_map(
            client("cloudfront").list_tags_for_resource(Resource=arn)["Tags"]["Items"]
        )
    if kind == "AWS::ApiGatewayV2::Api":
        arn = f"arn:aws:apigateway:{region}::/apis/{physical}"
        return client("apigatewayv2").get_tags(ResourceArn=arn).get("Tags", {})
    if kind == "AWS::ApiGatewayV2::Stage":
        arn = f"arn:aws:apigateway:{region}::/apis/{api_id}/stages/$default"
        return client("apigatewayv2").get_tags(ResourceArn=arn).get("Tags", {})
    raise ValueError(f"Add an explicit tagging check for resource type {kind}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--deployment", default="infralens-dev")
    parser.add_argument("--environment", choices=["dev", "prod"], default="dev")
    parser.add_argument("--stack", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    if account != args.account:
        raise SystemExit("AWS account does not match the expected account.")
    expected = {
        "Project": "infralens",
        "Environment": args.environment,
        "ManagedBy": "cloudformation",
        "Deployment": args.deployment,
    }
    cfn = session.client("cloudformation")
    inventory = {
        "account": account,
        "region": args.region,
        "recorded_at": datetime.now(UTC).isoformat(),
        "tags": expected,
        "stacks": [],
    }
    failures = []
    checked = 0
    for name in args.stack:
        stack = cfn.describe_stacks(StackName=name)["Stacks"][0]
        if not all(tag_map(stack["Tags"]).get(k) == v for k, v in expected.items()):
            failures.append(name)
        resources = [
            resource
            for page in cfn.get_paginator("list_stack_resources").paginate(
                StackName=name
            )
            for resource in page["StackResourceSummaries"]
        ]
        api_id = next(
            (
                r["PhysicalResourceId"]
                for r in resources
                if r["ResourceType"] == "AWS::ApiGatewayV2::Api"
            ),
            None,
        )
        recorded = []
        for resource in resources:
            kind = resource["ResourceType"]
            row = {
                key: resource[key]
                for key in (
                    "LogicalResourceId",
                    "PhysicalResourceId",
                    "ResourceType",
                    "ResourceStatus",
                )
                if key in resource
            }
            if resource["ResourceStatus"] == "DELETE_COMPLETE":
                row["tagging"] = "deleted"
                row["cleanup_note"] = "Resource deleted during stack operation"
            elif kind in UNTAGGABLE:
                row["tagging"] = "unsupported"
                row["cleanup_note"] = UNTAGGABLE[kind]
            else:
                tags = resource_tags(
                    session,
                    kind,
                    resource["PhysicalResourceId"],
                    account,
                    args.region,
                    api_id,
                )
                row["tags"] = tags
                row["tagging"] = (
                    "verified"
                    if all(tags.get(k) == v for k, v in expected.items())
                    else "missing"
                )
                checked += 1
                if row["tagging"] == "missing":
                    failures.append(resource["LogicalResourceId"])
            recorded.append(row)
        inventory["stacks"].append(
            {
                "name": name,
                "id": stack["StackId"],
                "status": stack["StackStatus"],
                "outputs": stack.get("Outputs", []),
                "resources": recorded,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(args.stack)} stacks; checked tags on {checked} resources.")
    print(f"Inventory: {args.output}")
    if failures:
        raise SystemExit("Missing deployment tags: " + ", ".join(failures))


if __name__ == "__main__":
    main()
