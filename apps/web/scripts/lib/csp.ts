// The Content Security Policy of plan §9, applied by the mechanism design note Q21 chose: a <meta>
// policy in each exported page, carrying the hashes of that page's inline scripts, written by a
// step that runs after `next build`. Nothing renders per request, so there are no nonces.
//
// Next's export is regular, machine-written HTML: every inline script it emits escapes "</" in
// its text, so a regular expression finds each <script> element exactly. The browser test checks
// the result independently: a hash this step got wrong is a CSP violation there.
import { createHash } from "node:crypto";

const SCRIPT = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi;
const CSP_META = /<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]*)"\s*\/?>/gi;
const CHARSET = /<meta\s+charset="[^"]*"\s*\/?>/i;
const EXECUTABLE = /^(?:text\/javascript|application\/javascript|module)$/i;

/** The text of every inline <script> a browser would run, exactly as written. */
export function inlineScripts(html: string): string[] {
  const scripts: string[] = [];
  for (const match of html.matchAll(SCRIPT)) {
    const attributes = match[1] ?? "";
    if (/\ssrc\s*=/i.test(attributes)) continue;
    const type = /\stype\s*=\s*"([^"]*)"/i.exec(attributes)?.[1];
    if (type !== undefined && type !== "" && !EXECUTABLE.test(type)) continue; // a data block
    scripts.push(match[2] ?? "");
  }
  return scripts;
}

/** The CSP hash source for a script's text. */
export function sha256Source(text: string): string {
  return `'sha256-${createHash("sha256").update(text, "utf8").digest("base64")}'`;
}

/**
 * The page policy: nothing by default, our own scripts and the page's own inline scripts, our own
 * styles, images and fonts, and connections to our own origin plus the configured hosts (the data
 * plane and OpenFreeMap's tile host). Workers may come from our origin or a blob: (MapLibre,
 * deck.gl and, from P2, the Lens worker).
 */
export function policyFor(hashes: readonly string[], connect: readonly string[]): string {
  return [
    "default-src 'none'",
    ["script-src 'self' 'wasm-unsafe-eval'", ...new Set(hashes)].join(" "),
    "style-src 'self'",
    "img-src 'self'",
    "font-src 'self'",
    ["connect-src 'self'", ...connect].join(" "),
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "base-uri 'none'",
    "form-action 'none'",
  ].join("; ");
}

function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function unescapeAttribute(value: string): string {
  return value.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}

/**
 * Insert the policy right after the charset declaration, ahead of every script, stylesheet and
 * link: a <meta> policy governs only what the parser meets after it.
 */
export function withMetaPolicy(html: string, policy: string): string {
  if (html.search(CSP_META) !== -1) throw new Error("the page already has a Content-Security-Policy <meta>");
  const charset = CHARSET.exec(html);
  if (!charset) throw new Error("no <meta charset> to put the policy after");
  const at = charset.index + charset[0].length;
  return `${html.slice(0, at)}<meta http-equiv="Content-Security-Policy" content="${escapeAttribute(policy)}"/>${html.slice(at)}`;
}

function directives(policy: string): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const part of policy.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) map.set(name.toLowerCase(), sources);
  }
  return map;
}

const ATTRIBUTE_URL = /<(script|link|img|iframe|source|video|audio|embed|object)\b([^>]*?)\s(src|href|data)="([^"]*)"/gi;
const ABSOLUTE = /^(?:[a-z][a-z0-9+.-]*:)?\/\//i;

/** The header and script-policy check for one exported page. An empty list means it passes. */
export function checkPage(html: string, connect: readonly string[]): string[] {
  const problems: string[] = [];
  const metas = [...html.matchAll(CSP_META)];
  if (metas.length === 0) return ["no Content-Security-Policy <meta>"];
  if (metas.length > 1) problems.push("more than one Content-Security-Policy <meta>");
  const meta = metas[0] as RegExpExecArray;
  const firstLoad = html.search(/<(script|link|style)\b/i);
  if (firstLoad !== -1 && firstLoad < meta.index) problems.push("the policy comes after a script, stylesheet or link");

  const policy = directives(unescapeAttribute(meta[1] ?? ""));
  if (policy.get("default-src")?.join(" ") !== "'none'") problems.push("default-src is not 'none'");
  const script = policy.get("script-src") ?? [];
  if (script[0] !== "'self'" || script[1] !== "'wasm-unsafe-eval'") problems.push("script-src does not start with 'self' 'wasm-unsafe-eval'");
  const allowed = new Set(script.slice(2));
  for (const source of allowed) {
    if (!/^'sha256-[A-Za-z0-9+/]+={0,2}'$/.test(source)) problems.push(`script-src allows ${source}`);
  }
  const hashes = inlineScripts(html).map(sha256Source);
  hashes.forEach((hash, i) => {
    if (!allowed.has(hash)) problems.push(`inline script ${i + 1} (${hash}) is not allowed by the policy`);
  });
  for (const source of allowed) {
    if (!hashes.includes(source)) problems.push(`the policy allows ${source}, which is not on the page`);
  }
  const expected = ["'self'", ...connect].sort().join(" ");
  const actual = [...(policy.get("connect-src") ?? [])].sort().join(" ");
  if (actual !== expected) problems.push(`connect-src is "${actual}", expected "${expected}"`);

  for (const match of html.matchAll(ATTRIBUTE_URL)) {
    const [, element = "", , , url = ""] = match;
    if (!ABSOLUTE.test(url)) continue;
    const what = element.toLowerCase() === "script" ? "third-party script" : `third-party ${element.toLowerCase()}`;
    problems.push(`${what}: ${url}`);
  }
  return problems;
}
