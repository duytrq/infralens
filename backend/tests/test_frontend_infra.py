from pathlib import Path

from cfnlint.decode import decode

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_origin_is_private_and_restricted_to_its_distribution():
    template, errors = decode(str(ROOT / "infra/frontend.yaml"))
    assert not errors
    resources = template["Resources"]
    bucket = resources["FrontendBucket"]
    assert bucket["DeletionPolicy"] == "Retain"
    assert all(bucket["Properties"]["PublicAccessBlockConfiguration"].values())
    assert "WebsiteConfiguration" not in bucket["Properties"]
    policy = resources["FrontendBucketPolicy"]["Properties"]["PolicyDocument"]
    allow = next(s for s in policy["Statement"] if s["Effect"] == "Allow")
    assert allow["Principal"] == {"Service": "cloudfront.amazonaws.com"}
    assert allow["Action"] == "s3:GetObject"
    assert "AWS:SourceArn" in allow["Condition"]["StringEquals"]
    config = resources["Distribution"]["Properties"]["DistributionConfig"]
    origin = config["Origins"][0]
    assert origin["DomainName"] == {
        "Fn::GetAtt": ["FrontendBucket", "RegionalDomainName"]
    }
    assert origin["OriginAccessControlId"] == {"Ref": "OriginAccessControl"}
    assert config["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"
    assert not any("ResponseCode" in item for item in config["CustomErrorResponses"])


def test_frontend_cache_does_not_retain_html_or_forward_auth_parameters():
    template, errors = decode(str(ROOT / "infra/frontend.yaml"))
    assert not errors
    resources = template["Resources"]
    html = resources["HtmlCachePolicy"]["Properties"]["CachePolicyConfig"]
    assert [html[key] for key in ("MinTTL", "DefaultTTL", "MaxTTL")] == [0, 0, 0]
    for name in ("HtmlCachePolicy", "AssetCachePolicy"):
        cache = resources[name]["Properties"]["CachePolicyConfig"]
        forwarded = cache["ParametersInCacheKeyAndForwardedToOrigin"]
        assert forwarded["CookiesConfig"]["CookieBehavior"] == "none"
        assert forwarded["QueryStringsConfig"]["QueryStringBehavior"] == "none"
        assert forwarded["HeadersConfig"]["HeaderBehavior"] == "none"
    security = resources["ResponseHeaders"]["Properties"][
        "ResponseHeadersPolicyConfig"
    ]["SecurityHeadersConfig"]
    assert security["ReferrerPolicy"]["ReferrerPolicy"] == "no-referrer"
    assert "unsafe-inline" not in str(security["ContentSecurityPolicy"])
    assert "frame-ancestors 'none'" in str(security["ContentSecurityPolicy"])
