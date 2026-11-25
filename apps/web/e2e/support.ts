// Shared helpers for the browser checks.
import type { Page, Route } from "@playwright/test";

export const ORIGIN = "http://127.0.0.1:4321";
export const STRINGS = {
  failed: "Couldn’t load the latest data.",
  retry: "Retry",
  noWebgl: "The SVG globe stays, with this list.",
  paused: "Live updates paused; history and cached pages still work",
};

const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");

/** A version 1 now.json (pull request 16's shape), with stamps the given minutes before `now`. */
export function nowJson(now: number, { stampAgo = 10, writtenAgo = 2 }: { stampAgo?: number; writtenAgo?: number } = {}) {
  const stamp = now - stampAgo * 60_000;
  return {
    manifest: "live/dt=2026-11-14/manifest/0f1e2d3c.json",
    seq: 412,
    streams: {
      english: { listed_at: iso(stamp + 4 * 60_000), stamp: iso(stamp) },
      translated: { listed_at: iso(stamp + 6 * 60_000), stamp: iso(stamp) },
    },
    v: 1,
    written_at: iso(now - writtenAgo * 60_000),
  };
}

/** Answer the local data plane's now.json with a body, an HTTP error, or after a delay. */
export async function serveNow(page: Page, answer: { body?: unknown; status?: number; delayMs?: number }) {
  await page.route("**/data/now.json", async (route: Route) => {
    if (answer.delayMs) await new Promise((resolve) => setTimeout(resolve, answer.delayMs));
    if (answer.status && answer.status >= 400) return route.fulfill({ status: answer.status, body: "" });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(answer.body) });
  });
}

/** Make WebGL2 unavailable before any script of the page runs. */
export async function withoutWebGL2(page: Page) {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    // @ts-expect-error -- narrowing the overloads is not the point of a test stub
    HTMLCanvasElement.prototype.getContext = function (type: string, ...rest: unknown[]) {
      return type === "webgl2" ? null : original.call(this, type as "2d", ...(rest as []));
    };
  });
}

/** Collect every CSP violation the page reports, enforced or report-only. */
export async function recordViolations(page: Page) {
  await page.addInitScript(() => {
    const seen: { directive: string; blocked: string; disposition: string; sample: string }[] = [];
    (window as unknown as { __violations: typeof seen }).__violations = seen;
    document.addEventListener("securitypolicyviolation", (event) => {
      seen.push({
        directive: event.effectiveDirective,
        blocked: event.blockedURI,
        disposition: event.disposition,
        sample: event.sample,
      });
    });
  });
}

export async function violations(page: Page) {
  return page.evaluate(() => (window as unknown as { __violations: { directive: string; blocked: string; disposition: string; sample: string }[] }).__violations ?? []);
}
