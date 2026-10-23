import base64
import copy
import json

import pytest
from botocore.exceptions import ClientError


def event(cloud, body='{"name":"Demo"}'):
    return {
        "version": "2.0",
        "rawPath": "/v1/projects/demo",
        "requestContext": {
            "http": {"method": "PUT"},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-a",
                        "iss": cloud.settings.issuer,
                        "client_id": cloud.settings.client_id,
                        "token_use": "access",
                        "scope": "openid infralens/api",
                    }
                }
            },
        },
        "headers": {"content-type": "application/json"},
        "body": body,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("iss", "https://other-issuer"),
        ("client_id", "other-client"),
        ("token_use", "id"),
        ("scope", "openid"),
        ("scope", None),
        ("scope", ["infralens/api"]),
        ("sub", "../user-b"),
        ("sub", None),
    ],
)
def test_wrong_or_malformed_identity_claims_are_rejected(cloud, field, value):
    request = event(cloud)
    request["requestContext"]["authorizer"]["jwt"]["claims"][field] = value
    assert cloud.handle(request)["statusCode"] == 401


def test_bearer_header_does_not_bypass_gateway_authorization(cloud):
    request = event(cloud)
    request["requestContext"].pop("authorizer")
    request["headers"]["authorization"] = "Bearer attacker-controlled"
    assert cloud.handle(request)["statusCode"] == 401


@pytest.mark.parametrize(
    "body,status",
    [
        ('{"name":"Demo","name":"Other"}', 400),
        ('{"name":NaN}', 400),
        ("[]", 422),
        ('{"name":', 400),
        ('{"name":"' + "x" * 70000 + '"}', 413),
    ],
)
def test_json_parsing_is_bounded_and_unambiguous(cloud, body, status):
    assert cloud.handle(event(cloud, body))["statusCode"] == status


def test_base64_utf8_requests_and_response_security_headers(cloud):
    request = event(cloud)
    request["body"] = base64.b64encode('{"name":"Hạ tầng"}'.encode()).decode()
    request["isBase64Encoded"] = True
    response = cloud.handle(request)
    assert response["statusCode"] == 201
    assert json.loads(response["body"])["name"] == "Hạ tầng"
    assert response["headers"]["cache-control"] == "no-store"
    assert response["headers"]["x-content-type-options"] == "nosniff"
    request["body"] = "not base64"
    assert cloud.handle(request)["statusCode"] == 400
    request["body"] = base64.b64encode(b"\xff").decode()
    assert cloud.handle(request)["statusCode"] == 400


def test_wrong_content_type_is_rejected(cloud):
    request = event(cloud)
    request["headers"]["content-type"] = "text/plain"
    assert cloud.handle(request)["statusCode"] == 415


def test_dependency_errors_do_not_expose_payloads_or_internal_details(
    cloud, monkeypatch, caplog
):
    secret = "PRIVATE_REPORT_AND_CREDENTIALS"

    def fail(**kwargs):
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": secret}}, "PutItem"
        )

    monkeypatch.setattr(cloud.table, "put_item", fail)
    response = cloud.handle(event(cloud))
    assert response["statusCode"] == 503
    assert secret not in json.dumps(response) + caplog.text


def test_project_pagination_rejects_cursor_from_another_user(api):
    for project in ("a", "b"):
        assert api("PUT", f"/v1/projects/{project}", {"name": project})[0] == 201
    first = api("GET", "/v1/projects", query={"limit": "1"})[1]
    cursor = first["next_cursor"]
    assert first["items"][0]["project_id"] == "a"
    assert cursor
    second = api("GET", "/v1/projects", query={"cursor": cursor, "limit": "1"})[1]
    assert second["items"][0]["project_id"] == "b"
    assert api("GET", "/v1/projects", user="user-b", query={"cursor": cursor})[0] == 422
    forged = json.loads(base64.urlsafe_b64decode(cursor))
    forged["scope"]["owner"] = "user-b"
    forged_cursor = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode()
    assert (
        api("GET", "/v1/projects", user="user-b", query={"cursor": forged_cursor})[0]
        == 422
    )


def test_config_does_not_require_a_user_even_with_an_invalid_bearer(api):
    assert api("GET", "/v1/config", user=None)[0] == 200


def test_public_config_does_not_mutate_settings(cloud):
    first = cloud.settings.public()
    first["upload"]["formats"].append("sarif")
    assert copy.deepcopy(cloud.settings.public())["upload"]["formats"] == ["json"]
