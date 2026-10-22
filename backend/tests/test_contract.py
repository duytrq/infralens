import json
from pathlib import Path

from cfnlint.decode import decode
from openapi_spec_validator import validate as validate_openapi

from infralens_backend.contract import openapi

ROOT = Path(__file__).resolve().parents[2]


def test_exported_contract_is_valid_and_current():
    contract = openapi()
    validate_openapi(contract)
    assert json.loads((ROOT / "contracts/openapi.json").read_text()) == contract


def test_all_contract_routes_are_deployed_and_only_config_is_public():
    template, errors = decode(str(ROOT / "infra/template.yaml"))
    assert not errors
    api = template["Resources"]["HttpApi"]["Properties"]
    auth = api["Auth"]
    assert auth["DefaultAuthorizer"] == "CognitoJwt"
    assert auth["Authorizers"]["CognitoJwt"]["AuthorizationScopes"] == ["infralens/api"]
    events = template["Resources"]["ApiFunction"]["Properties"]["Events"]
    deployed = {}
    for event in events.values():
        props = event["Properties"]
        deployed[(props["Method"].lower(), props["Path"])] = props
    documented = {
        (method, path)
        for path, methods in openapi()["paths"].items()
        for method in methods
        if method != "parameters"
    }
    assert set(deployed) == documented
    for (method, path), props in deployed.items():
        assert (props.get("Auth", {}).get("Authorizer") == "NONE") == (
            method == "get" and path in ("/v1/config", "/v1/dashboard-config")
        )


def test_storage_retention_and_upload_integrity_are_enforced_in_infrastructure():
    template, errors = decode(str(ROOT / "infra/template.yaml"))
    assert not errors
    resources = template["Resources"]
    for name in ("ReportsBucket", "StorageTable", "UserPool"):
        assert resources[name]["DeletionPolicy"] == "Retain"
        assert resources[name]["UpdateReplacePolicy"] == "Retain"
    bucket = resources["ReportsBucket"]["Properties"]
    assert all(bucket["PublicAccessBlockConfiguration"].values())
    lifecycle = bucket["LifecycleConfiguration"]["Rules"]
    assert any(
        r.get("TagFilters") == [{"Key": "state", "Value": "pending"}]
        and r["ExpirationInDays"] == 7
        for r in lifecycle
    )
    assert not any(
        r.get("TagFilters") == [{"Key": "state", "Value": "ready"}] for r in lifecycle
    )
    policy = resources["ReportsPolicy"]["Properties"]["PolicyDocument"]["Statement"]
    assert any(
        r.get("Condition", {}).get("StringNotEquals") == {"s3:if-none-match": "*"}
        and r["Effect"] == "Deny"
        for r in policy
    )
    assert "TimeToLiveSpecification" not in resources["StorageTable"]["Properties"]
    client = resources["CliClient"]["Properties"]
    assert client["AllowedOAuthFlows"] == ["code"]
    assert client["GenerateSecret"] is False
