"""Deployment configuration. No user AWS credentials are accepted."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    table_name: str
    bucket: str
    issuer: str
    client_id: str
    auth_domain: str
    callback_url: str = "http://localhost:8765/callback"
    scope: str = "infralens/api"
    upload_seconds: int = 900
    download_seconds: int = 300
    pending_seconds: int = 7 * 24 * 3600
    max_report_bytes: int = 50 * 1024 * 1024

    @classmethod
    def from_env(cls):
        return cls(
            table_name=os.environ["TABLE_NAME"],
            bucket=os.environ["REPORTS_BUCKET"],
            issuer=os.environ["COGNITO_ISSUER"],
            client_id=os.environ["COGNITO_CLIENT_ID"],
            auth_domain=os.environ["COGNITO_DOMAIN"],
            callback_url=os.environ.get("CALLBACK_URL", cls.callback_url),
        )

    def public(self):
        return {
            "schema_version": 1,
            "api_version": "v1",
            "auth": {
                "issuer": self.issuer,
                "client_id": self.client_id,
                "authorization_endpoint": f"{self.auth_domain}/oauth2/authorize",
                "token_endpoint": f"{self.auth_domain}/oauth2/token",
                "revocation_endpoint": f"{self.auth_domain}/oauth2/revoke",
                "callback_url": self.callback_url,
                "scopes": ["openid", self.scope],
                "pkce_method": "S256",
            },
            "upload": {
                "formats": ["json"],
                "max_report_bytes": self.max_report_bytes,
                "url_expires_seconds": self.upload_seconds,
            },
        }
