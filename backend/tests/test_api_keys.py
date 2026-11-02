from datetime import timedelta

import pytest

from infralens_backend import api_keys


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


def test_api_key_authorizer_handler(cloud, api, monkeypatch):
    from infralens_backend.handler import api_key_authorizer, api_key_table

    monkeypatch.setenv("TABLE_NAME", cloud.table.name)
    api_key_table.cache_clear()
    status, created = api(
        "POST", "/v1/api-keys", {"name": "CI", "expires_in_days": None}
    )
    assert status == 201
    event = {"headers": {"authorization": "Bearer " + created["api_key"]}}
    assert api_key_authorizer(event, None) == {
        "isAuthorized": True,
        "context": {"owner": "user-a", "auth_type": "api_key"},
    }
    assert api("DELETE", f"/v1/api-keys/{created['key_id']}")[0] == 204
    assert api_key_authorizer(event, None) == {"isAuthorized": False}


def test_invalid_key_requests(cloud, api):
    assert api("POST", "/v1/api-keys", {"name": "x", "expires_in_days": 2})[0] == 422
    assert api("POST", "/v1/api-keys", {"name": " ", "expires_in_days": None})[0] == 422
    assert api("GET", "/v1/api-keys", user=None)[0] == 401
