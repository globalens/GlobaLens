import { describe, expect, test } from "vitest";

import { directionOf, LANGS, langByIndex } from "./lang";

describe("the language table, generated from packages/gdelt/src/gdelt/lang.py", () => {
  test("the order is the point shards' wire format: English is 0", () => {
    expect(LANGS.length).toBe(66);
    expect(langByIndex(0)).toMatchObject({ code: "eng", tag: "en", dir: "ltr", script: "Latn" });
    expect(langByIndex(65)).toMatchObject({ code: "zho", tag: "zh" });
    expect(langByIndex(66)).toBeNull();
    expect(langByIndex(-1)).toBeNull();
  });
});

describe("directionOf: dir from the language, auto only when the language is unknown (Q6)", () => {
  test.each([
    ["ar", "rtl"],
    ["fa", "rtl"],
    ["he", "rtl"],
    ["ur", "rtl"],
    ["AR", "rtl"],
    ["ar-EG", "rtl"],
    ["en", "ltr"],
    ["uk", "ltr"],
    ["zh", "ltr"],
    ["hi", "ltr"],
    ["az", "ltr"],
    // A script subtag decides over the language.
    ["az-Arab", "rtl"],
    ["pa-Arab", "rtl"],
    ["sr-Latn", "ltr"],
    ["ur-Latn", "ltr"],
    // Right-to-left languages outside the table, by their default script.
    ["ckb", "rtl"],
    ["ps", "rtl"],
    ["yi", "rtl"],
    ["dv", "rtl"],
  ] as const)("%s -> %s", (tag, dir) => {
    expect(directionOf(tag)).toBe(dir);
  });

  test.each([[""], ["und"], ["x-unknown"], ["zz"], ["123"]])("%j is unknown, so auto", (tag) => {
    expect(directionOf(tag)).toBe("auto");
  });

  test("every row of the table agrees with directionOf", () => {
    for (const lang of LANGS) expect(directionOf(lang.tag)).toBe(lang.dir);
  });
});
