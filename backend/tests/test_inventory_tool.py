import importlib.util
from pathlib import Path
from types import SimpleNamespace

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber


@pytest.mark.parametrize("code", ["NoSuchTagSet", "AccessDenied"])
def test_inventory_records_absent_bucket_tags_without_hiding_permission_errors(code):
    path = Path(__file__).resolve().parents[2] / "infra/inventory.py"
    spec = importlib.util.spec_from_file_location("inventory_tool", path)
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    s3 = boto3.client(
        "s3",
        region_name="ap-southeast-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    session = SimpleNamespace(client=lambda service, **kwargs: s3)
    with Stubber(s3) as stub:
        stub.add_client_error(
            "get_bucket_tagging",
            service_error_code=code,
            http_status_code=404 if code == "NoSuchTagSet" else 403,
            expected_params={"Bucket": "untagged-bucket"},
        )
        args = (session, "AWS::S3::Bucket", "untagged-bucket", "123", "region", None)
        if code == "NoSuchTagSet":
            assert inventory.resource_tags(*args) == {}
        else:
            with pytest.raises(ClientError) as error:
                inventory.resource_tags(*args)
            assert error.value.response["Error"]["Code"] == "AccessDenied"
