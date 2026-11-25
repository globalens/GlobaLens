// All UI strings live in one module (plan §4; packages/ui/src/strings.ts), so a later language needs
// no refactor. This test fails on visible text typed straight into a component.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { expect, test } from "vitest";

const ROOTS = [new URL("./", import.meta.url).pathname, new URL("../../../packages/ui/src/", import.meta.url).pathname];

function components(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return components(path);
    return path.endsWith(".tsx") && !path.endsWith(".test.tsx") ? [path] : [];
  });
}

// Text between tags (`>Retry<`) and visible attributes with words in them.
const JSX_TEXT = />\s*([^<>{}\s][^<>{}]*?)\s*</g;
const VISIBLE_ATTRIBUTE = /\b(aria-label|aria-description|title|alt|placeholder)="([^"]*[A-Za-z][^"]*)"/g;

test("no component types its own visible text", () => {
  const found: string[] = [];
  for (const root of ROOTS) {
    for (const file of components(root)) {
      const source = readFileSync(file, "utf8")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      for (const match of source.matchAll(JSX_TEXT)) {
        const text = match[1] ?? "";
        // Type parameters (`Array<string>`), arrows (`=> x <`) and comparisons are code, not text.
        if (/[A-Za-z]{2,}/.test(text) && !/[=;()]|&&|\|\|/.test(text)) found.push(`${relative(root, file)}: >${text}<`);
      }
      for (const match of source.matchAll(VISIBLE_ATTRIBUTE)) found.push(`${relative(root, file)}: ${match[0]}`);
    }
  }
  expect(found).toEqual([]);
});
