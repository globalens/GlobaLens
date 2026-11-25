# deploy

What production runs. Production is reached only through CI: merging a change to `prod.lock` is
the owner's approval, and the pull deployer on each node follows it (task 16). No session, human
or agent, deploys from here.

| Path | What |
|---|---|
| `prod.lock` | Which node is primary (`primary = "paid"`) and any planned stoppage (`[drill]`), in TOML. The role guard reads both. Task 16 adds the image digests and the site's commit |
| `compose/node-paid/compose.yaml` | The paid node's stack: PostgreSQL 18, the migration step, the poller, two tier-1 workers, cloudflared behind the role guard. No port is published |
| `firstboot/` | What a node runs at its first boot: the deny-all-inbound firewall, then its secrets with a one-time token ([README](firstboot/README.md)) |
| `tests/unit/` | The stack, the images and the first boot checked without Docker. Part of `mise run check` |
| `tests/docker/` | The stack started, and the first boot run in a privileged container. Part of `mise run test` |

The images are built by `docker-bake.hcl` at the repository root, each for `linux/amd64` and
`linux/arm64` ([ADR-0014](../docs/adr/0014-node-images-and-stack.md)):

```bash
mise run images
```

builds all four for both platforms and keeps them in the build cache; nothing is pushed. To load
this machine's platform into Docker:

```bash
docker buildx bake --load --set '*.platform=linux/arm64'
```

## The role guard

cloudflared starts only through `python -m worker.guard`, the entrypoint of its image
(`apps/worker/src/worker/guard.py`). It runs cloudflared only if `prod.lock` names this node
primary with no drill stopping it, and this node's database is at the ledger epoch of the
published `now.json` or later. Otherwise it exits with 75 before cloudflared runs, and the
container's restart policy asks again. The same guard will front the API, the taste proxy, the
admin app, light jobs and timers as they arrive (CLAUDE.md, Roles).

Until the publisher has written its first `now.json`, the guard cannot read the published epoch,
so cloudflared stays down. In production `GL_NOW_JSON` is the data plane's public `https://`
address of `cdn/now.json`, never the node's own copy.

## Running the stack locally

`mise run test:node` does it in a throwaway project with no internet and removes it afterwards.
By hand, with images built as above and a folder of secret files laid out as the first boot
writes them (`docs/secrets.md`):

```bash
docker compose --env-file node.env -f deploy/compose/node-paid/compose.yaml up -d
```

where `node.env` sets every variable the top of `compose.yaml` lists.

If a test run is killed, its stack can be left behind, with its volumes. Remove any with:

```bash
for p in $(docker compose ls --all --quiet --filter name=gltest-); do docker compose -p "$p" down --volumes; done
```
