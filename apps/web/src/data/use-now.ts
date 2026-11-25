"use client";

// Reads now.json from the data plane this host uses (Q22), keeps the newest seq, and refreshes
// while the page is visible. The panel's loading, failed and stale states come from here.
import { useCallback, useEffect, useRef, useState } from "react";

import type { DataState } from "../shell/state";
import { dataPlaneBase } from "./base";
import { SITE_HOSTS } from "./hosts";
import { newer, parseNow, type NowDoc } from "./now";

/** How often a visible page asks for now.json again. The publisher writes it every pass. */
export const REFRESH_MS = 60_000;

export function useNowFeed(): { data: DataState; retry: () => void } {
  const [data, setData] = useState<DataState>(() => ({ phase: "loading", since: Date.now() }));
  const lastGood = useRef<NowDoc | null>(null);
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const base = dataPlaneBase(new URL(window.location.href), SITE_HOSTS);
      if (!base) throw new Error("no data plane is configured for this host");
      const response = await fetch(new URL("now.json", base), { cache: "no-store", credentials: "omit" });
      if (!response.ok) throw new Error(`now.json: HTTP ${response.status}`);
      const doc = parseNow(await response.json());
      if (!doc) throw new Error("now.json is not a version 1 document");
      lastGood.current = newer(lastGood.current, doc);
      setData({ phase: "ready", now: lastGood.current });
    } catch {
      setData({ phase: "failed", lastGood: lastGood.current });
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void load();
    const refresh = () => {
      if (document.visibilityState === "visible") void load();
    };
    const timer = window.setInterval(refresh, REFRESH_MS);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);

  return { data, retry: () => void load() };
}
