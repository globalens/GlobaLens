import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

import fonts from "./fonts.json";

const here = (name: string) => new URL(name, import.meta.url);
const fontsCss = readFileSync(here("./fonts.css"), "utf8");
const tokensCss = readFileSync(here("./tokens.css"), "utf8");
const pkg = JSON.parse(readFileSync(here("../package.json"), "utf8")) as { dependencies: Record<string, string> };

const all = [...fonts.ui, ...fonts.titles];

const token = (name: string): string => {
  const match = new RegExp(`--${name}:\\s*([^;]+);`).exec(tokensCss);
  if (!match?.[1]) throw new Error(`no --${name} in tokens.css`);
  return match[1];
};

describe("the type stack (design note §4, Q20)", () => {
  test("every family is a pinned npm package, and every font package is in the manifest", () => {
    for (const face of all) expect(pkg.dependencies[face.package]).toMatch(/^\d+\.\d+\.\d+$/);
    const fontPackages = Object.keys(pkg.dependencies).filter((name) => name.startsWith("@fontsource"));
    expect(fontPackages.sort()).toEqual(all.map((face) => face.package).sort());
  });

  test("fonts.css imports exactly the manifest's stylesheets, in its order", () => {
    const imports = [...fontsCss.matchAll(/@import\s+"([^"]+)";/g)].map((m) => m[1]);
    expect(imports).toEqual(all.map((face) => `${face.package}/${face.css}`));
  });

  test("the title stack names every title family in manifest order, then system fonts for CJK", () => {
    const stack = token("font-title");
    let last = -1;
    for (const face of fonts.titles) {
      const at = stack.indexOf(`"${face.family}"`);
      expect(at, face.family).toBeGreaterThan(last);
      last = at;
    }
    for (const system of fonts.systemFallbacks.cjk) expect(stack).toContain(system);
  });

  test("each UI role's token starts with its family", () => {
    for (const face of fonts.ui) expect(token(`font-${face.role}`).startsWith(`"${face.family}"`)).toBe(true);
  });

  test("the title families cover the scripts the plan names; CJK is left to system fonts", () => {
    const shipped = fonts.titles.flatMap((face) => face.scripts);
    expect(new Set(shipped).size).toBe(shipped.length);
    for (const script of ["Latn", "Cyrl", "Grek", "Arab", "Hebr", "Deva", "Beng", "Taml", "Telu", "Gujr", "Guru", "Knda", "Mlym", "Sinh", "Thai", "Geor", "Armn"]) {
      expect(shipped).toContain(script);
    }
    for (const script of ["Hani", "Hira", "Kana", "Hang"]) expect(shipped).not.toContain(script);
  });
});
