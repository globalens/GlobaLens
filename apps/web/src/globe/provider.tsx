"use client";

// The persistent globe's state, mounted once in app/(globe)/layout.tsx: where the first paint
// faces, whether WebGL can take over, and the drawer's detent on a phone (the globe is centred in
// the area the drawer leaves).
//
// Task 13 hooks in here: it mounts the MapLibre canvas into `webglContainer`, starts its camera at
// `view`, and calls `setWebGL("ready")` after its first frame, which crossfades from the SVG globe
// to the WebGL one (a cut under reduced motion); `setWebGL("lost")` on webglcontextlost brings the
// SVG globe back until the context is restored.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { GLOBE_LATITUDE, pickGlobe } from "./first-paint";
import styles from "./stage.module.css";
import { hasWebGL2 } from "./webgl";

export type WebGLStatus = "pending" | "ready" | "lost" | "unavailable";
export type Detent = "peek" | "half" | "full";

export interface GlobeStageApi {
  /** The longitude and latitude the first paint faces; the WebGL camera starts here. */
  view: { lon: number; lat: number };
  webgl: WebGLStatus;
  setWebGL(status: "ready" | "lost"): void;
  /** Where task 13 mounts the WebGL canvas. */
  webglContainer: HTMLDivElement | null;
  setWebglContainer(element: HTMLDivElement | null): void;
  detent: Detent;
  setDetent(detent: Detent): void;
}

const GlobeContext = createContext<GlobeStageApi | null>(null);

export function useGlobeStage(): GlobeStageApi {
  const api = useContext(GlobeContext);
  if (!api) throw new Error("useGlobeStage: outside the globe layout");
  return api;
}

function firstPaintLongitude(): number {
  const recorded = Number(document.documentElement.dataset["globeLon"]);
  return Number.isFinite(recorded) && document.documentElement.dataset["globeLon"] !== undefined
    ? recorded
    : pickGlobe(new Date().getTimezoneOffset()).lon;
}

export function GlobeProvider({ children }: { children: ReactNode }) {
  const [lon, setLon] = useState(0);
  const [webgl, setWebGLState] = useState<WebGLStatus>("pending");
  const [webglContainer, setWebglContainer] = useState<HTMLDivElement | null>(null);
  const [detent, setDetent] = useState<Detent>("peek");

  useEffect(() => {
    setLon(firstPaintLongitude());
    // After the first paint: the probe creates a context, which costs a few milliseconds.
    const probe = () => {
      if (!hasWebGL2(document)) setWebGLState("unavailable");
    };
    if ("requestIdleCallback" in window) {
      const id = window.requestIdleCallback(probe, { timeout: 2000 });
      return () => window.cancelIdleCallback(id);
    }
    const id = setTimeout(probe, 0);
    return () => clearTimeout(id);
  }, []);

  const setWebGL = useCallback((status: "ready" | "lost") => {
    setWebGLState((current) => (current === "unavailable" ? current : status));
  }, []);

  const api = useMemo<GlobeStageApi>(
    () => ({ view: { lon, lat: GLOBE_LATITUDE }, webgl, setWebGL, webglContainer, setWebglContainer, detent, setDetent }),
    [lon, webgl, setWebGL, webglContainer, detent],
  );

  return (
    <GlobeContext.Provider value={api}>
      <div className={styles.app} data-webgl={webgl} data-detent={detent}>
        {children}
      </div>
    </GlobeContext.Provider>
  );
}
