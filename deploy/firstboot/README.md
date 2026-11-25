# deploy/firstboot

What a GlobaLens node runs once, as root, the first time it boots after an install: it closes the
node to all inbound traffic, then takes its secrets with a one-time token. Why it is built this
way: [ADR-0015](../../docs/adr/0015-first-boot.md). The secrets it writes:
[docs/secrets.md](../../docs/secrets.md).

| File | What |
|---|---|
| `firstboot.py` | The program: `run` (the whole first boot), `firewall` (write, load and check the firewall; also run at every boot), `check` (compare the loaded firewall with `firewall.nft`). Standard library only, on the node's own `python3` |
| `firewall.nft` | The firewall, one nftables table (`inet globalens`): all inbound traffic denied, the metadata address refused to containers, no published port reachable |
| `ruff.toml` | Holds `firstboot.py` to Python 3.11, the oldest `python3` a Debian or Ubuntu node may have |

## What `run` does

In this order, every step safe to repeat (the program's docstring has the detail):

1. Writes `/etc/nftables.conf` from `firewall.nft`, loads it and checks it rule for rule. If the
   check fails, it stops there: a node whose firewall did not load takes no secret.
2. Installs `globalens-firewall-check.service`, which runs `firstboot.py firewall` at every boot,
   and a drop-in that makes `docker.service` require it, so no container starts on a node whose
   firewall is not this repository's.
3. Masks sshd. There is no SSH to a node; it changes only through CI.
4. Writes `/etc/globalens/node.env` (`GL_NODE`, `GL_SECRETS_DIR`) for Compose.
5. Generates the four database passwords, if missing. They never leave the node.
6. Reads the one-time token, fetches the bundle it names over HTTPS, checks its SHA-256 and
   writes its secrets (in Phase 1, `tunnel_token`). The token file is deleted afterwards, whether
   or not that worked; a node that has finished its first boot reads no token again.

The token is `glboot1.` followed by the base64url (padding optional) of
`{"url": "https://…", "sha256": "<64 lowercase hex>"}`; the bundle it names is
`{"v": 1, "secrets": {"tunnel_token": "…"}}`. The program refuses a bundle with a name it does
not know or without one it requires, so adding a secret means adding it to `BUNDLE_SECRETS` in
`firstboot.py` and a row to `docs/secrets.md`, in the same pull request.

## Seams: what the rest of task 7 decides

These wait for the OVH account and the setup answers (`docs/design/p1.md` §12).

- **How the node gets this program and the token.** Expected: cloud-init user-data, passed by
  the OVH API when the operating system is installed or reinstalled. Setup confirms how OVH passes
  it. A sketch of what the user-data would carry, not tested here:

  ```yaml
  #cloud-config
  write_files:
    - path: /run/globalens/firstboot.token   # /run is cleared at every reboot
      permissions: "0600"
      content: glboot1.<minted by the rebuild workflow>
  runcmd:
    - [git, clone, --no-checkout, "https://github.com/globalens/GlobaLens.git", /opt/globalens]
    - [git, -C, /opt/globalens, checkout, --detach, <the commit prod.lock approves>]
    - [python3, -I, /opt/globalens/deploy/firstboot/firstboot.py, run, --node, paid,
       --token-file, /run/globalens/firstboot.token]
  ```

  The program refuses a token file that anyone but its owner (root) may read.
- **Minting the token.** The rebuild workflow builds the bundle, stores it privately, gives it an
  HTTPS address that expires within 30 minutes (an R2 presigned URL is one; R2 is deferred), puts
  that address and the bundle's SHA-256 in the token, and deletes the bundle once the node is up.
  The bundle never enters the repository, a log or a workflow's output.
- **Installing Docker and the pull deployer** (task 16). The deployer should run
  `firstboot.py firewall` after it moves the checkout, so that a change to `firewall.nft` is
  loaded before Docker's next start (the boot unit does it at every boot).
- **A provider-managed firewall.** If setup finds that the `ovh/ovh` provider can manage one, it
  is added in `infra/live/node-paid` as a second layer. This table stays the baseline.
- **`infra/live/node-paid`** follows task 6's state-encryption convention for every stack under
  `infra/live`.
- **Phase 2** adds one input rule to `firewall.nft`: WireGuard from the free node's fixed address.

## Tests

```bash
mise run check       # deploy/tests/unit: the token, the bundle, the comparison, a whole run on a temporary root
mise run test:node   # deploy/tests/docker: the first boot as root in a privileged container, and the stack
```

`deploy/tests/docker/test_firstboot.py` boots the program for real in a privileged Debian 13
container, around which `firstboot_lab.py` builds network namespaces standing for the internet,
the provider's metadata address and a container behind a published port. It checks what gets in
and out before and after, tampers with the firewall three ways, and reloads it beside another
table. Privileged means the container may change its own network stack, nothing else's.
