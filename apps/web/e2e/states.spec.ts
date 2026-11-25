// The plain P1 states (design note Q7; frame 2, column C), with the plan's copy.
import { expect, test } from "@playwright/test";

import { nowJson, serveNow, STRINGS, withoutWebGL2 } from "./support";

const panel = (page: import("@playwright/test").Page) => page.getByRole("complementary", { name: "In the Lens" });

test("fresh data shows no state", async ({ page }) => {
  await serveNow(page, { body: nowJson(Date.now()) });
  await page.goto("/");
  await expect(panel(page).getByRole("heading", { name: "In the Lens" })).toBeVisible();
  await page.waitForTimeout(1500);
  await expect(panel(page).getByRole("status")).toBeEmpty();
});

test("no data plane: the failed state, and Retry recovers", async ({ page }) => {
  let fail = true;
  await page.route("**/data/now.json", (route) =>
    fail
      ? route.fulfill({ status: 503, body: "" })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(nowJson(Date.now())) }),
  );
  await page.goto("/");
  await expect(panel(page).getByText(STRINGS.failed)).toBeVisible();
  // A first load that failed has no last good data to name.
  await expect(panel(page).getByText(/Showing data from/)).toHaveCount(0);
  fail = false;
  await panel(page).getByRole("button", { name: STRINGS.retry }).click();
  await expect(panel(page).getByText(STRINGS.failed)).toHaveCount(0);
});

test("loading shows nothing for a second, then a skeleton", async ({ page }) => {
  await serveNow(page, { body: nowJson(Date.now()), delayMs: 4000 });
  await page.goto("/");
  await expect(panel(page).locator("[aria-busy=true]")).toHaveCount(0);
  await expect(panel(page).locator("[aria-busy=true]")).toBeVisible({ timeout: 3000 });
  await expect(panel(page).locator("[aria-busy=true]")).toHaveCount(0, { timeout: 6000 });
});

test("stale over 45 minutes: the warning badge names the last stamp in UTC", async ({ page }) => {
  const now = Date.parse("2026-11-14T14:50:00Z");
  await page.clock.setFixedTime(now);
  await serveNow(page, { body: nowJson(now, { stampAgo: 50, writtenAgo: 3 }) });
  await page.goto("/");
  await expect(panel(page).getByText("GDELT hasn’t published since 14:00 UTC; showing the last good data")).toBeVisible();
});

test("now.json itself over 45 minutes old: publishing has paused", async ({ page }) => {
  const now = Date.parse("2026-11-14T15:00:00Z");
  await page.clock.setFixedTime(now);
  await serveNow(page, { body: nowJson(now, { stampAgo: 70, writtenAgo: 50 }) });
  await page.goto("/");
  await expect(panel(page).getByText(STRINGS.paused)).toBeVisible();
});

test("no WebGL2: the SVG globe stays, and the panel says so", async ({ page }) => {
  await withoutWebGL2(page);
  await serveNow(page, { body: nowJson(Date.now()) });
  await page.goto("/");
  await expect(panel(page).getByText(STRINGS.noWebgl)).toBeVisible();
  await expect(page.locator("#gl-first-paint")).toBeVisible();
});

test("on a phone the drawer steps through its three detents", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the drawer is the phone layout");
  await serveNow(page, { body: nowJson(Date.now()) });
  await page.goto("/");
  const drawer = panel(page);
  const handle = drawer.getByRole("button", { name: "Show more of the list" });
  const height = async () => (await drawer.boundingBox())?.height ?? 0;
  await expect.poll(height).toBeCloseTo(120, 0);
  await handle.click();
  await expect.poll(height).toBeCloseTo(844 * 0.5, 0);
  await drawer.getByRole("button", { name: "Show more of the list" }).click();
  await expect.poll(height).toBeCloseTo(844 * 0.92, 0);
  await drawer.getByRole("button", { name: "Show less of the list" }).click();
  await expect.poll(height).toBeCloseTo(120, 0);
});
