# ADR-0003: Topology: one paid node in P1, the free node from P2, Cloudflare's free plan, state split by what a change may touch

Status: proposed · 2026-11-25 · Phase 1 (task 6) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

The master plan fixes the target topology: two nodes joined by WireGuard, Cloudflare's free plan
at the edge, R2 for what the public reads and for the archive (§5 "Two nodes", §6 "Compute",
"Edge + web" and "IaC", §9 "IaC layout"), with configuration S growing to M when a
pre-registered trigger fires (§9, §14). Phase 1 builds a subset of it (design note §4), and
since 20 November 2026 it builds that subset without a domain (design note §12.1; plan §17,
question 23). Task 6 writes the first infrastructure code, `infra/live/bootstrap` and
`infra/live/storage`, and the design note names this ADR for it (§9).

This ADR records what runs where in each phase, how the infrastructure code is split into stacks
with their own state, and the rules that keep a change to one stack from reaching another. No
metric is involved yet, so there is no ledger entry.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

There is no bake-off: the plan chose the topology, with its reasons, in §6. What this ADR expects,
from the plan's own figures:

- The paid node's 4 GB holds the P1 processes inside the design note's budget (§4: PostgreSQL
  1.2 GB; the tier-1 workers and the publisher 0.5 GB; the operating system, Docker, the
  exporters, the deployer and cloudflared 0.9 GB), so the sizing trigger stays quiet through P1.
  The plan expects it to fire around P4 (§14).
- R2 stays inside its free allowances in P1 apart from a few cents of storage: the raw zips take
  about 8.4 GB of the free 10 GB *(research)*, and the publisher's writes are held inside the
  free million Class A operations a month (design note §6.6).
- The `r2.dev` address carries a phase with no audience; it is not fit for a launch (§12.1).

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

**Compute.** The plan's §6 weighed these, and its reasons stand:

| Option | Why not, or when it would change |
|---|---|
| One paid node only (8 GB, "M alone") | Every model, job and query beside the ingester, at about twice the price of S. Kept as the fallback if Oracle's node cannot be had or is taken away |
| Paid node plus Oracle's free node (chosen) | — |
| Hetzner as the always-on server | Its cheapest orderable 8 GB plan costs about $34 a month *(research)*; used by the hour only (`infra/burst/`) |
| The free node on the must-run path | Oracle halved the allowance in June 2026 and reclaims idle instances *(research)* |
| Cloud Run with Neon | Scale-to-zero buys nothing for a small, constant load |
| AWS | App Runner is closed |
| Kubernetes (k3s) | Run in the P10 bake-off, not before |

**How the infrastructure code is split.**

| Option | Cost and risk |
|---|---|
| One stack, one state | Every plan touches everything: rebuilding a node would plan against the buckets, and one damaged state blocks every change |
| A stack per part, each with its own state (chosen) | More stacks to plan, and values that cross stacks (the state bucket's name, the `r2.dev` host) are passed on explicitly |

**Where the state lives.**

| Option | Cost and risk |
|---|---|
| R2, in a bucket of its own (chosen) | Free, and in the account that holds the data. R2 has no object versioning, so the bucket keeps only the current state; a lost state is rebuilt by importing the resources, which survive because they carry `prevent_destroy` |
| Another provider's object storage (B2, Oracle) | A second account on the path of every plan, for a state that is useless without the Cloudflare account anyway |
| A hosted Terraform service | Another account and service on the path of every plan, and it reads the state on its side; client-side state encryption is OpenTofu's (§6) |
| The owner's machine | One laptop holds the only copy, and CI cannot plan |

## Decision: exactly one choice

**What runs where.**

| | Compute | Data | Edge |
|---|---|---|---|
| **P1** | The paid node (OVH VPS-1, configuration S, US West): poller, tier-1 workers, publisher, PostgreSQL 18, cost job, deployer, cloudflared with no public hostname (design note §4) | R2 in Western North America (`wnam`, both nodes being in US West: plan §17, question 17): `globalens-raw`, `globalens-lake`, `globalens-cdn`, `globalens-fixtures`, and `globalens-tofu-state` | Cloudflare's free plan: the site on Workers Static Assets at its `workers.dev` address; the data plane at the `cdn` bucket's `r2.dev` address; no zone, no custom domain, no Cache Rules |
| **P2** | The free node joins (Oracle Always Free Ampere A1, arm64) over WireGuard: model workers, heavy jobs, the hot standby; every image for amd64 and arm64 | The raw zips move to the free node's disk and the `raw` bucket goes; `exports` and `models` are added | As P1 until a domain is bought |
| **When the sizing trigger fires** | The paid node moves to VPS-2 (configuration M) and the Anthropic caps drop to M's in the same change (§14). The trigger is pre-registered: PSI "some" above 10% for an hour, or MemAvailable under 15% at p95 over 24 hours, or disk above 70% (§9) | — | — |
| **If Oracle's node is lost for good** | "M alone": the paid node on M runs everything, with backups instead of a standby (§9, §14) | The backup repository moves to R2 | — |

**Stacks.** Each is a root module with its own state, `<folder>/terraform.tfstate` in
`globalens-tofu-state`, encrypted on the machine that runs OpenTofu (ADR-0013):

| Stack | Holds | Applied by |
|---|---|---|
| `infra/live/bootstrap` | The state bucket | The owner, once, from their machine; then its state moves into the bucket |
| `infra/live/storage` | The buckets, their lifecycle rules, the `cdn` bucket's `r2.dev` address; later bucket locks, custom domains and Cache Rules | CI |
| `infra/live/edge` | Zone, DNS, WAF, Tunnel, Access, Turnstile, Email Routing (waits for a domain, §12.1) | CI |
| `infra/live/web` | The static-assets deployment and its previews | CI |
| `infra/live/node-paid`, `node-free` | The two nodes | CI |
| `infra/live/observability`, `github` | Monitoring; the organisation's settings | CI |
| `infra/burst` | Machines by the hour, its own state | A workflow, per scenario |

**Rules that hold it together,** checked by Conftest (`infra/policy`) on every pull request and on
every plan:

1. Every storage resource keeps `prevent_destroy`: every resource of `bootstrap` and `storage`,
   and every R2 resource anywhere.
2. No plan outside `infra/burst/` destroys anything. `prevent_destroy` cannot cover this alone:
   it lives in the resource block, so a change that deletes the block deletes the guard with it,
   and OpenTofu then plans the destroy without complaint (checked; see Evidence).
3. Each stack keeps its state in R2 under its own folder's name, with locking on. Two stacks
   that shared a key would each plan to destroy the other's resources.
4. Only the `cdn` bucket is public. `lake` and `fixtures` hold real headlines.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

Nothing about the topology has been measured yet; nothing has been applied. What was checked on
25 November 2026, on the M3 Pro, with OpenTofu 1.13.9 and the Cloudflare provider 5.29.0:

- `tofu fmt -check`, `tofu init -backend=false` and `tofu validate` pass for every stack, and
  Conftest's policy tests and `mise run check` pass (ADR-0013 lists them).
- A plan of each stack, made in a scratch copy with a local backend, with every outbound HTTPS
  request sent to a dead local port, so that nothing could reach Cloudflare: `bootstrap` would
  create 2 resources and `storage` 9. Both plans pass the plan policy.
- In the same scratch copy, against a state in which every `storage` resource already exists:
  changing a lifecycle rule, adding one, or switching the `r2.dev` address off plans an update in
  place, so `prevent_destroy` does not get in the way of ordinary changes. Changing a bucket's
  `location` plans nothing (R2 honours a location hint only at creation). Deleting the
  `fixtures` bucket's resource blocks plans 2 destroys, with no error from OpenTofu; the plan
  policy refuses both.

What will test this ADR: the paid node's PSI, memory and disk against the sizing trigger during
the P1 soak; the P2 failover drill; the free-tier audit (§9).

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** A node rebuild plans only its own stack, never storage, as CLAUDE.md requires. The
storage stack has two guards that fail independently: `prevent_destroy` on every resource in
the code, and the plan policy for a resource that has left the code. Moving to a domain is the
`edge` stack plus one setting per address (§12.1).

**Harder.**

- One Cloudflare account holds the state and the data (the plan's risk R19). The state is
  encrypted, and the passphrase is escrowed off the account; the database backups go off
  Cloudflare from P4.
- R2 keeps no older state. Task 16's apply workflow should copy a stack's state aside before it
  applies.
- The bootstrap is the one apply that does not go through CI (`infra/live/bootstrap/README.md`).
- Until task 16 the storage stack has no apply path: CI is the only way to production, and the
  owner's one manual apply is the bootstrap. Which comes first is a question for the owner in
  task 6's pull request.
- The `r2.dev` address is rate-limited, uncached and meant for non-production traffic: accepted
  for a phase with no audience (§12.1).

**Rollback.** The stacks are independent. Reverting a stack's code leaves its resources in place
(`prevent_destroy`); a resource that must really go is removed from the state on purpose, never
destroyed by a plan.

**Next.** The `storage` apply (task 16, or an apply workflow before it); the CORS rule on `cdn`
and the per-bucket tokens (task 16); `node-paid` (task 7); the bucket lock on `lake/facts/` (task
20, Q17); `node-free` (P2); the `edge` stack when a domain is bought.
