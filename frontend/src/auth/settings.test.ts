import { describe, expect, it } from "vitest";
import { createUserManager, safeReturnPath } from "./settings";
import type { DashboardConfig } from "../api/types";

const config = {
  auth: {
    issuer: "https://issuer.example.com/pool",
    client_id: "dashboard-client",
    authorization_endpoint: "https://login.example.com/oauth2/authorize",
    token_endpoint: "https://login.example.com/oauth2/token",
    revocation_endpoint: "https://login.example.com/oauth2/revoke",
    callback_url: "https://dashboard.example.com/auth/callback",
    logout_url: "https://dashboard.example.com/",
    logout_endpoint: "https://login.example.com/logout",
    scopes: ["openid", "infralens/api"],
    pkce_method: "S256",
    allowed_origins: ["https://dashboard.example.com", "http://localhost:5173"],
  },
  schema_version: 1,
  api_version: "v1",
  upload: {
    formats: ["json"],
    max_report_bytes: 52428800,
    max_drift_report_bytes: 2097152,
    url_expires_seconds: 900,
  },
} satisfies DashboardConfig;

describe("dashboard auth configuration", () => {
  it("uses the active registered origin and session storage rather than the primary callback", () => {
    const manager = createUserManager(config, "http://localhost:5173");
    expect(manager.settings.redirect_uri).toBe(
      "http://localhost:5173/auth/callback",
    );
    expect(manager.settings.disablePKCE).toBe(false);
    expect(manager.settings.loadUserInfo).toBe(false);
    manager.stopSilentRenew();
  });
  it("rejects unregistered origins before starting a login", () => {
    expect(() =>
      createUserManager(config, "https://untrusted.example.com"),
    ).toThrow("not registered");
  });
  it("only restores internal non-callback routes", () => {
    expect(safeReturnPath("/runs/id?severity=HIGH")).toBe(
      "/runs/id?severity=HIGH",
    );
    for (const path of [
      "//evil.example",
      "/\\evil.example",
      "https://evil.example",
      "/auth/callback?code=x",
      "/",
      null,
    ]) {
      expect(safeReturnPath(path)).toBe("/projects");
    }
  });
});
