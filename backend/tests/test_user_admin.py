from datetime import UTC, datetime
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError

from infralens_backend import api_keys, handler
from infralens_backend.user_admin import manage_user


@pytest.fixture
def member(cloud, monkeypatch):
    cognito = boto3.client("cognito-idp")
    pool = cognito.create_user_pool(
        PoolName="operator-users", UsernameAttributes=["email"]
    )["UserPool"]["Id"]
    user = cognito.admin_create_user(
        UserPoolId=pool, Username="member@example.com", MessageAction="SUPPRESS"
    )["User"]
    owner = next(a["Value"] for a in user["Attributes"] if a["Name"] == "sub")
    monkeypatch.setattr(handler, "api_key_table", lambda: cloud.table)
    return cognito, pool, owner


@pytest.mark.parametrize("action", ["disable", "delete"])
def test_admin_blocks_old_keys_sessions_and_future_keys(cloud, api, member, action):
    cognito, pool, owner = member
    keys = [
        api_keys.create(
            cloud.table,
            owner,
            {"name": str(i), "expires_in_days": None},
            datetime.now(UTC),
        )
        for i in range(3)
    ]
    other = api_keys.create(
        cloud.table,
        "other-user",
        {"name": "other", "expires_in_days": None},
        datetime.now(UTC),
    )
    preview = manage_user(cloud.table, cognito, pool, owner, action)
    assert preview["revoked"] == 0 and preview["keys_to_revoke"] == 3
    assert preview["cognito_user_exists"]
    assert api_keys.authenticate(cloud.table, keys[0]["api_key"]) == owner
    result = manage_user(cloud.table, cognito, pool, owner, action, apply=True)
    assert result["revoked"] == 3
    if action == "delete":
        with pytest.raises(cognito.exceptions.UserNotFoundException):
            cognito.admin_get_user(UserPoolId=pool, Username=owner)
    else:
        assert not cognito.admin_get_user(UserPoolId=pool, Username=owner)["Enabled"]
    assert all(api_keys.authenticate(cloud.table, k["api_key"]) is None for k in keys)
    assert api_keys.authenticate(cloud.table, other["api_key"]) == "other-user"
    assert api("GET", "/v1/projects", user=owner)[0] == 403
    assert (
        api(
            "POST", "/v1/api-keys", {"name": "new", "expires_in_days": None}, user=owner
        )[0]
        == 403
    )
    with pytest.raises(ClientError):
        api_keys.create(
            cloud.table,
            owner,
            {"name": "racing", "expires_in_days": None},
            datetime.now(UTC),
        )
    assert (
        manage_user(cloud.table, cognito, pool, owner, action, apply=True)["revoked"]
        == 0
    )


def test_revocation_reads_all_pages_and_preserves_history(cloud, member):
    cognito, pool, owner = member
    with cloud.table.batch_writer() as batch:
        for i in range(103):
            key_id = f"{i:032x}"
            batch.put_item(Item={"pk": f"USER#{owner}", "sk": f"APIKEY#{key_id}"})
            batch.put_item(Item={"pk": f"APIKEY#{key_id}", "sk": "KEY", "owner": owner})
        batch.put_item(Item={"pk": f"USER#{owner}", "sk": "PROJECT#retained"})
    assert (
        manage_user(cloud.table, cognito, pool, owner, "delete", apply=True)["revoked"]
        == 103
    )
    assert cloud.table.get_item(
        Key={"pk": f"USER#{owner}", "sk": "PROJECT#retained"}
    ).get("Item")


def test_no_cognito_calls_during_authorization(cloud, member, monkeypatch):
    _, _, owner = member
    key = api_keys.create(
        cloud.table, owner, {"name": "CI", "expires_in_days": None}, datetime.now(UTC)
    )

    def unexpected(*args, **kwargs):
        pytest.fail("Authorization must not call Cognito")

    monkeypatch.setattr(boto3, "client", unexpected)
    monkeypatch.delenv("COGNITO_USER_POOL_ID", raising=False)
    assert handler.api_key_authorizer(
        {"headers": {"authorization": "Bearer " + key["api_key"]}}, None
    )["isAuthorized"]


def test_block_is_effective_even_if_cognito_disable_fails(cloud, member, monkeypatch):
    cognito, pool, owner = member
    key = api_keys.create(
        cloud.table, owner, {"name": "CI", "expires_in_days": None}, datetime.now(UTC)
    )

    def fail(**kwargs):
        raise ClientError(
            {"Error": {"Code": "InternalErrorException"}}, "AdminDisableUser"
        )

    monkeypatch.setattr(cognito, "admin_disable_user", fail)
    with pytest.raises(ClientError):
        manage_user(cloud.table, cognito, pool, owner, "delete", apply=True)
    assert api_keys.authenticate(cloud.table, key["api_key"]) is None


def test_wrong_identity_is_not_modified(cloud, member, monkeypatch):
    cognito, pool, owner = member
    monkeypatch.setattr(
        cognito,
        "admin_get_user",
        lambda **kw: {
            "Username": "someone",
            "UserAttributes": [{"Name": "sub", "Value": str(uuid4())}],
        },
    )
    with pytest.raises(ValueError, match="identity"):
        manage_user(cloud.table, cognito, pool, owner, "delete", apply=True)
    assert not cloud.table.get_item(Key={"pk": f"USER#{owner}", "sk": "ACCESS"}).get(
        "Item"
    )
