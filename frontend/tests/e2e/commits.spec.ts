import AxeBuilder from "@axe-core/playwright";
import { test, expect, project, run } from "./fixtures";
import type { DriftRun } from "../../src/api/types";

const drift: DriftRun = {
  ...run,
  run_id: "a7fe3c5e-6812-4d81-bbe2-7acb5ef6e771",
  run_type: "drift",
  scope: "production-default",
  tool: { ...run.tool, engine: "terraform" },
  artifact: { ...run.artifact, schema_version: "1.0" },
  drift_options: {
    input_mode: "refresh_only",
    trace: false,
    lookback_days: null,
    gate: { any_drift: true, minimum_priority: null, unknown_priority: false },
  },
  result: {
    collection_status: "completed",
    has_drift: false,
    summary: { resources: 0, attributes: 0 },
    priority_counts: { high: 0, medium: 0, unknown: 0 },
    gate_status: "passed",
    trace_status: "not_needed",
  },
};

test("commit view joins types across pages and keeps dirty/unknown runs separate", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const dirty = { ...run.source, git: { ...run.source.git!, dirty: true } };
  await page.route("https://api.example.com/v1/runs?**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get("run_type") === "drift")
      return route.fulfill({
        json: params.has("cursor")
          ? {
              items: [
                drift,
                { ...drift, run_id: "another-drift", scope: "development" },
              ],
              next_cursor: null,
            }
          : { items: [], next_cursor: "older-drift" },
      });
    return route.fulfill({
      json: {
        items: [
          run,
          { ...run, run_id: "dirty1", source: dirty },
          { ...run, run_id: "dirty2", source: dirty },
          { ...run, run_id: "old", source: { relative_path: "." } },
        ],
        next_cursor: null,
      },
    });
  });
  await page.goto(`/projects/${project.project_id}?view=commits`);
  const group = page.locator('section[aria-label^="Commit "]');
  await expect(group).toHaveCount(1);
  await expect(
    group.getByRole("link", { name: "Security report" }),
  ).toBeVisible();
  await expect(group.getByRole("link", { name: "Drift report" })).toHaveCount(
    0,
  );
  await expect(
    page.getByText("Grouping covers loaded reports.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load more reports" }).click();
  await expect(group.getByRole("link", { name: "Drift report" })).toHaveCount(
    2,
  );
  await expect(group).toContainText("production-default");
  await expect(group).toContainText("development");
  await expect(
    page.getByRole("heading", { name: "Uncommitted changes", exact: true }),
  ).toHaveCount(2);
  await page.getByLabel("Source category").selectOption("unrecorded");
  await expect(
    page.getByRole("heading", { name: "Without Git metadata", exact: true }),
  ).toHaveCount(1);
  await expect(group).toHaveCount(0);
  await page.getByLabel("Source category").selectOption("committed");
  await page.getByLabel("Commit SHA").fill("aaa");
  await expect(group).toHaveCount(1);
  await expect(group).toContainText(run.source.git!.commit);
  expect(errors).toEqual([]);
});

for (const width of [320, 768, 1440]) {
  test(`commit history readable and accessible at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/projects/${project.project_id}?view=commits`);
    await expect(
      page.getByRole("heading", { name: "Commit", exact: true }),
    ).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: `test-results/commits-${width}.png`,
      fullPage: true,
    });
  });
}

test("both report detail pages expose full commit and dirty base context near the top", async ({
  page,
}) => {
  await page.goto(`/runs/${run.run_id}`);
  const source = page.getByRole("region", { name: "Source revision" });
  await expect(source).toContainText(run.source.git!.commit);
  await expect(source).toContainText("main");
  await page.route(`https://api.example.com/v1/runs/${drift.run_id}`, (route) =>
    route.fulfill({
      json: {
        ...drift,
        source: { ...drift.source, git: { ...drift.source.git!, dirty: true } },
      },
    }),
  );
  await page.goto(`/runs/${drift.run_id}`);
  await expect(source).toContainText("Base commit");
  await expect(source).toContainText("Uncommitted changes");
  await expect(source).toContainText(drift.source.git!.commit);
});
