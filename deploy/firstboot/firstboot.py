#!/usr/bin/env python3
"""The first boot of a GlobaLens node: lock the node down, then take its secrets, once.

    python3 -I firstboot.py run --node paid --token-file /run/globalens/firstboot.token
    python3 -I firstboot.py firewall
    python3 -I firstboot.py check

It runs as root, from a checkout of this repository on the node. How the provider passes the
checkout's commit and the token at first boot is a setup answer (README.md, "Seams").

`run`, in this order, every step safe to repeat:

1. **Firewall** (the `firewall` command): writes /etc/nftables.conf from firewall.nft beside this
   file, loads it, and checks the loaded table rule for rule against the same file loaded in a
   throwaway network namespace. Nothing else happens until that check passes: a node whose
   firewall did not load takes no secret. Then nftables.service is enabled, so the table is
   loaded at every boot before the network comes up.
2. **Boot-time check.** globalens-firewall-check.service runs the `firewall` command at every
   boot, and a drop-in makes docker.service require it: if the firewall is not the one in the
   repository, Docker does not start, and so no container does.
3. **No SSH.** sshd is disabled and masked. The firewall already drops port 22; this keeps it
   shut if the firewall were ever lost. The node is changed only through CI.
4. **Node settings.** /etc/globalens/node.env with GL_NODE and GL_SECRETS_DIR, for Compose.
5. **Local secrets.** The four database passwords, generated here and never sent anywhere.
   They are written only when missing, so a second run keeps them.
6. **The one-time token.** Read once from --token-file, which is deleted afterwards whether or
   not it worked. It names an HTTPS address and the SHA-256 of a bundle holding the node's
   other secrets (in Phase 1, the tunnel token). The bundle is fetched, checked against the
   digest, and its secrets written. A node that has finished its first boot reads no token
   again.

Secrets go to /etc/globalens/secrets: a folder only root may enter, holding files any user may
read. Compose mounts each file into the containers that name it, and those do not run as root;
on the host, the folder keeps everyone but root out (docs/secrets.md).

Nothing printed carries a secret, the token or the token's address (a bearer credential).
Standard library only, on the node's own python3 (3.11 or later): it runs before anything else
is installed.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import hashlib
import http.client
import json
import os
import re
import secrets
import ssl
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

PROGRAM = Path(__file__).resolve()
HERE = PROGRAM.parent
FIREWALL = HERE / "firewall.nft"
TABLE = ("inet", "globalens")

NFTABLES_CONF = "etc/nftables.conf"
CHECK_UNIT = "globalens-firewall-check.service"
DOCKER_DROPIN = "etc/systemd/system/docker.service.d/globalens.conf"
NODE_ENV = "etc/globalens/node.env"
SECRETS_DIR = "etc/globalens/secrets"
DONE = "var/lib/globalens/firstboot.json"

NODES = ("paid", "free")
LOCAL_SECRETS = ("postgres_password", "migrator_password", "worker_password", "readonly_password")
BUNDLE_SECRETS = {"tunnel_token": True}  # name: required. docs/secrets.md lists every one.
SSH_UNITS = ("ssh.socket", "ssh.service")

TOKEN_PREFIX = "glboot1."
BUNDLE_LIMIT = 64 * 1024
FETCH_TIMEOUT = 30.0
RETRY_WAITS = (5.0, 10.0, 20.0, 40.0, 60.0)  # between tries, for a network error or a 5xx
_SECRET_VALUE = re.compile(r"[\x21-\x7e]{1,4096}")  # printable ASCII: no space, no line break
_HEX64 = re.compile(r"[0-9a-f]{64}")
_PROGRAM_PATH = re.compile(r"/[A-Za-z0-9/._-]+")

EXIT_FAILED = 1
EXIT_USAGE = 2


class BootError(Exception):
    """A step failed. Its message never carries a secret, the token or the token's address."""


class FetchFailed(Exception):
    """The bundle could not be fetched. `retryable` is False when trying again cannot help."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


Runner = Callable[[Sequence[str]], str]
Fetch = Callable[[str], bytes]


def run_command(command: Sequence[str]) -> str:
    """Run a command and return its output. No command here carries a secret."""
    try:
        done = subprocess.run(
            list(command), capture_output=True, text=True, timeout=120, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BootError(f"{command[0]} could not run: {type(error).__name__}") from None
    if done.returncode != 0:
        shown = " ".join(command[:4])
        raise BootError(f"`{shown}` exited with {done.returncode}: {done.stderr.strip()[:400]}")
    return done.stdout


def say(message: str) -> None:
    print(f"firstboot: {message}", flush=True)


# --- files -----------------------------------------------------------------------------------


def write_file(path: Path, text: str, mode: int) -> None:
    """Write `text` to `path` with `mode`, whole or not at all."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    with contextlib.suppress(FileNotFoundError):
        partial.unlink()
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(partial, mode)
        os.replace(partial, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            partial.unlink()
        raise
    folder = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def secrets_folder(root: Path) -> Path:
    """The secrets folder, created if missing, and only root's to enter whatever it was."""
    folder = root / SECRETS_DIR
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder


def write_secret(folder: Path, name: str, value: str) -> None:
    write_file(folder / name, value, 0o444)


# --- the firewall ----------------------------------------------------------------------------


def nftables_conf() -> str:
    """/etc/nftables.conf: firewall.nft with a header saying where it came from."""
    header = (
        "#!/usr/sbin/nft -f\n"
        "# Written by the GlobaLens first boot from deploy/firstboot/firewall.nft at every boot.\n"
        "# Change the repository, not this file: a table that differs from it stops Docker.\n\n"
    )
    return header + FIREWALL.read_text(encoding="utf-8")


def normalize(document: object) -> list[Any]:
    """`nft -j list table` output, without what changes from one load to the next: the
    metainfo entry, object handles and counter values."""

    def strip(value: object) -> Any:
        if isinstance(value, dict):
            stripped: dict[str, Any] = {}
            for key, inner in cast("dict[str, object]", value).items():
                if key == "handle":
                    continue
                if key == "counter" and isinstance(inner, dict):
                    stripped[key] = {"packets": 0, "bytes": 0}
                    continue
                stripped[key] = strip(inner)
            return stripped
        if isinstance(value, list):
            return [strip(inner) for inner in cast("list[object]", value)]
        return value

    if not isinstance(document, dict) or "nftables" not in document:
        raise BootError("nft did not return a ruleset")
    items = cast("list[object]", cast("dict[str, object]", document)["nftables"])
    return [strip(item) for item in items if not _is_metainfo(item)]


def _is_metainfo(item: object) -> bool:
    return isinstance(item, dict) and "metainfo" in cast("dict[str, object]", item)


def _chains(items: list[Any]) -> dict[str, dict[str, Any]]:
    return {item["chain"]["name"]: item["chain"] for item in items if "chain" in item}


def invariants(reference: list[Any]) -> list[str]:
    """What firewall.nft itself must say, whatever else it says: input dropped by default, and
    the metadata address refused to containers."""
    problems: list[str] = []
    chains = _chains(reference)
    entry = chains.get("input")
    if entry is None or entry.get("hook") != "input" or entry.get("policy") != "drop":
        problems.append("firewall.nft has no input chain that drops by default")
    forward = chains.get("forward")
    if forward is None or forward.get("hook") != "forward":
        problems.append("firewall.nft has no forward chain")
    text = json.dumps(reference)
    if "169.254.169.254" not in text:
        problems.append("firewall.nft does not keep containers from the metadata address")
    return problems


def compare(reference: list[Any], live: list[Any] | None) -> list[str]:
    """How the loaded table differs from firewall.nft, as lines a person can act on."""
    if live is None:
        return [f"the table {' '.join(TABLE)} is not loaded"]
    if live == reference:
        return []
    shown = [json.dumps(item, sort_keys=True) for item in reference]
    loaded = [json.dumps(item, sort_keys=True) for item in live]
    problems = [f"the loaded table {' '.join(TABLE)} differs from firewall.nft"]
    problems += [f"  loaded, not in firewall.nft: {line}" for line in loaded if line not in shown]
    problems += [f"  in firewall.nft, not loaded: {line}" for line in shown if line not in loaded]
    if len(problems) == 1:
        problems.append("  the same rules, in another order")
    return problems


def reference_table(runner: Runner) -> list[Any]:
    """firewall.nft as this machine's nft loads it, in a network namespace of its own, so the
    node's own ruleset is not touched."""
    script = 'nft -f "$1" && nft -j list table inet globalens'
    output = runner(["unshare", "--net", "--", "sh", "-c", script, "sh", str(FIREWALL)])
    return normalize(json.loads(output))


def live_table(runner: Runner) -> list[Any] | None:
    try:
        output = runner(["nft", "-j", "list", "table", *TABLE])
    except BootError:
        return None  # nft answers "No such file or directory" for a table that is not there
    return normalize(json.loads(output))


def check(runner: Runner = run_command) -> list[str]:
    """Every way the node's firewall is not the one in this repository; empty if it is."""
    reference = reference_table(runner)
    return invariants(reference) + compare(reference, live_table(runner))


def apply_firewall(root: Path, runner: Runner = run_command) -> None:
    """Write /etc/nftables.conf, load it, and check what was loaded."""
    conf = root / NFTABLES_CONF
    write_file(conf, nftables_conf(), 0o644)
    runner(["nft", "-f", str(conf)])
    problems = check(runner)
    if problems:
        raise BootError("the firewall is not as firewall.nft says:\n" + "\n".join(problems))
    say("firewall loaded and checked: all inbound traffic is denied")


# --- systemd ---------------------------------------------------------------------------------


def systemd_running(root: Path) -> bool:
    """True on a booted system whose manager is systemd (sd_booted)."""
    return root == Path("/") and Path("/run/systemd/system").is_dir()


def systemctl(root: Path, live: bool, *arguments: str) -> list[str]:
    """A systemctl command: against the running manager, or offline on the files under `root`
    (an image or a container with no systemd running)."""
    return ["systemctl", *arguments] if live else ["systemctl", f"--root={root}", *arguments]


def check_unit(program: Path) -> str:
    if not _PROGRAM_PATH.fullmatch(str(program)):
        raise BootError("the checkout's path has characters a unit file cannot hold")
    return (
        "# Written by the GlobaLens first boot (deploy/firstboot/firstboot.py).\n"
        "# At every boot: write the firewall from this checkout, load it and check it. Docker\n"
        "# requires this unit, so no container starts on a node whose firewall is not the one in\n"
        "# the repository.\n"
        "[Unit]\n"
        "Description=GlobaLens: load and check the deny-all-inbound firewall\n"
        "Wants=nftables.service\n"
        "After=nftables.service network-pre.target\n"
        "Before=docker.service\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "RemainAfterExit=yes\n"
        f"ExecStart=/usr/bin/python3 -I {program} firewall\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


DOCKER_DROPIN_TEXT = (
    "# Written by the GlobaLens first boot: Docker, and so every container, starts only after\n"
    f"# the firewall has been loaded and checked ({CHECK_UNIT}).\n"
    "[Unit]\n"
    f"Requires={CHECK_UNIT}\n"
    f"After={CHECK_UNIT}\n"
)


def install_units(root: Path, runner: Runner, live: bool, program: Path) -> None:
    write_file(root / "etc/systemd/system" / CHECK_UNIT, check_unit(program), 0o644)
    write_file(root / DOCKER_DROPIN, DOCKER_DROPIN_TEXT, 0o644)
    if live:
        runner(systemctl(root, live, "daemon-reload"))
    runner(systemctl(root, live, "enable", "nftables.service", CHECK_UNIT))
    say(f"{CHECK_UNIT} installed; docker.service requires it")


def shut_ssh(root: Path, runner: Runner, live: bool) -> None:
    if live:
        with contextlib.suppress(BootError):  # not installed: nothing to stop
            runner(systemctl(root, live, "disable", "--now", *SSH_UNITS))
    runner(systemctl(root, live, "mask", *SSH_UNITS))
    say("sshd masked")


# --- settings and local secrets --------------------------------------------------------------


def write_node_env(root: Path, node: str) -> None:
    text = (
        "# Written by the GlobaLens first boot. Compose reads it with --env-file\n"
        "# (deploy/compose/node-paid/compose.yaml); the deployer adds the images.\n"
        f"GL_NODE={node}\n"
        f"GL_SECRETS_DIR=/{SECRETS_DIR}\n"
    )
    write_file(root / NODE_ENV, text, 0o644)


def write_local_secrets(root: Path) -> list[str]:
    """The database passwords that are missing, generated here. Returns the names written."""
    folder = secrets_folder(root)
    written: list[str] = []
    for name in LOCAL_SECRETS:
        if not (folder / name).exists():
            # base64url: no quoting needed in SQL or in a URL (db/migrate.sh refuses others).
            write_secret(folder, name, secrets.token_urlsafe(32))
            written.append(name)
    return written


# --- the one-time token ----------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    url: str
    sha256: str

    def __repr__(self) -> str:  # never show the address: it is the credential
        return f"Token(sha256={self.sha256[:12]}…)"


def parse_token(text: str) -> Token:
    """`glboot1.` and the base64url of {"url": "https://…", "sha256": "<64 hex>"}."""
    text = text.strip()
    if not text.startswith(TOKEN_PREFIX):
        raise BootError("the token is not a GlobaLens first-boot token")
    body = text[len(TOKEN_PREFIX) :]
    try:
        raw = base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
        document: object = json.loads(raw)
    except (binascii.Error, ValueError):
        raise BootError("the token cannot be read") from None
    if not isinstance(document, dict) or set(cast("dict[str, object]", document)) != {
        "url",
        "sha256",
    }:
        raise BootError("the token must hold exactly an address and a digest")
    fields = cast("dict[str, object]", document)
    url, digest = fields["url"], fields["sha256"]
    if not isinstance(url, str) or not url.startswith("https://") or len(url) > 4096:
        raise BootError("the token's address is not an https:// address")
    if any(character.isspace() for character in url):
        raise BootError("the token's address is not an https:// address")
    if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
        raise BootError("the token's digest is not a SHA-256 in hexadecimal")
    return Token(url=url, sha256=digest)


def read_token(path: Path) -> str:
    """The token, from a file that only its owner, this user, may read."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise BootError(f"no token at {path}") from None
    if not stat.S_ISREG(info.st_mode):
        raise BootError(f"{path} is not a plain file")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise BootError(f"{path} may be read by others: it must be owned by root, mode 0600")
    return path.read_text(encoding="utf-8")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect: the bundle is read from the address the token names."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _describe(error: BaseException) -> str:
    """A failed request in words that cannot hold the address."""
    reason = getattr(error, "reason", error)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return f"certificate not trusted ({reason.verify_message})"
    if isinstance(reason, OSError) and reason.strerror:
        return f"{type(reason).__name__}: {reason.strerror}"
    return type(reason).__name__


def fetch_https(url: str) -> bytes:
    """GET the bundle over HTTPS, with no proxy and no redirect, up to BUNDLE_LIMIT bytes."""
    if not url.startswith("https://"):
        raise FetchFailed("the address is not https://", retryable=False)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    request = urllib.request.Request(url, headers={"User-Agent": "globalens-firstboot"})
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT) as response:
            data = cast("bytes", response.read(BUNDLE_LIMIT + 1))
    except urllib.error.HTTPError as error:
        # 403 and 404: expired or already spent. 3xx: refused above. Neither gets better.
        raise FetchFailed(f"HTTP {error.code}", retryable=error.code >= 500) from None
    except (OSError, http.client.HTTPException) as error:
        raise FetchFailed(_describe(error), retryable=True) from None
    if len(data) > BUNDLE_LIMIT:
        raise FetchFailed(f"the bundle is larger than {BUNDLE_LIMIT} bytes", retryable=False)
    return data


def redeem(token: Token, fetch: Fetch, sleep: Callable[[float], None]) -> bytes:
    """Fetch the bundle, trying again after a network error or a 5xx (the network may not be
    up yet, or the clock not yet right for TLS, at first boot)."""
    for attempt, wait in enumerate((*RETRY_WAITS, None), start=1):
        try:
            return fetch(token.url)
        except FetchFailed as error:
            if not error.retryable or wait is None:
                tries = "1 try" if attempt == 1 else f"{attempt} tries"
                raise BootError(
                    f"the bundle could not be fetched ({error}) after {tries}"
                ) from None
            say(f"fetching the bundle failed ({error}); trying again in {wait:g} s")
            sleep(wait)
    raise AssertionError("unreachable")


def parse_bundle(data: bytes, digest: str) -> dict[str, str]:
    """The bundle's secrets, if it is the bundle the token names and holds what it should."""
    if hashlib.sha256(data).hexdigest() != digest:
        raise BootError("the bundle is not the one the token names (its SHA-256 differs)")
    try:
        document: object = json.loads(data)
    except ValueError:
        raise BootError("the bundle is not JSON") from None
    if not isinstance(document, dict):
        raise BootError("the bundle is not a JSON object")
    fields = cast("dict[str, object]", document)
    if fields.get("v") != 1 or set(fields) != {"v", "secrets"}:
        raise BootError('the bundle must be {"v": 1, "secrets": {...}}')
    found = fields["secrets"]
    if not isinstance(found, dict):
        raise BootError("the bundle's secrets are not a JSON object")
    values = cast("dict[str, object]", found)
    unknown = sorted(set(values) - set(BUNDLE_SECRETS))
    if unknown:
        raise BootError(f"the bundle holds secrets no node takes: {unknown}")
    missing = sorted(
        name for name, required in BUNDLE_SECRETS.items() if required and name not in values
    )
    if missing:
        raise BootError(f"the bundle lacks {missing}")
    for name, value in values.items():
        if not isinstance(value, str) or not _SECRET_VALUE.fullmatch(value):
            raise BootError(f"the bundle's {name} is not 1 to 4096 printable characters")
    return cast("dict[str, str]", values)


# --- the whole first boot --------------------------------------------------------------------


def first_boot(
    node: str,
    token_file: Path,
    *,
    root: Path = Path("/"),
    runner: Runner = run_command,
    fetch: Fetch = fetch_https,
    sleep: Callable[[float], None] = time.sleep,
    live: bool | None = None,
    program: Path = PROGRAM,
) -> None:
    """Steps 1 to 6 of the module's docstring. `root`, `runner`, `fetch`, `sleep` and `live`
    are replaced in tests."""
    if node not in NODES:
        raise BootError(f"a node is one of {list(NODES)}, not {node!r}")
    live = systemd_running(root) if live is None else live

    apply_firewall(root, runner)
    install_units(root, runner, live, program)
    shut_ssh(root, runner, live)
    write_node_env(root, node)
    generated = write_local_secrets(root)
    say(f"node settings written; database passwords generated: {', '.join(generated) or 'none'}")

    done = root / DONE
    try:
        if done.exists():
            say("first boot finished before: no token is read")
            return
        token = parse_token(read_token(token_file))
        bundle = parse_bundle(redeem(token, fetch, sleep), token.sha256)
        folder = secrets_folder(root)
        for name, value in sorted(bundle.items()):
            write_secret(folder, name, value)
        record = {
            "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "node": node,
            "bundle_sha256": token.sha256,
            "secrets_from_bundle": sorted(bundle),
        }
        write_file(done, json.dumps(record, indent=2) + "\n", 0o600)
        say(f"secrets from the bundle written: {', '.join(sorted(bundle))}")
    finally:
        with contextlib.suppress(FileNotFoundError):
            token_file.unlink()
    say("done")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="firstboot.py", description="The first boot of a GlobaLens node."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="the whole first boot")
    run_parser.add_argument("--node", choices=NODES, required=True)
    run_parser.add_argument("--token-file", type=Path, required=True)
    commands.add_parser("firewall", help="write, load and check the firewall")
    commands.add_parser("check", help="check the loaded firewall against firewall.nft")
    arguments = parser.parse_args(argv)
    if os.geteuid() != 0:
        print("firstboot: must run as root", file=sys.stderr)
        return EXIT_USAGE
    try:
        if arguments.command == "run":
            first_boot(arguments.node, arguments.token_file)
        elif arguments.command == "firewall":
            apply_firewall(Path("/"))
        else:
            problems = check()
            if problems:
                print("\n".join(f"firstboot: {line}" for line in problems), file=sys.stderr)
                return EXIT_FAILED
            say("the loaded firewall is the one in firewall.nft")
    except BootError as error:
        print(f"firstboot: {error}", file=sys.stderr)
        return EXIT_FAILED
    return 0


if __name__ == "__main__":
    sys.exit(main())
