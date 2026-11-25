# Secrets

Every secret GlobaLens uses: its name, what it is for, where it lives, who reads it, who makes
and rotates it, what someone holding it could do, and how to revoke it. **Never a value**, not
even an example of one.

The rules (CLAUDE.md, plan §9):

- A secret gets its row here in the same pull request that first uses it.
- Secrets never go in code, logs, telemetry, commit messages or the repository's history. A
  visitor's own API key is not a secret of ours and never reaches our servers: it lives only in
  `apps/vault` (Phase 3).
- A secret reaches a process as a file or through the provider's secret store, never as a value
  in a Compose file, a unit file or a command line.
- Rotation: every 90 days at most, and at once after a suspected leak. Where a secret expires on
  its own, the date goes in the "Expires" column; from Phase 2 a monthly timer on the paid node
  reads that column and opens an issue 30 days ahead.

## On the paid node

The first boot (`deploy/firstboot/firstboot.py`, ADR-0015) writes these to
`/etc/globalens/secrets/`, one file each: a folder only root may enter (mode 0700), holding files
any user may read (mode 0444). Compose mounts each file into the containers that name it
(`deploy/compose/node-paid/compose.yaml`), as `/run/secrets/<name>`; those containers do not run
as root. A rebuild reinstalls the node and makes all of them anew.

| Secret | For | Made by | Read by | Rotated by | Someone holding it could | Revoke |
|---|---|---|---|---|---|---|
| `postgres_password` | PostgreSQL's superuser, `postgres` | The first boot, on the node (32 random bytes, base64url) | The `postgres` container when it creates the cluster; the migration step (`db/migrate.sh`) | A rebuild | Do anything to the database, from inside the node's Compose network: nothing outside the node can reach PostgreSQL (no port is published; the firewall denies all inbound) | Rebuild the node |
| `migrator_password` | The role `migrator`: runs `dbmate`, owns the schema | The first boot, on the node | The migration step, which also sets it in the database at every start | A rebuild; or a new file and a restart of the stack (the migration step sets it again) | Change the schema, from inside the node | As for rotation |
| `worker_password` | The role `worker`: the poller and the tier-1 workers (and the publisher, with task 11) | The first boot, on the node | `poll`, `work`; set by the migration step | As above | Read and write the ingest ledger, from inside the node | As above |
| `readonly_password` | The role `readonly`: the role guard reads the ledger epoch; later `/stats` | The first boot, on the node | `cloudflared`'s role guard; set by the migration step | As above | Read the ledger, from inside the node | As above |
| `tunnel_token` | cloudflared's credential for the node's Cloudflare Tunnel | Cloudflare, when the edge stack (task 6) creates the tunnel; delivered by the first boot's bundle | `cloudflared` (`TUNNEL_TOKEN_FILE`) | The edge stack from CI rotates the tunnel's secret; then a rebuild delivers the new token (from Phase 2 the deployer can) | Run a connector for our tunnel and receive the traffic of its public hostnames. Phase 1 has none, so: nothing, until the API arrives in Phase 3 | Rotate the tunnel's secret in Cloudflare (through the edge stack). That a rotation cuts off a connector still holding the old token is confirmed in Phase 2 task 17 |

The four database passwords never leave the node: no copy exists anywhere else, and none is
needed, because a rebuild restores the ledger from its export (`exports/`), not from a copy of the
database. They are base64url so that `db/migrate.sh` can place them in SQL and in a URL without
quoting; it refuses any other character.

### The one-time token

| Secret | For | Made by | Read by | Lives | Someone holding it could | Revoke |
|---|---|---|---|---|---|---|
| The first-boot token (`glboot1.…`) | Fetching the node's bundle once, at first boot | The rebuild workflow (the rest of task 7): it builds the bundle, stores it privately, and puts a short-lived HTTPS address for it and the bundle's SHA-256 into the token | The first boot, once | In the provider's user-data (served by its metadata service for the life of the instance) and in `/run/globalens/firstboot.token` until the first boot deletes it | Fetch the bundle (in Phase 1, the tunnel token) until the address expires (at most 30 minutes) or the bundle is deleted (once the node is up), whichever comes first | Delete the bundle. After first boot the token is spent, and containers cannot reach the metadata address (the firewall's forward chain) |

The bundle itself is never committed, logged or kept: it exists only between the rebuild
workflow minting it and the node fetching it.

## In CI and with the owner

Rows for secrets other tasks introduce. Each task completes its row in its own pull request; the
names below are the ones those tasks use.

| Secret | For | Lives | Added by |
|---|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | The Claude review of each pull request | A GitHub Actions secret of the repository | Task 5 (pull request 14) |
| The OpenTofu state passphrase (`state_passphrase`) | Encrypting OpenTofu state and plans client-side | With the owner, escrowed | Task 6 |
| Cloudflare API tokens | OpenTofu's `storage`, `edge` and `web` stacks | With the owner for the one-time bootstrap; then secrets of CI's protected `production` environment (plan §9) | Task 6 |
| `GL_HEALTHCHECK_URL` | The publisher's dead-man ping to Healthchecks.io | On the paid node | Task 11 (pull request 16) and task 16 |
| R2 access keys, one per bucket | The worker's and the publisher's writes to `raw`, `lake` and `cdn` | On the paid node | The task that brings the R2 store |
| OVH API credentials | The `node-paid` stack and the rebuild workflow | A secret of the protected `production` environment | The rest of task 7 |
