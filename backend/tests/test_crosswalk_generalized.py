"""Tests for the generalized per-platform crosswalk (multi-platform league
linking — docs/plans/multi-platform-linking-plan-2026-07-17.md §1).

The Crosswalk that was ESPN-only now carries per-platform external-id → Sleeper
maps (by_mfl_sleeper, by_sportradar_id, by_yahoo_id) built from ONE DP fetch,
plus a shared position-strict name fallback (#127). map_generic_rosters is the
one code path MFL/Fleaflicker use to resolve rosters.
"""
import os

import backend.espn_service as es

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
XWALK_FIXTURE = os.path.join(FIXTURES, "dp_playerids_snapshot_2026-07-11.csv")


def test_snapshot_carries_new_id_columns():
    xw = es.load_crosswalk(XWALK_FIXTURE)
    # re-cut snapshot: every DP id map is populated
    assert len(xw.by_mfl_sleeper) > 2000
    assert len(xw.by_sportradar_id) > 2000
    assert len(xw.by_yahoo_id) > 1000
    # espn map untouched (back-compat)
    assert len(xw.by_espn_id) > 2000


def test_id_maps_resolve_chase():
    xw = es.load_crosswalk(XWALK_FIXTURE)
    # Ja'Marr Chase: mfl 15281 / sportradar fa99e984-... / espn 4362628 → sleeper 7564
    assert xw.by_mfl_sleeper.get("15281") == "7564"
    assert xw.by_sportradar_id.get("fa99e984-d63b-4ef4-a164-407f68a7eeaf") == "7564"
    assert xw.by_espn_id.get("4362628") == "7564"
    assert xw.by_name_pos.get(("jamarr chase", "WR")) == "7564"


def test_ktc_mfl_name_maps_still_present():
    # by_mfl_id (mfl_id → (name,pos)) is the KTC-blend map (#145) — must stay
    # populated alongside the new by_mfl_sleeper (mfl_id → sleeper_id).
    xw = es.load_crosswalk(XWALK_FIXTURE)
    assert xw.by_mfl_id.get("15281") == ("Ja'Marr Chase", "WR")
    assert xw.by_mfl_sleeper.get("15281") == "7564"


def test_map_generic_rosters_by_id_and_name_and_out_of_pool():
    xw = es.load_crosswalk(XWALK_FIXTURE)
    teams = [
        ("A", [
            ("15281", "Ja'Marr Chase", "WR"),       # id hit
            ("999999", "Ja'Marr Chase", "WR"),       # bogus id → name fallback
            ("888888", "Totally Unknown", "RB"),     # unmatched
            ("777777", "A Kicker", "K"),             # out of pool
        ]),
    ]
    out = es.map_generic_rosters(teams, xw.by_mfl_sleeper, xw)
    r = out["report"]
    assert out["rosters"]["A"] == ["7564", "7564"]
    assert r["matched_by_id"] == 1
    assert r["matched_by_name"] == 1
    assert r["out_of_pool"] == 1
    assert [u["name"] for u in r["unmatched"]] == ["Totally Unknown"]
    assert r["match_rate"] == 2 / 3   # 2 matched of 3 pool players


def test_map_generic_rosters_position_strict_fallback():
    # #127 rule: a name hit whose position disagrees is NO match.
    xw = es.load_crosswalk(XWALK_FIXTURE)
    teams = [("A", [("badid", "Ja'Marr Chase", "RB")])]  # Chase is a WR
    out = es.map_generic_rosters(teams, xw.by_mfl_sleeper, xw)
    assert out["rosters"]["A"] == []
    assert len(out["report"]["unmatched"]) == 1


def test_map_generic_rosters_empty_pool_zero_rate():
    xw = es.Crosswalk(by_espn_id={}, by_name_pos={})
    out = es.map_generic_rosters([("A", [("1", "K Player", "K")])], {}, xw)
    assert out["report"]["match_rate"] == 0.0
    assert out["report"]["out_of_pool"] == 1
    assert out["rosters"] == {"A": []}
