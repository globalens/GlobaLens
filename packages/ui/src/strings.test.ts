import { describe, expect, test } from "vitest";

import { copiesLabel, interpolate, staleCopy, strings } from "./strings";

describe("the UI strings module", () => {
  test("the plain P1 states use the plan's own copy (frame 2, column C)", () => {
    expect(strings.states.empty).toBe("No located coverage here in 24 h.");
    expect(strings.states.failed).toBe("Couldn’t load the latest data.");
    expect(strings.states.retry).toBe("Retry");
    expect(strings.states.noWebgl).toBe("The SVG globe stays, with this list.");
    expect(staleCopy({ streams: ["english", "translated"], sinceUtc: "14:00" })).toBe(
      "GDELT hasn’t published since 14:00 UTC; showing the last good data",
    );
  });

  test("one stale stream is named", () => {
    expect(staleCopy({ streams: ["translated"], sinceUtc: "13:45" })).toBe(
      "GDELT hasn’t published translated articles since 13:45 UTC; showing the last good data",
    );
  });

  test("copies", () => {
    expect(copiesLabel(11, 4)).toBe("+11 copies · 4 outlets");
    expect(copiesLabel(1, 1)).toBe("+1 copy · 1 outlet");
  });

  test("interpolate splits a template around its placeholders", () => {
    expect(interpolate("Showing data from {time}.", { time: 7 })).toEqual(["Showing data from ", 7, "."]);
    expect(interpolate("{a} and {b}", { a: "x", b: "y" })).toEqual(["x", " and ", "y"]);
    expect(() => interpolate("{missing}", {})).toThrow(/missing/);
  });

  test("no string is empty", () => {
    const walk = (value: unknown): void => {
      if (typeof value === "string") expect(value.trim()).not.toBe("");
      else if (value && typeof value === "object") Object.values(value).forEach(walk);
    };
    walk(strings);
  });
});
