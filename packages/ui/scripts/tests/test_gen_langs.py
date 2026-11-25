"""packages/ui/src/langs.json is generated from gdelt.lang, never typed (Q6: dir from the language).

The point shards store a language as its index in gdelt.lang.LANGS, so the browser needs the same
table in the same order.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import gen_langs
from gdelt.lang import LANGS

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "packages/ui/scripts/gen_langs.py"


def test_the_committed_table_is_current() -> None:
    committed = (ROOT / gen_langs.TARGET).read_text(encoding="utf-8")
    assert committed == gen_langs.render(), (
        "run: uv run --no-sync python packages/ui/scripts/gen_langs.py write"
    )


def test_every_row_in_order() -> None:
    rows = json.loads(gen_langs.render())
    assert [row["code"] for row in rows] == [lang.code for lang in LANGS]
    assert rows[0] == {
        "code": "eng",
        "tag": "en",
        "endonym": "English",
        "dir": "ltr",
        "script": "Latn",
    }
    assert {row["dir"] for row in rows} == {"ltr", "rtl"}


def test_check_fails_when_the_file_differs(tmp_path: Path) -> None:
    target = tmp_path / "langs.json"
    target.write_text("[]\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--target", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "differs" in result.stderr
    subprocess.run([sys.executable, str(SCRIPT), "write", "--target", str(target)], check=True)
    assert target.read_text(encoding="utf-8") == gen_langs.render()
