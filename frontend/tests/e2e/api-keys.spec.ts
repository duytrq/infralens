import { test, expect } from "@playwright/test";
import { config, mockApi } from "./fixtures";

test("creates a key that is shown once and revokes it", async ({ page }) => {
  await mockApi(page);
  await page.route("https://api.example.com/v1/dashboard-config", (route) => route.fulfill({ json: { ...config, auth: { ...config.auth, allowed_origins: [...config.auth.allowed_origins, "http://localhost:5174"] } } }));
  let exists = false;
  const id = "a".repeat(32);
  const secret = `il_key_${id}_${"b".repeat(43)}`;
  const metadata = { key_id: id, name: "CI", created_at: "2026-10-29T00:00:00Z", expires_at: null };
  await page.route("https://api.example.com/v1/api-keys**", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer test-access-token");
    if (route.request().method() === "POST") {
      expect(route.request().postDataJSON()).toEqual({ name: "CI", expires_in_days: null });
      exists = true;
      return route.fulfill({ status: 201, json: { ...metadata, api_key: secret } });
    }
    if (route.request().method() === "DELETE") {
      exists = false;
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ json: { items: exists ? [metadata] : [], next_cursor: null } });
  });
  await page.goto("/api-keys");
  await page.getByRole("button", { name: "Create API key" }).click();
  await page.getByLabel("Name").fill("CI");
  await page.getByLabel("Expiration").selectOption("never");
  await page.getByRole("button", { name: "Create key" }).click();
  await expect(page.getByLabel("API key", { exact: true })).toHaveValue(secret);
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText(secret)).toHaveCount(0);
  await expect(page.getByText("CI", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("No API keys yet.")).toBeVisible();
});
