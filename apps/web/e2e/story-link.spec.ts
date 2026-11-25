// The story link rule (master plan §4; design note §9 task 12 and §10): an unknown /story/<id>
// lands on the globe with ?story=<id>.
import { expect, test } from "@playwright/test";

import { nowJson, ORIGIN, serveNow } from "./support";

test.beforeEach(async ({ page }) => {
  await serveNow(page, { body: nowJson(Date.now()) });
});

for (const [path, query] of [
  ["/story/abc123", "?story=abc123"],
  ["/story/2027-02-24-flood_a/", "?story=2027-02-24-flood_a"],
  ["/story/a%20b", "?story=a%20b"],
] as const) {
  test(`${path} lands on the globe with ${query}`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(404); // the host serves the not-found page
    await page.waitForURL(`${ORIGIN}/${query}`);
    await expect(page.locator("#gl-first-paint")).toBeVisible();
  });
}

test("any other unknown path is a plain not-found page", async ({ page }) => {
  const response = await page.goto("/nowhere");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await expect(page).toHaveURL(`${ORIGIN}/nowhere`);
  await page.getByRole("link", { name: "Back to the globe" }).click();
  await expect(page.locator("#gl-first-paint")).toBeVisible();
});
