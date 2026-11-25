# ADR-0014: The paid node's images and Compose stack, with cloudflared behind the role guard

Status: proposed · 2026-11-25 · Phase 1 (task 7, local half) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

Phase 1 task 7 puts the paid node's processes in a Docker Compose stack: PostgreSQL 18 pinned by
digest, the poller and the tier-1 workers, and cloudflared with no public hostname, under the
`mem_limit`s of `docs/design/p1.md` §4. The working agreement adds three rules this stack must
keep:

- every image builds for amd64 and arm64, and nothing assumes the free node is present;
- nothing starts cloudflared (or, later, the API, the taste proxy, the admin app, light jobs or
  timers) on a node that `deploy/prod.lock` does not name primary, or whose ledger epoch is not
  current;
- a new dependency or service gets an ADR.

The repository builds no image yet. PostgreSQL is pinned once, for the SQL tests only
(ADR-0007), and that ADR named this task as the point where the tests move to the production
image. This ADR records the new base images, the dbmate binary in an image, cloudflared as a
service, the role guard that starts it, and the shape of `deploy/prod.lock` that the guard reads.

The OVH order, `infra/live/node-paid` and the rebuild workflow are the rest of task 7 and wait for
the setup answers (`docs/design/p1.md` §12); the first boot is ADR-0015.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

There was no bake-off, and no prior was written down before the work, so none is claimed.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

**The images.** Four, from two Dockerfiles, built by one `docker-bake.hcl` for both platforms:

| Image | Base | Why this base |
|---|---|---|
| `postgres` | `postgres:18.6-trixie`, by the digest of its multi-platform index | The official image, already pinned by the SQL tests (ADR-0007). 18.7's image was pushed inside the 7-day cooldown; Renovate moves the pin when a build is old enough. No extension is added in P1: each later one arrives with its task, from a tagged tarball with its checksum (plan §6) |
| `migrate` | the `postgres` image, plus dbmate 2.37.0 | `psql` and `pg_isready` come with the server image; dbmate is the version mise pins, its two static Linux binaries checked by SHA-256 in `ADD --checksum` |
| `worker` | `python:3.13.17-slim-trixie` by digest, with uv 0.13.7 (by digest) in a build stage | The workspace requires Python 3.13; uv installs exactly `uv.lock` (`--locked --no-dev`) with the image's own Python. 3.13.18's build was pushed inside the cooldown |
| `edge` | the `worker` image, plus the `cloudflared` binary from `cloudflare/cloudflared:2026.11.1` by digest | The guard is Python and needs psycopg to read the epoch, so cloudflared joins the worker image rather than the reverse. Cloudflare builds the binary with CGO off, so it runs on Debian as it does in their distroless image |

Not chosen: Alpine bases (pyarrow and psycopg's wheels are built for glibc first, and the SQL
tests already run on Debian); Docker Hardened Images, which the plan brings in P2 with the
attested builds; distroless for the worker (no shell for the entrypoint that reads secret files;
P2 can revisit with the hardened images); a compiler and `psycopg[c]` in the worker image (the
trigger ADR-0008 named): the image keeps `psycopg[binary]` from the lockfile, so the developer's
Mac, CI and the node run the same wheel.

The PostgreSQL pin now lives in `db/Dockerfile` alone. The SQL tests and the ledger's tests build
its `server` target at the start of a run (`db/tests/pg/test_0001_ingest.py`), as ADR-0007's
trigger asked; `GL_TEST_PG_IMAGE` still points them at another image.

**Hardening, in every container:** no capability, `no-new-privileges`, a read-only root file
system with a small `/tmp`, rotated logs, no published port, no host network. PostgreSQL runs as
its image's own user (999) from the start, so its entrypoint never runs as root, with
`oom_score_adj` −500 on the postmaster and 0 on its backends (`PG_OOM_ADJUST_*`). Database
passwords reach containers as Compose secret files (`PGPASSWORD_FILE`, `POSTGRES_PASSWORD_FILE`),
so `docker inspect` never shows one; the test checks it.

**Memory.** The §4 lines are design values. Measured once in this task, by no committed script
*(research)*: in the worker image on arm64, a tier-1 worker peaks at 243 MiB on the largest file
of the fixture week (a 16.0 MB translated zip, 4,145 rows) and 123 MiB on a typical English file;
the poller's imports take 43 MiB. The limits are set from that: `work` 2 × 320m, `poll` 64m,
`postgres` 1200m (the plan's line), `migrate` and `cloudflared` 128m each. So the ingest services
take 704m against a 500m line that also has to hold the publisher. Phase 1 leaves the tier-2,
API and light-jobs lines (1.05 GB) unused, so nothing on the node is short of memory; but the
line in the plan does not hold the design note's two workers. The alternatives: one worker
(64m + 320m = 384m, leaving 116m of the line for the publisher), or keep two and move the line.
That is the owner's choice; this ADR does not make it, and the stack keeps the design note's two
workers until it is made.

**Where the role guard sits.**

| Option | Why not, or why |
|---|---|
| An exec wrapper in the image's entrypoint: `python -m worker.guard cloudflared -- cloudflared …` | **Chosen.** It runs every time the container starts, whoever starts it: Compose, the deployer, or dockerd's restart policy after a reboot, which is exactly how a revived old primary comes back. A `command:` cannot skip it; only an `entrypoint:` override could, and a unit test refuses one in the Compose file |
| A Compose `depends_on` on a guard service | Compose evaluates dependencies only when it runs. dockerd restarts containers after a reboot without Compose |
| A systemd unit condition on the host | Outside the containers, so a manual `docker start` skips it; and it would be host configuration the tests cannot run |
| Profiles that the deployer turns on only on the primary | The same weakness as `depends_on`, and a second place where the role is decided |

What the guard reads, in this order, refusing at the first failure (exit 75, before the command
runs at all; the restart policy asks again, at most a minute apart):

1. `deploy/prod.lock`, mounted read-only: `primary` must name this node, and no `[drill]` may
   stop this service on it.
2. The published `now.json`: in production, the data plane's public `https://` address of
   `cdn/now.json`, which is what a promotion raises. Never the node's own copy, which would
   agree with its own stale database. Plain HTTP is refused. A file path is for the local store
   of a single node and for tests.
3. This node's database, as the role `readonly`: its ledger epoch must not be older than
   `now.json`'s.

**The ledger epoch before Phase 2.** The plan adds `ingest.epoch` and the `epoch` field of
`now.json` with the standby in Phase 2 (`docs/design/p1.md` §2, §5). Until then no promotion can
have happened, so a ledger with no `ingest.epoch` and a `now.json` with no `epoch` both read as
0, and the comparison is already the real one. Anything the guard cannot read is a refusal: a
database with no ledger, a database whose `ingest.epoch` this guard does not know how to read
(Phase 2 changes both in one pull request), a missing or malformed `now.json`. So until the
publisher (task 11, pull request 16) has written its first `now.json`, cloudflared stays down.
That is deliberate: an absent `now.json` is an epoch the guard cannot read, not epoch 0.

**The shape of `deploy/prod.lock`.**

| Option | Why not, or why |
|---|---|
| TOML: `primary = "paid"` and an optional `[drill]` table with `node` and `services` | **Chosen.** Read by the standard library (`tomllib`), so the guard and the deployer add no dependency; comments allowed; no implicit typing (YAML reads `no` as false and `0755` as a number) |
| YAML, as the plan writes `primary:` and `drill:` | PyYAML is only a development dependency (ADR-0007); a production reader would make it a runtime one |
| JSON | No comments, and a bot's diff of it is harder to review |

The guard reads only `primary` and `drill` and ignores other fields, so task 16 can add the image
digests and the site's commit to the same file.

**The node runtime and the build tool.** Docker Engine with the Compose plugin on the node, as
the plan already decides (§4, §9); Buildx bake to build the images. How Docker is installed on
the node is part of the rest of task 7 and of the deployer (task 16).

## Decision: exactly one choice

- **Images:** `db/Dockerfile` (targets `server` and `migrate`) and `apps/worker/Dockerfile`
  (targets `worker` and `edge`), every base pinned by digest and every download by checksum, each
  build context an allow-list (`*.dockerignore`), all four built for `linux/amd64` and
  `linux/arm64` by `docker-bake.hcl` (`mise run images`). Nothing is pushed from here.
- **Stack:** `deploy/compose/node-paid/compose.yaml`: `postgres`, the one-shot `migrate`
  (`db/roles.sql`, each role's password from its secret file, `dbmate up` as `migrator`), `poll`,
  `work` ×2, and `cloudflared`. Every variable is required, with no default: the images by
  digest, `GL_NODE`, `GL_SECRETS_DIR`, `GL_NOW_JSON`.
- **Role guard:** `apps/worker/src/worker/guard.py`, the `edge` image's entrypoint, standard
  library plus psycopg.
- **`deploy/prod.lock`:** TOML, `primary = "paid"`, no drill.

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

Run on the owner's Mac (Apple M3 Pro, Docker Desktop 29.7.2, linux/arm64 containers) on
2026-11-25:

- `docker buildx bake` built all four images for `linux/amd64` and `linux/arm64`. Under
  emulation, the amd64 worker image imports pyarrow 26.0.1 and psycopg (binary), and the amd64
  `cloudflared`, `dbmate` and `postgres` binaries report their versions.
- `deploy/tests/docker/test_stack.py` (9 tests) starts the stack with no internet: the migration
  applies `0001` and runs again with nothing to do; the poller and two workers connect as
  `worker`; PostgreSQL runs as 999 with this repository's `postgresql.conf` and the OOM scores
  above; no port is bound; no password appears in any container's configuration; a wrong password
  is refused over the network. cloudflared starts under the guard when the lock names this node
  and both epochs are 0; it is refused with no `now.json`, with a `now.json` at a newer epoch, and
  with a lock naming the free node; it reads its token from the secret file.
- `apps/worker/tests/unit/test_guard.py` (72 tests) and `apps/worker/tests/pg/test_guard.py`
  (11 tests, against PostgreSQL 18 as the role `readonly`) cover the lock, both epochs and the
  hand-over; the command never runs when the guard refuses.
- The SQL tests (39) and the ledger's tests (76, the property test of 1,000 or more histories
  and the fence-removed run included) pass on the image `db/Dockerfile` builds.
- `deploy/tests/unit/test_compose.py` and `test_images.py` hold the stack and the Dockerfiles to
  the rules above without Docker, under `mise run check`.

Not verified: anything on a real node; the stack on `linux/amd64` (built and imports checked
under emulation only; CI runs the tests on both architectures once pull request 14 merges);
cloudflared connecting to Cloudflare (no tunnel exists yet, and the tests make no network call);
the memory limits under a real week of load (the soak).

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** One PostgreSQL pin. The node runs what CI built, by digest. A revived old primary
keeps cloudflared down without anyone acting, and the same guard will front the API and the
other primary-only services as they arrive.

**Harder.** `mise run test` now builds images, so its first run on a machine pulls the bases.
The guard is one more thing to keep in step with the epoch: Phase 2 must teach it to read
`ingest.epoch` in the same pull request that creates the table, or cloudflared stays down.
cloudflared stays down until the first `now.json` exists. Renovate must be told about the pins
in the Dockerfiles (task 5's configuration).

**Rollback.** Remove `deploy/compose`, the Dockerfiles and `docker-bake.hcl`; point the SQL tests
back at a `postgres` image by digest. The guard is unused without the `edge` image.

**Next.** The publisher joins the stack when pull request 16 merges (one more service of the
worker image, `command: [publish]`, in the ingest line once its memory is measured and the
owner's choice above is made). A committed bench script records the workers' peak memory in
`metrics/ledger.jsonl` before the soak. Task 16 adds the image digests to `prod.lock` and the
pull deployer that runs this stack. The rest of task 7 brings the node.
