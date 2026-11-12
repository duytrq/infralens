import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi, config, project } from "./fixtures";

test("sign-in sends PKCE S256 and uses the active localhost callback", async ({
  page,
}) => {
  await mockApi(page, false);
  await page.route("https://login.example.com/oauth2/authorize?**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: '<html lang="en"><title>Sign in</title><body>Identity provider</body></html>',
    }),
  );
  await page.goto("/projects/production-infra");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/login.example.com\/oauth2\/authorize/);
  const url = new URL(page.url());
  expect(url.searchParams.get("client_id")).toBe(config.auth.client_id);
  expect(url.searchParams.get("redirect_uri")).toBe(
    "http://localhost:5173/auth/callback",
  );
  expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  expect(url.searchParams.get("code_challenge")).toHaveLength(43);
  expect(url.searchParams.get("state")).toBeTruthy();
  expect(url.searchParams.get("nonce")).toBeTruthy();
});

test("callback rejects missing state and clears callback parameters", async ({
  page,
}) => {
  await mockApi(page, false);
  await page.goto("/auth/callback?code=untrusted&state=missing");
  await expect(page.getByRole("alert")).toContainText(
    "Sign-in could not be verified",
  );
  await expect(page).toHaveURL("/auth/callback");
});

test("gateway 401 clears the authenticated view", async ({ page }) => {
  await mockApi(page);
  await page.route("https://api.example.com/v1/projects?**", (route) =>
    route.fulfill({ status: 401, json: { message: "Unauthorized" } }),
  );
  await page.goto("/projects");
  await expect(
    page.getByRole("button", { name: "Sign in" }),
  ).toBeVisible();
  await expect(page.getByText("Authenticated workspace")).toHaveCount(0);
});

for (const succeeds of [true, false]) {
  test(`an expired session ${succeeds ? "renews before API access" : "returns to sign in when renewal fails"}`, async ({
    page,
  }) => {
    await mockApi(page);
    await page.addInitScript(
      ({ issuer, client }) => {
        const key = `oidc.user:${issuer}:${client}`;
        const session = JSON.parse(sessionStorage.getItem(key)!);
        session.expires_at = Math.floor(Date.now() / 1000) - 60;
        sessionStorage.setItem(key, JSON.stringify(session));
      },
      { issuer: config.auth.issuer, client: config.auth.client_id },
    );
    let refreshes = 0;
    await page.route(config.auth.token_endpoint, (route) => {
      refreshes++;
      return route.fulfill({
        status: succeeds ? 200 : 400,
        json: succeeds
          ? {
              access_token: "renewed-test-access",
              refresh_token: "renewed-test-refresh",
              token_type: "Bearer",
              expires_in: 900,
              scope: "openid infralens/api",
            }
          : { error: "invalid_grant" },
      });
    });
    await page.route("https://api.example.com/v1/projects?**", (route) => {
      expect(route.request().headers().authorization).toBe(
        "Bearer renewed-test-access",
      );
      return route.fulfill({ json: { items: [project], next_cursor: null } });
    });
    await page.goto("/projects");
    if (succeeds)
      await expect(
        page.getByRole("link", { name: project.name, exact: false }).first(),
      ).toBeVisible();
    else
      await expect(
        page.getByRole("button", { name: "Sign in" }),
      ).toBeVisible();
    expect(refreshes).toBe(1);
  });
}

test("sign-in page has no accessibility violations at 320px and 1440px", async ({
  page,
}) => {
  await mockApi(page, false);
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: "Sign in" }),
    ).toBeEnabled();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: `test-results/sign-in-${width}.png`,
      fullPage: true,
    });
  }
});
