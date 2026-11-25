// The first paint (design note §3.1 and §9 task 12; Q9): an SVG globe facing the visitor's
// longitude, guessed from the browser's time-zone offset. No prompt, no lookup, no server.
//
// The build draws 24 globes, one every 15° of longitude (scripts/gen-globes.ts, d3-geo over
// Natural Earth). An inline script in the page picks one before React loads, so the land paints
// as soon as the HTML and one small SVG have arrived.

/** The longitudes the build draws: 180° W to 165° E, every 15°. */
export const GLOBE_LONGITUDES: readonly number[] = Array.from({ length: 24 }, (_, i) => -180 + i * 15);

/** The latitude every first-paint globe is tilted to: the populated band faces the viewer. */
export const GLOBE_LATITUDE = 20;

/** Where the globes are served from. */
export const GLOBE_BASE = "/globe/";

/** The id of the <img> the inline script fills in. */
export const FIRST_PAINT_IMG_ID = "gl-first-paint";

export function globeFileName(lon: number): string {
  return `${lon < 0 ? "w" : "e"}${String(Math.abs(lon)).padStart(3, "0")}.svg`;
}

/**
 * The globe for a time-zone offset (Date.getTimezoneOffset(): minutes behind UTC). The offset's
 * longitude, rounded to the nearest 15° and wrapped into [-180°, 180°).
 *
 * Self-contained, because the inline script carries its source: no outer names, no helpers.
 */
export function pickGlobe(offsetMinutes: number): { lon: number; name: string } {
  const step = 15;
  const raw = isFinite(offsetMinutes) ? -offsetMinutes / 4 : 0;
  let lon = Math.round(raw / step) * step;
  lon = ((((lon + 180) % 360) + 360) % 360) - 180;
  if (lon === 0) lon = 0; // never -0
  const abs = Math.abs(lon);
  const name = (lon < 0 ? "w" : "e") + (abs < 10 ? "00" : abs < 100 ? "0" : "") + abs;
  return { lon: lon, name: name };
}

interface FirstPaintDocument {
  documentElement: { dataset: Record<string, string | undefined> };
  getElementById(id: string): object | null;
}

/**
 * What the inline script does: point the globe image at the picked file and record the longitude
 * for the globe stage (and, from task 13, the WebGL camera). Self-contained, like pickGlobe.
 */
export function firstPaint(
  doc: FirstPaintDocument,
  offsetMinutes: number,
  base: string,
  pick: (offset: number) => { lon: number; name: string },
): void {
  const globe = pick(offsetMinutes);
  doc.documentElement.dataset["globeLon"] = String(globe.lon);
  const img = doc.getElementById("gl-first-paint") as { src: string } | null;
  if (img) img.src = base + globe.name + ".svg";
}

/** The inline script's source: both functions above, run on the real document and clock. */
export function firstPaintScript(base: string = GLOBE_BASE): string {
  return `(${firstPaint.toString()})(document,new Date().getTimezoneOffset(),${JSON.stringify(base)},${pickGlobe.toString()})`;
}
