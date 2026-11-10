from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.stub import Stubber

from infralens_backend import api_keys, handler


@pytest.fixture
def authorizer(cloud, monkeypatch):
    cognito = boto3.client("cognito-idp")
    pool = cognito.create_user_pool(
        PoolName="api-key-owners", UsernameAttributes=["email"]
    )["UserPool"]["Id"]
    username = "owner@example.com"
    user = cognito.admin_create_user(
        UserPoolId=pool, Username=username, MessageAction="SUPPRESS"
    )["User"]
    owner = next(a["Value"] for a in user["Attributes"] if a["Name"] == "sub")
    cloud.now = lambda: datetime.now(UTC)
    monkeypatch.setenv("COGNITO_USER_POOL_ID", pool)
    monkeypatch.setattr(handler, "api_key_table", lambda: cloud.table)
    monkeypatch.setattr(handler, "api_key_cognito", lambda: cognito)

    def call(key):
        return handler.api_key_authorizer(
            {"headers": {"authorization": "Bearer " + key}}, None
        )

    return SimpleNamespace(
        cognito=cognito, pool=pool, username=username, owner=owner, call=call
    )


@pytest.mark.parametrize("days", [1, 3, 15, 30, None])
def test_key_lifecycle_and_immediate_revocation(cloud, api, days):
    status, created = api(
        "POST", "/v1/api-keys", {"name": "My key", "expires_in_days": days}
    )
    assert status == 201
    secret = created.pop("api_key")
    stored = cloud.table.get_item(
        Key={"pk": f"APIKEY#{created['key_id']}", "sk": "KEY"},
        ConsistentRead=True,
    )["Item"]
    assert secret not in str(stored)
    assert api_keys.authenticate(cloud.table, secret, cloud.now()) == "user-a"
    if days:
        assert (
            api_keys.authenticate(
                cloud.table, secret, cloud.now() + timedelta(days=days)
            )
            is None
        )
    status, page = api("GET", "/v1/api-keys")
    assert status == 200 and page["items"] == [created]
    assert secret not in str(page)
    assert api("DELETE", f"/v1/api-keys/{created['key_id']}", user="user-b")[0] == 404
    assert api_keys.authenticate(cloud.table, secret + "x", cloud.now()) is None
    altered = secret[:-1] + ("A" if secret[-1] != "A" else "B")
    assert api_keys.authenticate(cloud.table, altered, cloud.now()) is None
    assert api("DELETE", f"/v1/api-keys/{created['key_id']}")[0] == 204
    assert api_keys.authenticate(cloud.table, secret, cloud.now()) is None


def test_api_key_context_only_accepted_on_cli_routes(cloud, api):
    assert api("PUT", "/v1/projects/demo", {"name": "Demo"})[0] == 201
    event = {
        "rawPath": "/v1/cli/projects",
        "requestContext": {
            "http": {"method": "GET"},
            "authorizer": {"lambda": {"owner": "user-a", "auth_type": "api_key"}},
        },
        "queryStringParameters": {},
    }
    response = cloud.handle(event)
    assert response["statusCode"] == 200
    assert "demo" in response["body"]
    event["rawPath"] = "/v1/projects"
    assert cloud.handle(event)["statusCode"] == 401
    event["rawPath"] = "/v1/cli/api-keys"
    assert cloud.handle(event)["statusCode"] == 404
    event["rawPath"] = "/v1/cli/projects"
    event["requestContext"]["authorizer"]["lambda"]["owner"] = "user-b"
    assert "demo" not in cloud.handle(event)["body"]


def test_api_key_authorizer_handler(api, authorizer):
    status, created = api(
        "POST",
        "/v1/api-keys",
        {"name": "CI", "expires_in_days": None},
        user=authorizer.owner,
    )
    assert status == 201
    assert authorizer.call(created["api_key"]) == {
        "isAuthorized": True,
        "context": {"owner": authorizer.owner, "auth_type": "api_key"},
    }
    assert (
        api("DELETE", f"/v1/api-keys/{created['key_id']}", user=authorizer.owner)[0]
        == 204
    )
    assert authorizer.call(created["api_key"]) == {"isAuthorized": False}


@pytest.mark.parametrize("days", [1, None])
def test_disabling_owner_blocks_every_key_without_cached_approval(
    api, authorizer, days
):
    keys = [
        api(
            "POST",
            "/v1/api-keys",
            {"name": name, "expires_in_days": days},
            user=authorizer.owner,
        )[1]["api_key"]
        for name in ("CLI", "CI")
    ]
    assert all(authorizer.call(key)["isAuthorized"] for key in keys)
    authorizer.cognito.admin_disable_user(
        UserPoolId=authorizer.pool, Username=authorizer.username
    )
    assert all(authorizer.call(key) == {"isAuthorized": False} for key in keys)
    authorizer.cognito.admin_enable_user(
        UserPoolId=authorizer.pool, Username=authorizer.username
    )
    assert all(authorizer.call(key)["isAuthorized"] for key in keys)


def test_deleted_and_recreated_owner_cannot_reuse_old_key(api, authorizer):
    key = api(
        "POST",
        "/v1/api-keys",
        {"name": "CI", "expires_in_days": None},
        user=authorizer.owner,
    )[1]["api_key"]
    assert authorizer.call(key)["isAuthorized"]
    authorizer.cognito.admin_delete_user(
        UserPoolId=authorizer.pool, Username=authorizer.username
    )
    assert authorizer.call(key) == {"isAuthorized": False}
    replacement = authorizer.cognito.admin_create_user(
        UserPoolId=authorizer.pool,
        Username=authorizer.username,
        MessageAction="SUPPRESS",
    )["User"]
    new_owner = next(
        a["Value"] for a in replacement["Attributes"] if a["Name"] == "sub"
    )
    assert new_owner != authorizer.owner
    assert authorizer.call(key) == {"isAuthorized": False}
    new_key = api(
        "POST",
        "/v1/api-keys",
        {"name": "New CI", "expires_in_days": None},
        user=new_owner,
    )[1]["api_key"]
    assert authorizer.call(new_key)["context"]["owner"] == new_owner


@pytest.mark.parametrize(
    "response",
    [
        {"Enabled": False},
        {"Enabled": True},
        {"Enabled": True, "UserAttributes": [{"Name": "sub", "Value": "another-user"}]},
    ],
)
def test_owner_lookup_requires_enabled_user_and_matching_sub(api, authorizer, response):
    key = api(
        "POST",
        "/v1/api-keys",
        {"name": "CI", "expires_in_days": None},
        user=authorizer.owner,
    )[1]["api_key"]
    with Stubber(authorizer.cognito) as stub:
        stub.add_response(
            "admin_get_user",
            {"Username": authorizer.username, **response},
            {"UserPoolId": authorizer.pool, "Username": authorizer.owner},
        )
        assert authorizer.call(key) == {"isAuthorized": False}
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("reason", ["malformed", "wrong_secret", "expired", "revoked"])
def test_invalid_keys_do_not_query_cognito(cloud, api, authorizer, monkeypatch, reason):
    if reason == "expired":
        cloud.now = lambda: datetime.now(UTC) - timedelta(days=2)
    created = api(
        "POST",
        "/v1/api-keys",
        {"name": "CI", "expires_in_days": 1},
        user=authorizer.owner,
    )[1]
    key = created["api_key"]
    if reason == "malformed":
        key = "not-an-api-key"
    elif reason == "wrong_secret":
        key = key[:-1] + ("A" if key[-1] != "A" else "B")
    elif reason == "revoked":
        api("DELETE", f"/v1/api-keys/{created['key_id']}", user=authorizer.owner)

    def unexpected_lookup(**kwargs):
        pytest.fail("Invalid API keys must not trigger Cognito lookups")

    monkeypatch.setattr(authorizer.cognito, "admin_get_user", unexpected_lookup)
    assert authorizer.call(key) == {"isAuthorized": False}


@pytest.mark.parametrize(
    "error",
    ["TooManyRequestsException", "InternalErrorException", "AccessDeniedException"],
)
def test_cognito_service_errors_fail_closed_without_logging_secrets(
    api, authorizer, caplog, error
):
    key = api(
        "POST",
        "/v1/api-keys",
        {"name": "CI", "expires_in_days": None},
        user=authorizer.owner,
    )[1]["api_key"]
    with Stubber(authorizer.cognito) as stub:
        stub.add_client_error(
            "admin_get_user",
            service_error_code=error,
            service_message="private Cognito response",
            expected_params={
                "UserPoolId": authorizer.pool,
                "Username": authorizer.owner,
            },
        )
        with pytest.raises(RuntimeError, match="API key verification is unavailable"):
            authorizer.call(key)
        stub.assert_no_pending_responses()
    assert "api_key_authorization_dependency_failed" in caplog.text
    assert key not in caplog.text
    assert authorizer.owner not in caplog.text
    assert "private Cognito response" not in caplog.text


def test_cognito_network_error_fails_closed(api, authorizer, monkeypatch):
    key = api(
        "POST",
        "/v1/api-keys",
        {"name": "CI", "expires_in_days": None},
        user=authorizer.owner,
    )[1]["api_key"]

    def unavailable(**kwargs):
        raise EndpointConnectionError(endpoint_url="https://cognito.example")

    monkeypatch.setattr(authorizer.cognito, "admin_get_user", unavailable)
    with pytest.raises(RuntimeError, match="API key verification is unavailable"):
        authorizer.call(key)


def test_dynamodb_error_does_not_grant_access(cloud, api, authorizer, monkeypatch):
    key = api(
        "POST",
        "/v1/api-keys",
        {"name": "CI", "expires_in_days": None},
        user=authorizer.owner,
    )[1]["api_key"]

    def unavailable(**kwargs):
        raise ClientError({"Error": {"Code": "InternalServerError"}}, "GetItem")

    monkeypatch.setattr(cloud.table, "get_item", unavailable)
    with pytest.raises(RuntimeError, match="API key verification is unavailable"):
        authorizer.call(key)


def test_invalid_key_requests(cloud, api):
    assert api("POST", "/v1/api-keys", {"name": "x", "expires_in_days": 2})[0] == 422
    assert api("POST", "/v1/api-keys", {"name": " ", "expires_in_days": None})[0] == 422
    assert api("GET", "/v1/api-keys", user=None)[0] == 401
