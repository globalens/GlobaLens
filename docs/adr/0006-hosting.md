# ADR-0006: The site is a static export on Cloudflare Workers Static Assets

Status: proposed · 2026-11-25 · Phase 1 (task 12) · Spine: none

Accepted only after three things are confirmed on Cloudflare (design note §9, task 12): the
static-asset headers file, the not-found page, and the preview URL per pull request (task 16).
Nothing in this ADR has run on Cloudflare yet: the account has no R2 and nothing is deployed.

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

The plan fixes the shape (master plan §6, rows "App framework" and "Edge + web"; §9): the site is
a Next.js static export served as files by Cloudflare Workers Static Assets, and no Worker runs
on any page request. Phase 1 task 12 builds the shell and has to settle what the plan leaves to
it:

- **The Content Security Policy mechanism** (§9; design note Q21): a per-page `<meta>` policy
  with inline-script hashes, or a post-export step that moves inline scripts into hashed files.
- **The font files** (Q20): vendored, or pinned npm packages.
- **How a preview and production differ** (Q22): one build for both.
- **The story link rule** (§4): every story's own link is the globe with `?story=<id>`, and the
  not-found page turns an unknown `/story/<id>` into that link.
- **The build ID** (§9 step 1): pinned to the commit `deploy/prod.lock` approves, with a check
  that two builds of one commit differ only in pre-rendered HTML and data.

Since 20 November 2026 no domain is bought (design note §12.1): the site will be served at its
`workers.dev` address and the data plane at the `cdn` bucket's `r2.dev` address. No metric
forces these choices, so there is no ledger entry.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

There was no bake-off. The owner approved Q20 to Q22 as recommended on 15 November 2026 (design
note §13, group C). No prior was written down before the work, so none is claimed.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

**Hosting.** The plan's own comparison stands (§6 "Edge + web"): server rendering through
OpenNext on Workers Free (10–20 ms of CPU a request against the free plan's 10 ms, and every
request counts toward 100,000 a day *(research)*), Vercel Hobby (personal or non-commercial use
only *(research)*), and the paid plans (outside the $20 ceiling) were rejected. Static files on
Workers Static Assets are free and unlimited, at most 20,000 files and 25 MiB a file
*(research)*.

**CSP mechanism** (Q21):

| Option | Why, or why not |
|---|---|
| A `<meta>` policy in each exported page, carrying that page's inline-script hashes, written after `next build` | **Chosen**, as Q21 recommends. It changes one tag and leaves Next's output otherwise untouched, and it does not depend on the headers file's line limit. A `<meta>` policy cannot carry `frame-ancestors` or a report-only policy, so those two stay in the headers file |
| A post-export step that moves every inline script into a hashed file | Q21's fallback. Next's flight-data scripts would become extra requests, and the step would have to rewrite Next's markup. Trigger: the `<meta>` policy fails a check, or Cloudflare rewrites HTML in a way that breaks a hash |
| The whole policy in the headers file, one rule per page | Depends on the file's limits on Workers, which are not known yet (§12, Appendix C); every new page would be a new rule |
| Nonces | Need a server that renders each request; there is none |
| `'unsafe-inline'` | Rejected: it would allow any injected script |

**Fonts** (Q20): pinned Fontsource packages (**chosen**: Renovate tracks them, and each ships
`unicode-range` subsets); vendored files (no update path, and the subsetting would be ours to
redo); a font CDN (a third-party request from every page, which the plan forbids).

**Data-plane base** (Q22): from the page's hostname at run time (**chosen**: what a preview
tested is byte for byte what production serves); a build-time variable (two builds, so a preview
would not test the production files).

**Story links**: the not-found page's script (**chosen**, as the plan describes); a Worker that
redirects (a Worker on a page request, which the plan rules out); a `_redirects` rule
(`/story/* /?story=:splat`). Trigger for the last: if setup finds that Workers Static Assets
applies `_redirects` only to paths with no file, so that a pre-rendered `/story/<id>/` page (P4)
still wins, a redirect would spare the not-found page its script. Not checked yet.

## Decision: exactly one choice

The site is a Next.js static export (`output: 'export'`, ADR-0016) served by Cloudflare Workers
Static Assets with these settings and files:

- **Serving.** HTML handling `auto-trailing-slash` (the default); not-found handling `404-page`,
  so any unknown path gets `404.html` with status 404. `scripts/serve.ts` serves a local build
  the same way, and the browser checks run against it.
- **The headers file** (`apps/web/public/_headers`, copied into the export): HSTS for two years
  with subdomains, `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  strict-origin-when-cross-origin`, `Content-Security-Policy: frame-ancestors 'none'`, and
  `Content-Security-Policy-Report-Only: require-trusted-types-for 'script'; trusted-types
  globalens-worker-url` (Trusted Types is report-only in P1 and enforced from P2). Hashed build
  output under `/_next/static/` is cached for a year as immutable; the first-paint globes for a
  day. Until setup says otherwise, the check holds the file to the limits Cloudflare documents
  for Pages: 100 rules, 2,000 characters a line.
- **The page policy** (`apps/web/scripts/csp-postexport.ts`, run by `pnpm build`): a `<meta
  http-equiv="Content-Security-Policy">` placed right after `<meta charset>`, ahead of every
  script and stylesheet:
  `default-src 'none'; script-src 'self' 'wasm-unsafe-eval' <the page's inline-script hashes>;
  style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' <the data planes>
  https://tiles.openfreemap.org; worker-src 'self' blob:; manifest-src 'self'; base-uri 'none';
  form-action 'none'`. There are no frames in P1, so `frame-src` falls back to `'none'`; the
  vault, the bot-check frame and the custom-endpoint frame join it in their phases.
- **Hosts** (`apps/web/site.config.json`): the production site, the preview suffix
  (`-<worker>.<account>.workers.dev`), each one's data-plane base, and the extra `connect-src`
  hosts. The page picks its data plane from its hostname (`src/data/base.ts`); a local build
  reads `/data/` on its own origin. The `workers.dev` and `r2.dev` addresses do not exist yet,
  so they are `null`: until they are filled in, a deployed page says it could not load the
  latest data.
- **The build ID** is the full commit SHA: `GLOBALENS_BUILD_COMMIT` in CI, `git rev-parse HEAD`
  otherwise (`next.config.ts`). `mise run web:repro` builds twice from clean and fails if any
  file other than a page (`.html`) or its flight data (`.txt`) differs.
- **The story link rule**: `404.html` carries an inline script (hashed like the others) that
  sends `/story/<id>` and `/story/<id>/` to `/?story=<id>`, with the id decoded, limited to 200
  characters and encoded again (`src/story/link.ts`).
- **Fonts**: these packages, pinned exactly, all Fontsource 5.3.0 (released 2026-07-19), each
  under the SIL Open Font License 1.1. The browser downloads a file only when a character in its
  `unicode-range` is drawn.

  | Package | Family | Draws |
  |---|---|---|
  | `@fontsource-variable/inter` | Inter Variable | UI, caption, body (exact 450 and 550 weights) |
  | `@fontsource-variable/jetbrains-mono` | JetBrains Mono Variable | micro and data |
  | `@fontsource-variable/newsreader` | Newsreader Variable | chrome headlines |
  | `@fontsource/noto-serif` (400) | Noto Serif | titles in Latin, Cyrillic, Greek |
  | `@fontsource/noto-naskh-arabic` (400) | Noto Naskh Arabic | Arabic-script titles |
  | `@fontsource/noto-serif-hebrew` (400) | Noto Serif Hebrew | Hebrew |
  | `@fontsource/noto-serif-devanagari` (400) | Noto Serif Devanagari | Devanagari |
  | `@fontsource/noto-serif-bengali` (400) | Noto Serif Bengali | Bengali |
  | `@fontsource/noto-serif-tamil` (400) | Noto Serif Tamil | Tamil |
  | `@fontsource/noto-serif-telugu` (400) | Noto Serif Telugu | Telugu |
  | `@fontsource/noto-serif-gujarati` (400) | Noto Serif Gujarati | Gujarati |
  | `@fontsource/noto-serif-gurmukhi` (400) | Noto Serif Gurmukhi | Gurmukhi |
  | `@fontsource/noto-serif-kannada` (400) | Noto Serif Kannada | Kannada |
  | `@fontsource/noto-serif-malayalam` (400) | Noto Serif Malayalam | Malayalam |
  | `@fontsource/noto-serif-sinhala` (400) | Noto Serif Sinhala | Sinhala |
  | `@fontsource/noto-serif-thai` (400) | Noto Serif Thai | Thai |
  | `@fontsource/noto-serif-georgian` (400) | Noto Serif Georgian | Georgian |
  | `@fontsource/noto-serif-armenian` (400) | Noto Serif Armenian | Armenian |

  Chinese, Japanese and Korean titles use the reader's system fonts (plan §4). The list is the
  plan's; `packages/ui/src/fonts.json` is the manifest the coverage check (ADR-0020) and a unit
  test read. Of the scripts with no family here, the fixture week held Chinese, Japanese and
  Korean, and a few characters of others (Canadian syllabics 196, Khmer 28, Bopomofo 23,
  Myanmar 18, Tibetan 1; Ethiopic none): system fonts draw them, and the check reports them.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

On a local build, on the owner's Mac (Apple M3 Pro, macOS 27.2.1), 2026-11-25:

- `mise run web:check`: the script-policy check passes on all three pages (`index.html`,
  `404.html`, `_not-found.html`): one `<meta>` policy, first in `<head>`, every inline script's
  hash listed (8 on the globe page, 7 on the not-found page) and no other; no third-party
  script, stylesheet, image or frame; the header check passes on `_headers`; 178 files, the
  largest 224 KiB.
- `mise run web:e2e` (Playwright in Google Chrome 158, at 1440 × 900 and 390 × 844): no enforced
  CSP violation, no console error and no request to another origin on `/`, on `/story/abc123`
  and on an unknown path; a planted inline script without a hash is blocked; every response
  carries the headers file's headers; `/story/<id>` lands on `/?story=<id>`; an unknown path is
  a plain not-found page with status 404.
- Trusted Types, report-only: one kind of report, on the not-found page only: Turbopack's chunk
  loader sets `HTMLScriptElement.src` when the page's link to the globe prefetches it. Nothing is
  reported on the globe page.
- `mise run web:repro`: two clean builds of one commit produced the same 178 files, byte for
  byte, pages included.
- `mise run fonts:coverage` over the real fixture week (Q19; 1,344 files, 9 to 15 November 2026,
  2,022,896 titles): each of the 17 scripts the title families draw has every one of its
  characters covered, 100.000% against the 99.9% gate (ADR-0020).
- 70 woff2 files, 1,219 KiB in all, ship with the export; a page downloads only the ranges it
  draws. Fonts are reported, not budgeted (plan §11).

**Waiting for Cloudflare** (none of this is a design choice, and the ADR stays proposed until
each is checked):

- that Workers Static Assets reads `_headers` in this form, applies it to every response,
  including `404.html`, and within what limits;
- that `not_found_handling = "404-page"` serves `404.html` with status 404 at an unknown path,
  so the story link script runs there;
- the preview URL per pull request (task 16), and the preview suffix to put in `site.config.json`;
- the `workers.dev` and `r2.dev` addresses, and that the `r2.dev` address answers the site's
  cross-origin requests under the bucket's CORS rule (design note §12.1);
- that Cloudflare serves the HTML unchanged: anything that rewrites a page's inline scripts
  (an HTML-rewriting feature, or script injection for analytics) would break their hashes.

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** Every page is a file, so a launch spike reads files and cannot reach a quota. A
preview tests the files production will serve. The policy is generated, so no hash is ever kept
by hand.

**Harder.** `style-src 'self'` blocks a `style` attribute written into the HTML, so components
style themselves with classes and CSS variables; a style set from script after the page loads
is not affected. Every inline script must be in the HTML when the post-export step runs. Next's
client-side navigation adds none (it fetches flight data as `.txt` files), but a library that
injects inline scripts at run time would be blocked, which the browser checks would show. P2
must give Turbopack's chunk loader a Trusted Types policy (or Next's own, if it has one by then)
before enforcing Trusted Types; the policy name then joins `trusted-types` in the headers file.

**Rollback.** The headers file and the post-export step are independent: dropping the step
leaves pages with no policy (the check fails), and the fallback of Q21 replaces the step without
touching the app.

**Next.** At setup: the confirmations above, the addresses into `site.config.json`, and the
headers file's real limits. Task 16 deploys the export from CI and wires `mise run web:check`,
`web:e2e` and `web:repro` into `ci.yml` (task 5's workflow lists them as waiting for task 12).
