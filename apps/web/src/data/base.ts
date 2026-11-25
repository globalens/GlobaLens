// The data plane's base URL, chosen from the hostname at run time (design note Q22): one build for
// preview and production, so what a preview tested is byte for byte what production serves.
//
// Until a domain exists (§12.1) the site is served at a workers.dev address and the data plane at
// the cdn bucket's r2.dev address. Neither exists yet: site.config.json holds nulls until
// Cloudflare is set up, and an unconfigured host has no data plane (the shell says it could not
// load the latest data).

export interface SiteHosts {
  production: { site: string | null; dataPlane: string | null };
  /** Preview versions and aliases are `<prefix>-<worker>.<account>.workers.dev`. */
  preview: { siteSuffix: string | null; dataPlane: string | null };
}

const LOCAL = new Set(["localhost", "127.0.0.1", "[::1]"]);

/** The base every data-plane key (now.json, live/…) is relative to, or null for this host. */
export function dataPlaneBase(location: URL, hosts: SiteHosts): string | null {
  const host = location.hostname.toLowerCase();
  if (LOCAL.has(host)) return new URL("/data/", location.origin).href;
  const { production, preview } = hosts;
  if (production.site && host === production.site.toLowerCase()) return production.dataPlane;
  if (preview.siteSuffix) {
    const suffix = preview.siteSuffix.toLowerCase();
    const prefix = host.slice(0, -suffix.length);
    if (host.endsWith(suffix) && /^[a-z0-9][a-z0-9-]*$/.test(prefix)) return preview.dataPlane;
  }
  return null;
}
