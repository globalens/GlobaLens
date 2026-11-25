import { expect, test } from "vitest";

import { checkWorkerUrl, WORKER_URL_POLICY } from "./trusted-types";

const ORIGIN = "https://globalens.example-account.workers.dev";

test("same-origin and blob: worker URLs pass", () => {
  expect(checkWorkerUrl("/_next/static/chunks/worker.js", ORIGIN)).toBe(`${ORIGIN}/_next/static/chunks/worker.js`);
  expect(checkWorkerUrl(`blob:${ORIGIN}/5f0e`, ORIGIN)).toBe(`blob:${ORIGIN}/5f0e`);
});

test("any other origin is refused", () => {
  expect(() => checkWorkerUrl("https://cdn.example/worker.js", ORIGIN)).toThrow(WORKER_URL_POLICY);
  expect(() => checkWorkerUrl("data:text/javascript,1", ORIGIN)).toThrow(/may not load/);
});

test("the policy's name is the one the headers file allows", async () => {
  const { readFileSync } = await import("node:fs");
  const headers = readFileSync(new URL("../../public/_headers", import.meta.url), "utf8");
  expect(headers).toContain(`trusted-types ${WORKER_URL_POLICY}`);
});
