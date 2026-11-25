import { describe, expect, test } from "vitest";

import { absolutePoints, relativePath } from "./svg-path.ts";

describe("relativePath: d3-geo's absolute integer paths, written relative and shorter", () => {
  test("lines and rings", () => {
    expect(relativePath("M10,20L12,21L9,25Z")).toBe("M10 20l2 1-3 4z");
    expect(relativePath("M0,0L-5,-5M100,100L100,90")).toBe("M0 0l-5-5M100 100l0-10");
  });

  test("draws the same points", () => {
    const d = "M194,-981L171,-984L147,-985Z M-3,7L4,4L4,-9L-12,0Z".replace(/ /g, "");
    expect(absolutePoints(relativePath(d))).toEqual(absolutePoints(d));
  });

  test("an empty path stays empty", () => {
    expect(relativePath("")).toBe("");
  });

  test("anything but M, L and Z is refused", () => {
    expect(() => relativePath("M0,0A1,1,0,0,1,2,2")).toThrow(/unexpected/);
  });
});
