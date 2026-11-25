"""The role guard against a real PostgreSQL 18, and run as the process an image runs.

The database's epoch is read from the test container's ledger as the role `readonly`, the role
the guard uses on the node. The process tests start `python -m worker.guard` with a lock and a
now.json in a temporary folder and a command that leaves a file behind if it ever runs, so
"refused" means the command did not run at all, not that it ran and failed.
"""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import psycopg
import pytest
from worker import guard
from worker.guard import EpochUnreadable

Connection = psycopg.Connection[tuple[Any, ...]]


class Database(Protocol):
    """The conftest's migrated (or unmigrated) database in the test container."""

    def dsn(self, role: str) -> str: ...


# Leaves a file holding what it inherited in PGPASSWORD ("-" for nothing).
COMMAND = "import os, sys; open(sys.argv[1], 'w').write(os.environ.get('PGPASSWORD', '-'))"
UNREACHABLE = "postgresql://readonly@127.0.0.1:1/globalens"


def test_a_phase_1_ledger_is_at_epoch_0(database: Database) -> None:
    assert guard.read_database_epoch(database.dsn("readonly")) == 0


def test_a_database_with_no_ledger_is_unreadable(unmigrated: Database) -> None:
    with pytest.raises(EpochUnreadable, match="no ledger"):
        guard.read_database_epoch(unmigrated.dsn("readonly"))


def test_an_epoch_table_this_guard_cannot_read_is_unreadable(
    database: Database, admin: Connection
) -> None:
    admin.execute("create table ingest.epoch (epoch bigint not null)")
    try:
        with pytest.raises(EpochUnreadable, match=r"ingest\.epoch"):
            guard.read_database_epoch(database.dsn("readonly"))
    finally:
        admin.execute("drop table ingest.epoch")


def test_a_database_that_cannot_be_reached_is_unreadable() -> None:
    with pytest.raises(EpochUnreadable, match="cannot read"):
        guard.read_database_epoch(UNREACHABLE)


Guard = Callable[..., tuple[subprocess.CompletedProcess[str], Path]]


@pytest.fixture
def run_guard(tmp_path: Path, database: Database) -> Guard:
    """Runs the guard as a process on the paid node. Returns it and the command's marker file."""

    def run(
        *,
        lock: str = 'primary = "paid"\n',
        now: dict[str, object] | None = None,
        dsn: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        (tmp_path / "prod.lock").write_text(lock, encoding="utf-8")
        now_path = tmp_path / "now.json"
        if now is not None:
            now_path.write_text(json.dumps(now), encoding="utf-8")
        marker = tmp_path / "ran"
        environ = {
            "GL_NODE": "paid",
            "GL_PROD_LOCK": str(tmp_path / "prod.lock"),
            "GL_NOW_JSON": str(now_path),
            "GL_DATABASE_URL": dsn or database.dsn("readonly"),
            "PGPASSWORD": "not-needed-under-trust",  # the test server trusts local connections
            "PATH": os.environ.get("PATH", ""),
        }
        command = [sys.executable, "-c", COMMAND, str(marker)]
        done = subprocess.run(
            [sys.executable, "-m", "worker.guard", "cloudflared", "--", *command],
            env=environ,
            capture_output=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        return done, marker

    return run


NOW = {"v": 1, "seq": 41}


def test_the_named_primary_with_a_current_epoch_runs_the_command(run_guard: Guard) -> None:
    done, marker = run_guard(now=NOW)
    assert done.returncode == 0, done.stderr
    assert "cloudflared starts on node 'paid'" in done.stderr
    assert marker.read_text(encoding="utf-8") == "-"  # the password stayed with the guard


def test_a_node_that_prod_lock_does_not_name_primary_runs_nothing(run_guard: Guard) -> None:
    done, marker = run_guard(lock='primary = "free"\n', now=NOW)
    assert done.returncode == guard.EXIT_REFUSED
    assert "prod.lock names 'free' primary" in done.stderr
    assert not marker.exists()


def test_a_node_whose_ledger_epoch_is_older_than_now_json_runs_nothing(run_guard: Guard) -> None:
    done, marker = run_guard(now={**NOW, "epoch": 1})
    assert done.returncode == guard.EXIT_REFUSED
    assert "ledger epoch 0 and now.json at 1" in done.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    "case",
    ["drill", "no now.json", "unreachable database", "database with no ledger"],
)
def test_a_guard_that_cannot_confirm_runs_nothing(
    run_guard: Guard, unmigrated: Database, case: str
) -> None:
    drill = 'primary = "paid"\n[drill]\nnode = "paid"\nservices = ["cloudflared"]\n'
    done, marker = {
        "drill": lambda: run_guard(lock=drill, now=NOW),
        "no now.json": lambda: run_guard(),
        "unreachable database": lambda: run_guard(now=NOW, dsn=UNREACHABLE),
        "database with no ledger": lambda: run_guard(now=NOW, dsn=unmigrated.dsn("readonly")),
    }[case]()
    assert done.returncode == guard.EXIT_REFUSED, done.stderr
    assert "refused" in done.stderr
    assert not marker.exists()
