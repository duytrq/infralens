def test_config_is_public_and_contains_no_storage_identifiers(api):
    status, data = api("GET", "/v1/config", user=None)
    assert status == 200
    assert data["schema_version"] == 1
    assert data["upload"]["formats"] == ["json"]
    assert "bucket" not in str(data)
    assert "table" not in str(data)


def test_projects_are_private_and_creation_is_idempotent(api):
    status, project = api("PUT", "/v1/projects/my-infra", {"name": "My infra"})
    assert status == 201
    assert project["project_id"] == "my-infra"
    status, same = api("PUT", "/v1/projects/my-infra", {"name": "My infra"})
    assert status == 200
    assert same == project
    assert api("GET", "/v1/projects/my-infra", user="user-b")[0] == 404
    assert api("GET", "/v1/projects", user="user-b")[1]["items"] == []
    assert api("GET", "/v1/projects")[1]["items"] == [project]
    assert api("PUT", "/v1/projects/my-infra", {"name": "Changed"})[0] == 409


def test_projects_require_validated_access_token_claims(api):
    assert api("GET", "/v1/projects", user=None)[0] == 401


def test_project_input_is_bounded_and_rejects_owner_injection(api):
    assert api("PUT", "/v1/projects/demo", {"name": "Demo", "owner_id": "b"})[0] == 422
    assert api("PUT", "/v1/projects/bad%23id", {"name": "Demo"})[0] == 422
    assert api("PUT", "/v1/projects/demo", {"name": " "})[0] == 422
