"""IAM-operated account offboarding; data retention is separate from access removal."""

import re
from datetime import UTC, datetime

from boto3.dynamodb.conditions import Key

from infralens_backend import validation as v


def manage_user(table, cognito, pool, owner, action, *, apply=False):
    if action not in {"disable", "delete"} or not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", owner
    ):
        raise ValueError("Use disable/delete and the exact Cognito user sub UUID.")
    try:
        user = cognito.admin_get_user(UserPoolId=pool, Username=owner)
    except cognito.exceptions.UserNotFoundException:
        user = None
    if user and not any(
        a.get("Name") == "sub" and a.get("Value") == owner
        for a in user.get("UserAttributes", [])
    ):
        raise ValueError("Cognito identity does not match the requested sub.")
    result = {"owner": owner, "action": action, "apply": apply, "revoked": 0}
    if not apply:
        count, cursor = 0, None
        while True:
            page = table.query(
                KeyConditionExpression=Key("pk").eq(f"USER#{owner}")
                & Key("sk").begins_with("APIKEY#"),
                ConsistentRead=True,
                Select="COUNT",
                **({"ExclusiveStartKey": cursor} if cursor else {}),
            )
            count += page["Count"]
            cursor = page.get("LastEvaluatedKey")
            if not cursor:
                break
        result["keys_to_revoke"] = count
        result["cognito_user_exists"] = user is not None
        return result
    # Durable deny marker precedes all remote mutations. Old JWTs cannot create
    # replacement keys: key creation checks this marker in the same transaction.
    table.put_item(
        Item={
            "pk": f"USER#{owner}",
            "sk": "ACCESS",
            "action": action,
            "blocked_at": v.iso(datetime.now(UTC)),
        }
    )
    if user:
        cognito.admin_disable_user(UserPoolId=pool, Username=user["Username"])
    cursor = None
    while True:
        page = table.query(
            KeyConditionExpression=Key("pk").eq(f"USER#{owner}")
            & Key("sk").begins_with("APIKEY#"),
            ConsistentRead=True,
            Limit=100,
            **({"ExclusiveStartKey": cursor} if cursor else {}),
        )
        for row in page.get("Items", []):
            key_id = row["sk"].removeprefix("APIKEY#")
            if not re.fullmatch(r"[a-f0-9]{32}", key_id):
                raise ValueError("Invalid stored API key identifier; cleanup stopped.")
            table.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "Delete": {
                            "TableName": table.name,
                            "Key": {"pk": f"APIKEY#{key_id}", "sk": "KEY"},
                            "ConditionExpression": (
                                "attribute_not_exists(pk) OR #owner = :owner"
                            ),
                            "ExpressionAttributeNames": {"#owner": "owner"},
                            "ExpressionAttributeValues": {":owner": owner},
                        }
                    },
                    {
                        "Delete": {
                            "TableName": table.name,
                            "Key": {"pk": row["pk"], "sk": row["sk"]},
                        }
                    },
                ]
            )
            result["revoked"] += 1
        cursor = page.get("LastEvaluatedKey")
        if not cursor:
            break
    if action == "delete" and user:
        cognito.admin_delete_user(UserPoolId=pool, Username=user["Username"])
    return result
