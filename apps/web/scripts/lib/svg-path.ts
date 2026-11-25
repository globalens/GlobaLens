// d3-geo writes paths as absolute integer moveto/lineto/closepath commands ("M194,-981L171,-984Z").
// Written relative ("M194 -981l-23-3z") the same path is about 40% shorter, gzipped too.

const COMMAND = /([MLZ])([^MLZ]*)/gi;

function pair(text: string): [number, number] {
  const [x, y] = text.split(",").map(Number);
  if (x === undefined || y === undefined || !Number.isInteger(x) || !Number.isInteger(y)) {
    throw new Error(`relativePath: unexpected coordinates "${text}"`);
  }
  return [x, y];
}

function number(value: number, previous: string): string {
  // A minus sign separates two numbers on its own; anything else needs a space.
  return value < 0 || previous === "" ? String(value) : ` ${value}`;
}

export function relativePath(d: string): string {
  if (/[^MLZ0-9,-]/i.test(d)) throw new Error(`relativePath: unexpected command in "${d.slice(0, 40)}"`);
  let out = "";
  let x = 0;
  let y = 0;
  let inLine = false;
  for (const [, command, args = ""] of d.matchAll(COMMAND)) {
    if (command === "Z" || command === "z") {
      out += "z";
      inLine = false;
    } else if (command === "M") {
      [x, y] = pair(args);
      out += `M${x}${number(y, "x")}`;
      inLine = false;
    } else {
      const [nx, ny] = pair(args);
      out += inLine ? number(nx - x, "x") : `l${nx - x}`;
      out += number(ny - y, "x");
      [x, y] = [nx, ny];
      inLine = true;
    }
  }
  return out;
}

/** Every point a path visits, absolute: for tests. */
export function absolutePoints(d: string): [number, number][] {
  const points: [number, number][] = [];
  let x = 0;
  let y = 0;
  for (const [, command, args = ""] of d.matchAll(/([MLZ])([^MLZ]*)/gi)) {
    if (command === "Z" || command === "z") continue;
    const numbers = (args.match(/-?\d+/g) ?? []).map(Number);
    for (let i = 0; i + 1 < numbers.length; i += 2) {
      const a = numbers[i] as number;
      const b = numbers[i + 1] as number;
      [x, y] = command === "l" ? [x + a, y + b] : [a, b];
      points.push([x, y]);
    }
  }
  return points;
}
