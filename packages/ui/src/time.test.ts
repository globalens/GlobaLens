import { describe, expect, test } from "vitest";

import { formatClock, formatUtc, formatUtcClock } from "./time";

const t = Date.parse("2026-11-25T14:02:09Z");

describe("formatClock: the viewer's time zone, 24-hour clock", () => {
  test.each([
    ["UTC", "14:02"],
    ["Europe/Kyiv", "16:02"],
    ["America/New_York", "09:02"],
    ["Asia/Kolkata", "19:32"],
    ["Asia/Kathmandu", "19:47"],
  ])("%s -> %s", (zone, text) => {
    expect(formatClock(t, t, zone)).toBe(text);
  });

  test("a time on another day in that zone carries its date", () => {
    const yesterday = Date.parse("2026-11-24T23:50:00Z");
    expect(formatClock(yesterday, t, "UTC")).toBe("24 Nov 23:50");
    // Same instant: already the 25th in Kyiv, as is the reference time.
    expect(formatClock(yesterday, t, "Europe/Kyiv")).toBe("01:50");
  });
});

describe("formatUtc: what hover shows", () => {
  test("date, time and the zone name", () => {
    expect(formatUtc(t)).toBe("2026-11-25 14:02 UTC");
  });
  test("the clock alone, for copy that names UTC itself", () => {
    expect(formatUtcClock(t)).toBe("14:02");
  });
});
