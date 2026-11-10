"""API key lifecycle and request authorization."""

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta

from boto3.dynamodb.conditions import Key

from infralens_backend import validation as v
from infralens_backend.errors import ApiError, invalid, not_found
from infralens_backend.schemas import obj

KEY_PATTERN = re.compile(r"il_key_([a-f0-9]{32})_([A-Za-z0-9_-]{43})")
INPUT = obj(
    {
        "name": {"type": "string", "minLength": 1, "maxLength": 120},
        "expires_in_days": {"enum": [1, 3, 15, 30, None]},
    }
)


def create(table, owner, payload, now):
    name = payload["name"].strip()
    if not name or any(not char.isprintable() for char in name):
        raise invalid("Name must contain printable characters.")
    key_id = secrets.token_hex(16)
    secret = secrets.token_urlsafe(32)
    expires = (
        now + timedelta(days=payload["expires_in_days"])
        if payload["expires_in_days"]
        else None
    )
    metadata = {
        "key_id": key_id,
        "name": name,
        "created_at": v.iso(now),
        "expires_at": v.iso(expires) if expires else None,
    }
    lookup = {
        "pk": f"APIKEY#{key_id}",
        "sk": "KEY",
        "owner": owner,
        "secret_hash": hashlib.sha256(secret.encode("ascii")).hexdigest(),
        "expires_at": metadata["expires_at"],
    }
    listed = {"pk": f"USER#{owner}", "sk": f"APIKEY#{key_id}", "data": metadata}
    table.meta.client.transact_write_items(
        TransactItems=[
            {
                "Put": {
                    "TableName": table.name,
                    "Item": item,
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            }
            for item in (lookup, listed)
        ]
    )
    return {**metadata, "api_key": f"il_key_{key_id}_{secret}"}


def list_keys(table, owner, event):
    params = v.query(event, ["limit", "cursor"])
    scope = {"owner": owner, "type": "api_keys"}
    cursor = v.decode_cursor(
        params.get("cursor"), scope, {"pk": f"USER#{owner}", "sk": None}
    )
    if cursor and not cursor["sk"].startswith("APIKEY#"):
        raise invalid("Invalid API key cursor.")
    kwargs = {"ExclusiveStartKey": cursor} if cursor else {}
    page = table.query(
        KeyConditionExpression=Key("pk").eq(f"USER#{owner}")
        & Key("sk").begins_with("APIKEY#"),
        ConsistentRead=True,
        Limit=v.page_limit(params),
        **kwargs,
    )
    return {
        "items": [item["data"] for item in page.get("Items", [])],
        "next_cursor": v.encode_cursor(page.get("LastEvaluatedKey"), scope),
    }


def delete(table, owner, key_id):
    if not re.fullmatch(r"[a-f0-9]{32}", key_id):
        raise not_found()
    key = {"pk": f"USER#{owner}", "sk": f"APIKEY#{key_id}"}
    if not table.get_item(Key=key, ConsistentRead=True).get("Item"):
        raise not_found()
    table.meta.client.transact_write_items(
        TransactItems=[
            {
                "Delete": {
                    "TableName": table.name,
                    "Key": key,
                    "ConditionExpression": "attribute_exists(pk)",
                }
            },
            {
                "Delete": {
                    "TableName": table.name,
                    "Key": {"pk": f"APIKEY#{key_id}", "sk": "KEY"},
                    "ConditionExpression": "#owner = :owner",
                    "ExpressionAttributeNames": {"#owner": "owner"},
                    "ExpressionAttributeValues": {":owner": owner},
                }
            },
        ]
    )


def authenticate(table, credential, now=None):
    match = KEY_PATTERN.fullmatch(credential) if isinstance(credential, str) else None
    if not match:
        return None
    key_id, secret = match.groups()
    item = table.get_item(
        Key={"pk": f"APIKEY#{key_id}", "sk": "KEY"}, ConsistentRead=True
    ).get("Item")
    if not item:
        return None
    digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
    saved = item.get("secret_hash")
    owner = item.get("owner")
    if not isinstance(saved, str) or not hmac.compare_digest(digest, saved):
        return None
    if not isinstance(owner, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", owner):
        return None
    if "expires_at" not in item:
        return None
    expiry = item["expires_at"]
    if expiry is not None:
        try:
            if v.timestamp(expiry) <= (now or datetime.now(UTC)):
                return None
        except (ApiError, TypeError, ValueError):
            return None
    return owner


def owner_is_enabled(cognito, user_pool_id, owner):
    """Check live Cognito membership by immutable sub, without caching approval."""
    try:
        user = cognito.admin_get_user(UserPoolId=user_pool_id, Username=owner)
    except cognito.exceptions.UserNotFoundException:
        return False
    # Verify the sub as well: a recreated username must not inherit old keys.
    return user.get("Enabled") is True and any(
        attribute.get("Name") == "sub" and attribute.get("Value") == owner
        for attribute in user.get("UserAttributes", [])
    )
