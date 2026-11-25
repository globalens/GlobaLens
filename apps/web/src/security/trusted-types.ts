// Trusted Types (master plan §9): one named policy, allowing only same-origin and blob: worker URLs
// (MapLibre, deck.gl and, from P2, the Lens worker). P1 sends the requirement as report-only, in
// public/_headers; P2 enforces it. Task 13 builds its workers' URLs through workerUrl().

export const WORKER_URL_POLICY = "globalens-worker-url";

/** The URL, if a worker may be started from it: our own origin or a blob: made by our code. */
export function checkWorkerUrl(url: string, origin: string): string {
  const parsed = new URL(url, origin);
  if (parsed.protocol === "blob:" || parsed.origin === origin) return parsed.href;
  throw new TypeError(`${WORKER_URL_POLICY}: a worker may not load from ${parsed.origin}`);
}

interface ScriptUrlPolicy {
  createScriptURL(input: string): unknown;
}

interface TrustedTypesFactory {
  createPolicy(name: string, rules: { createScriptURL(input: string): string }): ScriptUrlPolicy;
}

let policy: ScriptUrlPolicy | null = null;

/** A worker URL as the page should pass it to `new Worker(...)`. */
export function workerUrl(url: string): unknown {
  const factory = (globalThis as { trustedTypes?: TrustedTypesFactory }).trustedTypes;
  const origin = globalThis.location.origin;
  if (!factory) return checkWorkerUrl(url, origin);
  policy ??= factory.createPolicy(WORKER_URL_POLICY, { createScriptURL: (input) => checkWorkerUrl(input, origin) });
  return policy.createScriptURL(url);
}
