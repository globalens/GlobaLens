import { describe, expect, test } from "vitest";

import { dataPlaneBase, type SiteHosts } from "./base";

const CONFIGURED: SiteHosts = {
  production: { site: "globalens.example-account.workers.dev", dataPlane: "https://pub-0123abcd.r2.dev/" },
  preview: {
    siteSuffix: "-globalens.example-account.workers.dev",
    dataPlane: "https://pub-0123abcd.r2.dev/preview/",
  },
};

const UNSET: SiteHosts = {
  production: { site: null, dataPlane: null },
  preview: { siteSuffix: null, dataPlane: null },
};

describe("dataPlaneBase: the data plane is chosen from the hostname at run time (Q22)", () => {
  test("production", () => {
    expect(dataPlaneBase(new URL("https://globalens.example-account.workers.dev/"), CONFIGURED)).toBe(
      "https://pub-0123abcd.r2.dev/",
    );
  });

  test("a preview version or alias reads the preview/ prefix", () => {
    for (const host of ["4f2a9c1e-globalens.example-account.workers.dev", "pr-42-globalens.example-account.workers.dev"]) {
      expect(dataPlaneBase(new URL(`https://${host}/`), CONFIGURED)).toBe("https://pub-0123abcd.r2.dev/preview/");
    }
  });

  test("a local build reads /data/ on its own origin", () => {
    expect(dataPlaneBase(new URL("http://localhost:4321/?story=x"), CONFIGURED)).toBe("http://localhost:4321/data/");
    expect(dataPlaneBase(new URL("http://127.0.0.1:3000/"), UNSET)).toBe("http://127.0.0.1:3000/data/");
    expect(dataPlaneBase(new URL("http://[::1]:3000/"), UNSET)).toBe("http://[::1]:3000/data/");
  });

  test("an unknown host, or a host that is not configured yet, has no data plane", () => {
    expect(dataPlaneBase(new URL("https://elsewhere.example/"), CONFIGURED)).toBeNull();
    expect(dataPlaneBase(new URL("https://globalens.example-account.workers.dev.evil.example/"), CONFIGURED)).toBeNull();
    expect(dataPlaneBase(new URL("https://globalens.example-account.workers.dev/"), UNSET)).toBeNull();
  });

  test("the preview suffix alone is not a preview host", () => {
    expect(dataPlaneBase(new URL("https://globalens.example-account.workers.dev/"), CONFIGURED)).not.toContain("preview");
    expect(
      dataPlaneBase(new URL("https://x.-globalens.example-account.workers.dev/"), CONFIGURED),
    ).toBeNull();
  });
});
