import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

import { GLOBE_IMAGE_SCALE, globeRadiusPx, RING_PX, RING_TO_RADIUS } from "./geometry";

const css = readFileSync(new URL("./stage.module.css", import.meta.url), "utf8");

test("the cold start globe: 353 px on a desktop, 229 px on a phone", () => {
  expect(globeRadiusPx(RING_PX.desktop)).toBeCloseTo(352.7, 1);
  expect(globeRadiusPx(RING_PX.phone)).toBeCloseTo(229.2, 1);
});

test("the stylesheet uses the same ratio and image scale", () => {
  expect(css).toContain(`/ ${RING_TO_RADIUS.toFixed(5)})`);
  expect(css).toContain(`* ${GLOBE_IMAGE_SCALE})`);
  expect(css).toContain(`* ${GLOBE_IMAGE_SCALE / 2})`);
});
