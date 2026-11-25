"""The first boot without a node: a temporary folder stands for /, a recorder stands for the
commands (nft, systemctl, unshare) and a dict stands for the HTTPS server.

`deploy/tests/docker/test_firstboot.py` runs the same program as root in a privileged container,
with a real nft, real network namespaces and a real HTTPS server.
"""

import base64
import hashlib
import importlib.util
import json
import os
import stat
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "deploy" / "firstboot" / "firstboot.py"
FAKE_PROGRAM = Path("/opt/globalens/deploy/firstboot/firstboot.py")
BUNDLE_URL = "https://bundles.example/one-time/abc?X-Amz-Signature=0123456789abcdef"
TUNNEL_TOKEN = "fake-tunnel-token-for-the-unit-tests"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("globalens_firstboot", PROGRAM)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their own module up by name
    spec.loader.exec_module(module)
    return module


fb = _load()


def token_for(bundle: bytes, url: str = BUNDLE_URL) -> str:
    body = json.dumps({"url": url, "sha256": hashlib.sha256(bundle).hexdigest()}).encode()
    return "glboot1." + base64.urlsafe_b64encode(body).decode().rstrip("=")


def bundle_of(**found: str) -> bytes:
    return json.dumps({"v": 1, "secrets": found}).encode()


BUNDLE = bundle_of(tunnel_token=TUNNEL_TOKEN)


def ruleset(*, policy: str = "drop", handle: int = 1, packets: int = 0) -> str:
    """`nft -j list table inet globalens` output, in the shape nft gives it."""
    items: list[dict[str, Any]] = [
        {"metainfo": {"version": "1.1.3", "release_name": "Commodore Bullmoose #4"}},
        {"table": {"family": "inet", "name": "globalens", "handle": handle}},
        {"chain": {"family": "inet", "table": "globalens", "name": "input", "handle": handle + 1,
                   "type": "filter", "hook": "input", "prio": 0, "policy": policy}},
        {"chain": {"family": "inet", "table": "globalens", "name": "forward",
                   "handle": handle + 2, "type": "filter", "hook": "forward", "prio": 0,
                   "policy": "accept"}},
        {"rule": {"family": "inet", "table": "globalens", "chain": "input", "handle": handle + 3,
                  "expr": [{"match": {"op": "in", "left": {"ct": {"key": "state"}},
                                      "right": ["established", "related"]}}, {"accept": None}]}},
        {"rule": {"family": "inet", "table": "globalens", "chain": "forward",
                  "handle": handle + 4,
                  "expr": [{"match": {"op": "==",
                                      "left": {"payload": {"protocol": "ip", "field": "daddr"}},
                                      "right": "169.254.169.254"}},
                           {"counter": {"packets": packets, "bytes": packets * 60}},
                           {"drop": None}]}},
    ]  # fmt: skip
    return json.dumps({"nftables": items})


class Node:
    """Records every command and answers the ones the program reads."""

    def __init__(self, *, live: str | None = None, reference: str | None = None) -> None:
        self.commands: list[list[str]] = []
        self.live = ruleset(handle=7, packets=12) if live is None else live
        self.reference = ruleset() if reference is None else reference
        self.loaded = False

    def __call__(self, command: Sequence[str]) -> str:
        command = list(command)
        self.commands.append(command)
        if command[:2] == ["nft", "-f"]:
            self.loaded = True
        if command[0] == "unshare":
            return self.reference
        if command[:3] == ["nft", "-j", "list"]:
            if not self.loaded or self.live == "":
                raise fb.BootError("Error: No such file or directory")
            return self.live
        return ""

    def ran(self, *words: str) -> bool:
        return any(command[: len(words)] == list(words) for command in self.commands)


class Server:
    """Serves the bundle from a dict of address to bytes, and counts the requests."""

    def __init__(self, pages: dict[str, bytes] | None = None) -> None:
        self.pages = {BUNDLE_URL: BUNDLE} if pages is None else pages
        self.requests: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.requests.append(url)
        if url not in self.pages:
            raise fb.FetchFailed("HTTP 404", retryable=False)
        return self.pages[url]


def write_token(path: Path, text: str, mode: int = 0o600) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def no_wait(seconds: float) -> None:
    pass


def boot(root: Path, token: Path, node: Node, server: Server, **options: Any) -> None:
    fb.first_boot("paid", token, root=root, runner=node, fetch=server, sleep=no_wait,
                  live=options.pop("live", False), program=FAKE_PROGRAM, **options)  # fmt: skip


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "root"
    folder.mkdir()
    return folder


@pytest.fixture
def token(tmp_path: Path) -> Path:
    return write_token(tmp_path / "firstboot.token", token_for(BUNDLE))


# --- the token -------------------------------------------------------------------------------


def test_a_token_names_an_https_address_and_a_digest() -> None:
    parsed = fb.parse_token(token_for(BUNDLE) + "\n")
    assert parsed.url == BUNDLE_URL
    assert parsed.sha256 == hashlib.sha256(BUNDLE).hexdigest()
    assert BUNDLE_URL not in repr(parsed)


def _raw(document: object) -> str:
    return "glboot1." + base64.urlsafe_b64encode(json.dumps(document).encode()).decode()


GOOD_DIGEST = "0" * 64


@pytest.mark.parametrize(
    "text",
    [
        "",
        "glboot2." + token_for(BUNDLE)[8:],
        "glboot1.not base64!",
        "glboot1." + base64.urlsafe_b64encode(b"not json").decode(),
        _raw(["https://a.example", GOOD_DIGEST]),
        _raw({"url": "https://a.example"}),
        _raw({"url": "https://a.example", "sha256": GOOD_DIGEST, "node": "paid"}),
        _raw({"url": "http://a.example/x", "sha256": GOOD_DIGEST}),
        _raw({"url": "file:///etc/shadow", "sha256": GOOD_DIGEST}),
        _raw({"url": "https://a.example/x y", "sha256": GOOD_DIGEST}),
        _raw({"url": "https://a.example/" + "x" * 4100, "sha256": GOOD_DIGEST}),
        _raw({"url": "https://a.example/x", "sha256": "A" * 64}),
        _raw({"url": "https://a.example/x", "sha256": "0" * 63}),
        _raw({"url": 1, "sha256": GOOD_DIGEST}),
    ],
)
def test_anything_else_is_not_a_token(text: str) -> None:
    with pytest.raises(fb.BootError):
        fb.parse_token(text)


def test_a_token_file_must_be_readable_by_its_owner_alone(tmp_path: Path) -> None:
    good = write_token(tmp_path / "good", "glboot1.x")
    assert fb.read_token(good) == "glboot1.x"
    shared = write_token(tmp_path / "shared", "glboot1.x", 0o644)
    with pytest.raises(fb.BootError, match="0600"):
        fb.read_token(shared)
    link = tmp_path / "link"
    link.symlink_to(good)
    with pytest.raises(fb.BootError, match="plain file"):
        fb.read_token(link)
    with pytest.raises(fb.BootError, match="no token"):
        fb.read_token(tmp_path / "absent")


# --- the bundle ------------------------------------------------------------------------------


def test_a_bundle_gives_the_secrets_it_holds() -> None:
    assert fb.parse_bundle(BUNDLE, hashlib.sha256(BUNDLE).hexdigest()) == {
        "tunnel_token": TUNNEL_TOKEN
    }


@pytest.mark.parametrize(
    "data",
    [
        b"not json",
        b"[]",
        json.dumps({"v": 2, "secrets": {"tunnel_token": "x"}}).encode(),
        json.dumps({"secrets": {"tunnel_token": "x"}}).encode(),
        json.dumps({"v": 1, "secrets": {"tunnel_token": "x"}, "note": "x"}).encode(),
        json.dumps({"v": 1, "secrets": ["tunnel_token"]}).encode(),
        bundle_of(),  # the tunnel token is required
        bundle_of(tunnel_token="x", postgres_password="x"),  # generated on the node, never sent
        bundle_of(tunnel_token="x", shell="x"),
        bundle_of(tunnel_token="two words"),
        bundle_of(tunnel_token="line\nbreak"),
        bundle_of(tunnel_token=""),
        bundle_of(tunnel_token="x" * 4097),
        json.dumps({"v": 1, "secrets": {"tunnel_token": 1}}).encode(),
    ],
)
def test_a_bundle_that_is_not_exactly_what_a_node_takes_is_refused(data: bytes) -> None:
    with pytest.raises(fb.BootError):
        fb.parse_bundle(data, hashlib.sha256(data).hexdigest())


def test_a_bundle_that_is_not_the_one_the_token_names_is_refused() -> None:
    with pytest.raises(fb.BootError, match="SHA-256"):
        fb.parse_bundle(BUNDLE, hashlib.sha256(b"another bundle").hexdigest())


# --- fetching it -----------------------------------------------------------------------------


def test_a_failed_fetch_is_tried_again_and_a_spent_token_is_not() -> None:
    token = fb.parse_token(token_for(BUNDLE))
    waits: list[float] = []
    answers: list[Exception | bytes] = [
        fb.FetchFailed("URLError", retryable=True),
        fb.FetchFailed("HTTP 503", retryable=True),
        BUNDLE,
    ]

    def flaky(url: str) -> bytes:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert fb.redeem(token, flaky, waits.append) == BUNDLE
    assert waits == [5.0, 10.0]

    waits.clear()
    with pytest.raises(fb.BootError, match="HTTP 404"):
        fb.redeem(token, Server({}), waits.append)
    assert waits == []


def test_fetching_gives_up_after_six_tries() -> None:
    token = fb.parse_token(token_for(BUNDLE))
    waits: list[float] = []

    def down(url: str) -> bytes:
        raise fb.FetchFailed("URLError", retryable=True)

    with pytest.raises(fb.BootError, match="after 6 tries"):
        fb.redeem(token, down, waits.append)
    assert waits == list(fb.RETRY_WAITS)


def test_the_bundle_is_fetched_over_https_only_and_never_redirected() -> None:
    with pytest.raises(fb.FetchFailed):
        fb.fetch_https("http://bundles.example/x")
    assert fb._NoRedirect().redirect_request() is None


def test_a_failed_request_is_described_without_its_address() -> None:
    import urllib.error

    failures = [
        urllib.error.URLError(OSError(111, "Connection refused")),
        urllib.error.URLError(f"cannot reach {BUNDLE_URL}"),
        ValueError(f"bad {BUNDLE_URL}"),
    ]
    for failure in failures:
        assert "bundles.example" not in fb._describe(failure)


# --- the firewall check ----------------------------------------------------------------------


def test_handles_metainfo_and_counters_do_not_count_as_differences() -> None:
    reference = fb.normalize(json.loads(ruleset()))
    live = fb.normalize(json.loads(ruleset(handle=40, packets=99)))
    assert reference == live
    assert fb.compare(reference, live) == []
    assert all("metainfo" not in item for item in reference)


def test_a_loaded_table_that_differs_is_reported() -> None:
    reference = fb.normalize(json.loads(ruleset()))
    opened = fb.normalize(json.loads(ruleset(policy="accept")))
    problems = fb.compare(reference, opened)
    assert problems[0].startswith("the loaded table inet globalens differs")
    assert any('"policy": "accept"' in line for line in problems)
    assert fb.compare(reference, None) == ["the table inet globalens is not loaded"]
    assert fb.compare(reference, list(reversed(reference)))[-1].endswith("another order")


def test_firewall_nft_itself_must_drop_input_and_keep_containers_from_the_metadata() -> None:
    assert fb.invariants(fb.normalize(json.loads(ruleset()))) == []
    assert fb.invariants(fb.normalize(json.loads(ruleset(policy="accept"))))
    without_metadata = ruleset().replace("169.254.169.254", "192.0.2.1")
    assert fb.invariants(fb.normalize(json.loads(without_metadata)))


def test_the_committed_firewall_never_flushes_other_tables() -> None:
    text = (ROOT / "deploy" / "firstboot" / "firewall.nft").read_text(encoding="utf-8")
    code = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not any(line.startswith("flush") for line in code)
    tables = [line for line in code if line.startswith(("table", "delete table"))]
    assert tables == [
        "table inet globalens",
        "delete table inet globalens",
        "table inet globalens {",
    ]
    assert "policy drop;" in text and "tcp dport" not in text


# --- the whole first boot --------------------------------------------------------------------


def test_a_first_boot_locks_the_node_then_takes_its_secrets(
    root: Path, token: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    node, server = Node(), Server()
    boot(root, token, node, server)

    conf = root / "etc/nftables.conf"
    assert conf.read_text(encoding="utf-8").endswith(
        (ROOT / "deploy/firstboot/firewall.nft").read_text(encoding="utf-8")
    )
    assert mode(conf) == 0o644
    assert node.commands[0] == ["nft", "-f", str(conf)]
    assert node.ran("unshare", "--net")  # the reference, in a namespace of its own
    assert node.ran("systemctl", f"--root={root}", "enable", "nftables.service", fb.CHECK_UNIT)
    assert node.ran("systemctl", f"--root={root}", "mask", "ssh.socket", "ssh.service")

    unit = (root / "etc/systemd/system" / fb.CHECK_UNIT).read_text(encoding="utf-8")
    assert f"ExecStart=/usr/bin/python3 -I {FAKE_PROGRAM} firewall" in unit
    dropin = (root / fb.DOCKER_DROPIN).read_text(encoding="utf-8")
    assert f"Requires={fb.CHECK_UNIT}" in dropin and f"After={fb.CHECK_UNIT}" in dropin

    env = (root / "etc/globalens/node.env").read_text(encoding="utf-8")
    assert "GL_NODE=paid\n" in env and "GL_SECRETS_DIR=/etc/globalens/secrets\n" in env

    folder = root / "etc/globalens/secrets"
    assert mode(folder) == 0o700
    names = sorted(path.name for path in folder.iterdir())
    assert names == sorted([*fb.LOCAL_SECRETS, "tunnel_token"])
    for name in names:
        assert mode(folder / name) == 0o444, name
    for name in fb.LOCAL_SECRETS:
        value = (folder / name).read_text(encoding="utf-8")
        assert len(value) == 43 and value.replace("-", "").replace("_", "").isalnum()
    assert (folder / "tunnel_token").read_text(encoding="utf-8") == TUNNEL_TOKEN

    done = root / fb.DONE
    assert mode(done) == 0o600
    record = json.loads(done.read_text(encoding="utf-8"))
    assert record["secrets_from_bundle"] == ["tunnel_token"]
    assert TUNNEL_TOKEN not in done.read_text(encoding="utf-8")
    assert not token.exists()
    assert server.requests == [BUNDLE_URL]

    printed = capsys.readouterr()
    for secret in [TUNNEL_TOKEN, BUNDLE_URL, token_for(BUNDLE), "bundles.example"]:
        assert secret not in printed.out + printed.err


def test_a_second_run_changes_nothing_and_reads_no_token(root: Path, token: Path) -> None:
    boot(root, token, Node(), Server())
    folder = root / "etc/globalens/secrets"
    before = {path.name: path.read_text(encoding="utf-8") for path in folder.iterdir()}

    again = write_token(token, token_for(BUNDLE))
    server = Server()
    boot(root, again, Node(), server)
    assert server.requests == []
    assert not again.exists()
    assert {path.name: path.read_text(encoding="utf-8") for path in folder.iterdir()} == before


def test_no_secret_is_taken_when_the_firewall_did_not_load_as_written(
    root: Path, token: Path
) -> None:
    node = Node(live=ruleset(policy="accept"))
    server = Server()
    with pytest.raises(fb.BootError, match="firewall"):
        boot(root, token, node, server)
    assert server.requests == []
    assert not (root / "etc/globalens/secrets").exists()
    assert not (root / "etc/systemd/system" / fb.CHECK_UNIT).exists()
    assert token.exists()  # never read: the run stopped before the token step


def test_a_spent_token_leaves_the_node_locked_and_without_the_bundle(
    root: Path, token: Path
) -> None:
    node = Node()
    with pytest.raises(fb.BootError, match="HTTP 404"):
        boot(root, token, node, Server({}))
    assert node.ran("nft", "-f")
    assert not (root / "etc/globalens/secrets/tunnel_token").exists()
    assert not (root / fb.DONE).exists()
    assert not token.exists()  # read once, whatever happened


def test_on_a_booted_system_systemd_is_told_directly(root: Path, token: Path) -> None:
    node = Node()
    boot(root, token, node, Server(), live=True)
    assert node.ran("systemctl", "daemon-reload")
    assert node.ran("systemctl", "enable", "nftables.service", fb.CHECK_UNIT)
    assert node.ran("systemctl", "disable", "--now", "ssh.socket", "ssh.service")
    assert node.ran("systemctl", "mask", "ssh.socket", "ssh.service")
    assert not any(part.startswith("--root") for command in node.commands for part in command)


def test_only_known_nodes_boot(root: Path, token: Path) -> None:
    with pytest.raises(fb.BootError, match="node"):
        fb.first_boot("laptop", token, root=root, runner=Node(), fetch=Server(), live=False)


def test_a_checkout_path_a_unit_cannot_hold_is_refused() -> None:
    with pytest.raises(fb.BootError):
        fb.check_unit(Path("/opt/global lens/firstboot.py"))


def test_the_program_refuses_to_run_as_anyone_but_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert fb.main(["check"]) == fb.EXIT_USAGE
    assert "root" in capsys.readouterr().err
