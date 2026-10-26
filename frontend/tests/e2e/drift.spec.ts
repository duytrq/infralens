import AxeBuilder from "@axe-core/playwright";
import { test, expect, project } from "./fixtures";
import type { DriftReport, DriftRun } from "../../src/api/types";

const drift: DriftRun = {
  schema_version: 1,
  run_id: "a7fe3c5e-6812-4d81-bbe2-7acb5ef6e770",
  project_id: project.project_id,
  run_type: "drift",
  scope: "production-default",
  started_at: "2026-10-23T04:00:00Z",
  finished_at: "2026-10-23T04:00:03Z",
  received_at: "2026-10-23T04:00:04Z",
  uploaded_at: "2026-10-23T04:00:05Z",
  upload_status: "ready",
  duration_ms: 3000,
  source: { relative_path: "." },
  tool: {
    infralens_version: "0.1.0",
    engine: "terraform",
    engine_version: "1.16.5",
  },
  drift_options: {
    input_mode: "imported_plan",
    trace: true,
    lookback_days: 7,
    gate: { any_drift: true, minimum_priority: null, unknown_priority: false },
  },
  result: {
    collection_status: "completed",
    has_drift: true,
    summary: { resources: 1, attributes: 5 },
    priority_counts: { high: 1, medium: 0, unknown: 0 },
    gate_status: "failed",
    trace_status: "complete",
  },
  artifact: {
    format: "json",
    content_type: "application/json",
    size_bytes: 4096,
    sha256: "a".repeat(64),
    schema_version: "1.0",
  },
};
const report: DriftReport = {
  schema_version: "1.0",
  kind: "drift",
  terraform_version: "1.16.5",
  input_mode: "imported_plan",
  checked_at: drift.finished_at,
  has_drift: true,
  summary: drift.result.summary,
  normalizations: [],
  notes: ["Imported plan: freshness and coverage are unverified."],
  trace: { status: "complete", has_errors: false },
  gate: {
    policy: "drift-gate-v1",
    review_policy: "builtin-review-v2",
    status: "failed",
    exit_code: 1,
    criteria: drift.drift_options.gate,
    priority_counts: drift.result.priority_counts,
    unassessed_resources: 0,
    matched_count: 1,
    matched_resources: [
      { address: "aws_instance.web", priority: "high", reasons: ["any_drift"] },
    ],
    reason_codes: [],
  },
  resources: [
    {
      address: "aws_instance.web",
      resource_type: "aws_instance",
      actions: ["update"],
      identifiers: {},
      attributes: [
        {
          path: ["instance_type"],
          before: { status: "known", value: "t3.micro" },
          after: { status: "known", value: "t3.small" },
        },
        {
          path: ["secret"],
          before: { status: "sensitive" },
          after: { status: "sensitive" },
        },
        {
          path: ["computed"],
          before: { status: "known", value: null },
          after: { status: "unknown" },
        },
        {
          path: ["removed"],
          before: { status: "known", value: true },
          after: { status: "absent" },
        },
        {
          path: ["tags", "script"],
          before: { status: "known", value: "safe" },
          after: { status: "known", value: '<script>alert("unsafe")</script>' },
        },
      ],
      source: {
        status: "located",
        context: "current_configuration",
        block_address: "aws_instance.web",
        locations: [
          {
            file: "compute/main.tf",
            start_line: 12,
            end_line: 30,
            syntax: "hcl",
          },
        ],
      },
      assessment: {
        policy: "builtin-review-v2",
        priority: "high",
        signals: [
          {
            code: "instance_type_changed",
            priority: "high",
            description: "Review workload capacity.",
            paths: [["instance_type"]],
          },
        ],
        guidance: {
          review_steps: ["Check the approved change record."],
          choices: [
            {
              id: "restore",
              title: "Restore approved configuration",
              steps: ["Review a normal Terraform plan."],
            },
          ],
        },
      },
      trace: {
        status: "matched",
        events: [
          {
            event_id: "event-1",
            event_name: "ModifyInstanceAttribute",
            event_source: "ec2.amazonaws.com",
            event_time: drift.started_at,
            region: "ap-southeast-1",
            actor: { arn: "arn:aws:iam::123456789012:role/operator" },
            matched_attributes: ["instance_type"],
            relation: "candidate",
          },
        ],
      },
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route(`https://api.example.com/v1/runs/${drift.run_id}`, (route) =>
    route.fulfill({ json: drift }),
  );
  await page.route(
    `https://api.example.com/v1/runs/${drift.run_id}/drift/report`,
    (route) => route.fulfill({ json: report }),
  );
  await page.route(
    `https://api.example.com/v1/runs/${drift.run_id}/drift/comparison**`,
    (route) =>
      route.fulfill({
        json: {
          current_run_id: drift.run_id,
          baseline_run_id: null,
          status: "baseline_missing",
          resources: [],
          summary: {
            new: 0,
            no_longer_reported: 0,
            changed: 0,
            unchanged: 0,
            indeterminate: 0,
          },
          notes: ["No longer reported does not prove repair."],
          next_cursor: null,
        },
      }),
  );
  await page.route("https://api.example.com/v1/runs?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("run_type") !== "drift") return route.fallback();
    return route.fulfill({ json: { items: [drift], next_cursor: null } });
  });
});

test("project drift tab filters history and opens complete safe report", async ({
  page,
}) => {
  const errors: string[] = [];
  const dialogs: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("dialog", (dialog) => {
    dialogs.push(dialog.type());
    void dialog.dismiss();
  });
  await page.goto(`/projects/${project.project_id}`);
  await page.getByRole("link", { name: "Drift", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Drift history", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Scope", { exact: true }).fill(drift.scope);
  await page
    .getByRole("combobox", { name: "Gate", exact: true })
    .selectOption("failed");
  const request = page.waitForRequest((r) => {
    const url = new URL(r.url());
    return (
      url.pathname === "/v1/runs" &&
      url.searchParams.get("scope") === drift.scope &&
      url.searchParams.get("gate_status") === "failed"
    );
  });
  await page.getByRole("button", { name: "Apply filters" }).click();
  await request;
  await page
    .getByRole("link", { name: `Open drift ${drift.run_id.slice(0, 8)}` })
    .click();
  await expect(
    page.getByRole("heading", {
      name: `Drift ${drift.run_id.slice(0, 8)}`,
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "CI gate", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Resource changes" }),
  ).toContainText("t3.micro");
  await expect(
    page.getByRole("region", { name: "Resource changes" }),
  ).toContainText("[sensitive]");
  await expect(
    page.getByRole("region", { name: "Resource changes" }),
  ).toContainText("[unknown]");
  await expect(
    page.getByRole("region", { name: "Resource changes" }),
  ).toContainText("[absent]");
  await expect(
    page.getByRole("region", { name: "Resource changes" }),
  ).toContainText("null");
  await expect(
    page.getByRole("region", { name: "Resource changes" }),
  ).toContainText(JSON.stringify('<script>alert("unsafe")</script>'));
  await expect(page.getByText("compute/main.tf:12–30")).toBeVisible();
  await expect(
    page.getByText("ModifyInstanceAttribute", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Imported plan: freshness and coverage are unverified.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "No comparable baseline" }),
  ).toBeVisible();
  expect(dialogs).toEqual([]);
  expect(errors).toEqual([]);
});

test("pending drift never renders zero results or loads report", async ({
  page,
}) => {
  let reports = 0;
  await page.route(`https://api.example.com/v1/runs/${drift.run_id}`, (route) =>
    route.fulfill({
      json: {
        ...drift,
        upload_status: "pending",
        received_at: new Date().toISOString(),
      },
    }),
  );
  await page.route(
    `https://api.example.com/v1/runs/${drift.run_id}/drift/report`,
    (route) => {
      reports++;
      return route.fulfill({ json: report });
    },
  );
  await page.goto(`/runs/${drift.run_id}`);
  await expect(
    page.getByRole("heading", { name: "Report upload is not complete" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download JSON" }),
  ).toBeDisabled();
  await expect(page.getByRole("region", { name: "Drift summary" })).toHaveCount(
    0,
  );
  expect(reports).toBe(0);
});

for (const width of [320, 768, 1024, 1440]) {
  test(`drift report is accessible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/runs/${drift.run_id}`);
    await expect(
      page.getByRole("region", { name: "Resource changes" }),
    ).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/drift-${width}.png`,
      fullPage: true,
    });
  });
}

test("comparison pins baseline through pagination and supports explicit selection", async ({
  page,
}) => {
  const baseline = "b7fe3c5e-6812-4d81-bbe2-7acb5ef6e770";
  const selected = "c7fe3c5e-6812-4d81-bbe2-7acb5ef6e770";
  const requests: URL[] = [];
  await page.route(
    `https://api.example.com/v1/runs/${drift.run_id}/drift/comparison**`,
    (route) => {
      const url = new URL(route.request().url());
      requests.push(url);
      return route.fulfill({
        json: {
          current_run_id: drift.run_id,
          baseline_run_id: url.searchParams.get("baseline_id") ?? baseline,
          status: "compared",
          resources: [
            {
              address: url.searchParams.has("cursor")
                ? "aws_instance.old"
                : "aws_instance.web",
              status: url.searchParams.has("cursor")
                ? "no_longer_reported"
                : "indeterminate",
              changed_paths: [],
            },
          ],
          summary: {
            new: 0,
            no_longer_reported: 1,
            changed: 0,
            unchanged: 0,
            indeterminate: 1,
          },
          notes: ["No longer reported does not prove repair."],
          next_cursor: url.searchParams.has("cursor") ? null : "page-two",
        },
      });
    },
  );
  await page.goto(`/runs/${drift.run_id}`);
  await expect(
    page.getByRole("region", { name: "Compared resources" }),
  ).toContainText("indeterminate");
  await page.getByRole("button", { name: "Load more", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Compared resources" }),
  ).toContainText("no longer reported");
  expect(requests[1].searchParams.get("baseline_id")).toBe(baseline);
  expect(requests[1].searchParams.get("cursor")).toBe("page-two");
  await page.getByLabel("Baseline run ID").fill(selected);
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByText(selected, { exact: true })).toBeVisible();
});

test("partial trace and comparison failure remain visible with report download", async ({
  page,
}) => {
  await page.route(`https://api.example.com/v1/runs/${drift.run_id}`, (route) =>
    route.fulfill({
      json: {
        ...drift,
        result: {
          ...drift.result,
          collection_status: "partial",
          gate_status: "incomplete",
          trace_status: "error",
        },
      },
    }),
  );
  await page.route(
    `https://api.example.com/v1/runs/${drift.run_id}/drift/comparison**`,
    (route) =>
      route.fulfill({
        status: 409,
        json: {
          error: {
            code: "artifact_missing",
            message: "Baseline is unavailable.",
          },
        },
      }),
  );
  await page.goto(`/runs/${drift.run_id}`);
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "CloudTrail could not complete" }),
  ).toBeVisible();
  await expect(
    page.getByRole("alert").filter({ hasText: "Baseline is unavailable" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download JSON" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("region", { name: "Resource changes" }),
  ).toBeVisible();
});

test("deleting a drift run returns to drift history and clears cached report", async ({
  page,
}) => {
  let removed = false;
  await page.route(
    `https://api.example.com/v1/runs/${drift.run_id}`,
    (route) => {
      if (route.request().method() === "DELETE") {
        removed = true;
        return route.fulfill({
          status: 202,
          json: {
            run_id: drift.run_id,
            upload_status: "deleting",
            delete_after: new Date().toISOString(),
          },
        });
      }
      return route.fulfill({ json: drift });
    },
  );
  await page.route("https://api.example.com/v1/runs?**", (route) =>
    route.fulfill({
      json: { items: removed ? [] : [drift], next_cursor: null },
    }),
  );
  await page.goto(`/runs/${drift.run_id}`);
  await page
    .getByRole("button", { name: "Delete drift run", exact: true })
    .click();
  await page.getByRole("button", { name: "Confirm deletion" }).click();
  await expect(page).toHaveURL(`/projects/${drift.project_id}?type=drift`);
  await expect(
    page.getByRole("heading", { name: "No drift reports" }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Resource changes" }),
  ).toHaveCount(0);
});
