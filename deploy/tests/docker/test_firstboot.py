"""The first boot, run for real: as root in a privileged container (firstboot.Dockerfile), with
the real nft, real network namespaces around the node, and a real HTTPS server holding the
bundle. firstboot_lab.py builds the lab and reports; the assertions are here.

Privileged means the container may change its own network stack: nft and the namespaces act on
the container's network namespace only, never on Docker's or this machine's. The container has
no network of its own (--network none); everything it reaches is inside the lab.

These tests need Docker, so they are not part of `mise run check`. They run under
`mise run test` and `mise run test:node`. With Docker down they fail; they never skip.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
IMAGE = "globalens-firstboot-lab:test"
TUNNEL_TOKEN = "fake-tunnel-token-for-the-lab"  # firstboot_lab.py's

INBOUND = ["ssh from outside", "published port from outside", "metadata from a container"]
OUTBOUND = ["metadata from the node", "internet from the node", "internet from a container"]


def run(command: list[str], *, timeout: int = 900, stdin: str | None = None) -> Any:
    return subprocess.run(
        command, input=stdin, capture_output=True, encoding="utf-8", timeout=timeout, check=False
    )


@pytest.fixture(scope="module")
def image() -> str:
    if run(["docker", "info"], timeout=30).returncode != 0:
        pytest.fail(
            "Docker is not running, and the first-boot tests need it (start it with "
            "`open -ga Docker`).",
            pytrace=False,
        )
    dockerfile = (HERE / "firstboot.Dockerfile").read_text(encoding="utf-8")
    built = run(["docker", "build", "--quiet", "--tag", IMAGE, "-"], stdin=dockerfile)
    assert built.returncode == 0, built.stderr
    return IMAGE


def lab(image: str, scenario: str) -> dict[str, Any]:
    done = run(
        [
            "docker",
            "run",
            "--rm",
            "--privileged",
            "--network",
            "none",
            "--volume",
            f"{ROOT / 'deploy' / 'firstboot'}:/opt/globalens/deploy/firstboot:ro",
            "--volume",
            f"{HERE / 'firstboot_lab.py'}:/lab/firstboot_lab.py:ro",
            image,
            "python3",
            "/lab/firstboot_lab.py",
            scenario,
        ]  # fmt: skip
    )
    assert done.returncode == 0, done.stderr[-4000:]
    return cast("dict[str, Any]", json.loads(done.stdout.splitlines()[-1]))


@pytest.fixture(scope="module")
def booted(image: str) -> dict[str, Any]:
    return lab(image, "boot")


@pytest.fixture(scope="module")
def spent(image: str) -> dict[str, Any]:
    return lab(image, "spent")


def test_before_the_first_boot_every_path_in_the_lab_is_open(booted: dict[str, Any]) -> None:
    # Without this, a closed path after the boot could be a broken lab, not a firewall.
    assert all(booted["before"].values()), booted["before"]


def test_after_it_nothing_comes_in_and_everything_still_goes_out(booted: dict[str, Any]) -> None:
    after = booted["after"]
    assert {path: after[path] for path in INBOUND} == dict.fromkeys(INBOUND, False)
    assert {path: after[path] for path in OUTBOUND} == dict.fromkeys(OUTBOUND, True)


def test_the_first_boot_finishes_and_says_nothing_secret(booted: dict[str, Any]) -> None:
    boot = booted["boot"]
    assert boot["exit"] == 0, boot["err"]
    assert boot["out"].splitlines()[0].endswith("all inbound traffic is denied")
    for text in (boot["out"], boot["err"]):
        assert TUNNEL_TOKEN not in text
        assert "10.9.0.2" not in text  # the bundle's address is the credential
        assert "glboot1." not in text


def test_the_bundle_came_through_the_firewall_once(booted: dict[str, Any]) -> None:
    # Fetched after the firewall was up: replies to the node's own connections still come in.
    assert booted["requests"] == ["/bundle.json"]
    assert booted["files"]["tunnel_token_matches"] is True


def test_the_secrets_are_root_only_on_the_host_and_readable_in_a_container(
    booted: dict[str, Any],
) -> None:
    files = booted["files"]
    assert files["secrets_mode"] == "0o700"
    assert set(files["secrets"]) == {
        "postgres_password",
        "migrator_password",
        "worker_password",
        "readonly_password",
        "tunnel_token",
    }
    for name, found in files["secrets"].items():
        assert found["mode"] == "0o444", name
    assert files["done_mode"] == "0o600"
    assert files["done"]["secrets_from_bundle"] == ["tunnel_token"]
    assert TUNNEL_TOKEN not in json.dumps(files["done"])
    assert files["token_left"] is False


def test_the_node_is_set_to_load_and_check_its_firewall_at_every_boot(
    booted: dict[str, Any],
) -> None:
    files = booted["files"]
    assert files["enabled"] == {
        "nftables.service": True,
        "globalens-firewall-check.service": True,
    }
    assert files["dropin"] is True
    assert files["masked"] == {"ssh.service": True, "ssh.socket": True}
    assert files["nftables_conf"].startswith("#!/usr/sbin/nft -f\n")
    assert files["nftables_conf"].endswith(
        (ROOT / "deploy" / "firstboot" / "firewall.nft").read_text(encoding="utf-8")
    )
    assert "GL_NODE=paid\n" in files["node_env"]
    assert booted["units"]["exit"] == 0, booted["units"]["err"]


def test_the_check_passes_on_the_loaded_firewall(booted: dict[str, Any]) -> None:
    assert booted["check"]["exit"] == 0, booted["check"]["err"]


def test_reloading_the_firewall_leaves_dockers_rules_alone(booted: dict[str, Any]) -> None:
    assert booted["reload"] == {
        "check": 0,
        "other_table_kept": True,
        "published_port_still_closed": True,
    }


@pytest.mark.parametrize(
    ("tampering", "said"),
    [
        ("a rule opens port 22", '"right": 22'),
        ("the input policy is accept", '"policy": "accept"'),
        ("the table is deleted", "is not loaded"),
    ],
)
def test_a_changed_firewall_is_caught_and_restored(
    booted: dict[str, Any], tampering: str, said: str
) -> None:
    found = booted["tampering"][tampering]
    assert found["ssh_open_while_tampered"] is True  # the change was real
    assert found["check"] == 1
    assert said in found["said"]
    assert (found["restored"], found["check_after"], found["ssh_open_after"]) == (0, 0, False)


def test_a_second_run_reads_no_token_and_keeps_the_passwords(booted: dict[str, Any]) -> None:
    rerun = booted["rerun"]
    assert rerun["exit"] == 0, rerun["err"]
    assert "database passwords generated: none" in rerun["out"]
    assert "no token is read" in rerun["out"]
    assert booted["rerun_token_left"] is False
    assert booted["requests"] == ["/bundle.json"]


def test_a_spent_token_leaves_the_node_locked_and_without_the_bundle(
    spent: dict[str, Any],
) -> None:
    assert spent["boot"]["exit"] == 1
    assert "HTTP 404" in spent["boot"]["err"]
    assert spent["requests"] == ["/bundle.json"]  # a spent token is not tried again
    after = spent["after"]
    assert {path: after[path] for path in INBOUND} == dict.fromkeys(INBOUND, False)
    assert spent["check"]["exit"] == 0
    files = spent["files"]
    assert "tunnel_token" not in files["secrets"]
    assert files["done"] is None
    assert files["token_left"] is False
