import { describe, expect, test } from "vitest";

import { firstPaint, firstPaintScript, globeFileName, GLOBE_LONGITUDES, pickGlobe } from "./first-paint";

// Date.getTimezoneOffset() is minutes *behind* UTC: UTC+2 gives -120, UTC-5 gives 300.
describe("pickGlobe: the time-zone offset gives the longitude the first paint faces", () => {
  test.each([
    [0, 0, "e000"], // UTC, London in winter
    [-60, 15, "e015"], // UTC+1
    [-120, 30, "e030"], // UTC+2, Kyiv in winter
    [-330, 90, "e090"], // UTC+5:30, India: 82.5° is halfway, and halves round east
    [-345, 90, "e090"], // UTC+5:45, Nepal: 86.25°
    [-480, 120, "e120"], // UTC+8, Beijing
    [-540, 135, "e135"], // UTC+9, Tokyo
    [-570, 150, "e150"], // UTC+9:30, Adelaide: 142.5° rounds up
    [300, -75, "w075"], // UTC-5, New York in winter
    [480, -120, "w120"], // UTC-8, Los Angeles in winter
    [600, -150, "w150"], // UTC-10, Honolulu
    [720, -180, "w180"], // UTC-12
    [-720, -180, "w180"], // UTC+12: 180° E is 180° W
    [-780, -165, "w165"], // UTC+13, Tonga: 195° wraps to -165°
    [-840, -150, "w150"], // UTC+14, Kiribati
  ])("offset %i min -> %i°", (offset, lon, name) => {
    expect(pickGlobe(offset)).toEqual({ lon, name });
  });

  test("every pick is one of the 24 globes the build draws", () => {
    for (let offset = -14 * 60; offset <= 12 * 60; offset += 15) {
      expect(GLOBE_LONGITUDES).toContain(pickGlobe(offset).lon);
    }
  });

  test("an offset that is not a finite number faces 0°", () => {
    expect(pickGlobe(Number.NaN)).toEqual({ lon: 0, name: "e000" });
  });
});

describe("the 24 globes", () => {
  test("one every 15° from 180° W to 165° E", () => {
    expect(GLOBE_LONGITUDES).toHaveLength(24);
    expect(GLOBE_LONGITUDES[0]).toBe(-180);
    expect(GLOBE_LONGITUDES.at(-1)).toBe(165);
    expect(new Set(GLOBE_LONGITUDES).size).toBe(24);
  });

  test("file names match what pickGlobe asks for", () => {
    expect(globeFileName(-180)).toBe("w180.svg");
    expect(globeFileName(0)).toBe("e000.svg");
    expect(globeFileName(30)).toBe("e030.svg");
  });
});

describe("firstPaint: what the inline script does before React loads", () => {
  function fakeDocument() {
    const img = { src: "" };
    const doc = {
      documentElement: { dataset: {} as Record<string, string> },
      getElementById: (id: string) => (id === "gl-first-paint" ? img : null),
    };
    return { doc, img };
  }

  test("points the globe image at the slot's file and records the longitude", () => {
    const { doc, img } = fakeDocument();
    firstPaint(doc, -120, "/globe/", pickGlobe);
    expect(img.src).toBe("/globe/e030.svg");
    expect(doc.documentElement.dataset["globeLon"]).toBe("30");
  });

  test("does nothing harmful when the image is missing", () => {
    const doc = { documentElement: { dataset: {} as Record<string, string> }, getElementById: () => null };
    expect(() => firstPaint(doc, 0, "/globe/", pickGlobe)).not.toThrow();
    expect(doc.documentElement.dataset["globeLon"]).toBe("0");
  });

  test("the inline script is self-contained: it runs on its own and does the same", () => {
    const { doc, img } = fakeDocument();
    const script = firstPaintScript("/globe/");
    // The script reads the real clock; give it a fixed one.
    const run = new Function("document", "Date", script);
    run(doc, class {
      getTimezoneOffset() {
        return 300;
      }
    });
    expect(img.src).toBe("/globe/w075.svg");
    expect(doc.documentElement.dataset["globeLon"]).toBe("-75");
  });
});
