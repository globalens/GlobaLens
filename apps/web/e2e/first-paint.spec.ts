// The first paint (design note §3.1, §9 task 12; Q9): an SVG globe at the visitor's longitude,
// guessed from the time-zone offset, painted before React loads.
import { expect, test } from "@playwright/test";

import { serveNow, nowJson } from "./support";

for (const [zone, file, lon] of [
  ["Europe/Kyiv", "e030.svg", "30"],
  ["America/New_York", "w075.svg", "-75"],
  ["Asia/Tokyo", "e135.svg", "135"],
  ["Pacific/Honolulu", "w150.svg", "-150"],
] as const) {
  test.describe(`in ${zone}`, () => {
    test.use({ timezoneId: zone });

    test(`faces ${lon}°`, async ({ page }) => {
      await serveNow(page, { body: nowJson(Date.now()) });
      await page.goto("/");
      const globe = page.locator("#gl-first-paint");
      await expect(globe).toHaveAttribute("src", `/globe/${file}`);
      await expect.poll(() => globe.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.dataset["globeLon"])).toBe(lon);
    });
  });
}

test("the SVG globe paints in under a second on a throttled phone-like connection and CPU", async ({ page, browserName }, info) => {
  test.skip(browserName !== "chromium", "CPU and network throttling need the Chrome DevTools Protocol");
  const cdp = await page.context().newCDPSession(page);
  // About a mid-range phone on fast 4G: 4x slower CPU, 150 ms latency, 9 Mbit/s down.
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 150,
    downloadThroughput: (9 * 1024 * 1024) / 8,
    uploadThroughput: (1.5 * 1024 * 1024) / 8,
  });
  await serveNow(page, { body: nowJson(Date.now()) });
  await page.goto("/");
  const painted = await page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries() as (PerformanceEntry & { identifier: string; renderTime: number; loadTime: number })[]) {
            if (entry.identifier === "first-paint-globe") resolve(entry.renderTime || entry.loadTime);
          }
        }).observe({ type: "element", buffered: true });
      }),
  );
  info.annotations.push({ type: "SVG globe painted (ms after navigation start, throttled)", description: painted.toFixed(0) });
  console.log(`[${info.project.name}] SVG globe painted at ${painted.toFixed(0)} ms (4x CPU, 150 ms, 9 Mbit/s)`);
  expect(painted).toBeLessThan(1000);
});

test("the globe is centred in the area the panel or drawer leaves", async ({ page }, info) => {
  await serveNow(page, { body: nowJson(Date.now()) });
  await page.goto("/");
  const box = await page.locator("#gl-first-paint").boundingBox();
  if (!box) throw new Error("the globe image has no box");
  const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  if (info.project.name === "desktop") {
    // Frame 1: top bar 44 px, panel 360 px; ring 160 px at 3,000 km gives a 353 px radius.
    expect(centre.x).toBeCloseTo(360 + (1440 - 360) / 2, 0);
    expect(centre.y).toBeCloseTo(44 + (900 - 44) / 2, 0);
    expect(box.width).toBeCloseTo(2.16 * 352.68, 0);
  } else {
    // Frame 3, detent 1: top bar 48 px, drawer 120 px; ring 104 px gives a 229 px radius.
    expect(centre.x).toBeCloseTo(195, 0);
    expect(centre.y).toBeCloseTo(48 + (844 - 48 - 120) / 2, 0);
    expect(box.width).toBeCloseTo(2.16 * 229.24, 0);
  }
});

// The hook task 13 crossfades into: when its first WebGL frame is drawn it calls setWebGL("ready"),
// which sets data-webgl="ready" on the globe layout. Here the attribute is set directly.
for (const motion of ["no-preference", "reduce"] as const) {
  test(`WebGL ready: the SVG globe fades out (${motion === "reduce" ? "a cut under reduced motion" : "400 ms"})`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: motion });
    await serveNow(page, { body: nowJson(Date.now()) });
    await page.goto("/");
    const globe = page.locator("#gl-first-paint");
    await expect(globe).toHaveCSS("opacity", "1");
    const duration = await globe.evaluate((img) => getComputedStyle(img).transitionDuration);
    expect(duration.split(",")[0]?.trim()).toBe(motion === "reduce" ? "0s" : "0.4s");
    await page.evaluate(() => document.querySelector("[data-webgl]")?.setAttribute("data-webgl", "ready"));
    await expect(globe).toHaveCSS("opacity", "0");
    await page.evaluate(() => document.querySelector("[data-webgl]")?.setAttribute("data-webgl", "lost"));
    await expect(globe).toHaveCSS("opacity", "1");
  });
}
