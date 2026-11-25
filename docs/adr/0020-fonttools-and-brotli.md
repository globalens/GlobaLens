# ADR-0020: fontTools and Brotli for the font coverage check

Status: proposed · 2026-11-25 · Phase 1 (task 12) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

The plan asks for "a fontTools CI check" that requires at least 99.9% glyph coverage, over a
fixture week, for every script we ship a font for (master plan §4, "Scripts and languages";
design note §9 task 12 and §10). Until the private `fixtures` bucket exists, the real week stays
on the owner's machine and the check runs there (Q19). The fonts ship as woff2 files (ADR-0006),
and fontTools reads woff2 only with a Brotli decoder. No metric is recorded in
`metrics/ledger.jsonl` by this task, so there is no ledger entry.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

There was no bake-off: the plan had named fontTools. No prior was written down before the work,
so none is claimed.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

| Option | Why, or why not |
|---|---|
| fontTools with Brotli, reading the woff2 files that ship | **Chosen.** The plan's tool, and it checks the very files a browser downloads. fontTools also carries Unicode's script data, which Python's own `unicodedata` lacks |
| fontTools alone, reading the `.woff` siblings Fontsource also ships | No Brotli, but it would check other files than the ones the site serves |
| A JavaScript font parser | The titles come from `packages/gdelt` (Python), which decodes and cleans them exactly as the publisher does |

## Decision: exactly one choice

In the uv workspace's development group, pinned exactly: `fonttools` 4.68.0 (MIT, released
2026-10-27) and `brotli` 1.2.1 (MIT, 2026-10-22), both inside the cooldown date in
`pyproject.toml`, both with wheels for CPython 3.13 on macOS and on Linux x86-64 and aarch64.

`packages/ui/scripts/font_coverage.py` reads every page title of the GKG files it is given the
way the parser does (`gdelt.title.clean_title`), counts every character of every title, and
checks each script with a shipped family against the union of the cmaps of the woff2 files that
family's stylesheet names (`packages/ui/src/fonts.json`). It fails below 99.9%, on no titles, or
on fewer days than asked. Common characters (spaces, digits, punctuation) are checked against all
title families together and reported; scripts drawn by system fonts are reported.

- `mise run fonts:coverage` runs it on `$GLOBALENS_FIXTURE_WEEK`, asking for 7 days.
- Its unit tests build tiny fonts with fontTools and tiny GKG files, and run in `mise run check`;
  the week-long test runs there too when `GLOBALENS_FIXTURE_WEEK` is set, and is skipped
  otherwise.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

On the owner's Mac (Apple M3 Pro), 2026-11-25, over the real fixture week (1,344 files, 9 to 15
November 2026, 2,022,896 titles) in 72 seconds: all 17 scripts the title families draw are
covered in full, 100.000% against 99.9%. The commonest are Latin (98.9 million characters),
Cyrillic (9.3 million), Greek (4.5 million) and Arabic (2.4 million). Common characters are
covered at 99.66%; the ones missing are Chinese and Japanese punctuation, which those titles'
system fonts draw. System fonts draw Han (2.9 million characters), Hangul, Hiragana, Katakana
and, rarely, Canadian syllabics, Khmer, Bopomofo, Myanmar and Tibetan.

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** A font package update that drops glyphs, or a new script in the feed, shows in the
report before a reader sees a missing glyph.

**Harder.** fontTools ships no type information, so its imports and its untyped calls carry
pyright markers, and the tests build their fonts through two names typed as `Any`.

**Rollback.** Remove the script, its tests and the two packages.

**Next.** When task 6 creates the `fixtures` bucket, CI fetches the week and runs the check.
