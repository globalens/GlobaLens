// Unit tests only: e2e/ holds the Playwright checks, which run against a built export.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.ts"],
  },
});
