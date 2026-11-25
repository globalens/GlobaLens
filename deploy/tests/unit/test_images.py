"""The node's images, read as text: every base pinned by digest, every download checked, both
architectures built, nothing in a build context that is not copied, and no image that runs as
root or can start cloudflared around the role guard.

No Docker here. The images are built and run by `deploy/tests/docker/test_stack.py`.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILES = [ROOT / "db" / "Dockerfile", ROOT / "apps" / "worker" / "Dockerfile"]
BAKE = ROOT / "docker-bake.hcl"
DIGEST = re.compile(r"[a-z0-9./:-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}")


def instructions(path: Path) -> list[tuple[str, str]]:
    """(instruction, arguments) pairs, with continuation lines joined and comments dropped."""
    joined = re.sub(r"\\\n", " ", path.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    for line in joined.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            word, _, rest = line.partition(" ")
            found.append((word.upper(), rest.strip()))
    return found


def stages(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Each named stage's instructions, FROM included."""
    named: dict[str, list[tuple[str, str]]] = {}
    current: list[tuple[str, str]] = []
    for instruction in instructions(path):
        if instruction[0] == "FROM":
            match = re.fullmatch(r"(\S+)(?: AS (\S+))?", instruction[1], re.IGNORECASE)
            assert match and match.group(2), f"{path}: every stage is named: {instruction[1]}"
            current = []
            named[match.group(2)] = current
        current.append(instruction)
    return named


@pytest.mark.parametrize("path", DOCKERFILES, ids=lambda path: path.parent.name)
def test_every_base_image_is_pinned_by_digest(path: Path) -> None:
    named = stages(path)
    for name, body in named.items():
        base = body[0][1].split()[0]
        if base in named or base == "scratch" or "${" in base:
            continue  # another stage of this file, or nothing
        assert DIGEST.fullmatch(base), f"{path.name} stage {name}: {base} has no digest"


@pytest.mark.parametrize("path", DOCKERFILES, ids=lambda path: path.parent.name)
def test_every_download_is_checked_and_every_copy_comes_from_the_context(path: Path) -> None:
    for word, rest in instructions(path):
        if word == "ADD":
            assert re.search(r"--checksum=sha256:[0-9a-f]{64}", rest), rest
            assert "https://" in rest, f"ADD is only for checked downloads: {rest}"
        if word == "RUN":
            assert not re.search(r"\b(curl|wget)\b", rest), f"download outside ADD: {rest}"


def test_the_final_images_never_run_as_root() -> None:
    worker = stages(ROOT / "apps" / "worker" / "Dockerfile")
    assert ("USER", "10001:10001") in worker["worker"]
    assert not any(word == "USER" for word, _ in worker["edge"])  # it inherits worker's
    database = stages(ROOT / "db" / "Dockerfile")
    assert ("USER", "postgres") in database["migrate"]
    # The server stage runs as the image's postgres user too: compose.yaml sets user 999:999.


def test_cloudflared_is_reachable_only_through_the_guard() -> None:
    edge = stages(ROOT / "apps" / "worker" / "Dockerfile")["edge"]
    entrypoints = [rest for word, rest in edge if word == "ENTRYPOINT"]
    assert entrypoints == [
        '["globalens-entrypoint", "python", "-m", "worker.guard", "cloudflared", "--"]'
    ]
    assert ("CMD", '["cloudflared", "tunnel", "--no-autoupdate", "run"]') in edge


def test_the_images_install_exactly_what_the_lockfile_says() -> None:
    build = stages(ROOT / "apps" / "worker" / "Dockerfile")["build"]
    syncs = [rest for word, rest in build if word == "RUN" and rest.startswith("uv sync")]
    assert len(syncs) == 2
    for sync in syncs:
        assert "--locked" in sync and "--no-dev" in sync, sync


def test_dbmate_in_the_image_is_the_version_mise_pins() -> None:
    mise = (ROOT / "mise.toml").read_text(encoding="utf-8")
    pinned = re.search(r'^dbmate = "([0-9.]+)"$', mise, re.MULTILINE)
    assert pinned
    dockerfile = (ROOT / "db" / "Dockerfile").read_text(encoding="utf-8")
    downloads = re.findall(r"dbmate/releases/download/v([0-9.]+)/dbmate-linux-(\w+)", dockerfile)
    assert sorted(downloads) == [(pinned.group(1), "amd64"), (pinned.group(1), "arm64")]


def test_uv_in_the_image_is_the_version_mise_pins() -> None:
    mise = (ROOT / "mise.toml").read_text(encoding="utf-8")
    pinned = re.search(r'^uv = "([0-9.]+)"$', mise, re.MULTILINE)
    assert pinned
    dockerfile = (ROOT / "apps" / "worker" / "Dockerfile").read_text(encoding="utf-8")
    assert f"ghcr.io/astral-sh/uv:{pinned.group(1)}@sha256:" in dockerfile


def test_the_python_in_the_image_is_the_one_the_workspace_requires() -> None:
    dockerfile = (ROOT / "apps" / "worker" / "Dockerfile").read_text(encoding="utf-8")
    version = re.search(r"FROM python:(3\.\d+)\.\d+-slim", dockerfile)
    assert version
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'requires-python = ">={version.group(1)},' in pyproject


@pytest.mark.parametrize(
    ("ignore", "copied"),
    [
        (ROOT / "db" / "Dockerfile.dockerignore", ROOT / "db" / "Dockerfile"),
        (
            ROOT / "apps" / "worker" / "Dockerfile.dockerignore",
            ROOT / "apps" / "worker" / "Dockerfile",
        ),
    ],
    ids=["db", "worker"],
)
def test_a_build_context_holds_only_what_its_image_copies(ignore: Path, copied: Path) -> None:
    lines = [
        line.strip()
        for line in ignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines[0] == "*", "the context starts empty"
    allowed = [line[1:].rstrip("/") for line in lines[1:] if line.startswith("!")]
    sources = [
        source
        for word, rest in instructions(copied)
        if word == "COPY" and "--from=" not in rest
        for source in [token for token in rest.split() if not token.startswith("--")][:-1]
    ]
    for source in sources:
        source = source.rstrip("/")
        assert any(source == path or source.startswith(path + "/") for path in allowed), source
    for path in allowed:
        assert any(source.rstrip("/") == path for source in sources), f"{path} is never copied"


def test_every_image_is_built_for_both_node_architectures() -> None:
    text = BAKE.read_text(encoding="utf-8")
    both = re.search(r'target "_both" \{\s*platforms = \[([^\]]*)\]', text)
    assert both
    assert sorted(re.findall(r'"([^"]+)"', both.group(1))) == ["linux/amd64", "linux/arm64"]
    targets = re.findall(r'target "(\w+)" \{(.*?)\n\}', text, re.DOTALL)
    built = {name: body for name, body in targets if name != "_both"}
    assert set(built) == {"postgres", "migrate", "worker", "edge"}
    for name, body in built.items():
        assert 'inherits   = ["_both"]' in body, name
        assert "platforms" not in body, f"{name} must not narrow the platforms"
    group = re.search(r'group "default" \{\s*targets = \[([^\]]*)\]', text)
    assert group and sorted(re.findall(r'"(\w+)"', group.group(1))) == sorted(built)
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "push" not in code and "output" not in code, "the bake file never pushes"
