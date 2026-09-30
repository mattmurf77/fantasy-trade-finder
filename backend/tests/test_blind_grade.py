"""blind_grade: export hides the source and dedupes; import validates and scores.

Pure local files; nothing here touches the network or production.
"""
import csv
import io
import json
import re
import stat

import pytest

from backend.eval import blind_grade


def _card(i, prefix, *, partner=None, reasons=("Fair on value",)):
    return {"league": "Bench League", "seat": "seat1", "partner": partner or f"p{i % 3}",
            "give": [{"id": f"{prefix}g{i}", "name": f"{prefix.upper()} Giver {i}",
                      "position": "WR", "market": 1000.0 + i}],
            "receive": [{"id": f"{prefix}r{i}", "name": f"{prefix.upper()} Getter {i}",
                         "position": "RB", "market": 1010.5 + i},
                        {"id": f"{prefix}x{i}", "name": f"{prefix.upper()} Extra {i}",
                         "position": "PICK", "market": None}],
            "reasons": list(reasons)}


def _set(variant, cards, source="value_core_bench"):
    return {"variant": variant, "source": source, "cards": cards}


def _rows(sheet):
    return list(csv.DictReader(io.StringIO(sheet.read_text())))


def test_export_samples_and_hides_source(tmp_path):
    sets = [_set("value_core_default", [_card(i, "v") for i in range(50)]),
            _set("incumbent_served", [_card(i, "s") for i in range(50)], source="served")]
    summary = blind_grade.export(sets, per_variant=40, seed=7, output_dir=tmp_path / "g1")
    assert summary == {"rows": 80, "per_variant": {"value_core_default": 40,
                                                   "incumbent_served": 40}}
    text = (tmp_path / "g1" / "grade-sheet.csv").read_text()
    for hidden in ("value_core_default", "incumbent_served", "value_core", "incumbent",
                   "served", "Fair on value"):
        assert hidden not in text
    rows = _rows(tmp_path / "g1" / "grade-sheet.csv")
    assert list(rows[0]) == list(blind_grade.SHEET_COLUMNS)
    assert [r["card_id"] for r in rows] == [f"c{i:02d}" for i in range(1, 81)]
    assert all(r["grade"] == r["tags"] == r["note"] == r["reasons"] == "" for r in rows)
    first = next(r for r in rows if r["you_give"] == "V Giver 3 (WR)")
    assert first["you_get"] == "V Getter 3 (RB) · V Extra 3 (PICK)"
    assert (first["give_value"], first["get_value"]) == ("1003", "")   # unknown market -> blank
    key = json.loads((tmp_path / "g1" / "key.private.json").read_text())
    assert set(key) == {r["card_id"] for r in rows}
    assert sum(v["variants"] == ["value_core_default"] for v in key.values()) == 40
    assert all(set(v) == {"variants", "seat", "league"} for v in key.values())

    blind_grade.export(sets, per_variant=40, seed=7, output_dir=tmp_path / "g2")
    for name in ("grade-sheet.csv", "key.private.json"):
        assert (tmp_path / "g1" / name).read_text() == (tmp_path / "g2" / name).read_text()
    blind_grade.export(sets, per_variant=40, seed=8, output_dir=tmp_path / "g3")
    assert (tmp_path / "g3" / "grade-sheet.csv").read_text() != text

    blind_grade.export(sets, per_variant=40, seed=7, output_dir=tmp_path / "g4",
                       show_reasons=True)
    assert "Fair on value" in (tmp_path / "g4" / "grade-sheet.csv").read_text()


def test_export_dedupes_across_variants(tmp_path):
    shared = _card(99, "z", partner="pz")
    sets = [_set("A", [shared, _card(1, "a")]), _set("B", [dict(shared, reasons=[]), _card(2, "b")])]
    summary = blind_grade.export(sets, output_dir=tmp_path / "g")
    assert summary == {"rows": 3, "per_variant": {"A": 2, "B": 2}}
    key = json.loads((tmp_path / "g" / "key.private.json").read_text())
    assert sorted(v["variants"] for v in key.values()) == [["A"], ["A", "B"], ["B"]]


def _grade(tmp_path, grades):
    """Export A (a0-a2 + shared) and B (b0 + shared); fill grades by the you_give text."""
    shared = _card(9, "s", partner="ps")
    sets = [_set("A", [_card(i, "a") for i in range(3)] + [shared]),
            _set("B", [_card(0, "b"), shared])]
    out = tmp_path / "g"
    blind_grade.export(sets, output_dir=out)
    sheet = out / "grade-sheet.csv"
    rows = _rows(sheet)
    for row in rows:
        row["grade"], row["tags"] = grades.get(row["you_give"], ("", ""))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=blind_grade.SHEET_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    sheet.write_text(buffer.getvalue())
    return sheet, out / "key.private.json"


def test_import_scores(tmp_path):
    sheet, key = _grade(tmp_path, {
        "A Giver 0 (WR)": ("5", ""), "A Giver 1 (WR)": ("4", "too_small"),
        "A Giver 2 (WR)": ("3", ""), "B Giver 0 (WR)": ("2", "never_accept"),
        "S Giver 9 (WR)": ("4", "overpay; junk_filler")})
    summary = blind_grade.import_grades(sheet, key)
    assert summary["variants"]["A"] == {"n": 4, "mean": 4.0, "share_ge_4": 0.75,
                                        "tag_counts": {"junk_filler": 1, "overpay": 1,
                                                       "too_small": 1}}
    assert summary["variants"]["B"] == {"n": 2, "mean": 3.0, "share_ge_4": 0.5,
                                        "tag_counts": {"junk_filler": 1, "never_accept": 1,
                                                       "overpay": 1}}
    assert summary["overall"]["n"] == 5 and summary["overall"]["mean"] == pytest.approx(3.6)
    assert summary["target_mean"] == 4.0
    assert json.loads((sheet.parent / "summary.json").read_text()) == summary

    ungraded_dir = tmp_path / "u"
    ungraded_dir.mkdir()
    sheet2, key2 = _grade(ungraded_dir, {"A Giver 0 (WR)": ("5", "")})
    partial = blind_grade.import_grades(sheet2, key2)
    assert partial["variants"] == {"A": {"n": 1, "mean": 5.0, "share_ge_4": 1.0,
                                         "tag_counts": {}}}


@pytest.mark.parametrize("grade, tags, message", [
    ("6", "", "grade '6'"), ("4.5", "", "grade '4.5'"), ("x", "", "grade 'x'"),
    ("4", "meh", "unknown tag 'meh'"), ("", "overpay;meh", "unknown tag 'meh'")])
def test_import_rejects_bad_values(tmp_path, grade, tags, message):
    sheet, key = _grade(tmp_path, {"A Giver 1 (WR)": (grade, tags)})
    card_id = next(r["card_id"] for r in _rows(sheet) if r["you_give"] == "A Giver 1 (WR)")
    with pytest.raises(ValueError) as err:
        blind_grade.import_grades(sheet, key)
    assert card_id in str(err.value) and message in str(err.value)
    assert re.search(r"\bc\d\d\b", str(err.value))
    assert not (sheet.parent / "summary.json").exists()


def test_private_files(tmp_path):
    sheet, key = _grade(tmp_path, {"A Giver 0 (WR)": ("5", "")})
    out = sheet.parent
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    fresh = tmp_path / "fresh"
    blind_grade.export([_set("A", [_card(1, "a")])], output_dir=fresh)
    assert stat.S_IMODE((fresh / "grade-sheet.csv").stat().st_mode) == 0o600
    assert stat.S_IMODE((fresh / "key.private.json").stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        blind_grade.export([_set("A", [_card(1, "a")])], output_dir=fresh)
    blind_grade.import_grades(sheet, key)
    assert stat.S_IMODE((out / "summary.json").stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        blind_grade.import_grades(sheet, key)                     # never overwrites a summary
