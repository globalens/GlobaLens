// now.json: the one data-plane object that changes in place (design note §6.1; written by the
// publisher, pull request 16, apps/worker/src/worker/manifest.py, VERSION 1). The shell reads it
// for the plain loading, failed and stale states; task 15's badge reads the same document.

export const NOW_VERSION = 1;

/** A stream is stale when its newest stamp is older than this (plan §4 "States": over 45 min). */
export const STALE_AFTER_MS = 45 * 60 * 1000;

export type StreamName = "english" | "translated";
const STREAMS: readonly StreamName[] = ["english", "translated"];

export interface StreamClock {
  stamp: number; // the newest published stamp, ms since the epoch
  listedAt: number; // when GDELT listed that file
}

export interface NowDoc {
  seq: number;
  writtenAt: number;
  manifest: string;
  streams: Record<StreamName, StreamClock | null>;
}

const TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

function time(value: unknown): number | null {
  return typeof value === "string" && TIME.test(value) ? Date.parse(value) : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Read a parsed now.json, or null if it is not a version 1 document. */
export function parseNow(value: unknown): NowDoc | null {
  if (!isRecord(value) || value["v"] !== NOW_VERSION) return null;
  const seq = value["seq"];
  const writtenAt = time(value["written_at"]);
  const manifest = value["manifest"];
  const streams = value["streams"];
  if (typeof seq !== "number" || !Number.isSafeInteger(seq) || seq < 0) return null;
  if (writtenAt === null || typeof manifest !== "string" || !isRecord(streams)) return null;
  const clocks = {} as Record<StreamName, StreamClock | null>;
  for (const name of STREAMS) {
    const clock = streams[name];
    if (clock === null || clock === undefined) {
      clocks[name] = null;
      continue;
    }
    if (!isRecord(clock)) return null;
    const stamp = time(clock["stamp"]);
    const listedAt = time(clock["listed_at"]);
    if (stamp === null || listedAt === null) return null;
    clocks[name] = { stamp, listedAt };
  }
  return { seq, writtenAt, manifest, streams: clocks };
}

/** The browser ignores a seq at or below one it has seen (design note §6.1). */
export function newer(seen: NowDoc | null, next: NowDoc): NowDoc {
  return seen && next.seq <= seen.seq ? seen : next;
}

export type Staleness =
  | { kind: "fresh" }
  | { kind: "gdelt"; streams: StreamName[]; since: number }
  | { kind: "paused"; since: number };

/**
 * Per stream, from the stream stamps of a fresh now.json; when now.json itself is older than the
 * same 45 minutes, publishing has paused instead (plan §4 "States").
 */
export function staleness(doc: NowDoc, nowMs: number): Staleness {
  if (nowMs - doc.writtenAt > STALE_AFTER_MS) return { kind: "paused", since: doc.writtenAt };
  const stale = STREAMS.filter((name) => {
    const clock = doc.streams[name];
    return clock !== null && nowMs - clock.stamp > STALE_AFTER_MS;
  });
  if (stale.length === 0) return { kind: "fresh" };
  const since = Math.min(...stale.map((name) => (doc.streams[name] as StreamClock).stamp));
  return { kind: "gdelt", streams: stale, since };
}

/** The time of the data a document points at: its newest stamp, else when it was written. */
export function lastDataTime(doc: NowDoc): number {
  const stamps = STREAMS.flatMap((name) => {
    const clock = doc.streams[name];
    return clock ? [clock.stamp] : [];
  });
  return stamps.length ? Math.max(...stamps) : doc.writtenAt;
}
