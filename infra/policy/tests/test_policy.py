"""The Conftest policies, run through conftest's real parsers.

The Rego unit tests (policy/*_test.rego) give the rules hand-built input. These tests give them
real files: every stack under infra/live; a stack (policy/testdata/hcl/stack.tf) broken one rule
at a time; and the saved plans in policy/testdata, through the script `mise run tofu:plan` uses.
They need conftest on PATH (mise.toml) and make no network calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

POLICY = Path(__file__).resolve().parents[1]
ROOT = POLICY.parents[1]
STACK = POLICY / "testdata" / "hcl" / "stack.tf"
CHECK_PLAN = POLICY / "check-plan.sh"

BACKEND = """  backend "s3" {
    bucket       = "globalens-tofu-state"
    key          = "storage/terraform.tfstate"
    use_lockfile = true
  }
"""


def run(args: list[str], cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, input=stdin, capture_output=True, text=True, check=False)


def failures(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in result.stdout.splitlines() if line.startswith("FAIL")]


def hcl_check(root: Path) -> subprocess.CompletedProcess[str]:
    """The HCL policy over every stack under root/infra/live, with paths relative to root."""
    files = sorted(str(p.relative_to(root)) for p in (root / "infra" / "live").glob("*/*.tf"))
    assert files
    args = ["conftest", "test", "--no-color", "--combine", "--policy", str(POLICY)]
    return run([*args, "--namespace", "globalens.hcl", *files], cwd=root)


def encryption_block(text: str) -> str:
    start = text.index("  encryption {")
    return text[start : text.index("\n  }\n", start) + len("\n  }\n")]


def test_the_rego_unit_tests_pass() -> None:
    args = ["conftest", "verify", "--strict", "--no-color", "--policy", str(POLICY)]
    result = run([*args, "--data", str(POLICY / "testdata")], cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_stack_in_the_repository_passes() -> None:
    result = hcl_check(ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_fixture_stack_passes(tmp_path: Path) -> None:
    (tmp_path / "infra" / "live" / "storage").mkdir(parents=True)
    (tmp_path / "infra" / "live" / "storage" / "main.tf").write_text(STACK.read_text())
    result = hcl_check(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


# Each case: the text to replace in stack.tf (exactly once), what replaces it, and the message the
# one refusal must contain.
CASES: dict[str, tuple[str, str, str]] = {
    "bucket-without-prevent-destroy": (
        '  name       = "globalens-cdn"\n\n  lifecycle {\n    prevent_destroy = true\n  }\n',
        '  name       = "globalens-cdn"\n',
        "cloudflare_r2_bucket.cdn is storage and must keep lifecycle { prevent_destroy = true }",
    ),
    "prevent-destroy-false": (
        '"globalens-cdn"\n\n  lifecycle {\n    prevent_destroy = true',
        '"globalens-cdn"\n\n  lifecycle {\n    prevent_destroy = false',
        "cloudflare_r2_bucket.cdn is storage and must keep",
    ),
    "state-not-encrypted": (
        "<the encryption block>",
        "",
        "infra/live/storage: a stack with state must encrypt its state and plans",
    ),
    "plan-not-enforced": (
        "    plan {\n      method   = method.aes_gcm.escrow\n      enforced = true\n    }",
        "    plan {\n      method = method.aes_gcm.escrow\n    }",
        "a stack with state must encrypt",
    ),
    "undefined-key-provider": (
        "keys = key_provider.pbkdf2.escrow",
        "keys = key_provider.pbkdf2.other",
        "a stack with state must encrypt",
    ),
    "unencrypted-fallback": (
        '    method "aes_gcm" "escrow" {',
        '    method "unencrypted" "migrate" {}\n    method "aes_gcm" "escrow" {',
        "the unencrypted method is not allowed",
    ),
    "lake-made-public": (
        "bucket_name = cloudflare_r2_bucket.cdn.name",
        "bucket_name = cloudflare_r2_bucket.lake.name",
        "makes ${cloudflare_r2_bucket.lake.name} public",
    ),
    "passphrase-in-code": (
        "passphrase = var.state_passphrase",
        'passphrase = "not-a-real-key-but-in-the-code"',
        'the pbkdf2 key provider "escrow" must take its passphrase from a variable',
    ),
    "passphrase-not-ephemeral": (
        "  ephemeral = true\n",
        "",
        'the pbkdf2 key provider "escrow" must take its passphrase from a variable',
    ),
    "passphrase-with-default": (
        "  ephemeral = true\n",
        '  ephemeral = true\n  default   = "not-a-real-key-0000"\n',
        'the pbkdf2 key provider "escrow" must take its passphrase from a variable',
    ),
    "another-stacks-state-key": (
        'key          = "storage/terraform.tfstate"',
        'key          = "bootstrap/terraform.tfstate"',
        'the state key must be "storage/terraform.tfstate"',
    ),
    "no-state-locking": (
        "    use_lockfile = true\n",
        "",
        'the state key must be "storage/terraform.tfstate", with use_lockfile = true',
    ),
    "local-backend": (
        BACKEND,
        '  backend "local" {}\n',
        'through the s3 backend, not a "local" backend',
    ),
    "infrequent-access": (
        '  name       = "globalens-cdn"\n',
        '  name          = "globalens-cdn"\n  storage_class = "InfrequentAccess"\n',
        "cloudflare_r2_bucket.cdn uses Infrequent Access",
    ),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_each_rule_refuses_a_real_file(case: str, tmp_path: Path) -> None:
    old, new, message = CASES[case]
    text = STACK.read_text()
    if old == "<the encryption block>":
        old = encryption_block(text)
    assert text.count(old) == 1, f"{case}: the text to replace must occur exactly once"
    folder = tmp_path / "infra" / "live" / "storage"
    folder.mkdir(parents=True)
    (folder / "main.tf").write_text(text.replace(old, new))

    result = hcl_check(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    fails = failures(result)
    assert len(fails) == 1, fails
    assert message in fails[0], fails[0]


# (fixture, the stack folder the plan is said to come from, how many changes destroy something)
PLANS = [
    ("plan_mixed", "infra/live/storage", 3),
    ("plan_mixed", "infra/live/bootstrap/", 3),
    ("plan_destroy", "infra/live/storage", 5),
    ("plan_destroy", "infra/burst/scratch", 0),
    ("plan_mixed", "infra/burst/scratch", 0),
]


@pytest.mark.parametrize(("fixture", "stack", "destroys"), PLANS)
def test_the_plan_check_that_tofu_plan_runs(fixture: str, stack: str, destroys: int) -> None:
    plan = (POLICY / "testdata" / fixture / "plan.json").read_text()

    result = run(["sh", str(CHECK_PLAN), stack], cwd=ROOT, stdin=plan)

    assert result.returncode == (1 if destroys else 0), result.stdout + result.stderr
    fails = failures(result)
    assert len(fails) == destroys, fails
    assert all(f"{stack.rstrip('/')}/tfplan.json: the plan destroys" in f for f in fails), fails


def test_the_plan_check_needs_the_stack_folder() -> None:
    result = run(["sh", str(CHECK_PLAN)], cwd=ROOT, stdin="{}")
    assert result.returncode == 2
    assert "usage" in result.stderr
