// Browser checks on the built static export (ADR-0018): the first paint, the plain states, the
// story link rule, the CSP and headers, no third-party request, axe, and the owner's screenshots.
//
//   pnpm build && pnpm e2e        (mise run web:e2e does both)
//
// The browser is the installed Google Chrome unless GLOBALENS_BROWSER_CHANNEL says otherwise
// (CI may install Playwright's own Chromium and set it to "chromium").
import { defineConfig } from "@playwright/test";

const PORT = 4321;
const channel = process.env["GLOBALENS_BROWSER_CHANNEL"] ?? "chrome";

export default defineConfig({
  testDir: "e2e",
  outputDir: "test-results",
  reporter: [["list"]],
  forbidOnly: true,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    ...(channel === "chromium" ? {} : { channel }),
    timezoneId: "Europe/Kyiv",
    locale: "en-GB",
    colorScheme: "dark",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "phone", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 } },
  ],
  webServer: {
    command: `node scripts/serve.ts --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: false,
  },
});
