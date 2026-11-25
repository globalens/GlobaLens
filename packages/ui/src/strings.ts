// Every string the UI shows, in one module (master plan §4: the UI is English in 3.0, and a later
// language needs no refactor). Components import from here; a test fails on text typed into a
// component. Copy for the plain P1 states is the plan's own (§4 "States"; design note Q7, frame 2).

export const strings = {
  meta: {
    title: "GlobaLens",
    description: "A globe of the world’s news coverage, built from the GDELT Project’s open data.",
  },
  brand: {
    name: "GlobaLens",
    home: "GlobaLens, the globe",
  },
  globe: {
    alt: "Globe",
    region: "Globe",
  },
  panel: {
    label: "In the Lens",
    eyebrow: "In the Lens",
    expand: "Show more of the list",
    collapse: "Show less of the list",
  },
  states: {
    loading: "Loading the latest data",
    empty: "No located coverage here in 24 h.",
    failed: "Couldn’t load the latest data.",
    failedShowing: "Showing data from {time}.",
    retry: "Retry",
    noWebgl: "The SVG globe stays, with this list.",
    paused: "Live updates paused; history and cached pages still work",
  },
  attribution: {
    label: "Sources",
    gdelt: "GDELT",
    gdeltTitle: "Source: The GDELT Project",
    naturalEarth: "Natural Earth",
    naturalEarthTitle: "Made with Natural Earth",
  },
  notFound: {
    title: "Page not found",
    body: "There is nothing at this address.",
    back: "Back to the globe",
  },
} as const;

export type Stream = "english" | "translated";

const STREAM_WORDS: Record<Stream, string> = {
  english: "English articles",
  translated: "translated articles",
};

/** The stale badge: per stream, read from the stream stamps in now.json (plan §4 "States"). */
export function staleCopy({ streams, sinceUtc }: { streams: readonly Stream[]; sinceUtc: string }): string {
  const what = streams.length === 1 && streams[0] ? `${STREAM_WORDS[streams[0]]} ` : "";
  return `GDELT hasn’t published ${what}since ${sinceUtc} UTC; showing the last good data`;
}

/** "+11 copies · 4 outlets" (plan §4; design note Q10: counted over the rows loaded). */
export function copiesLabel(copies: number, outlets: number): string {
  return `+${copies} ${copies === 1 ? "copy" : "copies"} · ${outlets} ${outlets === 1 ? "outlet" : "outlets"}`;
}

/** Split a template around {name} placeholders, so a value can be an element, not only text. */
export function interpolate<T>(template: string, values: Record<string, T>): (string | T)[] {
  const out: (string | T)[] = [];
  let last = 0;
  for (const match of template.matchAll(/\{(\w+)\}/g)) {
    const name = match[1] ?? "";
    if (!(name in values)) throw new Error(`interpolate: no value for {${name}}`);
    if (match.index > last) out.push(template.slice(last, match.index));
    out.push(values[name] as T);
    last = match.index + match[0].length;
  }
  if (last < template.length) out.push(template.slice(last));
  return out;
}
