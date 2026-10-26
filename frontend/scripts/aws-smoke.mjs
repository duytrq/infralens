// Operator smoke: credentials arrive on stdin, stay in memory, and are never logged.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { readFile, mkdir } from "node:fs/promises";

const input = JSON.parse(
  await new Promise((resolve) => {
    let value = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      value += chunk;
    });
    process.stdin.on("end", () => resolve(value));
  }),
);
const browser = await chromium.launch();
const contexts = [];
const checks = [];
const runs = [];
let stage = "initialize";
let ownerToken;
const endpoint = input.endpoint;

async function api(token, method, path, body, statuses = [200]) {
  const response = await fetch(endpoint + path, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  assert(
    statuses.includes(response.status),
    `${method} ${path.split("?")[0]} returned ${response.status}`,
  );
  return response.status === 204 ? null : response.json();
}

async function signIn(origin, account) {
  const context = await browser.newContext({ acceptDownloads: true });
  contexts.push(context);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", () => errors.push("pageerror"));
  await page.goto(origin + "/");
  await page.getByRole("button", { name: "Sign in" }).waitFor();
  const tokenResponse = page.waitForResponse(
    (response) =>
      response.url() === input.config.auth.token_endpoint &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.locator('input[name="username"]:visible').fill(account.username);
  await page.locator('input[name="password"]:visible').fill(account.password);
  await page.locator('input[name="signInSubmitButton"]:visible').click();
  const response = await tokenResponse;
  assert.equal(response.status(), 200, "Cognito code exchange failed");
  const tokens = await response.json();
  assert.equal(typeof tokens.access_token, "string");
  await page.getByRole("heading", { name: "Projects", exact: true }).waitFor();
  assert.equal(page.url(), origin + "/projects");
  assert.deepEqual(errors, []);
  return { page, tokens, errors };
}

try {
  for (const origin of input.origins) {
    stage = `login ${new URL(origin).hostname}`;
    process.stderr.write(`smoke: ${stage}\n`);
    const owner = await signIn(origin, input.accounts[0]);
    ownerToken = owner.tokens.access_token;
    checks.push(`real_pkce_login:${origin}`);
    const suffix = randomUUID().slice(0, 8);
    const project = `frontend-smoke-${suffix}`;
    const projectName = `Frontend verification ${suffix}`;
    await api(
      ownerToken,
      "PUT",
      `/v1/projects/${project}`,
      { name: projectName },
      [200, 201],
    );
    const report = Buffer.from(
      JSON.stringify({
        SchemaVersion: 2,
        ArtifactName: "frontend-smoke",
        ArtifactType: "filesystem",
        Results: [
          {
            Target: "main.tf",
            Class: "config",
            Type: "terraform",
            Misconfigurations: [
              {
                ID: "AVD-FRONTEND-SMOKE",
                Severity: "HIGH",
                Status: "FAIL",
                Title: "Smoke fixture finding",
                Message: "Verification data, not a real infrastructure scan.",
                Description: "End-to-end report ingestion fixture.",
                Resolution: "No production resource is involved.",
                References: ["https://docs.aws.amazon.com/"],
                CauseMetadata: {
                  Resource: "aws_s3_bucket.smoke",
                  StartLine: 1,
                  EndLine: 3,
                  Code: {
                    Lines: [
                      {
                        Number: 1,
                        Content: 'resource "aws_s3_bucket" "smoke" {',
                        IsCause: true,
                      },
                      {
                        Number: 2,
                        Content: '  bucket = "example"',
                        IsCause: false,
                      },
                      { Number: 3, Content: "}", IsCause: false },
                    ],
                  },
                },
              },
            ],
          },
        ],
      }),
    );
    const timestamp = new Date().toISOString();
    const counts = {
      total: 1,
      by_severity: { UNKNOWN: 0, LOW: 0, MEDIUM: 0, HIGH: 1, CRITICAL: 0 },
    };
    const metadata = {
      schema_version: 1,
      run_id: randomUUID(),
      project_id: project,
      run_type: "security_scan",
      started_at: timestamp,
      finished_at: timestamp,
      duration_ms: 0,
      source: { relative_path: "frontend-smoke-fixture" },
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
        findings: counts,
        warnings: [],
      },
      artifact: {
        format: "json",
        content_type: "application/json",
        size_bytes: report.length,
        sha256: createHash("sha256").update(report).digest("hex"),
        schema_version: 2,
      },
    };
    stage = "report ingestion";
    const registration = await api(ownerToken, "POST", "/v1/runs", metadata, [
      201,
    ]);
    runs.push(metadata.run_id);
    const uploaded = await fetch(registration.upload.url, {
      method: "PUT",
      headers: registration.upload.headers,
      body: report,
    });
    assert.equal(uploaded.status, 200, "Signed report upload failed");
    await api(ownerToken, "POST", `/v1/runs/${metadata.run_id}/complete`);
    let indexed;
    for (let attempt = 0; attempt < 40; attempt++) {
      indexed = await api(ownerToken, "GET", `/v1/runs/${metadata.run_id}`);
      if (indexed.analysis?.status === "ready") break;
      assert.notEqual(
        indexed.analysis?.status,
        "failed",
        "Report indexing failed",
      );
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    assert.equal(
      indexed.analysis?.status,
      "ready",
      "Report indexing timed out",
    );
    assert.equal(indexed.analysis.counts_match, true);
    checks.push(`stream_indexing:${origin}`);
    stage = "dashboard project/history/findings";
    await owner.page.goto(origin + "/projects");
    await owner.page
      .getByRole("link", { name: projectName, exact: false })
      .first()
      .click();
    await owner.page
      .getByRole("link", { name: `Open scan ${metadata.run_id.slice(0, 8)}` })
      .waitFor();
    await owner.page
      .getByRole("link", { name: `Open scan ${metadata.run_id.slice(0, 8)}` })
      .click();
    await owner.page
      .getByRole("link", { name: "Smoke fixture finding", exact: true })
      .click();
    await owner.page
      .getByRole("region", { name: "Source code excerpt" })
      .waitFor();
    await owner.page.reload();
    await owner.page
      .getByRole("heading", { name: "Smoke fixture finding", exact: true })
      .waitFor();
    await mkdir(input.screenshot_directory, { recursive: true });
    await owner.page.screenshot({
      path: `${input.screenshot_directory}/aws-finding-${new URL(origin).hostname}.png`,
      fullPage: true,
    });
    await owner.page
      .getByRole("link", { name: "Back to scan", exact: true })
      .click();
    const attachment = owner.page.waitForEvent("download");
    await owner.page.getByRole("button", { name: "Download JSON" }).click();
    const downloaded = await attachment;
    assert.deepEqual(await readFile(await downloaded.path()), report);
    checks.push(`dashboard_history_detail_download:${origin}`);
    stage = "cross-user ownership";
    const other = await signIn(origin, input.accounts[1]);
    const findings = await api(
      ownerToken,
      "GET",
      `/v1/runs/${metadata.run_id}/findings`,
    );
    for (const [method, path] of [
      ["GET", `/v1/projects/${project}`],
      ["GET", `/v1/runs/${metadata.run_id}`],
      ["GET", `/v1/runs/${metadata.run_id}/findings`],
      [
        "GET",
        `/v1/runs/${metadata.run_id}/findings/${findings.items[0].finding_id}`,
      ],
      ["GET", `/v1/runs/${metadata.run_id}/artifacts/json`],
      ["POST", `/v1/runs/${metadata.run_id}/analysis/retry`],
      ["DELETE", `/v1/runs/${metadata.run_id}`],
    ])
      await api(other.tokens.access_token, method, path, undefined, [404]);
    await other.page.goto(origin + `/runs/${metadata.run_id}`);
    await other.page
      .getByRole("alert")
      .filter({ hasText: "This item is unavailable" })
      .waitFor();
    checks.push(`cross_user_api_and_ui_isolation:${origin}`);
    stage = "retry and delete";
    await api(
      ownerToken,
      "POST",
      `/v1/runs/${metadata.run_id}/analysis/retry`,
      undefined,
      [200],
    );
    await owner.page
      .getByRole("button", { name: "Delete scan", exact: true })
      .click();
    await owner.page
      .getByRole("button", { name: "Confirm deletion", exact: true })
      .click();
    await owner.page
      .getByRole("heading", { name: "No scans yet", exact: true })
      .waitFor();
    await api(ownerToken, "GET", `/v1/runs/${metadata.run_id}`, undefined, [
      404,
    ]);
    checks.push(`retry_and_delete:${origin}`);
    stage = "logout and refresh-token revocation";
    await owner.page
      .getByRole("button", { name: "Sign out", exact: true })
      .click();
    await owner.page
      .getByRole("button", { name: "Sign in" })
      .waitFor();
    const revoked = await fetch(input.config.auth.token_endpoint, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: input.config.auth.client_id,
        refresh_token: owner.tokens.refresh_token,
      }),
    });
    assert.equal(
      revoked.status,
      400,
      "Refresh token must be revoked after logout",
    );
    checks.push(`logout_revocation:${origin}`);
    assert.deepEqual(owner.errors, []);
    assert.deepEqual(other.errors, []);
  }
  process.stdout.write(
    JSON.stringify({ status: "passed", checks, run_ids: runs }),
  );
} catch (error) {
  const message =
    error instanceof Error
      ? error.message.split("\n")[0].replace(/https?:\/\/\S+/g, "[URL]")
      : "Unknown error";
  process.stderr.write(
    `AWS frontend smoke failed during: ${stage}: ${message}\n`,
  );
  process.exitCode = 1;
} finally {
  if (ownerToken)
    for (const run of runs)
      await api(
        ownerToken,
        "DELETE",
        `/v1/runs/${run}`,
        undefined,
        [202, 204, 404],
      ).catch(() => {});
  await Promise.all(contexts.map((context) => context.close()));
  await browser.close();
}
