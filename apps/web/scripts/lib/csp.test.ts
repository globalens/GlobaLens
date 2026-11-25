import { createHash } from "node:crypto";
import { describe, expect, test } from "vitest";

import { checkPage, inlineScripts, policyFor, sha256Source, withMetaPolicy } from "./csp.ts";

// Shaped like Next's static export: charset first, then links and scripts, inline flight data.
const PAGE = [
  "<!DOCTYPE html><html lang=\"en\" dir=\"ltr\"><head><meta charSet=\"utf-8\"/>",
  "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>",
  "<link rel=\"stylesheet\" href=\"/_next/static/css/a1.css\" data-precedence=\"next\"/>",
  "<script src=\"/_next/static/chunks/main.js\" async=\"\"></script>",
  "<title>GlobaLens</title></head><body>",
  "<img id=\"gl-first-paint\" alt=\"Globe\"/><script>(function(){document.documentElement.dataset.x=\"1\"})()</script>",
  "<script>(self.__next_f=self.__next_f||[]).push([0])</script>",
  "<script>self.__next_f.push([1,\"0:{\\\"a\\\":\\\"\\u003c/script\\u003e\\\"}\\n\"])</script>",
  "</body></html>",
].join("");

const CONNECT = ["https://pub-0123abcd.r2.dev", "https://tiles.openfreemap.org"];

describe("inlineScripts", () => {
  test("returns the text of every <script> without a src, exactly as written", () => {
    const scripts = inlineScripts(PAGE);
    expect(scripts).toHaveLength(3);
    expect(scripts[0]).toBe('(function(){document.documentElement.dataset.x="1"})()');
    expect(scripts[2]).toContain("\\u003c/script\\u003e");
  });

  test("ignores external scripts and JSON data blocks", () => {
    expect(inlineScripts('<script src="/a.js"></script><script type="application/json">{"a":1}</script>')).toEqual([]);
  });
});

describe("sha256Source", () => {
  test("is the CSP hash source of the script's UTF-8 bytes", () => {
    const text = "alert('ü')";
    const expected = createHash("sha256").update(text, "utf8").digest("base64");
    expect(sha256Source(text)).toBe(`'sha256-${expected}'`);
  });
});

describe("policyFor: the plan's §9 policy for a static export", () => {
  const policy = policyFor(["'sha256-AAA='"], CONNECT);
  test.each([
    ["default-src 'none'"],
    ["script-src 'self' 'wasm-unsafe-eval' 'sha256-AAA='"],
    ["style-src 'self'"],
    ["img-src 'self'"],
    ["font-src 'self'"],
    ["connect-src 'self' https://pub-0123abcd.r2.dev https://tiles.openfreemap.org"],
    ["worker-src 'self' blob:"],
    ["base-uri 'none'"],
    ["form-action 'none'"],
  ])("has %s", (directive) => {
    expect(policy.split("; ")).toContain(directive);
  });

  test("never allows inline script or eval", () => {
    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("'unsafe-eval'");
  });

  test("frame-ancestors and report-only cannot live in a <meta> policy, so it has neither", () => {
    expect(policy).not.toContain("frame-ancestors");
    expect(policy).not.toContain("report-");
  });
});

describe("withMetaPolicy", () => {
  test("puts the policy right after the charset, before anything that loads", () => {
    const out = withMetaPolicy(PAGE, "default-src 'none'");
    expect(out).toContain(
      '<head><meta charSet="utf-8"/><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;"/><meta name="viewport"',
    );
  });

  test("refuses a page that already has one, or has no charset to follow", () => {
    const once = withMetaPolicy(PAGE, "default-src 'none'");
    expect(() => withMetaPolicy(once, "default-src 'none'")).toThrow(/already/);
    expect(() => withMetaPolicy("<html><head></head></html>", "x")).toThrow(/charset/);
  });
});

describe("checkPage: the header and script-policy check", () => {
  const good = withMetaPolicy(PAGE, policyFor(inlineScripts(PAGE).map(sha256Source), CONNECT));

  test("a page built by the post-export step passes", () => {
    expect(checkPage(good, CONNECT)).toEqual([]);
  });

  test("a page with no policy fails", () => {
    expect(checkPage(PAGE, CONNECT)).toContainEqual(expect.stringMatching(/no Content-Security-Policy/));
  });

  test("an inline script whose hash is missing fails", () => {
    const tampered = good.replace("dataset.x=\"1\"", "dataset.x=\"2\"");
    expect(checkPage(tampered, CONNECT).join("\n")).toMatch(/not allowed by the policy/);
  });

  test("a script from another origin fails", () => {
    const external = good.replace("</body>", '<script src="https://cdn.example/x.js"></script></body>');
    expect(checkPage(external, CONNECT).join("\n")).toMatch(/third-party script.*cdn\.example/);
  });

  test("a connect-src that differs from the configured hosts fails", () => {
    expect(checkPage(good, ["https://tiles.openfreemap.org"]).join("\n")).toMatch(/connect-src/);
  });

  test("a stylesheet, image or font from another origin fails", () => {
    const css = good.replace("</head>", '<link rel="stylesheet" href="https://fonts.example/a.css"/></head>');
    expect(checkPage(css, CONNECT).join("\n")).toMatch(/third-party.*fonts\.example/);
  });
});
