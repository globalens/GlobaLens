// The checks on the built export (design note §9 task 12 and §10, "Static export"):
//
// - the script-policy check on every page: a <meta> CSP ahead of everything, default-src 'none',
//   only our own scripts and the page's own inline-script hashes, connect-src exactly the
//   configured hosts, and no third-party script, stylesheet, image or frame;
// - the header check on the headers file;
// - no stylesheet that pulls from another origin;
// - Cloudflare's static-asset limits: at most 20,000 files and 25 MiB a file;
// - and a report of the font files shipped (fonts are reported, not budgeted: plan §11).
//
//   node scripts/check-export.ts        (after pnpm build; size-limit runs after it)
import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { checkPage } from "./lib/csp.ts";
import { walk } from "./lib/files.ts";
import { checkHeadersFile } from "./lib/headers.ts";
import { connectSources, readSiteConfig } from "./lib/site.ts";

const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const MAX_FILES = 20_000;
const MAX_FILE_BYTES = 25 * 1024 * 1024;

const problems: string[] = [];
const files = walk(OUT);
const connect = connectSources(readSiteConfig());

const pages = files.filter((file) => file.endsWith(".html"));
if (pages.length === 0) problems.push("no exported pages: build first");
for (const page of pages) {
  for (const problem of checkPage(readFileSync(OUT + page, "utf8"), connect)) problems.push(`${page}: ${problem}`);
}

if (!files.includes("_headers")) problems.push("_headers is missing from the export");
else for (const problem of checkHeadersFile(readFileSync(`${OUT}_headers`, "utf8"))) problems.push(`_headers: ${problem}`);

for (const css of files.filter((file) => file.endsWith(".css"))) {
  const text = readFileSync(OUT + css, "utf8");
  for (const match of text.matchAll(/(?:url\(\s*["']?|@import\s+["'])((?:https?:)?\/\/[^"')\s]+)/gi)) {
    problems.push(`${css}: a stylesheet loads from another origin: ${match[1]}`);
  }
}

if (files.length > MAX_FILES) problems.push(`${files.length} files, over Cloudflare's ${MAX_FILES}`);
let largest = { file: "", bytes: 0 };
let fontBytes = 0;
let fontFiles = 0;
for (const file of files) {
  const bytes = statSync(OUT + file).size;
  if (bytes > largest.bytes) largest = { file, bytes };
  if (bytes > MAX_FILE_BYTES) problems.push(`${file} is ${bytes} bytes, over Cloudflare's 25 MiB`);
  if (file.endsWith(".woff2")) {
    fontBytes += bytes;
    fontFiles += 1;
  }
}

console.log(`check-export: ${pages.length} pages, ${files.length} files, the largest ${largest.file} (${(largest.bytes / 1024).toFixed(0)} KiB)`);
console.log(`check-export: fonts (reported, not budgeted): ${fontFiles} woff2 files, ${(fontBytes / 1024).toFixed(0)} KiB in all; a page downloads only the ranges it draws`);
if (problems.length) {
  for (const problem of problems) console.error(`check-export: ${problem}`);
  process.exit(1);
}
console.log("check-export: ok");
