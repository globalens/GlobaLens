// Languages and text direction (design note Q6: `dir` comes from the language in P1, and `auto`
// only where the language is unknown).
//
// langs.json is generated from packages/gdelt/src/gdelt/lang.py by packages/ui/scripts/gen_langs.py
// and a test keeps the two equal. Its order is the point shards' wire format: a shard stores a
// language as its index in this table.
import table from "./langs.json";

export type Direction = "ltr" | "rtl";

export interface Lang {
  code: string; // GDELT's code
  tag: string; // BCP 47
  endonym: string;
  dir: Direction;
  script: string; // ISO 15924, the likely script
}

export const LANGS: readonly Lang[] = table as Lang[];

export function langByIndex(index: number): Lang | null {
  return Number.isInteger(index) && index >= 0 ? (LANGS[index] ?? null) : null;
}

const BY_TAG = new Map(LANGS.map((lang) => [lang.tag.toLowerCase(), lang.dir]));

// Scripts written right to left (Unicode's bidi class R or AL for their letters).
const RTL_SCRIPTS = new Set([
  "adlm", "arab", "aran", "armi", "avst", "chrs", "cprt", "elym", "hatr", "hebr", "hung", "khar",
  "lydi", "mand", "mani", "mend", "merc", "mero", "narb", "nbat", "nkoo", "orkh", "ougr", "palm",
  "phli", "phlp", "phnx", "prti", "rohg", "samr", "sarb", "sogd", "sogo", "syrc", "thaa", "yezi",
]);

// Languages outside the table whose default script is written right to left.
const RTL_LANGUAGES = new Set([
  "ar", "arc", "azb", "bal", "bqi", "ckb", "dv", "fa", "glk", "he", "iw", "ji", "khw", "ks",
  "lrc", "mzn", "nqo", "pnb", "prs", "ps", "sd", "skr", "syr", "ug", "ur", "yi",
]);

let names: Intl.DisplayNames | null = null;

function isKnownLanguage(code: string): boolean {
  names ??= new Intl.DisplayNames(["en"], { type: "language", fallback: "none" });
  try {
    return names.of(code) !== undefined;
  } catch {
    return false;
  }
}

/** The direction a text in this language is laid out in: its script decides, then its language. */
export function directionOf(tag: string): Direction | "auto" {
  const parts = tag.trim().toLowerCase().split(/[-_]/);
  const language = parts[0] ?? "";
  if (!/^[a-z]{2,3}$/.test(language) || language === "und") return "auto";
  const script = parts.slice(1).find((part) => /^[a-z]{4}$/.test(part));
  if (script) return RTL_SCRIPTS.has(script) ? "rtl" : "ltr";
  const known = BY_TAG.get(language);
  if (known) return known;
  if (RTL_LANGUAGES.has(language)) return "rtl";
  return isKnownLanguage(language) ? "ltr" : "auto";
}
