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
    findings_table_name: str = ""
    dashboard_client_id: str = ""
    dashboard_origin: str = "http://localhost:5173"
    environment: str = "dev"
    enable_local_dashboard: bool = False

    @classmethod
    def from_env(cls):
        return cls(
            table_name=os.environ["TABLE_NAME"],
            bucket=os.environ["REPORTS_BUCKET"],
            issuer=os.environ["COGNITO_ISSUER"],
            client_id=os.environ["COGNITO_CLIENT_ID"],
            auth_domain=os.environ["COGNITO_DOMAIN"],
            callback_url=os.environ.get("CALLBACK_URL", cls.callback_url),
            findings_table_name=os.environ.get("FINDINGS_TABLE", ""),
            dashboard_client_id=os.environ.get("DASHBOARD_CLIENT_ID", ""),
            dashboard_origin=os.environ.get("DASHBOARD_ORIGIN", cls.dashboard_origin),
            environment=os.environ.get("ENVIRONMENT", cls.environment),
            enable_local_dashboard=os.environ.get("ENABLE_LOCAL_DASHBOARD") == "true",
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
                "max_drift_report_bytes": 2 * 1024 * 1024,
                "url_expires_seconds": self.upload_seconds,
            },
        }

    def dashboard(self):
        config = self.public()
        config["auth"]["client_id"] = self.dashboard_client_id
        config["auth"]["callback_url"] = self.dashboard_origin + "/auth/callback"
        config["auth"]["logout_url"] = self.dashboard_origin + "/"
        config["auth"]["logout_endpoint"] = self.auth_domain + "/logout"
        origins = [self.dashboard_origin]
        if self.environment == "dev" and self.enable_local_dashboard:
            origins.append("http://localhost:5173")
        config["auth"]["allowed_origins"] = list(dict.fromkeys(origins))
        return config
