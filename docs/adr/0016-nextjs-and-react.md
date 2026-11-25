# ADR-0016: Next.js 16.4 and React 19.3, pinned exactly, for the site

Status: proposed · 2026-11-25 · Phase 1 (task 12) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

Phase 1 task 12 builds the site (`apps/web`). The plan chose the framework (master plan §6, "App
framework"): Next.js 16.4 with the App Router, built as a static export, React 19.3, and the
globe mounted once in `app/(globe)/layout.tsx`. ADR-0001 records the toolchain but not the app
framework, so this ADR adds it. No metric is involved, so there is no ledger entry.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

There was no bake-off: the plan had chosen the framework. No prior was written down before the
work, so none is claimed.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

The plan's comparison stands (§6): server rendering, incremental regeneration, Server Actions,
middleware, rewrites and per-request route handlers are ruled out because a static export has
none of them (trigger: a page that must be rendered per request and can be neither drawn in the
browser nor pre-rendered by the scheduled build); TanStack Start 1.0 was stable only from 13
October 2026; a Vite single-page app has no build-time pre-rendering for link previews and
indexing.

Open in this task: the bundler. Next 16 builds with Turbopack unless told to use webpack.
**Turbopack, the default**: the export it writes passes every check of task 12, two clean builds
are byte for byte the same (`mise run web:repro`), and nothing here needs a webpack plugin.
Trigger to switch: a check that Turbopack cannot pass and webpack can, such as a Trusted Types
policy for the chunk loader (ADR-0006).

## Decision: exactly one choice

In `apps/web`, pinned exactly: `next` 16.4.6 (released 2026-11-09), `react` and `react-dom`
19.3.1 (2026-10-14), and for types `@types/react` and `@types/react-dom` 19.3.0. Each is the
newest release that was 7 days old (ADR-0001's cooldown). `packages/ui` declares React as a peer
and uses the same versions for its tests.

How the app uses it (`apps/web/next.config.ts`):

- `output: 'export'`, `images.unoptimized` (the export cannot optimize images; the site uses
  none), `transpilePackages: ["@globalens/ui"]` (the workspace package is TypeScript and CSS
  Modules), `reactStrictMode`, no `X-Powered-By`, no browser source maps.
- `generateBuildId` returns the commit (ADR-0006).
- The build scripts set `NEXT_TELEMETRY_DISABLED=1`, so a build sends nothing to Vercel.
- Next brings `sharp` as an optional dependency, with prebuilt binaries and no install script.
  The site never optimizes an image, so it is installed and never run.
- No Next feature that needs a server is used, and the static export refuses them at build time.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

On the owner's Mac (Apple M3 Pro), 2026-11-25: `mise run check` passes (21 of 21 tasks), and
`mise run web:build` writes the export: `/`, the not-found page, and the icon. The initial route
loads 156.77 kB of JavaScript and CSS, gzipped, against the 200 kB budget (ADR-0019);
`mise run web:repro` finds two clean builds identical; the browser checks pass (ADR-0018).

Not verified: a build on Linux, on amd64 or arm64 (CI, task 16), and whether the two builds are
the same across machines rather than on one.

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** Pages that need their own link preview (P4, P5) are files the scheduled build
writes; the persistent layout keeps the globe mounted across them.

**Harder.** Next ships often and its security releases matter (plan §9, "Known CVEs"); Renovate
raises them, and each goes through the browser checks. React's own inline flight-data scripts
are what the per-page CSP has to hash (ADR-0006).

**Rollback.** The app is React components and CSS Modules over `packages/ui`; moving to another
React framework would replace the routing and the export, not the components.

**Next.** Task 16 builds the export in CI on Linux and checks the repro there.
