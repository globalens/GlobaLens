"use client";

// The globe: the SVG first paint and, from task 13, the WebGL canvas above it.
import { strings } from "@globalens/ui";
import { useEffect } from "react";

import { FIRST_PAINT_IMG_ID, firstPaint, GLOBE_BASE, pickGlobe } from "./first-paint";
import { useGlobeStage } from "./provider";
import styles from "./stage.module.css";

export function GlobeStage() {
  const { setWebglContainer } = useGlobeStage();
  // A page loaded from the server ran the inline script already. After a navigation inside the
  // app (from the not-found page, say) it did not: run the same code now.
  useEffect(() => {
    const img = document.getElementById(FIRST_PAINT_IMG_ID);
    if (img && !img.getAttribute("src")) firstPaint(document, new Date().getTimezoneOffset(), GLOBE_BASE, pickGlobe);
  }, []);
  return (
    <div className={styles.stage}>
      {/* The inline script after this element sets src before React loads (first-paint.ts). */}
      <img
        id={FIRST_PAINT_IMG_ID}
        className={styles.svg}
        alt={strings.globe.alt}
        fetchPriority="high"
        // Element Timing: when the SVG globe painted (plan §11, "SVG paints in < 1 s").
        elementtiming="first-paint-globe"
        suppressHydrationWarning
      />
      <div ref={setWebglContainer} className={styles.webgl} aria-hidden="true" />
    </div>
  );
}
