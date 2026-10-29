// Operator smoke: credentials arrive on stdin, stay in memory, and are never logged.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
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

async function checkSecurityCli(owner, project, origin) {
  const cli = input.security_cli;
  const output = `${cli.output_directory}/${randomUUID()}.json`;
  const env = { ...process.env, INFRALENS_ACCESS_TOKEN: ownerToken,
    XDG_CONFIG_HOME: cli.output_directory + "/config", APPDATA: cli.output_directory + "/appdata" };
  delete env.INFRALENS_API_URL;
  delete env.INFRALENS_PROJECT;
  function run(args, expected = 0) {
    const result = spawnSync(cli.executable, args, { env, encoding: "utf8", timeout: 240_000, input: "" });
    assert.equal(result.status, expected, "CLI cloud operation returned an unexpected exit code");
    return result;
  }
  run(["cloud", "configure", "--api-url", endpoint]);
  const cliProject = project + "-cli";
  run(["cloud", "project", "create", cliProject, "--name", "CLI verification"]);
  assert(run(["cloud", "project", "list"]).stdout.includes(cliProject));
  run(["cloud", "project", "use", cliProject]);
  const scanned = run([
    "scan", cli.project, "--format", "json", "--output", output,
    "--severity", "LOW", "--fail-on", "HIGH", "--upload",
  ], 1);
  const matched = scanned.stderr.match(/Uploaded security scan ([0-9a-f-]{36})/);
  assert(matched, "CLI must confirm the uploaded run ID before returning its findings exit");
  const runId = matched[1];
  runs.push(runId);
  await assert.rejects(readFile(output + ".upload.json"), { code: "ENOENT" });
  const report = await readFile(output);
  let indexed;
  for (let attempt = 0; attempt < 40; attempt++) {
    indexed = await api(ownerToken, "GET", `/v1/runs/${runId}`);
    if (indexed.analysis?.status === "ready") break;
    assert.notEqual(indexed.analysis?.status, "failed");
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  assert.equal(indexed.analysis?.status, "ready");
  assert.equal(indexed.analysis.counts_match, true);
  assert.equal(indexed.result.threshold_status, "failed");
  assert(indexed.result.findings.by_severity.HIGH > 0);
  assert.equal(indexed.project_id, cliProject);
  assert.equal(indexed.artifact.sha256, createHash("sha256").update(report).digest("hex"));
  checks.push(`cli_config_projects_upload_indexing:${origin}`);
  await owner.page.goto(origin + `/runs/${runId}`);
  const findings = await api(ownerToken, "GET", `/v1/runs/${runId}/findings`);
  await owner.page.getByRole("link", { name: findings.items[0].title, exact: true }).first().click();
  await owner.page.getByRole("heading", { name: findings.items[0].title, exact: true }).waitFor();
  await owner.page.getByRole("region", { name: "Source code excerpt" }).waitFor();
  await owner.page.getByRole("link", { name: "Back to scan", exact: true }).click();
  const downloaded = owner.page.waitForEvent("download");
  await owner.page.getByRole("button", { name: "Download JSON" }).click();
  assert.deepEqual(await readFile(await (await downloaded).path()), report);
  checks.push(`cli_security_dashboard_source_download:${origin}`);
  await api(ownerToken, "DELETE", `/v1/runs/${runId}`, undefined, [202, 204]);
  await owner.page.goto(origin + `/runs/${runId}`);
  await owner.page.getByRole("alert").filter({ hasText: "This item is unavailable" }).waitFor();
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
    if (input.security_cli) {
      stage = "CLI config/projects/Security upload and dashboard";
      await checkSecurityCli(owner, project, origin);
    }
    stage = "drift ingestion and comparison";
    const driftRuns = [];
    for (const observed of ["t3.small", "t3.medium"]) {
      const timestamp = new Date().toISOString();
      const driftReport = {
        schema_version: "1.0",
        kind: "drift",
        terraform_version: "1.15.7",
        input_mode: "imported_plan",
        checked_at: timestamp,
        has_drift: true,
        summary: { resources: 1, attributes: 1 },
        resources: [{
          address: "aws_instance.smoke",
          resource_type: "aws_instance",
          actions: ["update"],
          identifiers: {},
          attributes: [{
            path: ["instance_type"],
            before: { status: "known", value: "t3.micro" },
            after: { status: "known", value: observed },
          }],
          source: {
            status: "located",
            context: "current_configuration",
            block_address: "aws_instance.smoke",
            locations: [{ file: "main.tf", start_line: 1, end_line: 4, syntax: "hcl" }],
          },
        }],
        normalizations: [],
        notes: ["Deployment verification fixture; no infrastructure was changed."],
      };
      const bytes = Buffer.from(JSON.stringify(driftReport));
      const driftMetadata = {
        schema_version: 1,
        run_id: randomUUID(),
        project_id: project,
        run_type: "drift",
        scope: "deployment-smoke",
        started_at: timestamp,
        finished_at: timestamp,
        duration_ms: 0,
        source: { relative_path: "." },
        tool: { infralens_version: "0.1.0", engine: "terraform", engine_version: "1.15.7" },
        drift_options: {
          input_mode: "imported_plan",
          trace: false,
          lookback_days: null,
          gate: { any_drift: false, minimum_priority: null, unknown_priority: false },
        },
        result: {
          collection_status: "completed",
          has_drift: true,
          summary: driftReport.summary,
          priority_counts: { high: 0, medium: 0, unknown: 1 },
          gate_status: "disabled",
          trace_status: "disabled",
        },
        artifact: {
          format: "json",
          content_type: "application/json",
          size_bytes: bytes.length,
          sha256: createHash("sha256").update(bytes).digest("hex"),
          schema_version: "1.0",
        },
      };
      const registered = await api(ownerToken, "POST", "/v1/runs", driftMetadata, [201]);
      runs.push(driftMetadata.run_id);
      const put = await fetch(registered.upload.url, {
        method: "PUT", headers: registered.upload.headers, body: bytes,
      });
      assert.equal(put.status, 200, "Signed drift upload failed");
      const completed = await api(ownerToken, "POST", `/v1/runs/${driftMetadata.run_id}/complete`);
      assert.equal(completed.upload_status, "ready");
      assert.equal(completed.analysis, undefined);
      assert.deepEqual(await api(ownerToken, "GET", `/v1/runs/${driftMetadata.run_id}/drift/report`), driftReport);
      driftRuns.push({ id: driftMetadata.run_id, bytes });
    }
    const currentDrift = driftRuns[1];
    const comparison = await api(ownerToken, "GET", `/v1/runs/${currentDrift.id}/drift/comparison`);
    assert.equal(comparison.status, "compared");
    assert.equal(comparison.baseline_run_id, driftRuns[0].id);
    assert.equal(comparison.summary.changed, 1);
    const securityHistory = await api(ownerToken, "GET", `/v1/runs?project_id=${project}`);
    assert.deepEqual(securityHistory.items.map((run) => run.run_id), [metadata.run_id]);
    const driftHistory = await api(ownerToken, "GET", `/v1/runs?project_id=${project}&run_type=drift&scope=deployment-smoke`);
    assert.equal(driftHistory.items.length, 2);
    checks.push(`drift_signed_upload_report_comparison_isolation:${origin}`);
    stage = "drift dashboard and download";
    await owner.page.goto(origin + `/projects/${project}`);
    await owner.page.getByRole("link", { name: "Drift", exact: true }).click();
    await owner.page.getByRole("link", { name: `Open drift ${currentDrift.id.slice(0, 8)}` }).click();
    await owner.page.getByRole("heading", { name: `Drift ${currentDrift.id.slice(0, 8)}`, exact: true }).waitFor();
    await owner.page.getByRole("region", { name: "Resource changes" }).getByText('"t3.medium"', { exact: true }).waitFor();
    await owner.page.getByRole("region", { name: "Compared resources" }).getByText("changed", { exact: true }).waitFor();
    await owner.page.reload();
    await owner.page.getByRole("region", { name: "Drift summary" }).waitFor();
    const driftAttachment = owner.page.waitForEvent("download");
    await owner.page.getByRole("button", { name: "Download JSON" }).click();
    assert.deepEqual(await readFile(await (await driftAttachment).path()), currentDrift.bytes);
    await owner.page.screenshot({
      path: `${input.screenshot_directory}/aws-drift-${new URL(origin).hostname}.png`,
      fullPage: true,
    });
    checks.push(`drift_dashboard_deep_link_download:${origin}`);
    stage = "cross-user ownership";
    const other = await signIn(origin, input.accounts[1]);
    for (const suffix of ["", "/drift/report", "/drift/comparison", "/artifacts/json"])
      await api(other.tokens.access_token, "GET", `/v1/runs/${currentDrift.id}${suffix}`, undefined, [404]);
    for (const run of driftRuns)
      await api(ownerToken, "DELETE", `/v1/runs/${run.id}`, undefined, [202, 204]);
    await api(ownerToken, "GET", `/v1/runs/${currentDrift.id}/drift/report`, undefined, [404]);
    checks.push(`drift_cross_user_isolation_and_deletion:${origin}`);
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
    await owner.page.goto(origin + `/runs/${metadata.run_id}`);
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
