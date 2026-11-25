import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

import { checkHeadersFile, headersFor, parseHeadersFile } from "./headers.ts";

const FILE = readFileSync(new URL("../../public/_headers", import.meta.url), "utf8");

describe("the static-asset headers file (public/_headers)", () => {
  test("parses into path rules", () => {
    const rules = parseHeadersFile("# comment\n/*\n  X-A: 1\n  X-B: two words\n/_next/static/*\n  Cache-Control: max-age=1\n");
    expect(rules).toEqual([
      { pattern: "/*", headers: [["X-A", "1"], ["X-B", "two words"]] },
      { pattern: "/_next/static/*", headers: [["Cache-Control", "max-age=1"]] },
    ]);
  });

  test("every page gets the plan's headers (§9, §15)", () => {
    const page = Object.fromEntries(headersFor(parseHeadersFile(FILE), "/"));
    expect(page["Strict-Transport-Security"]).toMatch(/^max-age=\d{8,}/);
    expect(page["X-Content-Type-Options"]).toBe("nosniff");
    expect(page["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(page["Content-Security-Policy"]).toBe("frame-ancestors 'none'");
  });

  test("Trusted Types is report-only in P1, with one named policy", () => {
    const page = Object.fromEntries(headersFor(parseHeadersFile(FILE), "/story/abc"));
    expect(page["Content-Security-Policy-Report-Only"]).toMatch(/require-trusted-types-for 'script'/);
    expect(page["Content-Security-Policy-Report-Only"]).toMatch(/trusted-types globalens-worker-url/);
    expect(page["Content-Security-Policy"]).not.toMatch(/require-trusted-types-for/);
  });

  test("hashed build output is cached for good; nothing else is", () => {
    const rules = parseHeadersFile(FILE);
    expect(Object.fromEntries(headersFor(rules, "/_next/static/chunks/a1b2.js"))["Cache-Control"]).toBe(
      "public, max-age=31536000, immutable",
    );
    expect(Object.fromEntries(headersFor(rules, "/"))["Cache-Control"]).toBeUndefined();
  });

  test("the check passes on the committed file and stays within the line limits we assume", () => {
    expect(checkHeadersFile(FILE)).toEqual([]);
  });

  test("the check names what is missing", () => {
    expect(checkHeadersFile("/*\n  X-Content-Type-Options: nosniff\n").join("\n")).toMatch(/Strict-Transport-Security/);
  });
});
