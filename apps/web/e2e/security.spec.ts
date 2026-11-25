// The headers file, the <meta> CSP (Q21), Trusted Types in report-only mode, and no third-party
// request from any page (master plan §9; design note §9 task 12 and §10).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { nowJson, ORIGIN, recordViolations, serveNow, violations, withoutWebGL2 } from "./support";

const ROUTES = ["/", "/story/abc123", "/nowhere"];

async function load(page: Page, path: string) {
  await recordViolations(page);
  await serveNow(page, { body: nowJson(Date.now()) });
  const requests: string[] = [];
  const errors: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  const response = await page.goto(path);
  await page.waitForLoadState("networkidle");
  return { response, requests, errors };
}

for (const path of ROUTES) {
  test(`${path}: no enforced CSP violation, no error, no request to another origin`, async ({ page }, info) => {
    const { requests, errors } = await load(page, path);
    const all = await violations(page);
    const enforced = all.filter((v) => v.disposition === "enforce");
    const reported = all.filter((v) => v.disposition === "report");
    if (reported.length) {
      info.annotations.push({ type: "Trusted Types report-only", description: JSON.stringify(reported) });
      console.log(`[${info.project.name}] ${path}: report-only violations: ${JSON.stringify(reported)}`);
    }
    expect(enforced).toEqual([]);
    expect(errors.filter((text) => !text.includes("404 (Not Found)"))).toEqual([]);
    expect(requests.filter((url) => !url.startsWith(`${ORIGIN}/`) && !url.startsWith("data:"))).toEqual([]);
  });
}

test("the page's policy is a <meta> tag ahead of every script, from default-src 'none'", async ({ page }) => {
  await load(page, "/");
  const first = await page.evaluate(() => {
    const meta = document.head.querySelector('meta[http-equiv="Content-Security-Policy"]');
    const firstScript = document.head.querySelector("script, link[rel=stylesheet]");
    return {
      policy: meta?.getAttribute("content") ?? "",
      before: !!meta && !!firstScript && !!(meta.compareDocumentPosition(firstScript) & Node.DOCUMENT_POSITION_FOLLOWING),
    };
  });
  expect(first.before).toBe(true);
  expect(first.policy).toMatch(/^default-src 'none'; script-src 'self' 'wasm-unsafe-eval' 'sha256-/);
  expect(first.policy).toContain("connect-src 'self' https://tiles.openfreemap.org");
  expect(first.policy).not.toContain("unsafe-inline");
});

test("the headers file's headers reach every response", async ({ page }) => {
  const { response } = await load(page, "/");
  if (!response) throw new Error("no response for /");
  const headers = response.headers();
  expect(headers["strict-transport-security"]).toMatch(/^max-age=63072000/);
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(headers["content-security-policy"]).toBe("frame-ancestors 'none'");
  expect(headers["content-security-policy-report-only"]).toContain("require-trusted-types-for 'script'");
});

test("an inline script whose hash is not in the policy is blocked", async ({ page }) => {
  await recordViolations(page);
  await serveNow(page, { body: nowJson(Date.now()) });
  await page.route("**/", async (route) => {
    const response = await route.fetch();
    const html = (await response.text()).replace("</body>", "<script>window.__planted = 1</script></body>");
    await route.fulfill({ response, body: html });
  });
  await page.goto("/");
  expect(await page.evaluate(() => (window as unknown as { __planted?: number }).__planted)).toBeUndefined();
  expect((await violations(page)).some((v) => v.directive === "script-src-elem" && v.disposition === "enforce")).toBe(true);
});

for (const [name, setup] of [
  ["fresh", async (page: Page) => serveNow(page, { body: nowJson(Date.now()) })],
  ["failed", async (page: Page) => serveNow(page, { status: 503 })],
  ["stale", async (page: Page) => serveNow(page, { body: nowJson(Date.now(), { stampAgo: 60, writtenAgo: 2 }) })],
  ["no WebGL2", async (page: Page) => (await withoutWebGL2(page), serveNow(page, { body: nowJson(Date.now()) }))],
] as const) {
  test(`axe: no serious or critical violation (${name})`, async ({ page }) => {
    await setup(page);
    await page.goto("/");
    await page.waitForTimeout(1500);
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });
}

test("axe: the not-found page", async ({ page }) => {
  await page.goto("/nowhere");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
});
