// Draw the first-paint globes (design note §3.1 and §9 task 12; Q9; ADR-0017).
//
//   node scripts/gen-globes.ts        # runs before `next dev` and `next build`
//
// One SVG per 15° of longitude, 24 in all, into public/globe/ (generated, not committed). Each is
// the Deep Field globe of frame 3, detent 1: the atmosphere rim, the ocean disc, a 15° graticule,
// the land, interior borders and the coast, tilted to 20° N. d3-geo projects Natural Earth's
// 1:110m countries (the world-atlas package) orthographically and clips them at the horizon. The
// browser downloads one file and runs no projection code.
//
// The globe's radius is 1000 units in a 2160-unit square, so the page sizes the image to
// 2.16 times the radius it wants. Strokes do not scale: their widths are screen pixels.
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { geoGraticule, geoOrthographic, geoPath } from "d3-geo";
import type { GeometryCollection, Topology } from "topojson-specification";
import { feature, mesh } from "topojson-client";

import { GLOBE_LATITUDE, GLOBE_LONGITUDES, globeFileName } from "../src/globe/first-paint.ts";
import { relativePath } from "./lib/svg-path.ts";

export const RADIUS = 1000;
export const HALF_SIZE = 1080; // the rim glow reaches 1.075 radii
const OUT = fileURLToPath(new URL("../public/globe/", import.meta.url));

// Colours: packages/ui/src/tokens.css (--color-atmosphere, ocean, graticule, land, border-country, coast).
const ATMOSPHERE = "#478CC4";
const OCEAN = "#030910";
const GRATICULE = "#141D27";
const LAND = "#11181F";
const BORDER = "#232E39";
const COAST = "#2C3742";

type World = Topology<{ countries: GeometryCollection; land: GeometryCollection }>;

export function loadWorld(): World {
  const require = createRequire(import.meta.url);
  return JSON.parse(readFileSync(require.resolve("world-atlas/countries-110m.json"), "utf8")) as World;
}

/** The SVG for one longitude. Only numbers from d3-geo and fixed tokens go into it. */
export function globeSvg(world: World, lon: number): string {
  const projection = geoOrthographic()
    .rotate([-lon, -GLOBE_LATITUDE, 0])
    .translate([0, 0])
    .scale(RADIUS)
    .clipAngle(90)
    .precision(1);
  const path = geoPath(projection).digits(0);
  const land = relativePath(path(feature(world, world.objects.land)) ?? "");
  const borders = relativePath(path(mesh(world, world.objects.countries, (a, b) => a !== b)) ?? "");
  const graticule = relativePath(path(geoGraticule().step([15, 15])()) ?? "");
  const line = 'fill="none" vector-effect="non-scaling-stroke"';
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${-HALF_SIZE} ${-HALF_SIZE} ${2 * HALF_SIZE} ${2 * HALF_SIZE}">`,
    "<defs>",
    `<radialGradient id="a" cx="0" cy="0" r="1075" gradientUnits="userSpaceOnUse">`,
    `<stop offset=".86" stop-color="${ATMOSPHERE}" stop-opacity="0"/>`,
    `<stop offset=".93" stop-color="${ATMOSPHERE}" stop-opacity=".38"/>`,
    `<stop offset="1" stop-color="${ATMOSPHERE}" stop-opacity="0"/>`,
    "</radialGradient>",
    `<clipPath id="c"><circle r="${RADIUS}"/></clipPath>`,
    `<path id="l" d="${land}"/>`,
    "</defs>",
    `<circle r="1075" fill="url(#a)"/>`,
    `<circle r="${RADIUS}" fill="${OCEAN}"/>`,
    `<g clip-path="url(#c)">`,
    `<path d="${graticule}" ${line} stroke="${GRATICULE}" stroke-width="1"/>`,
    `<use href="#l" fill="${LAND}"/>`,
    `<path d="${borders}" ${line} stroke="${BORDER}" stroke-width=".8"/>`,
    `<use href="#l" ${line} stroke="${COAST}" stroke-width="1"/>`,
    "</g>",
    "</svg>",
    "",
  ].join("\n");
}

function main(): void {
  const world = loadWorld();
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  let bytes = 0;
  for (const lon of GLOBE_LONGITUDES) {
    const svg = globeSvg(world, lon);
    writeFileSync(`${OUT}${globeFileName(lon)}`, svg);
    bytes += Buffer.byteLength(svg);
  }
  console.log(`gen-globes: ${GLOBE_LONGITUDES.length} globes, ${(bytes / 1024).toFixed(0)} KiB, in public/globe/`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
