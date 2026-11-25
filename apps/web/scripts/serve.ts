// Serve the static export the way Cloudflare Workers Static Assets is configured to (ADR-0006),
// so the browser tests run against a local build:
//
// - auto-trailing-slash HTML handling: /x is x.html or x/index.html;
// - the 404 page for anything else, with status 404 (not_found_handling = "404-page");
// - the response headers of out/_headers, which is not itself served;
// - gzip for text, as Cloudflare compresses what it serves, so timings measured here are fair;
// - and, for a local build only, a data plane under /data/ (src/data/base.ts), from --data.
//
//   node scripts/serve.ts [--port 4321] [--data DIR]
//
// It binds 127.0.0.1 only. How Cloudflare really treats the headers file and the not-found page
// is confirmed at setup, before ADR-0006 is accepted.
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer, type Server } from "node:http";
import { createGzip } from "node:zlib";
import { extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { headersFor, parseHeadersFile } from "./lib/headers.ts";

const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

const COMPRESSED = /^(text\/|application\/json|image\/svg\+xml)/;

function inside(root: string, path: string): string | null {
  const full = normalize(join(root, path));
  return full === root || full.startsWith(root.endsWith(sep) ? root : root + sep) ? full : null;
}

function file(path: string | null): string | null {
  return path && existsSync(path) && statSync(path).isFile() ? path : null;
}

/** The file a request path maps to, or null for the 404 page. */
export function resolve(root: string, pathname: string): string | null {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  if (decoded === "/_headers") return null;
  const exact = file(inside(root, decoded));
  if (exact) return exact;
  const base = decoded.replace(/\/+$/, "");
  return file(inside(root, `${base}.html`)) ?? file(inside(root, `${base}/index.html`)) ?? (decoded === "/" ? file(inside(root, "index.html")) : null);
}

export function serve({ root, port, data }: { root: string; port: number; data?: string | undefined }): Server {
  const headersPath = join(root, "_headers");
  const rules = existsSync(headersPath) ? parseHeadersFile(readFileSync(headersPath, "utf8")) : [];
  const server = createServer((request, response) => {
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    let target: string | null;
    let status = 200;
    if (data && url.pathname.startsWith("/data/")) {
      target = file(inside(data, url.pathname.slice("/data".length)));
      if (!target) status = 404;
    } else {
      target = resolve(root, url.pathname);
      if (!target) {
        status = 404;
        target = file(join(root, "404.html"));
      }
    }
    for (const [name, value] of headersFor(rules, url.pathname)) response.setHeader(name, value);
    if (!target) {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("not found");
      return;
    }
    const type = TYPES[extname(target)] ?? "application/octet-stream";
    const gzip = COMPRESSED.test(type) && /\bgzip\b/.test(String(request.headers["accept-encoding"] ?? ""));
    response.writeHead(status, { "content-type": type, ...(gzip ? { "content-encoding": "gzip", vary: "Accept-Encoding" } : {}) });
    if (request.method === "HEAD") response.end();
    else if (gzip) createReadStream(target).pipe(createGzip()).pipe(response);
    else createReadStream(target).pipe(response);
  });
  server.listen(port, "127.0.0.1");
  return server;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { port: { type: "string", default: "4321" }, data: { type: "string" } } });
  const root = fileURLToPath(new URL("../out/", import.meta.url));
  serve({ root, port: Number(values.port), data: values.data });
  console.log(`serving ${root} at http://127.0.0.1:${values.port}/${values.data ? ` (data plane: ${values.data})` : ""}`);
}
