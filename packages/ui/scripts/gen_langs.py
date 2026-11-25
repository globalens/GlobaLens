"""Write packages/ui/src/langs.json from gdelt.lang, the language table the parser uses.

    uv run --no-sync python packages/ui/scripts/gen_langs.py write
    uv run --no-sync python packages/ui/scripts/gen_langs.py check    # exit 1 if the file differs

The browser needs the same table in the same order: a point shard stores a language as its index
in gdelt.lang.LANGS, and the Lens takes each title's `lang` and `dir` from it (design note Q6).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from gdelt.lang import LANGS

ROOT = Path(__file__).resolve().parents[3]
TARGET = Path("packages/ui/src/langs.json")


def render() -> str:
    """The file's exact text: one object per language, in table order."""
    rows = [
        {
            "code": lang.code,
            "tag": lang.tag,
            "endonym": lang.endonym,
            "dir": lang.direction,
            "script": lang.script,
        }
        for lang in LANGS
    ]
    return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_langs.py", description=__doc__)
    parser.add_argument("command", choices=("write", "check"))
    parser.add_argument("--target", type=Path, default=ROOT / TARGET)
    args = parser.parse_args(argv)
    target: Path = args.target
    text = render()
    if args.command == "write":
        target.write_text(text, encoding="utf-8")
        return 0
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        print(f"{target} differs from gdelt.lang: run gen_langs.py write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
