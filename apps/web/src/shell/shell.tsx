"use client";

// The chrome around the persistent globe: the top bar, the "In the Lens" panel (a drawer with
// three detents on a phone, frame 3), its plain states, and the credits.
import { Panel, strings } from "@globalens/ui";
import { useEffect, useState, type ReactNode } from "react";

import { useNowFeed } from "../data/use-now";
import { useGlobeStage, type Detent } from "../globe/provider";
import { Attribution } from "./attribution";
import { LOADING_QUIET_MS, panelBlocks } from "./state";
import { StateBlocks } from "./states";
import styles from "./shell.module.css";
import { TopBar } from "./top-bar";

/** How often the states are looked at again (stale after 45 minutes). */
const TICK_MS = 30_000;
const NEXT_DETENT: Record<Detent, Detent> = { peek: "half", half: "full", full: "peek" };

function useClock(data: { phase: string }): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const interval = window.setInterval(tick, TICK_MS);
    // While loading, look again once the quiet second is over: the skeleton shows after it.
    const quiet = data.phase === "loading" ? window.setTimeout(tick, LOADING_QUIET_MS) : undefined;
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(quiet);
    };
  }, [data.phase]);
  return now;
}

export function Shell({ children }: { children?: ReactNode }) {
  const { webgl, detent, setDetent } = useGlobeStage();
  const { data, retry } = useNowFeed();
  const now = useClock(data);
  const blocks = panelBlocks({
    data,
    nowMs: now,
    webgl: webgl === "unavailable" ? "unavailable" : webgl === "pending" ? "unknown" : "available",
  });

  return (
    <>
      <TopBar />
      <Panel
        label={strings.panel.label}
        className={styles.panel}
        header={
          <>
            <button
              type="button"
              className={styles.grab}
              aria-expanded={detent !== "peek"}
              aria-label={detent === "full" ? strings.panel.collapse : strings.panel.expand}
              onClick={() => setDetent(NEXT_DETENT[detent])}
            >
              <span className={styles.grabBar} aria-hidden="true" />
            </button>
            <h2 className={styles.eyebrow}>{strings.panel.eyebrow}</h2>
          </>
        }
      >
        <StateBlocks blocks={blocks} onRetry={retry} />
        {children}
      </Panel>
      <Attribution />
    </>
  );
}
