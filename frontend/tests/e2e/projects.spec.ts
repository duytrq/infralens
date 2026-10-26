import AxeBuilder from "@axe-core/playwright";
import { test, expect, project, run } from "./fixtures";

test("projects link to history, exact date filters survive reload", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/projects");
  await expect(
    page.getByRole("heading", { name: "Projects", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: project.name, exact: false })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: project.name, exact: true }),
  ).toBeVisible();
  await page.getByLabel("Started from").fill("2026-10-20T10:00");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/from=/);
  await page.reload();
  await expect(page.getByLabel("Started from")).toHaveValue("2026-10-20T10:00");
  await expect(
    page.getByRole("link", { name: `Open scan ${run.run_id.slice(0, 8)}` }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("a filtered empty page still permits loading the next cursor", async ({
  page,
}) => {
  await page.route("https://api.example.com/v1/projects?**", (route) =>
    route.fulfill({
      json: new URL(route.request().url()).searchParams.has("cursor")
        ? { items: [project], next_cursor: null }
        : { items: [], next_cursor: "opaque-cursor" },
    }),
  );
  await page.goto("/projects");
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(
    page.getByRole("link", { name: project.name, exact: false }).first(),
  ).toBeVisible();
});

test("create project uses an explicit permanent ID and handles conflicts", async ({
  page,
}) => {
  await page.route("https://api.example.com/v1/projects/existing", (route) =>
    route.fulfill({
      status: 409,
      json: {
        error: {
          code: "conflict",
          message: "Project ID already exists with a different name.",
        },
      },
    }),
  );
  await page.goto("/projects");
  await page.getByRole("button", { name: "New project" }).click();
  await page
    .getByLabel("Project name", { exact: true })
    .fill("Another project");
  await page.getByLabel("Project ID", { exact: true }).fill("existing");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("already exists");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "New project" })).toBeFocused();
});

for (const width of [320, 768, 1024, 1440]) {
  test(`projects layout and accessibility at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/projects");
    await expect(
      page.getByRole("link", { name: project.name, exact: false }).first(),
    ).toBeVisible();
    const violations = (await new AxeBuilder({ page }).analyze()).violations;
    expect(violations).toEqual([]);
    const layout = await page.evaluate(() => ({
      width: window.innerWidth,
      document: document.documentElement.scrollWidth,
      overflow: [...document.querySelectorAll("body *")]
        .filter(
          (node) => node.getBoundingClientRect().right > window.innerWidth,
        )
        .slice(0, 15)
        .map((node) => ({
          tag: node.tagName,
          class: node.className,
          right: node.getBoundingClientRect().right,
        })),
    }));
    expect(layout.document, JSON.stringify(layout)).toBeLessThanOrEqual(
      layout.width,
    );
    await page.screenshot({
      path: `test-results/projects-${width}.png`,
      fullPage: true,
    });
  });
}
