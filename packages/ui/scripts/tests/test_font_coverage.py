"""The fontTools coverage check (design note §9, task 12; §10, "Font coverage").

The gate: at least 99.9% glyph coverage, over the fixture week, for every script we ship a font
for. These tests build tiny fonts and tiny GKG files, so they need no real data and no network.
The week-long run needs the real fixture week (Q19) and is skipped without
GLOBALENS_FIXTURE_WEEK.
"""

from __future__ import annotations

import json
import os
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import font_coverage as fc
import fontTools.fontBuilder  # pyright: ignore[reportMissingTypeStubs]
import fontTools.pens.ttGlyphPen  # pyright: ignore[reportMissingTypeStubs]
import pytest

# fontTools ships no type information; the test font is built through these two names only.
FontBuilder: Any = fontTools.fontBuilder.FontBuilder
TTGlyphPen: Any = fontTools.pens.ttGlyphPen.TTGlyphPen

ROOT = Path(__file__).resolve().parents[4]
WEEK_VARIABLE = "GLOBALENS_FIXTURE_WEEK"


def make_font(path: Path, chars: str, flavor: str | None = None) -> Path:
    """A font whose cmap holds exactly `chars`."""
    names = [".notdef"] + [f"g{ord(c):04X}" for c in chars]
    fb: Any = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(c): f"g{ord(c):04X}" for c in chars})
    pen: Any = TTGlyphPen(None)
    glyph = pen.glyph()
    fb.setupGlyf({name: glyph for name in names})
    fb.setupHorizontalMetrics({name: (500, 0) for name in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    if flavor:
        fb.font.flavor = flavor
    fb.save(str(path))
    return path


def gkg_line(seq: int, title: str) -> bytes:
    columns = [b"x"] * 27
    columns[0] = f"20261109000000-T{seq}".encode()
    columns[1] = b"20261109000000"
    columns[26] = (
        f"<PAGE_PRECISEPUBTIMESTAMP>20261109000000</PAGE_PRECISEPUBTIMESTAMP><PAGE_TITLE>{title}</PAGE_TITLE>".encode()
    )
    return b"\t".join(columns)


def write_gkg_zip(folder: Path, stamp: str, titles: list[str]) -> Path:
    name = f"{stamp}.translation.gkg.csv"
    path = folder / f"{name}.zip"
    body = b"\n".join(gkg_line(i, t) for i, t in enumerate(titles)) + b"\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, body)
    return path


# --- scripts -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("char", "script"),
    [
        ("A", "Latn"),
        ("é", "Latn"),
        ("Ж", "Cyrl"),
        ("Ω", "Grek"),
        ("ا", "Arab"),
        ("א", "Hebr"),
        ("क", "Deva"),
        ("中", "Hani"),
        ("あ", "Hira"),
        ("한", "Hang"),
        (" ", "Zyyy"),
        ("1", "Zyyy"),
        ("“", "Zyyy"),
        ("́", "Zinh"),
    ],
)
def test_script_of(char: str, script: str) -> None:
    assert fc.script_of(char) == script


# --- the census ----------------------------------------------------------------------------


def test_census_counts_every_character_of_every_title() -> None:
    census = fc.census(["ab", "ba", "Ж"])
    assert census == Counter({"a": 2, "b": 2, "Ж": 1})


def test_titles_are_read_and_cleaned_the_way_the_parser_does(tmp_path: Path) -> None:
    write_gkg_zip(tmp_path, "20261109000000", ["R&amp;D in &#x41A;&#x438;&#x435;&#x432;", "plain"])
    write_gkg_zip(tmp_path, "20261110000000", ["second day"])
    read = fc.read_titles([tmp_path])
    assert read.titles == ["R&D in Киев", "plain", "second day"]
    assert read.files == 2
    assert read.days == ("20261109", "20261110")


# --- coverage --------------------------------------------------------------------------------


def test_coverage_per_script_and_the_threshold(tmp_path: Path) -> None:
    latin = fc.cmap_of([make_font(tmp_path / "latin.ttf", "abcdefghij ")])
    arabic = fc.cmap_of([make_font(tmp_path / "arabic.ttf", "اب")])
    census = Counter({"a": 999, "é": 1, "ا": 10, "ب": 5, "中": 7, " ": 20, "“": 2})
    report = fc.coverage(census, {"Latn": latin, "Arab": arabic})

    by_script = {row.script: row for row in report.scripts}
    assert by_script["Latn"].occurrences == 1000
    assert by_script["Latn"].covered == 999
    assert by_script["Latn"].ok  # 99.9% exactly passes
    assert by_script["Latn"].missing == {"U+00E9": 1}
    assert by_script["Arab"].ratio == 1.0
    # Han has no shipped font: system fonts draw it, and it does not count against the gate.
    assert report.system == {"Hani": 7}
    # Common characters are checked against every shipped title font together.
    assert report.common.occurrences == 22
    assert report.common.covered == 20
    assert report.ok


def test_one_more_missing_glyph_fails(tmp_path: Path) -> None:
    latin = fc.cmap_of([make_font(tmp_path / "latin.ttf", "a")])
    report = fc.coverage(Counter({"a": 998, "é": 2}), {"Latn": latin})
    assert not report.ok
    assert not report.scripts[0].ok


def test_woff2_files_are_read(tmp_path: Path) -> None:
    path = make_font(tmp_path / "x.woff2", "xyz", flavor="woff2")
    assert fc.cmap_of([path]) == frozenset(map(ord, "xyz"))


# --- the shipped fonts -----------------------------------------------------------------------


def test_the_shipped_woff2_files_are_the_ones_each_stylesheet_names() -> None:
    faces = fc.load_manifest(ROOT / "packages/ui/src/fonts.json")
    titles = [face for face in faces if face.scripts]
    assert titles, "the manifest lists title fonts"
    for face in titles:
        files = fc.shipped_files(face, ROOT / "packages/ui/node_modules")
        assert files, face.family
        assert all(path.suffix == ".woff2" and path.is_file() for path in files)


def test_the_noto_serif_cmap_covers_basic_latin_cyrillic_and_greek() -> None:
    faces = {face.family: face for face in fc.load_manifest(ROOT / "packages/ui/src/fonts.json")}
    cmap = fc.cmap_of(fc.shipped_files(faces["Noto Serif"], ROOT / "packages/ui/node_modules"))
    for text in ("The quick brown fox", "Київ Москва", "Αθήνα"):
        assert all(ord(c) in cmap for c in text if not c.isspace()), text


# --- the command ------------------------------------------------------------------------------


def test_main_reports_json_and_its_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_gkg_zip(tmp_path, "20261109000000", ["Київ", "Αθήνα", "Paris"])
    code = fc.main(["--require-days", "1", str(tmp_path)])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["ok"] is True
    assert report["titles"] == 3
    assert {row["script"] for row in report["scripts"]} >= {"Latn", "Cyrl", "Grek"}


def test_main_fails_without_enough_days(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_gkg_zip(tmp_path, "20261109000000", ["Paris"])
    assert fc.main(["--require-days", "7", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_main_fails_on_no_titles(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert fc.main([str(tmp_path)]) == 1
    capsys.readouterr()


@pytest.mark.skipif(
    not os.environ.get(WEEK_VARIABLE), reason=f"set {WEEK_VARIABLE} to the real fixture week"
)
def test_the_fixture_week_passes(capsys: pytest.CaptureFixture[str]) -> None:
    week = Path(os.environ[WEEK_VARIABLE]).expanduser()
    code = fc.main(["--require-days", "7", str(week)])
    out = capsys.readouterr().out
    assert code == 0, out
