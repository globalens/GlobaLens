# ADR-0013: OpenTofu tooling: the Cloudflare provider, Conftest, encrypted state in R2, and infra in the check

Status: proposed · 2026-11-25 · Phase 1 (task 6) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

Phase 1 task 6 writes the first OpenTofu stacks (`infra/live/bootstrap`, `infra/live/storage`)
and the Conftest policies that guard them (ADR-0003 has the topology). That adds two
dependencies, and CLAUDE.md asks for an ADR for each new dependency: the Cloudflare provider for
OpenTofu, and Conftest. OpenTofu 1.13 and age were pinned by task 4 (ADR-0001). The plan names
Conftest, client-side state encryption and plan-on-PR (§6 "IaC", §9 "IaC layout"), but leaves
the versions, the key provider, the backend settings and the way the checks run open. No service
and no cost is added: R2 is already in the plan, and its use here stays inside the free tier.
No metric is involved, so there is no ledger entry.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

No bake-off. Expected: the policy checks add seconds, not minutes, to `mise run check`, and need
neither credentials nor the network; a real plan needs read-only credentials and stays out of the
check.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

**The provider.** `cloudflare/cloudflare` 5.29.0 (chosen): the newest release at least 7 days
old on 25 November 2026 (released 11 November), the cooldown of ADR-0001. It has every R2
resource the stacks use: buckets, lifecycle rules, bucket locks, the `r2.dev` managed domain,
custom domains and CORS. The 4.x and 3.x lines still get releases; 5.x is the current major.

**The policy tool.**

| Option | Cost and risk |
|---|---|
| Conftest (chosen; the plan names it) | One binary with OPA 1.21.1 inside and parsers for HCL and JSON, so no conversion step before the rules run |
| OPA alone | Needs a separate HCL-to-JSON step, with its own parser to trust |
| Checkov, Trivy or tfsec | Rule packs aimed at the big clouds; this project's rules (state keys, which bucket is public, where the passphrase comes from) would still be custom |
| Sentinel | HCP Terraform only |

**What the policies read.** The OpenTofu source (no credentials, every pull request) and the
saved plan (needs credentials and real state). Both, because each catches what the other cannot:
the source shows a guard removed before any plan runs; only the plan shows a resource that has
left the source (ADR-0003, rule 2).

**The state encryption key.**

| Option | Cost and risk |
|---|---|
| `pbkdf2` from a passphrase the owner escrows, feeding `aes_gcm` (chosen) | One secret to escrow; it must reach CI as a secret of the protected environment |
| A cloud KMS (`aws_kms`, `gcp_kms`) | A new account and service on the path of every plan |
| OpenBao | A service to run |
| The `external` key provider with age | No passphrase in the environment, but a custom program in the trust path, and the same escrow problem one level down |

**How the passphrase reaches OpenTofu.** An `ephemeral` and `sensitive` variable (chosen), or the
whole encryption configuration in `TF_ENCRYPTION`, which would take it out of review in the
repository. A variable that is only `sensitive` is not enough (see Evidence).

**The backend.** OpenTofu's `s3` backend on R2 with `use_lockfile` (chosen): it locks with a
conditional write (`If-None-Match`), which R2 supports. DynamoDB locking does not exist on R2,
and no locking lets two runs write one state.

**How the checks run.**

| Option | Cost and risk |
|---|---|
| `infra/` as a workspace member that Turborepo runs (chosen) | The same pattern as the Python members: a `package.json` with `lint`, `typecheck` and `test`, so the Stop hook and CI run it with everything else |
| The root `package.json` scripts | Shared with other work in flight (pull request 14 changes them) |
| A CI job of its own | The Stop hook would not run it, and no workflow exists until pull request 14 merges |

`tofu validate` needs the provider's binary, downloaded from the registry, so it is a mise task
of its own (`tofu:validate`), not part of the check: CLAUDE.md keeps network calls out of unit
tests, and CI's egress allow-list does not name `registry.opentofu.org`.

## Decision: exactly one choice

- **Provider:** `cloudflare/cloudflare` 5.29.0, pinned exactly, with each stack's
  `.terraform.lock.hcl` committed (hashes for every platform). Tasks run `init` with
  `-lockfile=readonly`.
- **Conftest 0.71.1** in `mise.toml`.
- **Policies** in `infra/policy`: `hcl.rego` on the source and `plan.rego` on saved plans, with
  Rego unit tests, tests in `policy/tests` that run real files through conftest's parsers, and
  plan fixtures that are real `tofu show -json` output (`policy/testdata/make-plans.sh`). The
  rules: storage keeps `prevent_destroy`; a stack with state encrypts its state and its plans,
  enforced, never with the `unencrypted` method; only the `cdn` bucket is public; the passphrase
  comes from an ephemeral, sensitive variable with no default; each stack keeps its own locked
  state key in R2; no Infrequent Access storage; no plan outside `infra/burst/` destroys.
- **State:** the `s3` backend on R2, bucket `globalens-tofu-state`, key
  `<stack>/terraform.tfstate`, `use_lockfile = true`, with the settings of Cloudflare's guide to
  R2 as a remote backend. Encryption: `pbkdf2` (the passphrase) into `aes_gcm`, `state` and
  `plan` both `enforced = true`.
- **Checks:** `infra` is a pnpm workspace member. `mise run check` runs `tofu fmt -check`,
  `conftest fmt --check`, ruff, pyright and pytest over it. `mise run tofu:validate` runs
  `init -backend=false` and `validate` for every stack (network, no credentials).
  `mise run tofu:plan` plans every stack read-only and checks each plan with
  `infra/policy/check-plan.sh` (credentials; it never applies).
- **Departure from ADR-0001,** which says the workspace covers `apps/*` and `packages/*` only:
  `infra` joins it, with no dependencies, so `pnpm-lock.yaml` does not change.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

Run on 25 November 2026 on the M3 Pro, with the mise on this Mac (2025.4.0).

**How each tool was verified.** mise 2025.4.0 does not check the signatures of these three, so
each was checked by hand and the installed binary compared with the verified one:

| Tool | What mise checked | Checked by hand |
|---|---|---|
| Conftest 0.71.1 | the archive's SHA-256 against the release's `checksums.txt` | `gh attestation verify`: SLSA provenance from `open-policy-agent/conftest`'s `release.yaml` at tag `v0.71.1` (commit `8f7ac01`); installed binary identical |
| OpenTofu 1.13.9 (task 4) | `SHA256SUMS`; it skipped the signature because cosign is not installed | the GPG signature on `SHA256SUMS`, with OpenTofu's key `E3E6E43D84CB852EADB0051D0C0AF313E5FD9F80`, the fingerprint OpenTofu's own installer pins; installed binary identical |
| age 1.3.2 (task 4) | nothing: its install log has no checksum step | `gh attestation verify`: SLSA provenance from `FiloSottile/age`'s `build.yml` at tag `v1.3.2` (commit `b74dce4`); installed `age` and `age-keygen` identical |

`tofu init` installs the provider through the OpenTofu registry and reports it as signed (key ID
`C76001609EE3B136`).

**The checks.**

- `tofu fmt -check`, `tofu init -backend=false` and `tofu validate` pass for every stack
  (`mise run tofu:validate`).
- 43 Rego unit tests and 23 tests through the real parsers pass: every stack in the repository,
  a good fixture stack, 14 copies of it each broken in one way and each refused once with its own
  message, and the plan check on 5 fixture cases. `mise run check` passes, 24 of 24 tasks.
- 31 faults planted in the policies one at a time (a condition dropped, a pattern widened, a
  rule switched off, `check-plan.sh` given the wrong path) are all caught; the real-parser tests
  alone catch 16 of them. They exist to prove the input's shape, not to cover every branch.

**Found while checking.**

- `tofu show -json` printed a variable that was only `sensitive` in clear text, under
  `variables`. With `ephemeral = true` the value was in neither the saved plan nor the JSON.
  Rule 5 of `hcl.rego` requires it.
- `tofu validate` does not look at the backend or encryption blocks: a misspelled backend
  argument and a method keyed by an undefined key provider both pass it. Rule 2 checks the
  encryption block's references.
- `tofu init` refuses a misspelled backend argument, except when `-backend-config` is also
  given: then OpenTofu 1.13.9 accepts it. Both stacks' backend blocks were checked offline, with
  the endpoint in a scratch copy pointed at a dead local port: both get as far as connecting,
  and a planted typo is refused.
- A plan of each stack with a local backend, with every outbound HTTPS request sent to a dead
  local port, works without reaching Cloudflare: `bootstrap` creates 2 resources and `storage` 9,
  and both plans pass `check-plan.sh` (ADR-0003 has the rest).
- mise renders a task's script as a template, so `${#array[@]}` (an opening brace followed by a
  hash sign starts a template comment) made it print the script and fail without running it.
  `tofu:plan` avoids the pair.

**Not verified.** Nothing ran against Cloudflare: no apply, no real plan, no `init` of the real
backend. So it is still open whether `cloudflare_r2_managed_domain` switches the `r2.dev`
address on, and whether `use_lockfile` locks on R2 in practice (Cloudflare's documentation says
R2 supports conditional writes). Not run either: the mise in CI (2026.11.4) installing Conftest,
or whether it checks attestations itself.

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** A change that breaks a rule fails `mise run check` in the session that writes it,
and in CI once pull request 14 merges. A plan is checked before anyone applies it.

**Harder.**

- A provider bump also refreshes each lock file for every platform
  (`tofu providers lock -platform=…`); whether Renovate can do that for OpenTofu's registry is a
  question for its configuration.
- `tofu:validate` and `tofu:plan` run nowhere automatically until task 16 adds a plan job, with
  `registry.opentofu.org` in its egress allow-list. Plan output contains the account ID and the
  bucket names (not secrets) and never the passphrase.
- Every stack that adds state has to follow the rules above; the first other one is `node-paid`
  (task 7).

**Rollback.** Remove `infra` from `pnpm-workspace.yaml` and Conftest from `mise.toml`; the stacks
are plain OpenTofu.

**Next.** Task 16 runs `tofu:validate` and `tofu:plan` in CI and posts the plan on the pull
request; the first real `init` against R2 settles the open points above.
