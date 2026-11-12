"""Disable/delete an InfraLens member through AWS IAM; dry-run by default."""

import argparse
import json

import boto3
from botocore.config import Config

from infralens_backend.user_admin import manage_user


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["disable", "delete"])
    parser.add_argument("--account", required=True)
    parser.add_argument("--user-sub", required=True)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--stack", default="infralens-dev")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    config = Config(
        connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 3}
    )
    if (
        session.client("sts", config=config).get_caller_identity()["Account"]
        != args.account
    ):
        raise SystemExit("AWS account does not match the expected account.")
    stack = session.client("cloudformation", config=config).describe_stacks(
        StackName=args.stack
    )["Stacks"][0]
    tags = {t["Key"]: t["Value"] for t in stack.get("Tags", [])}
    if tags.get("Project") != "infralens" or tags.get("Deployment") != args.stack:
        raise SystemExit("Stack is not an identified InfraLens deployment.")
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
    result = manage_user(
        session.resource("dynamodb", config=config).Table(outputs["StorageTable"]),
        session.client("cognito-idp", config=config),
        outputs["UserPoolId"],
        args.user_sub,
        args.action,
        apply=args.apply,
    )
    print(
        json.dumps(
            {
                **result,
                "account": args.account,
                "stack": args.stack,
                "report_data": "retained",
            }
        )
    )


if __name__ == "__main__":
    main()
