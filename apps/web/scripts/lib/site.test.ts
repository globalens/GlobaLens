import { expect, test } from "vitest";

import { connectSources, readSiteConfig, type SiteConfig } from "./site.ts";

test("the committed config: no data plane yet, OpenFreeMap's tile host only", () => {
  expect(connectSources(readSiteConfig())).toEqual(["https://tiles.openfreemap.org"]);
});

test("configured data planes join connect-src by origin, once", () => {
  const config: SiteConfig = {
    production: { site: "globalens.a.workers.dev", dataPlane: "https://pub-0123.r2.dev/" },
    preview: { siteSuffix: "-globalens.a.workers.dev", dataPlane: "https://pub-0123.r2.dev/preview/" },
    connect: ["https://tiles.openfreemap.org"],
  };
  expect(connectSources(config)).toEqual(["https://pub-0123.r2.dev", "https://tiles.openfreemap.org"]);
});
