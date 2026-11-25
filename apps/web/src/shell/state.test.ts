import { describe, expect, test } from "vitest";

import { parseNow, type NowDoc } from "../data/now";
import { LOADING_QUIET_MS, panelBlocks, type DataState } from "./state";

const at = (iso: string) => Date.parse(iso);

const NOW = parseNow({
  manifest: "live/dt=2026-11-14/manifest/0f1e2d3c.json",
  seq: 412,
  streams: {
    english: { listed_at: "2026-11-14T14:04:51Z", stamp: "2026-11-14T14:00:00Z" },
    translated: { listed_at: "2026-11-14T14:07:02Z", stamp: "2026-11-14T14:00:00Z" },
  },
  v: 1,
  written_at: "2026-11-14T14:08:30Z",
}) as NowDoc;

const ready: DataState = { phase: "ready", now: NOW };
const kinds = (blocks: ReturnType<typeof panelBlocks>) => blocks.map((b) => b.kind);

describe("panelBlocks: the plain P1 states of frame 2, column C", () => {
  test("loading shows nothing for the first second, then a skeleton", () => {
    const loading: DataState = { phase: "loading", since: 1_000 };
    expect(panelBlocks({ data: loading, nowMs: 1_000 + LOADING_QUIET_MS - 1, webgl: "unknown" })).toEqual([]);
    expect(kinds(panelBlocks({ data: loading, nowMs: 1_000 + LOADING_QUIET_MS, webgl: "unknown" }))).toEqual([
      "loading",
    ]);
  });

  test("ready and fresh shows no state", () => {
    expect(panelBlocks({ data: ready, nowMs: at("2026-11-14T14:20:00Z"), webgl: "available" })).toEqual([]);
  });

  test("a failed first load has no last good data to name", () => {
    expect(panelBlocks({ data: { phase: "failed", lastGood: null }, nowMs: 0, webgl: "available" })).toEqual([
      { kind: "failed", lastDataAt: null },
    ]);
  });

  test("a failed refresh names the time of the last good data", () => {
    expect(panelBlocks({ data: { phase: "failed", lastGood: NOW }, nowMs: 0, webgl: "available" })).toEqual([
      { kind: "failed", lastDataAt: at("2026-11-14T14:00:00Z") },
    ]);
  });

  test("stale and paused come from now.json", () => {
    expect(panelBlocks({ data: ready, nowMs: at("2026-11-14T14:46:00Z"), webgl: "available" })).toEqual([
      { kind: "stale", streams: ["english", "translated"], since: at("2026-11-14T14:00:00Z") },
    ]);
    expect(panelBlocks({ data: ready, nowMs: at("2026-11-14T15:00:00Z"), webgl: "available" })).toEqual([
      { kind: "paused", since: at("2026-11-14T14:08:30Z") },
    ]);
  });

  test("empty comes from the Lens (task 14), and only once data is ready", () => {
    const nowMs = at("2026-11-14T14:20:00Z");
    expect(kinds(panelBlocks({ data: ready, nowMs, webgl: "available", lensEmpty: true }))).toEqual(["empty"]);
    expect(
      kinds(panelBlocks({ data: { phase: "loading", since: nowMs }, nowMs, webgl: "available", lensEmpty: true })),
    ).toEqual([]);
  });

  test("no WebGL2 adds its note to whatever else shows, last", () => {
    expect(kinds(panelBlocks({ data: ready, nowMs: at("2026-11-14T14:20:00Z"), webgl: "unavailable" }))).toEqual([
      "no-webgl",
    ]);
    expect(
      kinds(panelBlocks({ data: { phase: "failed", lastGood: null }, nowMs: 0, webgl: "unavailable" })),
    ).toEqual(["failed", "no-webgl"]);
  });

  test("no data plane configured for this host reads as a failed load", () => {
    expect(kinds(panelBlocks({ data: { phase: "failed", lastGood: null }, nowMs: 0, webgl: "unknown" }))).toEqual([
      "failed",
    ]);
  });
});
