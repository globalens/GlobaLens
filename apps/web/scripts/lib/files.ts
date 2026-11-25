import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/** Every file under a folder, as paths relative to it, sorted. */
export function walk(root: string): string[] {
  const out: string[] = [];
  const visit = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) visit(path);
      else out.push(relative(root, path));
    }
  };
  visit(root);
  return out.sort();
}
