import { test, expect, run, config } from "./fixtures";

test("refresh hides cached scan data when the backend reports deletion", async ({
  page,
}) => {
  let deleted = false;
  await page.route(`https://api.example.com/v1/runs/${run.run_id}`, (route) =>
    route.fulfill(
      deleted
        ? {
            status: 404,
            json: { error: { code: "not_found", message: "Not found" } },
          }
        : { json: run },
    ),
  );
  await page.goto(`/runs/${run.run_id}`);
  await expect(
    page.getByRole("heading", { name: "Findings", exact: true }),
  ).toBeVisible();
  deleted = true;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "This item is unavailable",
  );
  await expect(
    page.getByRole("heading", { name: "Findings", exact: true }),
  ).toHaveCount(0, { timeout: 1500 });
});

test("sign-out still clears the hosted session when token revocation is unavailable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route(config.auth.revocation_endpoint, (route) =>
    route.fulfill({ status: 503, json: { error: "temporarily_unavailable" } }),
  );
  await page.route(config.auth.logout_endpoint + "?**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: '<html lang="en"><title>Signed out</title><body>Signed out</body></html>',
    }),
  );
  await page.goto("/projects");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/login.example.com\/logout/);
  expect(new URL(page.url()).searchParams.get("logout_uri")).toBe(
    "http://localhost:5173/",
  );
  expect(errors).toEqual([]);
});
