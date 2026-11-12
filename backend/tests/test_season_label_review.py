"""Win-now season signal WI-4: the operator label review (`backend/eval/season_label_review.py`).

Spec: docs/plans/win-now-season-signal/validation.md §4 (what the operator grades, the bar:
85% agreement over at least 120 graded labelled players in two leagues), lld.md §8,
build-plan.md WI-4. No network, no database; pages are written to a temporary folder that
stands in for the git-ignored `data/` root, except where the guard itself is tested.

Covered (each proven red against the named sabotage, then green on revert):
- test_marks_round_trip_and_unmarked_players_are_not_graded. Sabotage: count an
  unmarked player as agreement.
- test_bar_needs_85_percent_120_players_two_leagues. Sabotage: drop the league count
  from the bar.
- test_page_is_written_only_under_the_ignored_folder. Sabotage: remove the folder guard
  in `write_review`.
- test_fixture_page_has_players_and_labels_but_no_managers.
- test_score_report_is_aggregate_only.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from backend import feature_flags as ff, trade_service as ts
from backend.eval import season_label_review as lr

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))


@pytest.fixture
def ignored(tmp_path, monkeypatch):
    """A temporary stand-in for the git-ignored data/ root."""
    monkeypatch.setattr(lr, "IGNORED_ROOT", tmp_path)
    return tmp_path / "season-label-review"


def _rows(key, n, labels=lr.LABELS):
    players = [{"id": f"{key}-{i}", "name": f"Player {key} {i}", "position": "WR", "age": 25, "ppg": 10.0,
                "line": 9.0, "value": 5000.0 - i, "future": 1000.0, "startable": True,
                "label": labels[i % len(labels)]} for i in range(n)]
    own = [{"id": f"{key}-{i}", "name": f"Player {key} {i}", "position": "WR", "ppg": 10.0,
            "starts_for_you": i % 2 == 0} for i in range(10)]
    return {"schema": lr.SCHEMA, "league_key": key, "label_rules_version": "season-labels-1",
            "line": {"WR": 9.0}, "players": players, "own": own}


def _marks(rows, *, agree, disagree=0, expected="depth", starts_right=10):
    """Agree on the first `agree` players, disagree on the next `disagree`; the rest unmarked."""
    marks = {}
    for p in rows["players"][:agree]:
        marks[p["id"]] = "agree"
    for p in rows["players"][agree:agree + disagree]:
        marks[p["id"]] = expected if p["label"] != expected else "win_now"
    starts = {p["id"]: "right" if i < starts_right else "wrong" for i, p in enumerate(rows["own"])}
    return {"schema": lr.MARKS_SCHEMA, "league_key": rows["league_key"], "marks": marks, "starts": starts}


def test_marks_round_trip_and_unmarked_players_are_not_graded(ignored, tmp_path):
    rows = _rows("league-a", 100)
    page, sidecar = lr.write_review(rows, ignored)
    assert page.parent == ignored and json.loads(sidecar.read_text()) == rows
    text = page.read_text()
    assert lr.MARKS_SCHEMA in text and "league-a.marks.json" in text
    assert all(f'data-id="{p["id"]}"' in text for p in rows["players"])
    marks = _marks(rows, agree=40, disagree=10)            # 50 unmarked
    export = tmp_path / "league-a.marks.json"
    export.write_text(json.dumps(marks))
    result = lr.score(lr.load_reviews([export], ignored))
    assert (result["graded"], result["agreed"]) == (50, 40)
    assert result["agreement"] == pytest.approx(.8)
    assert sum(n for _, n in result["by_label"].values()) == 50
    assert sum(result["confusion"].values()) == 10
    assert result["starts"] == (10, 10)
    # Marking the shown label is agreement too.
    marks["marks"][rows["players"][45]["id"]] = rows["players"][45]["label"]
    assert lr.score([(rows, marks)])["agreed"] == 41


def test_bar_needs_85_percent_120_players_two_leagues():
    a, b = _rows("league-a", 80), _rows("league-b", 80)
    passing = [(a, _marks(a, agree=52, disagree=8)), (b, _marks(b, agree=51, disagree=9))]  # 103 / 120
    result = lr.score(passing)
    assert result["graded"] == 120 and result["agreement"] == pytest.approx(103 / 120) and result["passed"]
    low = [(a, _marks(a, agree=51, disagree=9)), (b, _marks(b, agree=50, disagree=10))]     # 101 / 120 = 84%
    assert not lr.score(low)["passed"]
    small = [(a, _marks(a, agree=52, disagree=8)), (b, _marks(b, agree=51, disagree=8))]    # 119 graded
    assert not lr.score(small)["passed"]
    big = _rows("league-a", 200)
    assert not lr.score([(big, _marks(big, agree=150))])["passed"]                          # one league
    assert "[FAIL]" in lr.report(lr.score(low)) and "[PASS]" in lr.report(result)


def test_top_24_and_unlabelled_rows():
    rows = _rows("league-a", 40)
    rows["players"][39]["label"] = None
    marks = _marks(rows, agree=0, disagree=3)
    marks["marks"][rows["players"][39]["id"]] = "depth"
    result = lr.score([(rows, marks)])
    assert result["top_disagreements"] == {"league-a": 3}
    assert result["unlabelled_graded"] == 1 and result["graded"] == 3


def test_page_is_written_only_under_the_ignored_folder(tmp_path):
    with pytest.raises(ValueError, match="git-ignored"):
        lr.write_review(_rows("league-a", 3), tmp_path / "outside")
    assert not (tmp_path / "outside").exists()
    with pytest.raises(ValueError, match="git-ignored"):
        lr.write_review(_rows("league-a", 3), REPO / "docs")
    assert lr.IGNORED_ROOT == REPO / "data" and lr.IGNORED_ROOT in lr.DEFAULT_DIR.parents
    if shutil.which("git"):
        probe = lr.DEFAULT_DIR.relative_to(REPO) / "probe.html"
        assert subprocess.run(["git", "check-ignore", "-q", str(probe)], cwd=REPO).returncode == 0
    with pytest.raises(ValueError, match="plain file name"):
        rows = _rows("league-a", 3)
        rows["league_key"] = "../escape"
        lr.write_review(rows, lr.DEFAULT_DIR)


def test_fixture_page_has_players_and_labels_but_no_managers(ignored):
    rows = lr.fixture_rows()
    counts = lr.label_counts(rows)
    assert all(counts[label] for label in lr.LABELS)
    assert sum(counts.values()) == len(rows["players"]) > 200
    assert rows["own"] and all(isinstance(p["starts_for_you"], bool) for p in rows["own"])
    page, _ = lr.write_review(rows, ignored)
    text = page.read_text()
    league = json.loads((REPO / "backend/tests/fixtures/season-signal/league-12.json").read_text())
    for team in league["teams"][1:]:          # synthetic manager ids ("me" is too short to test)
        assert f'"{team["owner_id"]}"' not in text and f">{team['owner_id']}<" not in text
    assert "Davante Adams" in text            # public NFL names are expected on the page


def test_score_report_is_aggregate_only():
    a, b = _rows("league-a", 80), _rows("league-b", 80)
    text = lr.report(lr.score([(a, _marks(a, agree=60, disagree=5)), (b, _marks(b, agree=60, disagree=5))]))
    for rows in (a, b):
        for p in rows["players"]:
            assert p["id"] not in text and p["name"] not in text
