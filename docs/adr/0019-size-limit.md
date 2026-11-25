# ADR-0019: size-limit holds the site's bundle budgets

Status: proposed · 2026-11-25 · Phase 1 (task 12) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

The plan sets two bundle budgets, held by size-limit in CI from P1 (master plan §4,
"Design-system tooling"; design note §15): the initial route at most 200 KB gzipped, and the
globe chunk, loaded after the SVG paint, at most 800 KB gzipped. `CLAUDE.md` lists size-limit
among the budgets that fail CI. Task 12 builds the first route, so the first budget starts here;
the globe chunk arrives with task 13. No metric is recorded in `metrics/ledger.jsonl` by this
task, so there is no ledger entry.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

There was no bake-off: the plan had named the tool. No prior was written down before the work,
so none is claimed.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

| Option | Why, or why not |
|---|---|
| size-limit with its file plugin | **Chosen.** The plan's tool. Sums the gzipped size of a list of files and fails over a limit; the list is computed from the exported page |
| size-limit's app preset | Also times the code in a headless browser; the plan asks for bytes, and the browser checks measure the paint (ADR-0018) |
| A script of our own | Little code, but the plan names size-limit and CI already expects it (ADR-0011, "Waiting for task 12") |

## Decision: exactly one choice

In `apps/web`, as development dependencies, pinned exactly: `size-limit` 14.3.0 and
`@size-limit/file` 14.3.0 (both MIT, released 2026-10-22).

`apps/web/.size-limit.ts` reads `out/index.html` and measures what it loads: its scripts, its
script and style preloads, and its stylesheets, gzipped, against 200 kB. A `nomodule` script is
left out: browsers that run modules never fetch it. Fonts are not in the budget; the export check
reports them (plan §11: "JS is held by size-limit, fonts and tiles reported"). `mise run
web:check` runs it after a build.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

On the owner's Mac, 2026-11-25: the initial route is 156.77 kB gzipped, under 200 kB. React DOM
and Next's runtime are most of it.

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** A dependency that grows the first route past the budget fails the check.

**Harder.** The budget follows whatever the page loads, so a script moved out of the HTML and
loaded later would leave it; task 13's globe chunk gets an entry of its own for that reason.

**Rollback.** Remove the config and the two packages.

**Next.** Task 13 adds the globe chunk's entry (800 kB); task 16 runs `web:check` in CI.
