// site.config.json, read by the build steps (the page reads it through src/data/hosts.ts).
import { readFileSync } from "node:fs";

export interface SiteConfig {
  production: { site: string | null; dataPlane: string | null };
  preview: { siteSuffix: string | null; dataPlane: string | null };
  connect: string[];
}

export function readSiteConfig(path = new URL("../../site.config.json", import.meta.url)): SiteConfig {
  return JSON.parse(readFileSync(path, "utf8")) as SiteConfig;
}

/** The hosts the page may connect to besides its own: the configured data planes and the tiles. */
export function connectSources(config: SiteConfig): string[] {
  const planes = [config.production.dataPlane, config.preview.dataPlane].flatMap((url) => (url ? [new URL(url).origin] : []));
  return [...new Set([...planes, ...config.connect])];
}
