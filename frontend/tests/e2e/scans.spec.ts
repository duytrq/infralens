import AxeBuilder from "@axe-core/playwright";
import { test, expect, finding, run } from "./fixtures";

test("scan findings link to safe, readable detail and preserve exact filters", async ({
  page,
}) => {
  const dialogs: string[] = [];
  const errors: string[] = [];
  page.on("dialog", (dialog) => {
    dialogs.push(dialog.type());
    void dialog.dismiss();
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`/runs/${run.run_id}`);
  await expect(
    page.getByRole("region", { name: "Report-derived findings" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Severity", exact: true })
    .selectOption("CRITICAL");
  await page.getByLabel("Rule ID", { exact: true }).fill(finding.rule_id);
  await page.getByLabel("File", { exact: true }).fill(finding.file!);
  const request = page.waitForRequest(
    (request) =>
      request.url().includes("/findings?") &&
      new URL(request.url()).searchParams.get("file") === finding.file,
  );
  await page.getByRole("button", { name: "Apply filters" }).click();
  await request;
  await page.getByRole("link", { name: finding.title, exact: true }).click();
  await expect(
    page.getByRole("heading", { name: finding.title, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Source code excerpt" }),
  ).toContainText('<script>alert("unsafe")</script>');
  const source = page.getByRole("region", { name: "Source code excerpt" });
  const firstLine = await source
    .getByText('<script>alert("unsafe")</script>', { exact: true })
    .boundingBox();
  const secondLine = await source
    .getByText('  acl = "public-read"', { exact: true })
    .boundingBox();
  expect(secondLine!.y).toBeGreaterThan(firstLine!.y);
  await expect(
    page.getByRole("link", { name: "javascript:alert(1)" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Recommended resolution" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "https://example.com/docs" }),
  ).toHaveAttribute("rel", "noopener noreferrer");
  await page.getByRole("link", { name: "Back to scan", exact: true }).click();
  await expect(page.getByLabel("Rule ID", { exact: true })).toHaveValue(
    finding.rule_id,
  );
  expect(dialogs).toEqual([]);
  expect(errors).toEqual([]);
});

test("failed analysis retains download, shows caller counts and allows explicit retry", async ({
  page,
}) => {
  let retried = false;
  await page.route(`https://api.example.com/v1/runs/${run.run_id}`, (route) =>
    route.fulfill({
      json: {
        ...run,
        analysis: {
          ...run.analysis,
          status: "failed",
          findings: null,
          error_code: "unsupported_report",
        },
      },
    }),
  );
  await page.route(
    `https://api.example.com/v1/runs/${run.run_id}/analysis/retry`,
    (route) => {
      retried = true;
      return route.fulfill({
        status: 202,
        json: {
          ...run,
          analysis: {
            ...run.analysis,
            status: "pending",
            build_id: "new-build",
            requested_at: new Date().toISOString(),
            findings: null,
          },
        },
      });
    },
  );
  await page.goto(`/runs/${run.run_id}`);
  await expect(
    page.getByRole("heading", { name: "Analysis could not be completed" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download JSON" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("region", { name: "CLI-reported findings" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Retry analysis", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Analysis is in progress" }),
  ).toBeVisible();
  expect(retried).toBe(true);
  await expect(
    page.getByRole("heading", { name: "Findings", exact: true }),
  ).toHaveCount(0);
});

test("pending uploads never appear as zero findings or offer a download", async ({
  page,
}) => {
  await page.route(`https://api.example.com/v1/runs/${run.run_id}`, (route) =>
    route.fulfill({
      json: { ...run, upload_status: "pending", analysis: undefined },
    }),
  );
  await page.goto(`/runs/${run.run_id}`);
  await expect(
    page.getByRole("heading", { name: "Report upload is not complete" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download JSON" }),
  ).toBeDisabled();
  await expect(page.getByText("total findings", { exact: true })).toHaveCount(
    0,
  );
});

test("pending analysis polls metadata and publishes findings when ready", async ({
  page,
}) => {
  let reads = 0;
  await page.route(`https://api.example.com/v1/runs/${run.run_id}`, (route) =>
    route.fulfill({
      json:
        ++reads === 1
          ? {
              ...run,
              analysis: {
                ...run.analysis,
                status: "pending",
                requested_at: new Date().toISOString(),
                findings: null,
              },
            }
          : run,
    }),
  );
  await page.goto(`/runs/${run.run_id}`);
  await expect(
    page.getByRole("heading", { name: "Analysis is in progress" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Findings", exact: true }),
  ).toBeVisible({ timeout: 10_000 });
  expect(reads).toBe(2);
});

for (const status of [202, 204]) {
  test(`delete ${status} removes the scan and returns to history`, async ({
    page,
  }) => {
    let removed = false;
    await page.route(
      `https://api.example.com/v1/runs/${run.run_id}`,
      (route) => {
        if (route.request().method() === "DELETE") {
          removed = true;
          return route.fulfill({
            status,
            ...(status === 202
              ? {
                  json: {
                    run_id: run.run_id,
                    upload_status: "deleting",
                    delete_after: new Date().toISOString(),
                  },
                }
              : {}),
          });
        }
        return route.fulfill({ json: run });
      },
    );
    await page.route("https://api.example.com/v1/runs?**", (route) =>
      route.fulfill({
        json: { items: removed ? [] : [run], next_cursor: null },
      }),
    );
    await page.goto(`/runs/${run.run_id}`);
    await page
      .getByRole("button", { name: "Delete scan", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page
      .getByRole("button", { name: "Confirm deletion", exact: true })
      .click();
    await expect(page).toHaveURL(`/projects/${run.project_id}`);
    await expect(
      page.getByRole("heading", { name: "No scans yet" }),
    ).toBeVisible();
    expect(removed).toBe(true);
  });
}

test("JSON download navigates to a fresh signed attachment URL", async ({
  page,
}) => {
  await page.route("https://downloads.example.com/**", (route) =>
    route.fulfill({
      headers: {
        "content-disposition": 'attachment; filename="report.json"',
        "content-type": "application/json",
      },
      body: '{"SchemaVersion":2}',
    }),
  );
  await page.goto(`/runs/${run.run_id}`);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON" }).click();
  expect((await download).suggestedFilename()).toBe("report.json");
});

test("counts mismatch and truncated fields remain visible", async ({
  page,
}) => {
  await page.route(`https://api.example.com/v1/runs/${run.run_id}`, (route) =>
    route.fulfill({
      json: { ...run, analysis: { ...run.analysis, counts_match: false } },
    }),
  );
  await page.route(
    `https://api.example.com/v1/runs/${run.run_id}/findings/${finding.finding_id}`,
    (route) =>
      route.fulfill({
        json: { ...finding, truncated_fields: ["code", "description"] },
      }),
  );
  await page.goto(`/runs/${run.run_id}`);
  await expect(page.getByText("Finding counts differ")).toBeVisible();
  await page.getByRole("link", { name: finding.title, exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Some content was shortened: code, description",
  );
});

test("a foreign or deleted scan shows an unavailable state", async ({
  page,
}) => {
  await page.route(`https://api.example.com/v1/runs/${run.run_id}`, (route) =>
    route.fulfill({
      status: 404,
      json: { error: { code: "not_found", message: "Not found" } },
    }),
  );
  await page.goto(`/runs/${run.run_id}`);
  await expect(page.getByRole("alert")).toContainText(
    "belongs to another account",
  );
  await expect(
    page.getByRole("heading", { name: "Findings", exact: true }),
  ).toHaveCount(0);
});

for (const width of [320, 768, 1440]) {
  test(`scan and finding detail accessibility at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    for (const path of [
      `/runs/${run.run_id}`,
      `/runs/${run.run_id}/findings/${finding.finding_id}`,
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      await page.screenshot({
        path: `test-results/${path.includes("/findings/") ? "finding" : "scan"}-${width}.png`,
        fullPage: true,
      });
    }
  });
}
