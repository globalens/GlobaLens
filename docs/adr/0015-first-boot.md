# ADR-0015: The node's first boot: an nftables firewall first, then a one-time token

Status: proposed · 2026-11-25 · Phase 1 (task 7, local half) · Spine: none

## Context: the requirement or measurement that forces a decision (link the metric/ledger entry)

The plan gives the paid node "a first-boot bootstrap with a one-time token and no long-lived
secret in it (containers are kept from any metadata address the provider exposes)" and a
deny-all-inbound firewall, "provider-managed, or a host firewall written by the bootstrap" and
"checked by a boot-time test" (plan §9 and P1 task 7; `docs/design/p1.md` §9, §13). Setup has
not answered whether the `ovh/ovh` provider can manage a firewall for the VPS, nor how OVH passes
a first-boot script on a reinstall (§12). The host firewall is needed either way: the plan makes
it the baseline and the provider's firewall, if there is one, a second layer.

So this task builds what does not depend on those answers: the program the node runs at first
boot, the firewall it writes, and the protocol of the one-time token. It is tested in a
privileged container. New host-side dependencies: nftables, util-linux's `unshare` and systemd,
all part of a Debian 13 install, and the node's own `python3` (cloud-init is Python, so a cloud
image has it). No metric is involved.

## Prior: what you expect each option to measure, before measuring (bake-offs and triggers)

There was no bake-off, and no prior was written down before the work, so none is claimed.

## Options considered: each with cost, risk, ops burden, and the trigger that would change the answer

**The firewall tool.**

| Option | Why not, or why |
|---|---|
| nftables, one table of our own (`inet globalens`), loaded by `nftables.service` | **Chosen.** Debian's default firewall; one table covers IPv4 and IPv6; it coexists with Docker's own rules, which live in other tables: a packet must pass every table's chains on a hook, so another table can add a refusal but cannot undo ours |
| ufw | Its own state on top of iptables; known to be bypassed by Docker's published ports, which is the hole this design closes |
| iptables (legacy) | Debian has moved to nftables; two firewalls in two syntaxes would be worse |
| firewalld | A daemon and zones for a node with one rule set |
| The provider's firewall only | Setup has not said one exists for the VPS; the plan wants the host firewall as the baseline in any case |

What the table does: input is dropped by default, except replies to the node's own connections,
loopback, IPv6 neighbour discovery and DHCP replies (none of them a service). Forward refuses the
provider's metadata address, 169.254.169.254, to containers (the node itself may still reach it:
cloud-init does), and refuses any new connection that arrives by destination NAT, which is how
Docker publishes a port, so not even a port published by mistake reaches a container. The file
never flushes the whole ruleset; it replaces only its own table, so reloading it leaves Docker's
rules in place. There is no SSH: the first boot also masks sshd.

**How the firewall is held to the repository.** The `firewall` command writes
`/etc/nftables.conf` from `deploy/firstboot/firewall.nft`, loads it, and checks the loaded table
against the same file loaded by the same `nft` in a throwaway network namespace (`unshare --net`),
rule for rule, ignoring only handles and counter values. Comparing against nft's own rendering of
our file, not against a fixture, keeps the check exact across nft versions. A systemd unit runs
that command at every boot, and a drop-in makes `docker.service` require it, so a node whose
firewall is not the repository's starts no container. That is the plan's boot-time test. The
check also refuses a `firewall.nft` that does not drop input by default or does not name the
metadata address, so a bad commit to the file cannot pass by matching itself.

**The one-time token.**

| Option | Why not, or why |
|---|---|
| A token naming a short-lived HTTPS address and the SHA-256 of a secrets bundle: `glboot1.` + base64url of `{"url", "sha256"}` | **Chosen.** The user-data, which the provider's metadata service keeps serving, carries no long-lived secret: only an address that expires (the minting side gives it at most 30 minutes) and is deleted once the node is up. The digest means the node takes exactly the bundle that was minted for it. It needs no server of ours: an R2 presigned URL is such an address |
| The secrets themselves in the user-data | The plan forbids it: the metadata service would serve them to anything that reached it, for as long as the instance exists |
| An encrypted bundle with its key in the user-data | Adds a cipher (Python has none in its standard library) and protects nothing against whoever can read the user-data, which holds the key |
| The node makes its own key and CI encrypts to it | A round trip: the node would wait for a merged change after every reinstall |
| A registration service that exchanges the token once | A new service to run and secure. Revisit if a provider-side single-use primitive appears |

The bundle in Phase 1 holds the tunnel token only. The four database passwords are generated on
the node at first boot and never leave it: a rebuild makes new ones, and the ledger is restored
from its export, not from a copy of the database. The program refuses a bundle that holds a name
it does not know or lacks one it requires, so no secret reaches a node without being in
`docs/secrets.md` and in the program's list.

The token is read once, from a root-only file, and the file is deleted whether or not the
redemption worked; a network error or a 5xx is retried for about two minutes (the network or the
clock may not be ready at first boot), a 4xx is not (spent or expired). The address and the
token never appear in what the program prints.

**Where the secrets live.** `/etc/globalens/secrets`: a folder only root may enter, holding files
any user may read. Compose mounts each file into the containers that name it, and those run as
users other than root, so the files must be readable there; on the host the folder keeps everyone
but root out. Compose's `uid`, `gid` and `mode` options for secrets do not apply to file-based
secrets outside Swarm (Compose 5.3.1 says so when they are set: "secrets `uid`, `gid` and `mode`
are not supported, they will be ignored"), so the folder is what protects them.

**The language of the program.** Python's standard library on the node's own `python3`, 3.11 or
later, rather than a shell script: it parses JSON and nft's JSON output, handles TLS and is unit
tested with the rest of the repository. Nothing is installed to run it.

## Decision: exactly one choice

`deploy/firstboot/firstboot.py` with three commands, `run` (the whole first boot), `firewall`
(write, load, check) and `check`, and `deploy/firstboot/firewall.nft`. `run` does, in this order:
the firewall (nothing else happens if its check fails); the boot-time unit and Docker's drop-in;
sshd masked; `/etc/globalens/node.env`; the database passwords if missing; the one-time token.
Every step can run again with the same result.

How the program and the token reach the node, how the token is minted, and how Docker is
installed are the seams this task leaves (`deploy/firstboot/README.md`).

## Evidence: bench/eval/bake-off links; pre-registration; prior vs measured

Run on the owner's Mac (Apple M3 Pro, Docker Desktop 29.7.2, linux/arm64) on 2026-11-25:

- `deploy/tests/docker/test_firstboot.py` (13 tests) boots a privileged Debian 13 container
  with network namespaces standing for the internet, the metadata service and a container behind
  a Docker-style published port. Before the first boot all six paths are open; after it, SSH from
  outside, the published port and the metadata address from the container are closed, while the
  node, and the container, still reach the internet and the bundle server. The bundle is fetched
  once over HTTPS through the new firewall, the secrets land with the modes above, the token file
  is gone, the units are enabled and pass `systemd-analyze verify`, and sshd is masked. Three
  tamperings (a rule opening port 22, the input policy set to accept, the table deleted) each
  really open port 22, and each is caught by `check` and undone by `firewall`. Reloading the file
  leaves the other table's rules. A second run reads no token and keeps the passwords. A spent
  token (HTTP 404) leaves the node locked, with no bundle secret and nothing marked done.
- `deploy/tests/unit/test_firstboot.py` (48 tests) covers the token, the bundle, the retries,
  the comparison and the whole run against a temporary root, a recorded runner and a fake server;
  nothing printed contains the token, its address or a secret.

Not verified: a real node, a real boot under systemd (the container runs no systemd: the units
are written, enabled offline and verified, not started), OVH's metadata address and network
(DHCP or static), IPv6 on the node, and Docker's own rules beside the table (the test stands them
in with a table of the same shape). Nor that a container cannot read a secret file with a
stricter mode: Docker Desktop on macOS let a container's user 10001 read a root-owned file of
mode 0400 through a bind mount, so only Linux (the nodes, and CI once pull request 14 merges)
shows that the files must be 0444.

## Consequences: what gets easier/harder; rollback plan; what we will measure next

**Easier.** A node comes up closed before it holds a secret, stays closed across reboots, and
refuses to start containers if anyone changes its firewall by hand. A firewall change is a
change to one file in the repository.

**Harder.** A change to `firewall.nft` must be loaded on the node before Docker's next start:
the boot unit does it at every boot, and the deployer (task 16) should run `firstboot.py firewall`
when it moves the checkout. With SSH masked, the only ways onto the node are the provider's
console and a rebuild, as the plan intends.

**Rollback.** Delete the table (`nft delete table inet globalens`), disable the unit and remove the
drop-in: Docker then starts without the check. Only through a rebuild, since nothing else reaches
the node.

**Next.** Setup's answers decide how the program and the token are passed (cloud-init user-data
through the OVH API is the expected route) and whether a provider firewall is added as a second
layer in `infra/live/node-paid`. The rebuild workflow mints the token and deletes the bundle once
the node is up. Phase 2 adds one input rule for WireGuard from the free node's fixed address.
