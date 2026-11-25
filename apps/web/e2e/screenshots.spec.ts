// Screenshots of the built shell for the owner to set beside the visual target: frame 1's desktop
// size (1440 x 900) and frame 3's phone size (390 x 844). Written to GLOBALENS_SCREENSHOT_DIR, or
// test-results/screenshots. The clock is fixed so the times in them do not move.
import { test, type Page } from "@playwright/test";

import { nowJson, serveNow, withoutWebGL2 } from "./support";

const DIR = process.env["GLOBALENS_SCREENSHOT_DIR"] ?? "test-results/screenshots";
const NOW = Date.parse("2026-11-14T14:20:00Z");

async function shoot(page: Page, name: string, project: string) {
  await page.waitForTimeout(400);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${DIR}/${project}-${name}.png` });
}

test("fresh: the globe at the visitor's longitude, the panel with no state", async ({ page }, info) => {
  await page.clock.setFixedTime(NOW);
  await serveNow(page, { body: nowJson(NOW) });
  await page.goto("/");
  await shoot(page, "fresh", info.project.name);
});

test("failed: no data plane yet", async ({ page }, info) => {
  await page.clock.setFixedTime(NOW);
  await serveNow(page, { status: 503 });
  await page.goto("/");
  await page.getByText("Couldn’t load the latest data.").waitFor();
  await shoot(page, "failed", info.project.name);
});

test("stale, and no WebGL2", async ({ page }, info) => {
  await page.clock.setFixedTime(NOW);
  await withoutWebGL2(page);
  await serveNow(page, { body: nowJson(NOW, { stampAgo: 50, writtenAgo: 3 }) });
  await page.goto("/");
  await page.getByText("The SVG globe stays, with this list.").waitFor();
  if (info.project.name === "phone") await page.getByRole("button", { name: "Show more of the list" }).click();
  await shoot(page, "stale-no-webgl", info.project.name);
});
