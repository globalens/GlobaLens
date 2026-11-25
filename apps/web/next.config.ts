// The site is a static export (master plan §6, "App framework"; design note §9 task 12; ADR-0016):
// every page is a file, and nothing renders on a request.
import { execFileSync } from "node:child_process";

import type { NextConfig } from "next";

/**
 * The build ID is the commit the site is built from (plan §9: "pinned to the commit that prod.lock
 * approves"). CI passes it in GLOBALENS_BUILD_COMMIT; a local build asks git.
 */
function buildCommit(): string {
  const commit = process.env["GLOBALENS_BUILD_COMMIT"] ?? execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  if (!/^[0-9a-f]{40}$/.test(commit)) throw new Error(`the build commit is not a full SHA: "${commit}"`);
  return commit;
}

const config: NextConfig = {
  output: "export",
  reactStrictMode: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  images: { unoptimized: true },
  transpilePackages: ["@globalens/ui"],
  devIndicators: false,
  generateBuildId: () => buildCommit(),
};

export default config;
