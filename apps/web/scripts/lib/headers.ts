// The static-asset headers file (public/_headers, copied into the export). Cloudflare Workers
// Static Assets reads it; the format is the one Cloudflare documents for Pages: a path pattern on
// its own line, then indented "Name: value" lines. Its limits on Workers are a setup question
// (design note §12, Appendix C); until then this check holds the file to the Pages limits.

export interface HeaderRule {
  pattern: string;
  headers: [string, string][];
}

export const MAX_RULES = 100;
export const MAX_LINE = 2000;

export function parseHeadersFile(text: string): HeaderRule[] {
  const rules: HeaderRule[] = [];
  for (const raw of text.split(/\r?\n/)) {
    if (raw.trim() === "" || raw.trimStart().startsWith("#")) continue;
    if (!/^\s/.test(raw)) {
      rules.push({ pattern: raw.trim(), headers: [] });
      continue;
    }
    const rule = rules.at(-1);
    const colon = raw.indexOf(":");
    if (!rule || colon === -1) throw new Error(`a header line outside a rule, or without a colon: ${raw.trim()}`);
    rule.headers.push([raw.slice(0, colon).trim(), raw.slice(colon + 1).trim()]);
  }
  return rules;
}

function matcher(pattern: string): RegExp {
  const source = pattern
    .split(/(\*|:[A-Za-z]\w*)/)
    .map((part) => (part === "*" ? ".*" : part.startsWith(":") ? "[^/]+" : part.replace(/[.+?^${}()|[\]\\]/g, "\\$&")))
    .join("");
  return new RegExp(`^${source}$`);
}

/** Every header the file sets for a path, in file order. */
export function headersFor(rules: readonly HeaderRule[], path: string): [string, string][] {
  return rules.filter((rule) => matcher(rule.pattern).test(path)).flatMap((rule) => rule.headers);
}

const REQUIRED: [string, RegExp][] = [
  ["Strict-Transport-Security", /^max-age=(\d+)/],
  ["X-Content-Type-Options", /^nosniff$/],
  ["Referrer-Policy", /^strict-origin-when-cross-origin$/],
  ["Content-Security-Policy", /^frame-ancestors 'none'$/],
  ["Content-Security-Policy-Report-Only", /require-trusted-types-for 'script'/],
];

/** The header check: every page gets the plan's headers (§9, §15), within the assumed limits. */
export function checkHeadersFile(text: string): string[] {
  const problems: string[] = [];
  text.split(/\r?\n/).forEach((line, i) => {
    if (line.length > MAX_LINE) problems.push(`line ${i + 1} is ${line.length} characters, over ${MAX_LINE}`);
  });
  const rules = parseHeadersFile(text);
  if (rules.length > MAX_RULES) problems.push(`${rules.length} rules, over ${MAX_RULES}`);
  for (const path of ["/", "/404.html", "/story/abc"]) {
    const headers = new Map(headersFor(rules, path));
    for (const [name, pattern] of REQUIRED) {
      const value = headers.get(name);
      if (value === undefined) problems.push(`${path}: no ${name}`);
      else if (!pattern.test(value)) problems.push(`${path}: ${name} is "${value}"`);
    }
    const hsts = /^max-age=(\d+)/.exec(headers.get("Strict-Transport-Security") ?? "");
    if (hsts && Number(hsts[1]) < 31536000) problems.push(`${path}: Strict-Transport-Security is under a year`);
  }
  return problems;
}
