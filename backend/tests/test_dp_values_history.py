"""Tests for `backend/dp_values_history.py` — dated DynastyProcess boards.

Three things are worth protecting here:

  1. The **offline path** genuinely never touches the network. Every analysis
     built on this module claims repeatability; a silent live fetch would
     break that without failing anything.
  2. The **name → Sleeper-id join** keeps working. It reuses the shipped
     crosswalk, so crosswalk rot or a DP naming change would quietly shrink
     the value map and degrade every downstream number rather than erroring.
     `test_real_preseason_boards_resolve_at_documented_rate` pins the measured
     rate reported in dated-values-revalidation-2026-08-09.md.
  3. **No look-ahead.** A board keyed to date D must not carry a `scrape_date`
     after D, or a "preseason" prediction is quietly reading the future.

Network calls are exercised through the module's `_opener` seam (the same
convention as `espn_service` / `bye_weeks`), which also switches
`observe_call` to inactive so no analytics rows are written from tests.
"""

from __future__ import annotations

import datetime
import io
import json
import os

import pytest

from backend import dp_values_history as dvh
from backend.espn_service import Crosswalk


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener_for(payload: str, seen: list):
    def _open(req, timeout=None):
        seen.append((req.full_url, dict(req.headers)))
        return _FakeResponse(payload.encode("utf-8"))
    return _open


def _no_network(req, timeout=None):        # pragma: no cover - must never run
    raise AssertionError("offline path made a network call: %s" % req.full_url)


COMMITS_JSON = json.dumps([
    {"sha": "abc123def456", "commit": {"committer": {"date": "2024-08-30T02:53:34Z"}}},
])

RAW_CSV = (
    "player,pos,team,age,draft_year,ecr_1qb,ecr_2qb,ecr_pos,"
    "value_1qb,value_2qb,scrape_date,fp_id\n"
    "Ja'Marr Chase,WR,CIN,24.5,2021,1.7,5.0,1,9900,9100,2024-08-30,19788\n"
    "Allen Robinson II,WR,DET,31.0,2014,200,210,90,150,120,2024-08-30,11111\n"
    "Retired Guy,RB,FA,40.0,2005,500,500,300,0,0,2024-08-30,22222\n"
)


# ---------------------------------------------------------------------------
# Season calendar
# ---------------------------------------------------------------------------

def test_week_boundary_anchors_on_kickoff_and_steps_one_week():
    assert dvh.week_boundary(2024, 0) == datetime.date(2024, 9, 5)
    assert dvh.week_boundary(2024, 14) == datetime.date(2024, 12, 12)
    with pytest.raises(KeyError):
        dvh.week_boundary(1999, 0)


# ---------------------------------------------------------------------------
# Live resolve / fetch (through the injected opener)
# ---------------------------------------------------------------------------

def test_resolve_commit_queries_the_values_file_at_or_before_the_date():
    seen: list = []
    ref = dvh.resolve_commit(datetime.date(2024, 9, 5),
                             _opener=_opener_for(COMMITS_JSON, seen))
    assert ref.sha == "abc123def456"
    assert ref.committed_at == "2024-08-30T02:53:34Z"
    url, headers = seen[0]
    assert url.startswith(dvh.COMMITS_URL)
    assert "path=files%2Fvalues-players.csv" in url
    assert "until=2024-09-05T23%3A59%3A59Z" in url
    # raw.githubusercontent/api.github both need a UA or serve a stub
    assert any(k.lower() == "user-agent" for k in headers)


def test_resolve_commit_raises_when_no_commit_precedes_the_date():
    with pytest.raises(LookupError):
        dvh.resolve_commit(datetime.date(2010, 1, 1),
                           _opener=_opener_for("[]", []))


def test_fetch_values_csv_pins_the_sha_in_the_raw_url():
    seen: list = []
    raw = dvh.fetch_values_csv("abc123", _opener=_opener_for(RAW_CSV, seen))
    assert raw == RAW_CSV
    assert seen[0][0] == (
        "https://raw.githubusercontent.com/dynastyprocess/data/abc123/"
        "files/values-players.csv")


def test_slim_csv_keeps_only_used_columns_and_drops_value_less_rows():
    slim = dvh.slim_csv(RAW_CSV)
    header = slim.splitlines()[0]
    assert header == ",".join(dvh.SLIM_COLUMNS)
    assert "Retired Guy" not in slim          # no 1QB and no SF value
    assert "Ja'Marr Chase" in slim
    assert "fp_id" not in header and "ecr_1qb" not in header


# ---------------------------------------------------------------------------
# Name -> sleeper id join
# ---------------------------------------------------------------------------

def _rows(*triples):
    return [{"player": p, "pos": pos, "value_1qb": v, "value_2qb": v,
             "scrape_date": "2024-08-30"} for p, pos, v in triples]


def test_join_tier_1_uses_the_shipped_crosswalk_position_strictly():
    xw = Crosswalk(by_espn_id={}, by_name_pos={("jamarr chase", "WR"): "7564",
                                               ("kenneth walker", "RB"): "8155"})
    values, rep = dvh.build_value_map(
        _rows(("Ja'Marr Chase", "WR", "9900"),
              ("Ja'Marr Chase", "RB", "1")),   # same name, wrong position
        crosswalk=xw)
    assert values == {"7564": 9900.0}
    assert rep.matched == 1 and rep.by_tier == {1: 1}
    assert rep.unmatched == 1
    assert rep.unmatched_names == [("Ja'Marr Chase", "RB")]


def test_join_tier_2_strips_generational_suffix_drift():
    xw = Crosswalk(by_espn_id={}, by_name_pos={("allen robinson", "WR"): "2309"})
    values, rep = dvh.build_value_map(
        _rows(("Allen Robinson II", "WR", "150")), crosswalk=xw)
    assert values == {"2309": 150.0}
    assert rep.by_tier == {2: 1}


def test_join_tier_3_uses_a_caller_supplied_index_and_stays_position_strict():
    xw = Crosswalk(by_espn_id={}, by_name_pos={})
    extra = {("kenneth walker", "RB"): "8155"}
    values, rep = dvh.build_value_map(
        _rows(("Kenneth Walker III", "RB", "5000"),
              ("Kenneth Walker III", "WR", "1")),
        crosswalk=xw, extra_name_pos=extra)
    assert values == {"8155": 5000.0}
    assert rep.by_tier == {3: 1} and rep.unmatched == 1


def test_scoring_format_selects_the_right_value_column():
    xw = Crosswalk(by_espn_id={}, by_name_pos={("jamarr chase", "WR"): "7564"})
    rows = [{"player": "Ja'Marr Chase", "pos": "WR", "value_1qb": "9900",
             "value_2qb": "9100", "scrape_date": "2024-08-30"}]
    assert dvh.build_value_map(rows, scoring="1qb", crosswalk=xw)[0] == {"7564": 9900.0}
    assert dvh.build_value_map(rows, scoring="2qb", crosswalk=xw)[0] == {"7564": 9100.0}
    # internal format keys resolve through DP_SCORING_PARAM too
    assert dvh.build_value_map(rows, scoring="sf_tep", crosswalk=xw)[0] == {"7564": 9100.0}


# ---------------------------------------------------------------------------
# Committed-snapshot (offline) path
# ---------------------------------------------------------------------------

def test_values_as_of_reads_a_committed_snapshot_without_network():
    values, rep, meta = dvh.values_as_of(
        "2024-09-05", scoring="1qb", _opener=_no_network)
    assert meta["season"] == 2024 and meta["week"] == 0
    assert meta["sha"].startswith("ce5e9ba0")
    assert rep.total_rows > 400
    # the real board is Sleeper-id keyed and non-degenerate
    assert len(values) > 400
    assert max(values.values()) > 5000


def test_values_as_of_refuses_an_uncaptured_date_rather_than_substituting():
    with pytest.raises(KeyError) as exc:
        dvh.values_as_of("2024-09-06", allow_network=False)
    assert "no committed DP board" in str(exc.value)


def test_values_as_of_accepts_a_date_object():
    a, _, _ = dvh.values_as_of(datetime.date(2024, 9, 5))
    b, _, _ = dvh.values_as_of("2024-09-05")
    assert a == b


# ---------------------------------------------------------------------------
# Fixture-set invariants
# ---------------------------------------------------------------------------

def test_every_indexed_snapshot_exists_and_carries_no_look_ahead():
    """A board keyed to date D must have been scraped on or before D — the
    whole point of a dated board is that it cannot know the future."""
    index = dvh.load_index()
    snaps = index["snapshots"]
    assert len(snaps) >= 24
    for key, meta in snaps.items():
        path = os.path.join(dvh.SNAPSHOT_DIR, meta["file"])
        assert os.path.exists(path), key
        assert meta["scrape_date"] <= key, (
            "%s board was scraped %s — after the date it prices"
            % (key, meta["scrape_date"]))
        assert meta["rows"] > 300, key


def test_all_four_preseason_boards_are_present_and_distinct():
    boards = {s: dvh.values_as_of(dvh.week_boundary(s, 0))[0]
              for s in (2022, 2023, 2024, 2025)}
    tops = []
    for season, vals in boards.items():
        assert len(vals) > 400, season
        tops.append(max(vals, key=vals.get))
    # If the fetcher silently served one board four times, every season's
    # top asset (and the whole map) would be identical.
    assert len({json.dumps(sorted(v.items())) for v in boards.values()}) == 4


def test_real_preseason_boards_resolve_at_documented_rate():
    """Regression guard on the join. Rates measured 2026-08-09 (report §2):
    7.8 % / 5.9 % / 3.4 % / 2.4 % unmatched DP rows for 2022..2025 using
    tiers 1-2 only. Bar is deliberately loose — this catches rot, not drift."""
    for season in (2022, 2023, 2024, 2025):
        _vals, rep, _meta = dvh.values_as_of(dvh.week_boundary(season, 0))
        assert rep.unmatched_rate < 0.12, (season, rep.summary())
        assert rep.by_tier.get(1, 0) > 400, (season, rep.summary())
