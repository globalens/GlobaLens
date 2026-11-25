"""Glyph coverage of the shipped title fonts over a set of GKG files.

    uv run --no-sync python packages/ui/scripts/font_coverage.py [--require-days N] PATH ...
    mise run fonts:coverage      # the week in $GLOBALENS_FIXTURE_WEEK, at least 7 days

The plan's gate (master plan §4; design note §9 task 12 and §10): at least 99.9% glyph coverage,
over the fixture week, for every script we ship a font for. A path is a GKG file (`.csv` or
`.csv.zip`) or a folder of them; the real week is never committed (Q19).

How it counts. Every page title is read and cleaned the way the parser does (`gdelt.title`), and
every character of every title is counted, so a headline carried by twelve outlets counts twelve
times, as it is drawn twelve times. Each character belongs to its Unicode script
(`fontTools.unicodedata`). For each script with a shipped family (`packages/ui/src/fonts.json`),
coverage is the share of that script's characters the family's cmap holds, over every woff2 file
its stylesheet names. Common and inherited characters (spaces, digits, punctuation, combining
marks) are checked against all the title families together and reported, not gated: the browser
takes them from whichever family draws the text around them. Scripts with no shipped family
(Chinese, Japanese and Korean among them) are drawn by system fonts and only reported.

The exit code is 0 only if at least one title was read, at least N days were covered and every
shipped script reaches the threshold.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from fontTools import unicodedata as ftunicodedata  # pyright: ignore[reportMissingTypeStubs]
from fontTools.ttLib import TTFont  # pyright: ignore[reportMissingTypeStubs]
from gdelt.files import find_gkg_files, read_gkg_bytes
from gdelt.title import clean_title

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "packages/ui/src/fonts.json"
NODE_MODULES = ROOT / "packages/ui/node_modules"

THRESHOLD = 0.999
COMMON_SCRIPTS = frozenset({"Zyyy", "Zinh", "Zzzz"})
MISSING_SHOWN = 20

_TITLE_OPEN = b"<PAGE_TITLE>"
_TITLE_CLOSE = b"</PAGE_TITLE>"
_STAMPED_NAME = re.compile(r"(\d{8})\d{6}\.")
_WOFF2_URL = re.compile(r"url\(\./files/([^)]+\.woff2)\)")


def script_of(char: str) -> str:
    """The ISO 15924 script of one character (Zyyy common, Zinh inherited, Zzzz unknown)."""
    script: str = ftunicodedata.script(char)  # pyright: ignore[reportUnknownMemberType]
    return script


def census(titles: Iterable[str]) -> Counter[str]:
    """How many times each character occurs across the titles."""
    counts: Counter[str] = Counter()
    for title in titles:
        counts.update(title)
    return counts


# --- reading titles ----------------------------------------------------------------------------


def iter_titles(paths: Iterable[Path]) -> Iterator[tuple[Path, str]]:
    """(file, cleaned title) for every 27-column row that has a non-empty page title."""
    for path in find_gkg_files(paths):
        for line in read_gkg_bytes(path).split(b"\n"):
            if line.count(b"\t") != 26:
                continue
            start = line.find(_TITLE_OPEN)
            if start < 0:
                continue
            end = line.find(_TITLE_CLOSE, start + len(_TITLE_OPEN))
            if end < 0:
                continue
            raw = line[start + len(_TITLE_OPEN) : end].decode("utf-8", "replace")
            title = clean_title(raw)
            if title:
                yield path, title


def day_of(path: Path) -> str | None:
    stamped = _STAMPED_NAME.match(path.name)
    return stamped.group(1) if stamped else None


@dataclass(frozen=True, slots=True)
class ReadTitles:
    titles: list[str]
    files: int
    days: tuple[str, ...]


def read_titles(paths: Iterable[Path]) -> ReadTitles:
    """Every title, in file order. For small inputs; `scan` counts without keeping them."""
    titles: list[str] = []
    files: set[Path] = set()
    for path, title in iter_titles(paths):
        files.add(path)
        titles.append(title)
    days = {day for day in map(day_of, files) if day}
    return ReadTitles(titles, len(files), tuple(sorted(days)))


@dataclass(slots=True)
class Scan:
    counts: Counter[str] = field(default_factory=lambda: Counter[str]())
    titles: int = 0
    files: int = 0
    days: set[str] = field(default_factory=lambda: set[str]())


def scan(paths: Iterable[Path]) -> Scan:
    """The character census of every title under `paths`, without keeping the titles."""
    result = Scan()
    for path in find_gkg_files(paths):
        result.files += 1
        day = day_of(path)
        if day:
            result.days.add(day)
        for _, title in iter_titles([path]):
            result.titles += 1
            result.counts.update(title)
    return result


# --- fonts -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Face:
    family: str
    package: str
    css: str
    scripts: tuple[str, ...]  # empty for the chrome's faces


def load_manifest(path: Path = MANIFEST) -> list[Face]:
    data = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    faces: list[Face] = []
    for group in ("ui", "titles"):
        for entry in cast(list[dict[str, Any]], data[group]):
            scripts = cast(list[str], entry.get("scripts", []))
            faces.append(Face(entry["family"], entry["package"], entry["css"], tuple(scripts)))
    return faces


def shipped_files(face: Face, node_modules: Path = NODE_MODULES) -> list[Path]:
    """The woff2 files the face's stylesheet names: what a browser may download."""
    package = node_modules / face.package
    css = (package / face.css).read_text(encoding="utf-8")
    return [package / "files" / name for name in dict.fromkeys(_WOFF2_URL.findall(css))]


def cmap_of(paths: Iterable[Path]) -> frozenset[int]:
    """Every code point any of the fonts maps to a glyph."""
    points: set[int] = set()
    for path in paths:
        font = TTFont(str(path), lazy=True)
        try:
            best = font.getBestCmap()
            points.update(best or {})
        finally:
            font.close()  # pyright: ignore[reportUnknownMemberType]
    return frozenset(points)


# --- coverage ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScriptRow:
    script: str
    occurrences: int
    covered: int
    missing: dict[str, int]  # "U+00E9" -> occurrences, the most frequent first

    @property
    def ratio(self) -> float:
        return 1.0 if self.occurrences == 0 else self.covered / self.occurrences

    @property
    def ok(self) -> bool:
        return self.ratio >= THRESHOLD

    def to_json(self) -> dict[str, Any]:
        return {
            "script": self.script,
            "occurrences": self.occurrences,
            "covered": self.covered,
            "ratio": round(self.ratio, 6),
            "ok": self.ok,
            "missing": self.missing,
        }


@dataclass(frozen=True, slots=True)
class Report:
    scripts: list[ScriptRow]
    common: ScriptRow
    system: dict[str, int]  # scripts with no shipped font -> occurrences

    @property
    def ok(self) -> bool:
        return all(row.ok for row in self.scripts)


def _row(script: str, chars: Mapping[str, int], cmap: frozenset[int]) -> ScriptRow:
    occurrences = sum(chars.values())
    missing = Counter({c: n for c, n in chars.items() if ord(c) not in cmap})
    shown = {f"U+{ord(c):04X}": n for c, n in missing.most_common(MISSING_SHOWN)}
    return ScriptRow(script, occurrences, occurrences - sum(missing.values()), shown)


def coverage(counts: Mapping[str, int], cmaps: Mapping[str, frozenset[int]]) -> Report:
    """Coverage per shipped script, the common characters against every title font, and the rest."""
    by_script: dict[str, dict[str, int]] = {}
    for char, n in counts.items():
        by_script.setdefault(script_of(char), {})[char] = n
    rows = [_row(script, by_script.get(script, {}), cmap) for script, cmap in sorted(cmaps.items())]
    union = frozenset[int]().union(*cmaps.values())
    common_chars: dict[str, int] = {}
    for script in COMMON_SCRIPTS:
        common_chars.update(by_script.get(script, {}))
    common = _row("common", common_chars, union)
    system = {
        script: sum(chars.values())
        for script, chars in sorted(by_script.items(), key=lambda item: -sum(item[1].values()))
        if script not in cmaps and script not in COMMON_SCRIPTS
    }
    return Report(rows, common, system)


def title_cmaps(
    faces: Iterable[Face], node_modules: Path = NODE_MODULES
) -> dict[str, frozenset[int]]:
    cmaps: dict[str, frozenset[int]] = {}
    for face in faces:
        if face.scripts:
            cmap = cmap_of(shipped_files(face, node_modules))
            for script in face.scripts:
                cmaps[script] = cmap
    return cmaps


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="font_coverage.py", description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="GKG files or folders of them")
    parser.add_argument("--require-days", type=int, default=0, metavar="N")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--node-modules", type=Path, default=NODE_MODULES)
    args = parser.parse_args(argv)

    faces = load_manifest(args.manifest)
    families = {script: face.family for face in faces for script in face.scripts}
    report = coverage((found := scan(args.paths)).counts, title_cmaps(faces, args.node_modules))
    days = sorted(found.days)
    ok = report.ok and found.titles > 0 and len(days) >= args.require_days
    out = {
        "ok": ok,
        "threshold": THRESHOLD,
        "files": found.files,
        "titles": found.titles,
        "days": days,
        "require_days": args.require_days,
        "scripts": [{**row.to_json(), "family": families[row.script]} for row in report.scripts],
        "common": report.common.to_json(),
        "system_fonts": report.system,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
