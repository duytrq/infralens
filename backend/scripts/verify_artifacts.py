"""Run with python -S to verify SAM artifacts without development site-packages."""

import json
import os
import subprocess
import sys
from pathlib import Path


def check(path):
    artifact = Path(path).resolve()
    assert (artifact / "infralens_backend/handler.py").is_file()
    for excluded in ("moto", "pytest", "infralens", "tests", ".venv"):
        assert not (artifact / excluded).exists(), excluded
    env = {
        **os.environ,
        "AWS_ACCESS_KEY_ID": "artifact-check",
        "AWS_SECRET_ACCESS_KEY": "artifact-check",
        "AWS_SESSION_TOKEN": "artifact-check",
        "AWS_DEFAULT_REGION": "ap-southeast-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "TABLE_NAME": "artifact-check",
        "REPORTS_BUCKET": "artifact-check",
        "COGNITO_ISSUER": "https://cognito-idp.ap-southeast-1.amazonaws.com/example",
        "DASHBOARD_CLIENT_ID": "example",
        "COGNITO_DOMAIN": "https://example.auth.ap-southeast-1.amazoncognito.com",
    }
    if artifact.name == "ApiKeyAuthorizerFunction":
        code = """
import copy, hashlib, sys
sys.path.insert(0, sys.argv[1])
from botocore.stub import Stubber
from infralens_backend import handler

table = handler.api_key_table()
key_id, secret, owner = 'a' * 32, 'b' * 43, 'artifact-owner'
event = {'headers': {'authorization': f'Bearer il_key_{key_id}_{secret}'}}
item = {
    'owner': {'S': owner},
    'secret_hash': {'S': hashlib.sha256(secret.encode()).hexdigest()},
    'expires_at': {'NULL': True},
}
with Stubber(table.meta.client) as database:
    for enabled in (True, False):
        database.add_response('get_item', {'Item': copy.deepcopy(item)})
        database.add_response('get_item', {} if enabled else {
            'Item': {'pk': {'S': f'USER#{owner}'}, 'sk': {'S': 'ACCESS'}}
        })
        result = handler.api_key_authorizer(event, None)
        assert result['isAuthorized'] is enabled
        if enabled:
            assert result['context']['owner'] == owner
    database.assert_no_pending_responses()
"""
    else:
        code = """
import json,sys
sys.path.insert(0, sys.argv[1])
from infralens_backend.handler import api_handler
event = {'rawPath':'/v1/dashboard-config','requestContext':{'http':{'method':'GET'}}}
result = api_handler(event, None)
assert result['statusCode'] == 200
assert json.loads(result['body'])['upload']['formats'] == ['json']
event['rawPath'] = '/v1/projects'
assert api_handler(event, None)['statusCode'] == 401
"""
    subprocess.run(
        [sys.executable, "-S", "-c", code, str(artifact)], env=env, check=True
    )
    print(json.dumps({"artifact": artifact.name, "verified": True}))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Pass one or more SAM artifact directories.")
    for argument in sys.argv[1:]:
        check(argument)
