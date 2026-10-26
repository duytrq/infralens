import {
  test as base,
  expect,
  type Page as BrowserPage,
} from "@playwright/test";
import type {
  DashboardConfig,
  Finding,
  Project,
  Run,
} from "../../src/api/types";

export const config: DashboardConfig = {
  schema_version: 1,
  api_version: "v1",
  auth: {
    issuer: "https://issuer.example.com/pool",
    client_id: "dashboard-client",
    authorization_endpoint: "https://login.example.com/oauth2/authorize",
    token_endpoint: "https://login.example.com/oauth2/token",
    revocation_endpoint: "https://login.example.com/oauth2/revoke",
    callback_url: "https://dashboard.example.com/auth/callback",
    logout_url: "https://dashboard.example.com/",
    logout_endpoint: "https://login.example.com/logout",
    allowed_origins: ["http://localhost:5173", "https://dashboard.example.com"],
    scopes: ["openid", "infralens/api"],
    pkce_method: "S256",
  },
  upload: {
    formats: ["json"],
    max_report_bytes: 52428800,
    url_expires_seconds: 900,
  },
};

export const run: Run = {
  schema_version: 1,
  run_id: "b7fe3c5e-6812-4d81-bbe2-7acb5ef6e770",
  project_id: "production-infra",
  run_type: "security_scan",
  started_at: "2026-10-23T03:30:00Z",
  finished_at: "2026-10-23T03:30:04Z",
  duration_ms: 4000,
  received_at: "2026-10-23T03:30:06Z",
  uploaded_at: "2026-10-23T03:30:07Z",
  upload_status: "ready",
  source: {
    relative_path: "infrastructure/production",
    git: { commit: "a".repeat(40), branch: "main", dirty: false },
  },
  tool: {
    infralens_version: "0.1.0",
    engine: "trivy",
    engine_version: "0.76.0",
  },
  scan_options: {
    severity: ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
    fail_on: "HIGH",
    ignore_sha256: null,
  },
  result: {
    scan_status: "completed",
    threshold_status: "failed",
    findings: {
      total: 2,
      by_severity: { UNKNOWN: 0, LOW: 0, MEDIUM: 0, HIGH: 1, CRITICAL: 1 },
    },
    warnings: [],
  },
  artifact: {
    format: "json",
    content_type: "application/json",
    size_bytes: 2048,
    sha256: "b".repeat(64),
    schema_version: 2,
  },
  analysis: {
    status: "ready",
    version: 1,
    build_id: "f".repeat(32),
    requested_at: "2026-10-23T03:30:07Z",
    completed_at: "2026-10-23T03:30:10Z",
    findings: {
      total: 2,
      by_severity: { UNKNOWN: 0, LOW: 0, MEDIUM: 0, HIGH: 1, CRITICAL: 1 },
    },
    counts_match: true,
    error_code: null,
  },
};
export const project: Project = {
  project_id: run.project_id,
  name: "Production infrastructure",
  created_at: "2026-10-20T02:00:00Z",
  latest_scan: {
    run_id: run.run_id,
    started_at: run.started_at,
    finished_at: run.finished_at,
    result: run.result,
  },
};
export const finding: Finding = {
  finding_id: `0-${"a".repeat(32)}`,
  rule_id: "AVD-AWS-0086",
  severity: "CRITICAL",
  title: "S3 bucket access should be restricted",
  file: "storage/main.tf",
  resource: "aws_s3_bucket.logs",
  start_line: 12,
  end_line: 16,
  message: "Public access is enabled.",
  description: "Public buckets may expose sensitive data.",
  resolution: "Enable the S3 public access block.",
  references: ["https://example.com/docs", "javascript:alert(1)"],
  code: [
    { number: 12, content: '<script>alert("unsafe")</script>', is_cause: true },
    { number: 13, content: '  acl = "public-read"', is_cause: false },
    { number: 14, content: "}", is_cause: false },
  ],
  truncated_fields: [],
};

export async function mockApi(page: BrowserPage, signedIn = true) {
  if (signedIn)
    await page.addInitScript(
      ({ issuer, client }) => {
        sessionStorage.setItem(
          `oidc.user:${issuer}:${client}`,
          JSON.stringify({
            access_token: "test-access-token",
            refresh_token: "test-refresh-token",
            token_type: "Bearer",
            scope: "openid infralens/api",
            expires_at: Math.floor(Date.now() / 1000) + 3600,
            profile: {
              sub: "user-a",
              iss: issuer,
              aud: client,
              exp: Math.floor(Date.now() / 1000) + 3600,
              iat: Math.floor(Date.now() / 1000),
            },
          }),
        );
      },
      { issuer: config.auth.issuer, client: config.auth.client_id },
    );
  await page.route("https://api.example.com/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/v1/dashboard-config") return route.fulfill({ json: config });
    if (route.request().headers().authorization !== "Bearer test-access-token")
      return route.fulfill({ status: 401, json: { message: "Unauthorized" } });
    if (path === "/v1/projects")
      return route.fulfill({ json: { items: [project], next_cursor: null } });
    if (path === `/v1/projects/${project.project_id}`)
      return route.fulfill({ json: project });
    if (path === "/v1/runs")
      return route.fulfill({ json: { items: [run], next_cursor: null } });
    if (path === `/v1/runs/${run.run_id}`) return route.fulfill({ json: run });
    if (path.endsWith("/findings"))
      return route.fulfill({ json: { items: [finding], next_cursor: null } });
    if (path.includes("/findings/")) return route.fulfill({ json: finding });
    if (path.endsWith("/artifacts/json"))
      return route.fulfill({
        json: {
          url: "https://downloads.example.com/report.json?signature=example",
          expires_at: "2026-10-23T04:00:00Z",
        },
      });
    return route.fulfill({
      status: 404,
      json: { error: { code: "not_found", message: "Not found" } },
    });
  });
}

export const test = base.extend<{ authenticated: void }>({
  authenticated: [
    async ({ page }, use) => {
      await mockApi(page);
      await use();
    },
    { auto: true },
  ],
});
export { expect };
