// Bundle budgets (master plan §4 "Design-system tooling"; ADR-0019): the initial route is at most
// 200 kB gzipped. The globe chunk (at most 800 kB, loaded after the SVG paint) gets its own entry
// with task 13. Fonts are reported by scripts/check-export.ts, not budgeted (plan §11).
//
// The files are the ones out/index.html loads: its scripts, its script preloads and its
// stylesheets. A nomodule script is left out: browsers that run modules never fetch it.
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("./out/index.html", import.meta.url), "utf8");
const scripts = [...html.matchAll(/<script\b[^>]*\bsrc="(\/_next\/[^"]+)"[^>]*>/g)]
  .filter((match) => !/\snomodule\b/i.test(match[0]))
  .map((match) => match[1]);
const preloads = [...html.matchAll(/<link\b[^>]*\brel="(?:preload|modulepreload)"[^>]*\bhref="(\/_next\/[^"]+\.(?:js|css))"/g)].map(
  (match) => match[1],
);
const styles = [...html.matchAll(/<link\b[^>]*\brel="stylesheet"[^>]*\bhref="(\/_next\/[^"]+)"/g)].map((match) => match[1]);
const files = [...new Set([...scripts, ...preloads, ...styles])].map((path) => `out${path}`);

if (files.length === 0) throw new Error(".size-limit.ts: out/index.html loads no files; build first");

export default [{ name: "initial route: the JS and CSS that / loads", path: files, gzip: true, limit: "200 kB" }];
