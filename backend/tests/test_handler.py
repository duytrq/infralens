from urllib.parse import urlsplit

import pytest

from infralens_backend import handler


@pytest.mark.parametrize("region", ["ap-southeast-1", "us-east-1"])
@pytest.mark.parametrize("operation", ["put_object", "get_object"])
def test_lambda_presigned_urls_target_bucket_region_without_redirect(
    monkeypatch, region, operation
):
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": region,
        "AWS_EC2_METADATA_DISABLED": "true",
        "TABLE_NAME": "runs",
        "REPORTS_BUCKET": "infralens-test-reports",
        "COGNITO_ISSUER": "https://issuer.example",
        "COGNITO_CLIENT_ID": "client",
        "COGNITO_DOMAIN": "https://auth.example",
    }.items():
        monkeypatch.setenv(key, value)
    handler.application.cache_clear()
    try:
        app = handler.application()
        url = app.s3.generate_presigned_url(
            operation,
            Params={"Bucket": app.settings.bucket, "Key": "report.json"},
            ExpiresIn=60,
        )
        assert urlsplit(url).hostname == (
            f"infralens-test-reports.s3.{region}.amazonaws.com"
        )
    finally:
        handler.application.cache_clear()
