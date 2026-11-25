// Where the globe sits, shared by the SVG first paint (CSS in stage.module.css) and, from task 13,
// the WebGL camera: the two must line up for the crossfade.
//
// The cold start is the Lens's widest aperture (3,000 km) with its ring at a fixed screen size, so
// the globe's radius is ring / sin(3000 km / 6371 km): 353 px on a desktop (ring 160 px, frame 1)
// and 229 px on a phone (ring 104 px, frame 3), centred in the area the panel or drawer leaves.

export const EARTH_RADIUS_KM = 6371;
export const MAX_APERTURE_KM = 3000;

/** The ring's radius in CSS pixels (design frames 1 and 3). */
export const RING_PX = { desktop: 160, phone: 104 } as const;

/** sin(3000 / 6371), the ratio stage.module.css divides the ring by. */
export const RING_TO_RADIUS = Math.sin(MAX_APERTURE_KM / EARTH_RADIUS_KM);

export function globeRadiusPx(ringPx: number): number {
  return ringPx / RING_TO_RADIUS;
}

/** The first-paint SVG is 2160 units square around a 1000-unit globe (scripts/gen-globes.ts). */
export const GLOBE_IMAGE_SCALE = 2.16;
