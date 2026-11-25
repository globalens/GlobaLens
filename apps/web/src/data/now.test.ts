import { describe, expect, test } from "vitest";

import { lastDataTime, newer, parseNow, staleness, STALE_AFTER_MS, type NowDoc } from "./now";

// The shape the publisher writes (pull request 16, apps/worker/src/worker/manifest.py, VERSION 1).
const SAMPLE = {
  manifest: "live/dt=2026-11-14/manifest/0f1e2d3c.json",
  seq: 412,
  streams: {
    english: { listed_at: "2026-11-14T14:04:51Z", stamp: "2026-11-14T14:00:00Z" },
    translated: { listed_at: "2026-11-14T14:07:02Z", stamp: "2026-11-14T13:45:00Z" },
  },
  v: 1,
  written_at: "2026-11-14T14:08:30Z",
};

const at = (iso: string) => Date.parse(iso);

describe("parseNow", () => {
  test("reads version 1", () => {
    const doc = parseNow(SAMPLE);
    expect(doc).not.toBeNull();
    expect(doc?.seq).toBe(412);
    expect(doc?.writtenAt).toBe(at("2026-11-14T14:08:30Z"));
    expect(doc?.manifest).toBe("live/dt=2026-11-14/manifest/0f1e2d3c.json");
    expect(doc?.streams.english).toEqual({ stamp: at("2026-11-14T14:00:00Z"), listedAt: at("2026-11-14T14:04:51Z") });
  });

  test("a stream with nothing published is null", () => {
    const doc = parseNow({ ...SAMPLE, streams: { english: SAMPLE.streams.english, translated: null } });
    expect(doc?.streams.translated).toBeNull();
  });

  test.each([
    ["another version", { ...SAMPLE, v: 2 }],
    ["no seq", { ...SAMPLE, seq: undefined }],
    ["a seq that is not a whole number", { ...SAMPLE, seq: 1.5 }],
    ["a time without a zone", { ...SAMPLE, written_at: "2026-11-14T14:08:30" }],
    ["a stream that is not an object", { ...SAMPLE, streams: { english: "x", translated: null } }],
    ["no streams", { ...SAMPLE, streams: undefined }],
    ["a manifest that is not a string", { ...SAMPLE, manifest: 7 }],
    ["not an object", "now"],
    ["null", null],
  ])("rejects %s", (_name, value) => {
    expect(parseNow(value)).toBeNull();
  });
});

describe("newer: the browser ignores a seq at or below one it has seen", () => {
  const doc = parseNow(SAMPLE) as NowDoc;
  test("keeps the higher seq", () => {
    const later = { ...doc, seq: 413 };
    expect(newer(doc, later)).toBe(later);
    expect(newer(later, doc)).toBe(later);
    expect(newer(doc, { ...doc, seq: 412 })).toBe(doc);
    expect(newer(null, doc)).toBe(doc);
  });
});

describe("staleness", () => {
  const doc = parseNow(SAMPLE) as NowDoc;

  test("fresh while every stream's newest stamp is at most 45 minutes old", () => {
    expect(staleness(doc, at("2026-11-14T14:20:00Z"))).toEqual({ kind: "fresh" });
    expect(staleness(doc, at("2026-11-14T13:45:00Z") + STALE_AFTER_MS)).toEqual({ kind: "fresh" });
  });

  test("a stream whose newest stamp is older than 45 minutes is stale, with its stamp", () => {
    expect(staleness(doc, at("2026-11-14T14:31:00Z"))).toEqual({
      kind: "gdelt",
      streams: ["translated"],
      since: at("2026-11-14T13:45:00Z"),
    });
  });

  test("when both streams are stale, since is the older stamp", () => {
    expect(staleness({ ...doc, writtenAt: at("2026-11-14T14:50:00Z") }, at("2026-11-14T14:51:00Z"))).toEqual({
      kind: "gdelt",
      streams: ["english", "translated"],
      since: at("2026-11-14T13:45:00Z"),
    });
  });

  test("when now.json itself is older than 45 minutes, publishing has paused", () => {
    expect(staleness(doc, at("2026-11-14T14:54:00Z"))).toEqual({
      kind: "paused",
      since: at("2026-11-14T14:08:30Z"),
    });
  });

  test("a stream with nothing published says nothing", () => {
    const one = { ...doc, streams: { english: doc.streams.english, translated: null } };
    expect(staleness(one, at("2026-11-14T14:20:00Z"))).toEqual({ kind: "fresh" });
  });
});

describe("lastDataTime: the time 'Showing data from' names", () => {
  test("the newest stamp of any stream", () => {
    expect(lastDataTime(parseNow(SAMPLE) as NowDoc)).toBe(at("2026-11-14T14:00:00Z"));
  });
  test("when no stream has a stamp, when now.json was written", () => {
    const doc = parseNow({ ...SAMPLE, streams: { english: null, translated: null } }) as NowDoc;
    expect(lastDataTime(doc)).toBe(at("2026-11-14T14:08:30Z"));
  });
});
