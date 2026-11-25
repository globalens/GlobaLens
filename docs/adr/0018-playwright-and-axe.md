# ADR-0018: Playwright and axe-core check the built site in a browser

Status: proposed · 2026-11-25 · Phase 1 (task 12) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

Several of task 12's checks can only be made in a browser (design note §9 task 12 and §10,
"Static export"): that an unknown `/story/<id>` lands on the globe with `?story=<id>` (a script
in the not-found page does it); that no page triggers a CSP violation or loads anything from
another origin; that the first paint picks the right globe for a time zone and paints in under
a second; and that the plain states read as frame 2 shows them. `CLAUDE.md` adds "axe 0
serious" to the budgets that fail CI, and the owner's done-list asks for axe and for screenshots
at the frames' sizes.

The plan names the tools: Playwright for the smoke test (task 16) and the visual tests (P4), and
axe for components and the main route (§4, "Design-system tooling"). Neither is installed yet.
No metric is involved, so there is no ledger entry.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

There was no bake-off: the plan had named the tools. No prior was written down before the work,
so none is claimed.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

| Option | Why, or why not |
|---|---|
| Playwright Test, with `@axe-core/playwright` | **Chosen.** The plan's tools. One runner for the checks here, task 16's smoke test and P4's visual tests; it can throttle the CPU and network through the DevTools protocol, fix the clock, and stub WebGL before a page's own scripts run |
| Puppeteer | Chrome only, and the plan's later suites are written for Playwright |
| Checks on the HTML text alone | Cannot see a CSP violation, a redirect done by script, or what a browser fetches. The export check does read the HTML text as well (`mise run web:check`), as a second, independent check |

## Decision: exactly one choice

In `apps/web`, as development dependencies, pinned exactly: `@playwright/test` 1.65.1
(Apache-2.0, released 2026-11-13) and `@axe-core/playwright` 4.14.0 (MPL-2.0, 2026-10-15), which
brings `axe-core` 4.14.1. axe-core's licence is file-level copyleft; it runs in the test browser
only, unmodified, and nothing of it ships in the site.

- **The browser.** No browser is downloaded: locally the checks drive the installed Google
  Chrome (`channel: "chrome"`). `GLOBALENS_BROWSER_CHANNEL=chromium` switches to Playwright's own
  Chromium, which CI installs when task 16 wires the checks in.
- **What runs** (`apps/web/e2e/`, `mise run web:e2e`, after a build): at 1440 × 900 and at
  390 × 844 (phone, touch), against `scripts/serve.ts`, which serves the export as Workers Static
  Assets is configured to (ADR-0006). The first paint in four time zones and under throttling;
  the globe's position; the five plain states and the drawer's three detents; the story link
  rule; the headers, the `<meta>` policy, a planted unhashed script being blocked, and no
  request to another origin; axe on the globe page in four states and on the not-found page,
  failing on any serious or critical violation; and the screenshots for the owner.
- `now.json` is answered by the test (`page.route`), never fetched from a real data plane.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

On the owner's Mac (Apple M3 Pro, Google Chrome 158), 2026-11-25: 65 checks pass and 1 is
skipped (the drawer test, on the desktop layout). axe reports no serious or critical violation.

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** Task 16's smoke test, P2's axe gate and P4's visual tests have their runner.

**Harder.** The checks need a build first, so they are not part of `mise run check`; they run as
`mise run web:e2e` and, from task 16, as a CI job.

**Rollback.** Remove `e2e/` and the two packages; the export check still runs.

**Next.** Task 16 adds the job to `ci.yml` with Playwright's Chromium installed, and the smoke
test against a preview.
