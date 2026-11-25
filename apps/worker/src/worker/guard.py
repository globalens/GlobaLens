"""The role guard: what every primary-only service runs before it starts.

    python -m worker.guard <service> -- <command> [<argument> ...]

The guard runs <command> in its own place (exec), so <command> keeps the process, its signals
and its exit status. It does that only if all of these hold, read in this order:

1. `deploy/prod.lock` names this node `primary`, and no `[drill]` in it stops <service> on
   this node.
2. `now.json`, as the current primary last published it, has a ledger epoch that can be read.
3. This node's database has a ledger epoch that can be read, and it is not older than the one
   in `now.json`.

Otherwise it writes the reason to stderr and exits with EXIT_REFUSED, before <command> has
run at all. The container's restart policy starts the guard again, so a node that becomes
primary brings its services up within the restart back-off (Docker caps it at one minute).
The guard sits in the image's entrypoint and not in a Compose dependency because Docker
restarts containers after a reboot on its own, without Compose: a revived old primary is a
node that rebooted.

**Which services.** The ones the working agreement names (CLAUDE.md, Roles): cloudflared, the
API, the taste proxy, the admin app, light jobs and timers. Phase 1 has only cloudflared. The
workers and the publisher are not behind the guard: on a node that is not primary they keep
running but neither lease nor publish, which the ledger epoch enforces inside the ledger once
it exists (plan §7 step 2). The pull deployer is not behind it either: it is what carries out
a change of `primary`.

**Settings** (all required; the guard starts nothing without them):

    GL_NODE          this node's name, `paid` or `free`, written by the node's first boot
    GL_PROD_LOCK     path to deploy/prod.lock, mounted read-only
    GL_NOW_JSON      where the published now.json is read: an https:// address, or a file
    GL_DATABASE_URL  this node's database, as a role that can read the ledger (readonly);
                     the password comes in PGPASSWORD, which <command> does not inherit

**Which now.json.** The one every visitor reads: in production the data plane's public address
of `cdn/now.json`, over HTTPS. Never the node's own copy: after a promotion the new primary
publishes the higher epoch, and only that copy tells a revived old primary that it is stale.
Its own copy would agree with its own old database. A file path is for the local object store
of a single node and for tests; plain HTTP is refused, because whoever could change the answer
in transit could tell a stale node that it is current.

**The ledger epoch before Phase 2.** The epoch is a counter that a promotion raises in the
promoted database and stamps on `now.json` (plan §7 step 2). Its table, `ingest.epoch`, and its
field in `now.json` arrive with the standby in Phase 2 (`docs/design/p1.md` §2, §5). Until then
there has been no promotion, so both sides are at epoch 0: a database without `ingest.epoch`
and a `now.json` without `epoch` both read as 0, and the comparison is already the real one. A
database that does have an `ingest.epoch` table is refused as unreadable, because this guard
does not know the table's shape: Phase 2 teaches the guard to read it in the same change that
creates it. Reading a value is never guessed.
"""

import http.client
import json
import os
import re
import sys
import tomllib
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import psycopg

__all__ = [
    "EXIT_CANNOT_RUN",
    "EXIT_CONFIG",
    "EXIT_REFUSED",
    "NODES",
    "Drill",
    "EpochUnreadable",
    "Lock",
    "LockError",
    "database_epoch",
    "epoch_refusal",
    "main",
    "parse_lock",
    "published_epoch",
    "read_database_epoch",
    "read_lock",
    "read_now_json",
    "role_refusal",
]

NODES = frozenset({"paid", "free"})
"""The nodes of the plan: the paid node (OVH) and the free node (Oracle, from Phase 2)."""

EXIT_REFUSED = 75
"""The guard refused: this node may not run the service now (EX_TEMPFAIL: ask again later)."""

EXIT_CONFIG = 78
"""The guard was called without its settings, or wrongly (EX_CONFIG)."""

EXIT_CANNOT_RUN = 127
"""The guard allowed the command, but the command could not be started."""

_SERVICE = re.compile(r"[a-z][a-z0-9-]{0,62}")
_NOW_LIMIT = 64 * 1024  # now.json is about 1 KB (docs/design/p1.md §6)
_DRILL_KEYS = {"node", "services"}
_CONNECT_SECONDS = 10


class LockError(ValueError):
    """deploy/prod.lock does not say exactly which node is primary."""


class EpochUnreadable(Exception):
    """A ledger epoch could not be read. The guard refuses, as it would for an old one."""


@dataclass(frozen=True)
class Drill:
    """A planned stoppage: `services` stay down on `node` while the entry is in the lock."""

    node: str
    services: frozenset[str]


@dataclass(frozen=True)
class Lock:
    """The part of deploy/prod.lock that the guard reads."""

    primary: str
    drill: Drill | None


def parse_lock(text: str) -> Lock:
    """Read deploy/prod.lock (TOML). Raises LockError unless `primary` names a node and any
    `[drill]` names a node and at least one service."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise LockError(f"not TOML: {error}") from None
    primary = document.get("primary")
    if not isinstance(primary, str) or primary not in NODES:
        raise LockError(f"`primary` must be one of {sorted(NODES)}, not {primary!r}")
    return Lock(primary=primary, drill=_parse_drill(document.get("drill")))


def _parse_drill(value: object) -> Drill | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LockError("`drill` must be a table: [drill] with `node` and `services`")
    table = cast("dict[str, Any]", value)
    unknown = set(table) - _DRILL_KEYS
    if unknown:
        raise LockError(f"`drill` has fields the guard does not know: {sorted(unknown)}")
    node = table.get("node")
    if not isinstance(node, str) or node not in NODES:
        raise LockError(f"`drill.node` must be one of {sorted(NODES)}, not {node!r}")
    services: object = table.get("services")
    if not isinstance(services, list) or not services:
        raise LockError("`drill.services` must be a list of at least one service")
    names = cast("list[object]", services)
    if not all(isinstance(name, str) and _SERVICE.fullmatch(name) for name in names):
        raise LockError(f"`drill.services` must be service names, not {names!r}")
    return Drill(node=node, services=frozenset(cast("list[str]", names)))


def read_lock(path: Path) -> Lock:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LockError(f"cannot read {path}: {error}") from None
    return parse_lock(text)


def role_refusal(lock: Lock, node: str, service: str) -> str | None:
    """Why `service` may not start on `node` under `lock`, or None if the lock allows it."""
    if lock.primary != node:
        return f"prod.lock names {lock.primary!r} primary, and this node is {node!r}"
    if lock.drill is not None and lock.drill.node == node and service in lock.drill.services:
        return f"a drill in prod.lock stops {service!r} on {node!r}"
    return None


def published_epoch(data: bytes) -> int:
    """The ledger epoch of a now.json. One with no `epoch` field predates Phase 2: epoch 0.
    Raises EpochUnreadable for anything that is not a now.json with a valid epoch."""
    try:
        document: object = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EpochUnreadable(f"now.json is not JSON: {error}") from None
    if not isinstance(document, dict):
        raise EpochUnreadable("now.json is not a JSON object")
    fields = cast("dict[str, object]", document)
    if not _is_count(fields.get("seq")):
        raise EpochUnreadable("now.json has no pass number (`seq`), so it is not a now.json")
    epoch = fields.get("epoch", 0)
    if not _is_count(epoch):
        raise EpochUnreadable(f"now.json's `epoch` is not a whole number at or above 0: {epoch!r}")
    return cast("int", epoch)


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect: now.json is read from the address the node was given."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class _Response(Protocol):
    def read(self, amount: int, /) -> bytes: ...


class Opener(Protocol):
    def open(
        self, request: urllib.request.Request, /, *, timeout: float
    ) -> AbstractContextManager[_Response]: ...


_OPENER: Opener = cast("Opener", urllib.request.build_opener(_NoRedirect))


def read_now_json(location: str, *, opener: Opener = _OPENER) -> bytes:
    """The bytes of the published now.json, from an https:// address or a file. Raises
    EpochUnreadable for any other address, a failed read, or a body over 64 KiB."""
    if location.startswith("https://"):
        request = urllib.request.Request(
            location, headers={"Cache-Control": "no-cache", "User-Agent": "globalens-guard"}
        )
        try:
            with opener.open(request, timeout=_CONNECT_SECONDS) as response:
                data = response.read(_NOW_LIMIT + 1)
        except (OSError, http.client.HTTPException) as error:
            # urllib's errors name the address and the status, never a credential: none is sent.
            raise EpochUnreadable(f"cannot read now.json from {location}: {error}") from None
        if len(data) > _NOW_LIMIT:
            raise EpochUnreadable(f"now.json at {location} is larger than {_NOW_LIMIT} bytes")
        return data
    if "://" in location:
        raise EpochUnreadable("now.json is read over https:// or from a file, never otherwise")
    try:
        return Path(location).read_bytes()
    except OSError as error:
        raise EpochUnreadable(f"cannot read now.json: {error.strerror or error}") from None


def database_epoch(conn: psycopg.Connection[tuple[Any, ...]]) -> int:
    """The ledger epoch this node's database carries: 0 for a Phase 1 ledger, which has no
    `ingest.epoch`. Raises EpochUnreadable for a database with no ledger, or with an
    `ingest.epoch` this guard cannot read yet (see the module's note)."""
    found = conn.execute(
        "select to_regclass('ingest.interval') is not null,"
        "       to_regclass('ingest.epoch') is not null"
    ).fetchone()
    if found is None:
        raise EpochUnreadable("the database returned no answer")
    has_ledger, has_epoch = bool(found[0]), bool(found[1])
    if not has_ledger:
        raise EpochUnreadable("this node's database has no ledger (ingest.interval)")
    if has_epoch:
        raise EpochUnreadable(
            "this node's database has an ingest.epoch table, which this guard cannot read yet"
        )
    return 0


def read_database_epoch(dsn: str) -> int:
    """Connect as the guard's role and read the epoch. Any failure is EpochUnreadable."""
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=_CONNECT_SECONDS) as conn:
            return database_epoch(conn)
    except psycopg.Error as error:
        # psycopg's message names the host and the port, never the password.
        raise EpochUnreadable(f"cannot read this node's database: {error}".strip()) from None


def epoch_refusal(database: int, published: int) -> str | None:
    """Why a node whose database is at epoch `database` may not serve when now.json is at
    `published`, or None if its epoch is current."""
    if database < published:
        return (
            f"this node's database is at ledger epoch {database} and now.json at {published}: "
            "another node has been promoted since"
        )
    return None


Execute = Callable[[str, list[str], Mapping[str, str]], object]


def main(
    argv: Sequence[str],
    environ: Mapping[str, str],
    *,
    read_now: Callable[[str], bytes] = read_now_json,
    read_epoch: Callable[[str], int] = read_database_epoch,
    execvp: Execute = os.execvpe,
) -> int:
    """Check, then hand over to the command. Returns an exit status only when it does not
    hand over; `read_now` (now.json's bytes), `read_epoch` (the database's epoch, from a DSN)
    and `execvp` are replaced in tests."""
    usage = "usage: python -m worker.guard <service> -- <command> [<argument> ...]"
    if len(argv) < 3 or argv[1] != "--" or not _SERVICE.fullmatch(argv[0]):
        return _stop(EXIT_CONFIG, usage)
    service, command = argv[0], list(argv[2:])
    settings: dict[str, str] = {}
    for name in ("GL_NODE", "GL_PROD_LOCK", "GL_NOW_JSON", "GL_DATABASE_URL"):
        value = environ.get(name, "")
        if not value:
            return _stop(EXIT_CONFIG, f"{name} is not set; {service} does not start")
        settings[name] = value
    node = settings["GL_NODE"]
    if node not in NODES:
        return _stop(EXIT_CONFIG, f"GL_NODE is {node!r}, not one of {sorted(NODES)}")

    def refused(reason: str) -> int:
        return _stop(EXIT_REFUSED, f"{service} refused on node {node!r}: {reason}")

    try:
        lock = read_lock(Path(settings["GL_PROD_LOCK"]))
    except LockError as error:
        return refused(f"prod.lock: {error}")
    reason = role_refusal(lock, node, service)
    if reason is not None:
        return refused(reason)
    try:
        published = published_epoch(read_now(settings["GL_NOW_JSON"]))
        database = read_epoch(settings["GL_DATABASE_URL"])
    except EpochUnreadable as error:
        return refused(str(error))
    reason = epoch_refusal(database, published)
    if reason is not None:
        return refused(reason)

    print(
        f"guard: {service} starts on node {node!r}: primary in prod.lock, ledger epoch "
        f"{database} (now.json {published})",
        file=sys.stderr,
        flush=True,
    )
    # The command does not inherit the guard's database credential.
    inherited = {
        key: value for key, value in environ.items() if key not in ("PGPASSWORD", "PGPASSWORD_FILE")
    }
    try:
        execvp(command[0], command, inherited)
    except OSError as error:
        return _stop(EXIT_CANNOT_RUN, f"cannot start {command[0]!r}: {error.strerror or error}")
    return EXIT_CANNOT_RUN  # an exec that returns did not run the command


def _stop(status: int, message: str) -> int:
    print(f"guard: {message}", file=sys.stderr, flush=True)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
