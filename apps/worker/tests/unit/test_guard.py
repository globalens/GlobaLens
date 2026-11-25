"""The role guard without a database: the lock, the two epochs, the decision and the hand-over.

The database's epoch is read through a stand-in here; `tests/pg/test_guard.py` reads it from a
real PostgreSQL 18 and runs the guard end to end as a process.
"""

import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

import pytest
from worker import guard
from worker.guard import Drill, EpochUnreadable, Lock, LockError

LOCK = 'primary = "paid"\n'


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def now_json(seq: int = 7, **extra: object) -> bytes:
    return json.dumps({"v": 1, "seq": seq, **extra}).encode()


# --- deploy/prod.lock ------------------------------------------------------------------------


def test_a_lock_names_its_primary() -> None:
    assert guard.parse_lock(LOCK) == Lock(primary="paid", drill=None)
    assert guard.parse_lock('primary = "free"').primary == "free"


def test_a_lock_may_carry_a_drill_for_one_node() -> None:
    lock = guard.parse_lock(
        'primary = "paid"\n[drill]\nnode = "paid"\nservices = ["cloudflared", "api"]\n'
    )
    assert lock.drill == Drill(node="paid", services=frozenset({"cloudflared", "api"}))


def test_a_lock_keeps_fields_the_guard_does_not_read() -> None:
    # Task 16 adds the image digests and the site's commit to the same file.
    text = LOCK + '[images]\nworker = "ghcr.io/globalens/worker@sha256:00"\n'
    assert guard.parse_lock(text).primary == "paid"


@pytest.mark.parametrize(
    "text",
    [
        "",  # no primary
        'primary = ""',
        'primary = "standby"',  # not a node
        'primary = "Paid"',
        "primary = 1",
        "primary = true",
        'primary = ["paid"]',
        "primary = paid",  # not TOML
        'primary = "paid"\nprimary = "free"',  # a key twice is not TOML either
        'primary = "paid"\ndrill = "paid"',  # a drill is a table
        'primary = "paid"\n[drill]\nservices = ["cloudflared"]',  # no node
        'primary = "paid"\n[drill]\nnode = "edge"\nservices = ["cloudflared"]',
        'primary = "paid"\n[drill]\nnode = "paid"',  # no services
        'primary = "paid"\n[drill]\nnode = "paid"\nservices = []',
        'primary = "paid"\n[drill]\nnode = "paid"\nservices = "cloudflared"',
        'primary = "paid"\n[drill]\nnode = "paid"\nservices = ["Cloud Flared"]',
        'primary = "paid"\n[drill]\nnode = "paid"\nservices = ["cloudflared"]\nuntil = 1',
    ],
)
def test_a_lock_that_does_not_say_exactly_who_is_primary_is_refused(text: str) -> None:
    with pytest.raises(LockError):
        guard.parse_lock(text)


def test_the_committed_lock_names_the_paid_node_primary_with_no_drill() -> None:
    committed = Path(__file__).resolve().parents[4] / "deploy" / "prod.lock"
    assert guard.read_lock(committed) == Lock(primary="paid", drill=None)


# --- the role ---------------------------------------------------------------------------------


def test_the_named_primary_may_start_a_service() -> None:
    assert guard.role_refusal(Lock("paid", None), "paid", "cloudflared") is None


def test_a_node_that_is_not_the_named_primary_may_not() -> None:
    reason = guard.role_refusal(Lock("free", None), "paid", "cloudflared")
    assert reason is not None
    assert "free" in reason and "paid" in reason


def test_a_drill_keeps_its_services_down_on_its_node_only() -> None:
    drill = Drill(node="paid", services=frozenset({"cloudflared"}))
    reason = guard.role_refusal(Lock("paid", drill), "paid", "cloudflared")
    assert reason is not None and "drill" in reason
    assert guard.role_refusal(Lock("paid", drill), "paid", "api") is None
    other = Drill(node="free", services=frozenset({"cloudflared"}))
    assert guard.role_refusal(Lock("paid", other), "paid", "cloudflared") is None


# --- the epochs -------------------------------------------------------------------------------


def test_a_now_json_from_before_the_ledger_epoch_is_at_epoch_0() -> None:
    assert guard.published_epoch(now_json()) == 0


def test_a_now_json_carries_its_epoch_from_phase_2() -> None:
    assert guard.published_epoch(now_json(epoch=3)) == 3


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not json",
        b"[]",
        b"{}",  # no seq: not a now.json
        json.dumps({"seq": -1}).encode(),
        json.dumps({"seq": "7"}).encode(),
        json.dumps({"seq": True}).encode(),
        json.dumps({"seq": 7, "epoch": -1}).encode(),
        json.dumps({"seq": 7, "epoch": 1.0}).encode(),
        json.dumps({"seq": 7, "epoch": "1"}).encode(),
        json.dumps({"seq": 7, "epoch": False}).encode(),
        json.dumps({"seq": 7, "epoch": None}).encode(),
        b"\xff\xfe",
    ],
)
def test_a_now_json_whose_epoch_cannot_be_read_is_unreadable(data: bytes) -> None:
    with pytest.raises(EpochUnreadable):
        guard.published_epoch(data)


@pytest.mark.parametrize(("database", "published"), [(0, 0), (3, 3), (4, 3)])
def test_a_database_epoch_at_or_past_now_json_is_current(database: int, published: int) -> None:
    assert guard.epoch_refusal(database, published) is None


def test_a_database_epoch_older_than_now_json_is_not_current() -> None:
    reason = guard.epoch_refusal(0, 1)
    assert reason is not None
    assert "0" in reason and "1" in reason


# --- where now.json is read -------------------------------------------------------------------

DATA_PLANE = "https://pub-0123.r2.dev/now.json"


class Opener:
    """Stands in for urllib's opener: answers every request with `body`, or raises `error`."""

    def __init__(self, body: bytes = b"", error: Exception | None = None) -> None:
        self.body = body
        self.error = error
        self.requests: list[tuple[urllib.request.Request, float]] = []

    def open(
        self, request: urllib.request.Request, /, *, timeout: float
    ) -> AbstractContextManager[io.BytesIO]:
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        return nullcontext(io.BytesIO(self.body))


def test_now_json_is_read_from_the_data_plane_over_https_without_a_cache() -> None:
    opener = Opener(now_json(epoch=2))
    assert guard.read_now_json(DATA_PLANE, opener=opener) == now_json(epoch=2)
    ((request, timeout),) = opener.requests
    assert request.full_url == DATA_PLANE
    assert request.get_header("Cache-control") == "no-cache"
    assert 0 < timeout <= 30


def test_now_json_is_read_from_a_file(tmp_path: Path) -> None:
    path = write(tmp_path / "now.json", now_json().decode())
    assert guard.read_now_json(str(path)) == now_json()


@pytest.mark.parametrize(
    "location",
    ["http://pub-0123.r2.dev/now.json", "file:///data/store/cdn/now.json", "ftp://host/now.json"],
)
def test_now_json_is_never_read_any_other_way(location: str) -> None:
    opener = Opener(now_json())
    with pytest.raises(EpochUnreadable, match="https"):
        guard.read_now_json(location, opener=opener)
    assert opener.requests == []


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.HTTPError(DATA_PLANE, 404, "Not Found", None, None),  # type: ignore[arg-type]
        urllib.error.URLError("timed out"),
        ConnectionResetError("reset"),
    ],
)
def test_a_now_json_that_cannot_be_fetched_is_unreadable(error: Exception) -> None:
    with pytest.raises(EpochUnreadable, match="cannot read now.json"):
        guard.read_now_json(DATA_PLANE, opener=Opener(error=error))


def test_a_now_json_too_large_to_be_one_is_unreadable() -> None:
    with pytest.raises(EpochUnreadable, match="larger"):
        guard.read_now_json(DATA_PLANE, opener=Opener(b" " * (64 * 1024 + 1)))


def test_a_missing_now_json_file_is_unreadable(tmp_path: Path) -> None:
    with pytest.raises(EpochUnreadable, match="cannot read now.json"):
        guard.read_now_json(str(tmp_path / "absent.json"))


def test_the_opener_follows_no_redirect() -> None:
    # A redirect could send the guard to an address it was not given.
    handler = guard._NoRedirect()  # pyright: ignore[reportPrivateUsage]
    assert handler.redirect_request() is None


# --- the process ------------------------------------------------------------------------------


class HandedOver(Exception):
    """Raised by the stand-in for os.execvpe, which in real life never returns."""


class Exec:
    """Stands in for os.execvpe and records the hand-over instead of making it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], dict[str, str]]] = []

    def __call__(self, file: str, args: list[str], environ: Mapping[str, str]) -> None:
        self.calls.append((file, args, dict(environ)))
        raise HandedOver


@pytest.fixture
def setup(tmp_path: Path) -> dict[str, str]:
    """The environment of a guard on the paid node, with a lock and a now.json that let it pass."""
    return {
        "GL_NODE": "paid",
        "GL_PROD_LOCK": str(write(tmp_path / "prod.lock", LOCK)),
        "GL_NOW_JSON": str(write(tmp_path / "now.json", now_json().decode())),
        "GL_DATABASE_URL": "postgresql://readonly@postgres:5432/globalens",
        "PGPASSWORD": "the-readonly-password",
        "PGPASSWORD_FILE": "/run/secrets/readonly_password",
        "PATH": "/usr/bin",
    }


def run(
    environ: Mapping[str, str],
    *,
    database: Callable[[str], int] = lambda dsn: 0,
    argv: list[str] | None = None,
) -> tuple[int | None, Exec]:
    """The guard's exit status and what it handed over to; the status is None after a hand-over."""
    execvp = Exec()
    try:
        status = guard.main(
            ["cloudflared", "--", "cloudflared", "tunnel", "run"] if argv is None else argv,
            environ,
            read_epoch=database,
            execvp=execvp,
        )
    except HandedOver:
        return None, execvp
    return status, execvp


def test_when_everything_agrees_the_guard_hands_over_to_the_command(
    setup: dict[str, str],
) -> None:
    status, execvp = run(setup)
    assert status is None
    assert len(execvp.calls) == 1
    file, args, environ = execvp.calls[0]
    assert (file, args) == ("cloudflared", ["cloudflared", "tunnel", "run"])
    # The command gets the guard's environment, less the database password it does not need.
    assert "PGPASSWORD" not in environ
    assert "PGPASSWORD_FILE" not in environ
    assert environ["PATH"] == "/usr/bin"


def test_a_command_that_cannot_be_started_exits_127(
    setup: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(file: str, args: list[str], environ: Mapping[str, str]) -> None:
        raise FileNotFoundError(2, "No such file or directory", file)

    status = guard.main(
        ["cloudflared", "--", "cloudflared"], setup, read_epoch=lambda dsn: 0, execvp=missing
    )
    assert status == guard.EXIT_CANNOT_RUN
    assert "cloudflared" in capsys.readouterr().err


def test_a_node_that_is_not_primary_is_refused_before_the_database_is_asked(
    setup: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path / "prod.lock", 'primary = "free"\n')
    asked: list[str] = []

    def database(dsn: str) -> int:
        asked.append(dsn)
        return 0

    status, execvp = run(setup, database=database)
    assert status == guard.EXIT_REFUSED
    assert execvp.calls == []
    assert asked == []
    assert "refused" in capsys.readouterr().err


def test_a_database_older_than_now_json_is_refused(
    setup: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path / "now.json", now_json(epoch=1).decode())
    status, execvp = run(setup, database=lambda dsn: 0)
    assert status == guard.EXIT_REFUSED
    assert execvp.calls == []
    assert "epoch" in capsys.readouterr().err


def test_an_epoch_that_cannot_be_read_is_refused(setup: dict[str, str], tmp_path: Path) -> None:
    def unreachable(dsn: str) -> int:
        raise EpochUnreadable("connection refused")

    status, execvp = run(setup, database=unreachable)
    assert (status, execvp.calls) == (guard.EXIT_REFUSED, [])

    (tmp_path / "now.json").unlink()
    status, execvp = run(setup)
    assert (status, execvp.calls) == (guard.EXIT_REFUSED, [])


def test_a_lock_that_cannot_be_read_is_refused(setup: dict[str, str], tmp_path: Path) -> None:
    write(tmp_path / "prod.lock", "primary = \n")
    assert run(setup)[0] == guard.EXIT_REFUSED
    (tmp_path / "prod.lock").unlink()
    assert run(setup)[0] == guard.EXIT_REFUSED


@pytest.mark.parametrize("missing", ["GL_NODE", "GL_PROD_LOCK", "GL_NOW_JSON", "GL_DATABASE_URL"])
def test_a_guard_missing_a_setting_starts_nothing(setup: dict[str, str], missing: str) -> None:
    del setup[missing]
    status, execvp = run(setup)
    assert (status, execvp.calls) == (guard.EXIT_CONFIG, [])


def test_a_guard_on_a_node_with_an_unknown_name_starts_nothing(setup: dict[str, str]) -> None:
    setup["GL_NODE"] = "laptop"
    status, execvp = run(setup)
    assert (status, execvp.calls) == (guard.EXIT_CONFIG, [])


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["cloudflared"],
        ["cloudflared", "--"],
        ["cloudflared", "cloudflared", "tunnel", "run"],  # no --
        ["Cloud Flared", "--", "cloudflared"],
        ["", "--", "cloudflared"],
    ],
)
def test_a_guard_called_wrongly_starts_nothing(setup: dict[str, str], argv: list[str]) -> None:
    status, execvp = run(setup, argv=argv)
    assert (status, execvp.calls) == (guard.EXIT_CONFIG, [])


def test_the_reasons_never_carry_the_password(
    setup: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(dsn: str) -> int:
        raise EpochUnreadable(f"could not connect to {dsn}")

    run(setup, database=failing)
    write(tmp_path / "now.json", now_json(epoch=2).decode())
    run(setup)
    run(setup, argv=["cloudflared", "--", "cloudflared"])
    assert "the-readonly-password" not in capsys.readouterr().err
