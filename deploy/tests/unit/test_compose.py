"""The paid node's Compose file, read as data: what runs, with what limits, and what never does.

No Docker here. `deploy/tests/docker/test_stack.py` starts the same file and checks the running
stack; this file checks the promises a reviewer would otherwise have to read for: no published
port, no image without a digest from outside, a memory limit on every container, and no way to
start cloudflared around the role guard.
"""

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "deploy" / "compose" / "node-paid" / "compose.yaml"

SERVICES = {"postgres", "migrate", "poll", "work", "cloudflared"}
SECRET_NAMES = {
    "postgres_password",
    "migrator_password",
    "worker_password",
    "readonly_password",
    "tunnel_token",
}
NODE_MIB = 4096  # configuration S: OVH VPS-1, 4 GB (docs/design/p1.md §4)
SYSTEM_LINE_MIB = 900  # the operating system, Docker, exporters, deployer and cloudflared
HEADROOM_MIB = 350  # the plan's headroom on S, kept free
USER_AND_PASSWORD = re.compile(r"://[^/@\s]*:[^/@\s]*@")  # postgresql://user:password@host


def load() -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(COMPOSE.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return load()


@pytest.fixture(scope="module")
def services(compose: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return cast("dict[str, dict[str, Any]]", compose["services"])


def mib(limit: str) -> int:
    match = re.fullmatch(r"(\d+)([mg])", limit)
    assert match, f"a memory limit is written as <number>m or <number>g, not {limit!r}"
    return int(match.group(1)) * (1024 if match.group(2) == "g" else 1)


def replicas(service: dict[str, Any]) -> int:
    return int(service.get("deploy", {}).get("replicas", 1))


def test_the_stack_is_the_phase_1_paid_node(services: dict[str, dict[str, Any]]) -> None:
    assert set(services) == SERVICES
    assert services["work"]["command"] == ["work"]
    assert services["poll"]["command"] == ["poll"]
    assert replicas(services["work"]) == 2  # docs/design/p1.md §4, "Proposed"


def test_nothing_is_published_or_shares_the_host(services: dict[str, dict[str, Any]]) -> None:
    for name, service in services.items():
        for key in ("ports", "expose", "network_mode", "pid", "ipc", "privileged", "devices"):
            assert key not in service, f"{name} sets {key}"
        assert "cap_add" not in service, name


def test_every_image_is_named_by_the_node_and_never_built_there(
    services: dict[str, dict[str, Any]],
) -> None:
    for name, service in services.items():
        assert "build" not in service, name
        image = service["image"]
        # ${GL_..._IMAGE:?reason}: required, with no default to fall back on.
        assert re.fullmatch(r"\$\{GL_[A-Z]+_IMAGE:\?[^}]+\}", image), (name, image)


def test_every_variable_is_required(compose: dict[str, Any]) -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    variables = re.findall(r"\$\{([^}]*)\}", text)
    assert variables
    for variable in variables:
        assert re.fullmatch(r"GL_[A-Z_]+:\?.+", variable), variable


def test_every_container_has_a_memory_limit_and_together_they_fit_the_node(
    services: dict[str, dict[str, Any]],
) -> None:
    limits = {name: mib(service["mem_limit"]) for name, service in services.items()}
    assert limits["postgres"] == 1200  # the plan's Postgres line on configuration S
    total = sum(limits[name] * replicas(services[name]) for name in services)
    assert total <= NODE_MIB - SYSTEM_LINE_MIB - HEADROOM_MIB, total


def test_the_ingest_line_is_what_the_pull_request_states(
    services: dict[str, dict[str, Any]],
) -> None:
    # 64m + 2 x 320m: over the plan's 500m line for workers and publisher together, because a
    # worker peaks at 243 MiB (research) on the largest file of the fixture week (compose.yaml).
    ingest = sum(
        mib(services[name]["mem_limit"]) * replicas(services[name]) for name in ("poll", "work")
    )
    assert ingest == 704


def test_postgres_is_protected_from_the_kernel_and_its_backends_are_not(
    services: dict[str, dict[str, Any]],
) -> None:
    postgres = services["postgres"]
    assert postgres["oom_score_adj"] < 0
    assert postgres["environment"]["PG_OOM_ADJUST_FILE"] == "/proc/self/oom_score_adj"
    assert postgres["environment"]["PG_OOM_ADJUST_VALUE"] == "0"
    for name in SERVICES - {"postgres"}:
        assert "oom_score_adj" not in services[name], name


def test_every_container_runs_hardened(services: dict[str, dict[str, Any]]) -> None:
    for name, service in services.items():
        assert service["read_only"] is True, name
        assert service["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in service["security_opt"], name
        assert service["logging"]["options"]["max-size"], name
    assert services["postgres"]["user"] == "999:999"  # never root, even in its entrypoint


def test_restart_policies(services: dict[str, dict[str, Any]]) -> None:
    assert services["migrate"]["restart"] == "no"
    for name in SERVICES - {"migrate"}:
        assert services[name]["restart"] == "unless-stopped", name


def test_the_schema_is_migrated_before_anything_uses_it(
    services: dict[str, dict[str, Any]],
) -> None:
    assert services["migrate"]["depends_on"] == {"postgres": {"condition": "service_healthy"}}
    for name in ("poll", "work", "cloudflared"):
        assert services[name]["depends_on"] == {
            "migrate": {"condition": "service_completed_successfully"}
        }, name


def test_cloudflared_starts_only_through_the_role_guard(
    services: dict[str, dict[str, Any]],
) -> None:
    edge = services["cloudflared"]
    # The image's entrypoint is the guard; an `entrypoint:` here would run around it.
    assert "entrypoint" not in edge
    assert "command" not in edge
    environment = edge["environment"]
    assert set(environment) >= {"GL_NODE", "GL_PROD_LOCK", "GL_NOW_JSON", "GL_DATABASE_URL"}
    assert environment["GL_DATABASE_URL"].startswith("postgresql://readonly@")
    assert environment["GL_PROD_LOCK"] == "/etc/globalens/prod.lock"
    assert "../../prod.lock:/etc/globalens/prod.lock:ro" in edge["volumes"]
    assert (COMPOSE.parent / "../../prod.lock").resolve() == ROOT / "deploy" / "prod.lock"
    assert environment["TUNNEL_TOKEN_FILE"] == "/run/secrets/tunnel_token"


def test_no_credential_is_written_into_the_stack(
    compose: dict[str, Any], services: dict[str, dict[str, Any]]
) -> None:
    assert set(compose["secrets"]) == SECRET_NAMES
    for name, definition in compose["secrets"].items():
        assert definition == {
            "file": f"${{GL_SECRETS_DIR:?the folder of the node's secret files}}/{name}"
        }
    for name, service in services.items():
        assert set(service.get("secrets", [])) <= SECRET_NAMES, name
        for key, value in service.get("environment", {}).items():
            assert "PASSWORD" not in key or key.endswith("_FILE"), (name, key)
            assert "TOKEN" not in key or key.endswith("_FILE"), (name, key)
            assert not USER_AND_PASSWORD.search(str(value)), (name, key)


def test_each_service_gets_only_the_secrets_it_uses(services: dict[str, dict[str, Any]]) -> None:
    assert services["postgres"]["secrets"] == ["postgres_password"]
    assert set(services["migrate"]["secrets"]) == SECRET_NAMES - {"tunnel_token"}
    assert services["poll"]["secrets"] == ["worker_password"]
    assert services["work"]["secrets"] == ["worker_password"]
    assert set(services["cloudflared"]["secrets"]) == {"readonly_password", "tunnel_token"}
