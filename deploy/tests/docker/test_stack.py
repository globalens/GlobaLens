"""The paid node's stack, running: the images built for this machine, started by Docker Compose
from deploy/compose/node-paid/compose.yaml with the test override beside this file.

One stack per run, under a project name of its own and cut off from the internet. Secrets are
random, written the way the first boot writes them (deploy/firstboot): a folder only root may
enter, with files any user may read, because Compose mounts each file into the containers that
name it and the containers do not run as root.

These tests need Docker, so they are not part of `mise run check`. They run under
`mise run test` and `mise run test:node`. With Docker down they fail; they never skip.
"""

import json
import os
import secrets
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "deploy" / "compose" / "node-paid" / "compose.yaml"
OVERRIDE = Path(__file__).with_name("compose.test.yaml")
TAG = "test"
PASSWORDS = ["postgres", "migrator", "worker", "readonly"]
REFUSED = 75  # worker.guard.EXIT_REFUSED


def run(
    command: list[str], *, timeout: int = 300, environ: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
        env=environ,
        cwd=ROOT,
    )


def require_docker() -> None:
    if run(["docker", "info"], timeout=30).returncode != 0:
        pytest.fail(
            "Docker is not running, and the stack tests need it (start it with `open -ga Docker`).",
            pytrace=False,
        )


@pytest.fixture(scope="module")
def images() -> dict[str, str]:
    """The four images, built for this machine's architecture and loaded into Docker."""
    require_docker()
    arch = run(["docker", "version", "--format", "{{.Server.Arch}}"]).stdout.strip()
    assert arch in ("amd64", "arm64"), arch
    environ = {**os.environ, "TAG": TAG}
    built = run(
        ["docker", "buildx", "bake", "--load", "--set", f"*.platform=linux/{arch}"],
        timeout=1800,
        environ=environ,
    )
    assert built.returncode == 0, built.stderr[-4000:]
    return {name: f"globalens/{name}:{TAG}" for name in ("postgres", "migrate", "worker", "edge")}


@dataclass(frozen=True)
class Stack:
    project: str
    env_file: Path
    folder: Path

    def compose(
        self, *args: str, extra: Path | None = None, timeout: int = 300
    ) -> subprocess.CompletedProcess[str]:
        command = ["docker", "compose", "-p", self.project, "--env-file", str(self.env_file)]
        command += ["-f", str(COMPOSE), "-f", str(OVERRIDE)]
        if extra is not None:
            command += ["-f", str(extra)]
        return run([*command, *args], timeout=timeout)

    def psql(self, sql: str) -> str:
        """Run SQL as the superuser through the server's own socket, and return the rows."""
        done = self.compose(
            "exec", "-T", "postgres", "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", "globalens", "-c", sql,
        )  # fmt: skip
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    def containers(self) -> list[dict[str, Any]]:
        done = self.compose("ps", "--all", "--format", "json")
        assert done.returncode == 0, done.stderr
        text = done.stdout.strip()
        # One JSON object per line (Compose 2.21 and later) or one array (earlier).
        if text.startswith("["):
            return cast("list[dict[str, Any]]", json.loads(text))
        return [cast("dict[str, Any]", json.loads(line)) for line in text.splitlines() if line]

    def write_now_json(self, document: dict[str, object] | None) -> None:
        """Put a now.json into the store volume (or take it away), as the publisher would."""
        if document is None:
            script = "import os; os.remove('/data/store/cdn/now.json')"
            done = self.compose("run", "--rm", "-T", "--no-deps", "--entrypoint", "python", "poll",
                                "-c", script)  # fmt: skip
        else:
            script = (
                "import os, sys; os.makedirs('/data/store/cdn', exist_ok=True);"
                "open('/data/store/cdn/now.json', 'w').write(sys.argv[1])"
            )
            done = self.compose("run", "--rm", "-T", "--no-deps", "--entrypoint", "python", "poll",
                                "-c", script, json.dumps(document))  # fmt: skip
        assert done.returncode == 0, done.stderr

    def edge(self, extra: Path | None = None) -> subprocess.CompletedProcess[str]:
        """Run the cloudflared service once, as its container would start."""
        return self.compose("run", "--rm", "-T", "--no-deps", "cloudflared", extra=extra)


@pytest.fixture(scope="module")
def stack(images: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    folder = tmp_path_factory.mktemp("node")
    secrets_dir = folder / "secrets"
    secrets_dir.mkdir(mode=0o700)
    for name in PASSWORDS:
        (secrets_dir / f"{name}_password").write_text(secrets.token_urlsafe(32), encoding="utf-8")
    (secrets_dir / "tunnel_token").write_text("not-a-real-tunnel-token", encoding="utf-8")
    for path in secrets_dir.iterdir():
        path.chmod(0o444)
    env_file = folder / "node.env"
    env_file.write_text(
        "\n".join(
            [
                f"GL_POSTGRES_IMAGE={images['postgres']}",
                f"GL_MIGRATE_IMAGE={images['migrate']}",
                f"GL_WORKER_IMAGE={images['worker']}",
                f"GL_EDGE_IMAGE={images['edge']}",
                "GL_NODE=paid",
                f"GL_SECRETS_DIR={secrets_dir}",
                "GL_NOW_JSON=/data/store/cdn/now.json",
                "",
            ]
        ),
        encoding="utf-8",
    )
    created = Stack(project=f"gltest-{uuid.uuid4().hex[:10]}", env_file=env_file, folder=folder)
    try:
        up = created.compose(
            "up", "--detach", "--wait", "--wait-timeout", "240", "postgres", "migrate", "poll",
            "work", timeout=600,
        )  # fmt: skip
        assert up.returncode == 0, up.stdout + up.stderr + created.compose("logs").stdout
        yield created
    finally:
        created.compose("down", "--volumes", "--remove-orphans", timeout=180)


def wait_for(check: Callable[[], int], seconds: float = 60) -> int:
    deadline = time.monotonic() + seconds
    while True:
        value = check()
        if value or time.monotonic() > deadline:
            return value
        time.sleep(0.5)


def test_the_migration_runs_first_and_leaves_the_schema_applied(stack: Stack) -> None:
    (migrate,) = [c for c in stack.containers() if c["Service"] == "migrate"]
    assert migrate["State"] == "exited" and migrate["ExitCode"] == 0
    logs = stack.compose("logs", "--no-log-prefix", "migrate").stdout
    assert "Applied: 0001_ingest.sql" in logs
    assert stack.psql("select version from public.schema_migrations") == "0001"


def test_the_poller_and_two_workers_are_connected_as_worker(stack: Stack) -> None:
    def sessions() -> int:
        found = stack.psql(
            "select count(*) from pg_stat_activity where usename = 'worker'"
            " and datname = 'globalens'"
        )
        return int(found) if int(found) >= 3 else 0

    assert wait_for(sessions) == 3
    running = sorted(c["Service"] for c in stack.containers() if c["State"] == "running")
    assert running == ["poll", "postgres", "work", "work"]


def test_nothing_is_published_and_nobody_is_root(stack: Stack) -> None:
    for container in stack.containers():
        # An image's EXPOSE shows here with published port 0; nothing may be bound to the host.
        publishers = cast("list[dict[str, Any]]", container.get("Publishers") or [])
        for publisher in publishers:
            assert publisher["PublishedPort"] == 0, (container["Name"], publisher)
        bound = run(["docker", "port", container["Name"]])
        assert bound.returncode == 0 and bound.stdout.strip() == "", container["Name"]
    expected = {"postgres": "999", "poll": "10001", "work": "10001"}
    for container in stack.containers():
        if container["State"] != "running":
            continue
        uid = run(["docker", "exec", container["Name"], "id", "-u"]).stdout.strip()
        assert uid == expected[container["Service"]], container["Name"]


def test_no_password_is_in_any_container_configuration(stack: Stack) -> None:
    passwords = [
        (stack.folder / "secrets" / f"{name}_password").read_text(encoding="utf-8")
        for name in PASSWORDS
    ]
    for container in stack.containers():
        config = run(["docker", "inspect", container["Name"]]).stdout
        for password in passwords:
            assert password not in config, container["Name"]


def test_postgres_runs_with_this_repositorys_configuration(stack: Stack) -> None:
    assert stack.psql("show config_file") == "/etc/postgresql/postgresql.conf"
    assert stack.psql("show shared_buffers") == "256MB"
    assert stack.psql("show password_encryption") == "scram-sha-256"
    scores = stack.compose(
        "exec", "-T", "postgres", "sh", "-c",
        'cat /proc/1/oom_score_adj; for p in $(pgrep -f "^postgres: "); do'
        " cat /proc/$p/oom_score_adj; done",
    )  # fmt: skip
    postmaster, *backends = scores.stdout.split()
    assert postmaster == "-500"
    assert backends and set(backends) == {"0"}


def test_over_the_network_a_role_needs_its_password(stack: Stack) -> None:
    def connect(password: str) -> subprocess.CompletedProcess[str]:
        url = f"postgresql://worker:{password}@postgres:5432/globalens"
        return stack.compose("run", "--rm", "-T", "--no-deps", "--entrypoint", "psql", "migrate",
                             "-X", "-A", "-t", url, "-c", "select current_user")  # fmt: skip

    wrong = connect("not-the-password")
    assert wrong.returncode != 0
    assert "password authentication failed" in wrong.stderr
    right = connect((stack.folder / "secrets" / "worker_password").read_text(encoding="utf-8"))
    assert right.returncode == 0, right.stderr
    assert right.stdout.strip() == "worker"


def test_the_migration_step_runs_again_and_changes_nothing(stack: Stack) -> None:
    again = stack.compose("run", "--rm", "-T", "--no-deps", "migrate")
    assert again.returncode == 0, again.stdout + again.stderr
    assert "Applying" not in again.stdout
    assert stack.psql("select version from public.schema_migrations") == "0001"


def test_cloudflared_starts_only_on_the_named_primary_with_a_current_epoch(
    stack: Stack,
) -> None:
    # Nothing published yet: the epoch cannot be read, so cloudflared does not start.
    absent = stack.edge()
    assert absent.returncode == REFUSED, absent.stdout + absent.stderr
    assert "cannot read now.json" in absent.stdout + absent.stderr
    assert "cloudflared version" not in absent.stdout

    # This node is primary in the committed prod.lock and both epochs are 0: it starts.
    stack.write_now_json({"v": 1, "seq": 3})
    allowed = stack.edge()
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert "guard: cloudflared starts on node 'paid'" in allowed.stdout + allowed.stderr
    assert "cloudflared version" in allowed.stdout

    # Another node was promoted since: now.json carries a newer epoch than this database.
    stack.write_now_json({"v": 1, "seq": 4, "epoch": 1})
    stale = stack.edge()
    assert stale.returncode == REFUSED, stale.stdout + stale.stderr
    assert "ledger epoch 0 and now.json at 1" in stale.stdout + stale.stderr
    assert "cloudflared version" not in stale.stdout

    # prod.lock names the other node primary.
    stack.write_now_json({"v": 1, "seq": 5})
    lock = stack.folder / "prod.lock"
    lock.write_text('primary = "free"\n', encoding="utf-8")
    override = stack.folder / "compose.free.yaml"
    override.write_text(
        f"services:\n  cloudflared:\n    volumes:\n      - {lock}:/etc/globalens/prod.lock:ro\n",
        encoding="utf-8",
    )
    other = stack.edge(override)
    assert other.returncode == REFUSED, other.stdout + other.stderr
    assert "prod.lock names 'free' primary" in other.stdout + other.stderr
    assert "cloudflared version" not in other.stdout


def test_cloudflared_reads_its_token_from_the_secret_file(stack: Stack) -> None:
    stack.write_now_json({"v": 1, "seq": 6})
    done = stack.compose("run", "--rm", "-T", "--no-deps", "cloudflared",
                         "cloudflared", "tunnel", "--no-autoupdate", "run")  # fmt: skip
    # The fake token is refused by cloudflared itself, before it opens any connection.
    assert done.returncode != 0
    assert "Provided Tunnel token is not valid" in done.stdout + done.stderr
