// Two builds of one commit differ only in pre-rendered HTML and data (master plan §9 step 1;
// design note §9 task 12 and §10). The build ID is the commit (next.config.ts), so everything
// else, scripts, styles, fonts and the globes, must come out byte for byte the same.
//
//   node scripts/check-repro.ts
//
// Builds twice from clean (.next and out removed each time), compares the two exports, and fails
// on any difference outside the pages (.html) and their data (.txt, Next's flight data). It also
// says whether those differed: in P1 nothing is pre-rendered from data, so they should not.
import { execFileSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { walk } from "./lib/files.ts";

const APP = fileURLToPath(new URL("../", import.meta.url));
const next = createRequire(import.meta.url).resolve("next/dist/bin/next");
const DATA = /\.(html|txt)$/;

function build(): string {
  rmSync(join(APP, ".next"), { recursive: true, force: true });
  rmSync(join(APP, "out"), { recursive: true, force: true });
  const env = { ...process.env, NEXT_TELEMETRY_DISABLED: "1" };
  for (const args of [["scripts/gen-globes.ts"], [next, "build"], ["scripts/csp-postexport.ts"]]) {
    execFileSync(process.execPath, args, { cwd: APP, env, stdio: ["ignore", "ignore", "inherit"] });
  }
  const copy = mkdtempSync(join(tmpdir(), "globalens-export-"));
  cpSync(join(APP, "out"), copy, { recursive: true });
  return copy;
}

const first = build();
const second = build();
const a = new Set(walk(first));
const b = new Set(walk(second));
const problems: string[] = [];
const dataDiffers: string[] = [];
for (const file of new Set([...a, ...b])) {
  if (!a.has(file) || !b.has(file)) {
    problems.push(`${file} is in only one build`);
    continue;
  }
  if (readFileSync(join(first, file)).equals(readFileSync(join(second, file)))) continue;
  if (DATA.test(file)) dataDiffers.push(file);
  else problems.push(`${file} differs`);
}
rmSync(first, { recursive: true, force: true });
rmSync(second, { recursive: true, force: true });

console.log(`check-repro: ${a.size} files in each build; ${dataDiffers.length} pages or data files differ${dataDiffers.length ? `: ${dataDiffers.join(", ")}` : ""}`);
if (problems.length) {
  for (const problem of problems) console.error(`check-repro: ${problem}`);
  process.exit(1);
}
console.log("check-repro: ok, the two builds differ only in pre-rendered HTML and data");
