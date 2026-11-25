# ADR-0017: d3-geo, topojson-client and world-atlas draw the first-paint globes at build time

Status: proposed · 2026-11-25 · Phase 1 (task 12) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

The first paint is an SVG globe at the visitor's longitude, which the browser's time-zone offset
suggests (design note §3.1, §9 task 12; Q9, approved 25 November 2026), and it must paint in
under a second (plan §11, "SVG paints in < 1 s"). The plan names d3-geo for it (§10, P1 task 12:
"d3-geo SVG placeholder at the visitor's longitude").

Drawing a globe means clipping each country at the horizon. The shortcut the design frames used
(push hidden points out to the rim) only works while the point opposite the viewer is in the
sea. Seen from the Pacific (a time zone of UTC−10) that point is in Africa, and by the same
reasoning the shortcut would paint the ocean as land; it was not tried. d3-geo clips at the
horizon properly.

No metric forces the choice, so there is no ledger entry; the paint time it gives is measured
below.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

No prior was written down before the work, so none is claimed.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

| Option | Why, or why not |
|---|---|
| d3-geo at build time: one SVG per 15° of longitude, 24 in all; an inline script picks one from the time-zone offset | **Chosen.** The land paints as soon as the HTML and one SVG of 9–13 KB (gzipped) have arrived, whether or not React has loaded, and no projection code goes to the browser in P1 |
| d3-geo in the browser, from a land outline in the page | The plan's wording. The land could paint only after React's JavaScript (about 150 kB gzipped) had arrived and run; on a slow phone that is the risky part of the one-second budget. Not built or measured |
| Our own projection and clipping, in the inline script | No dependency, but a correct clip on the sphere is the hard part, and the rim shortcut above fails whenever the far side's centre is on land |
| A raster image per longitude | Larger, blurry when scaled, and the coast and borders could not take the token colours |

Trigger to revisit: P2 makes the SVG globe interactive when WebGL is missing (plan §4,
"States"); that needs projection in the browser, and d3-geo then ships to it as well.

## Decision: exactly one choice

In `apps/web`, as build-time dependencies, pinned exactly: `d3-geo` 3.1.2 (ISC, released
2026-11-03), `topojson-client` 3.1.0 (ISC) and `world-atlas` 2.0.2 (ISC; Natural Earth's vector
data, version 4.1.0, which is in the public domain), with `@types/d3-geo` 3.1.1,
`@types/topojson-client` 3.1.5 and `@types/topojson-specification` 1.0.5.

`apps/web/scripts/gen-globes.ts` runs before `next dev` and `next build` and writes
`public/globe/w180.svg` … `e165.svg` (not committed): Natural Earth's 1:110m countries, projected
orthographically at each longitude and 20° N, clipped at the horizon, with the coast, the
interior borders, a 15° graticule, the ocean disc and the atmosphere rim in the token colours of
frame 3. Paths are written with integer coordinates, relative, which halves their size. Strokes
do not scale, so their widths are screen pixels at any globe size.

The inline script and the in-app fallback run the same function (`src/globe/first-paint.ts`):
the offset's longitude, rounded to the nearest 15° (halves round east) and wrapped into
[−180°, 180°). The globe's size and centre are CSS (`src/globe/stage.module.css`): ring / sin(3000
km / 6371 km), so 353 px on a desktop and 229 px on a phone, centred in the area the panel or the
drawer leaves. Task 13's camera starts from the same longitude, latitude and radius.

The data is Natural Earth, already in `prov/sources.yml` (`natural-earth`); the map credits it.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

On the owner's Mac (Apple M3 Pro), 2026-11-25, on a local build served with gzip:

- With Chrome's CPU slowed 4× and the network at 150 ms latency and 9 Mbit/s, the SVG globe
  painted (Element Timing) between 704 and 760 ms after navigation began, over two runs of the
  desktop and the phone layouts (`e2e/first-paint.spec.ts`; the test fails at 1,000 ms). Local
  runs under emulation, not a measurement on a real phone.
- The browser checks find the right file in four time zones (Kyiv, New York, Tokyo, Honolulu)
  and the globe centred where the frames put it.
- Seen from 150° W the Pacific stays ocean, and from 30° E Africa and Europe are whole: two of
  the 24 files were rendered in Chrome and looked at.
- The 24 files are 669 KiB together; one is 23–32 KB, 9–13 KB gzipped.

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** The first paint does not wait for JavaScript. P4's share cards, which the plan draws
as d3-geo SVG globes, start from the same code.

**Harder.** The first-paint globe is a picture: it does not turn. A visitor whose browser cannot
run WebGL sees it fixed until P2 makes it interactive. Changing the globe's look means changing
the generator, not CSS.

**Rollback.** Delete the generator and the image; the stage falls back to an empty globe area
until WebGL draws.

**Next.** The SVG paint time on the reference Android at the P1 close (plan §11).
