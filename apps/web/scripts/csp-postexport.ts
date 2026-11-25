// After `next build`: give every exported page its Content Security Policy (design note Q21;
// master plan §9). The policy is a <meta> tag carrying the hashes of the page's own inline scripts.
//
//   node scripts/csp-postexport.ts
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { inlineScripts, policyFor, sha256Source, withMetaPolicy } from "./lib/csp.ts";
import { walk } from "./lib/files.ts";
import { connectSources, readSiteConfig } from "./lib/site.ts";

const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const connect = connectSources(readSiteConfig());
const pages = walk(OUT).filter((file) => file.endsWith(".html"));
for (const page of pages) {
  const html = readFileSync(OUT + page, "utf8");
  const hashes = inlineScripts(html).map(sha256Source);
  writeFileSync(OUT + page, withMetaPolicy(html, policyFor(hashes, connect)));
  console.log(`csp: ${page}: ${hashes.length} inline script${hashes.length === 1 ? "" : "s"} hashed`);
}
if (pages.length === 0) throw new Error("csp: no exported pages in out/");
