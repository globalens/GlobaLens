// The shell's plain states (design note Q7; frame 2, column C): which blocks the panel shows.
// Pure: the data hook, the WebGL probe and (from task 14) the Lens feed it.
import { lastDataTime, staleness, type NowDoc, type StreamName } from "../data/now";

/** Loading shows nothing under 1 s, then a skeleton (plan §4, the NN/g thresholds). */
export const LOADING_QUIET_MS = 1000;

export type DataState =
  | { phase: "loading"; since: number }
  | { phase: "ready"; now: NowDoc }
  | { phase: "failed"; lastGood: NowDoc | null };

export type WebGLState = "unknown" | "available" | "unavailable";

export type PanelBlock =
  | { kind: "loading" }
  | { kind: "failed"; lastDataAt: number | null }
  | { kind: "stale"; streams: StreamName[]; since: number }
  | { kind: "paused"; since: number }
  | { kind: "empty" }
  | { kind: "no-webgl" };

export interface PanelInput {
  data: DataState;
  nowMs: number;
  webgl: WebGLState;
  /** Set by the Lens (task 14) when the ring holds no located coverage. */
  lensEmpty?: boolean;
}

export function panelBlocks({ data, nowMs, webgl, lensEmpty = false }: PanelInput): PanelBlock[] {
  const blocks: PanelBlock[] = [];
  if (data.phase === "loading") {
    if (nowMs - data.since >= LOADING_QUIET_MS) blocks.push({ kind: "loading" });
  } else if (data.phase === "failed") {
    blocks.push({ kind: "failed", lastDataAt: data.lastGood ? lastDataTime(data.lastGood) : null });
  } else {
    const state = staleness(data.now, nowMs);
    if (state.kind === "gdelt") blocks.push({ kind: "stale", streams: state.streams, since: state.since });
    else if (state.kind === "paused") blocks.push({ kind: "paused", since: state.since });
    if (lensEmpty) blocks.push({ kind: "empty" });
  }
  if (webgl === "unavailable") blocks.push({ kind: "no-webgl" });
  return blocks;
}
