"""Sleeper trade universe crawler: pilot findings (commit C).

Covers:
- the snapshot instant: Sunday 13:00 US Eastern of the NFL week, the UTC hour
  moving when daylight time ends; NFL week 1 is the Thursday after Labor Day;
- an add booked in leg w AFTER week w's snapshot instant is not in week w's
  replay (the leg-based model put it there); an empty matchup row is not a
  snapshot; the forward base is the previous season's final /rosters (an
  end-of-season change with no transaction is in it);
- the optional per-player lock (a player's own kickoff, from an nflverse
  schedule and a team map);
- report on a store derived by older code: NULL-safe, says "derive needed"
  with exit 9 instead of a traceback, and is clean after `derive`;
- the leak scan's ambiguous names: a team named '2025' cannot fail the run by
  equality with the stored season, is counted, and a real name still fails.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import sqlite3
from pathlib import Path

import pytest

from backend.sleeper_universe import reconstruct as rc
from backend.sleeper_universe.identity import KeyRing
from backend.sleeper_universe.report import leak_scan
from backend.tests.support.sleeper_universe_world import (
    TEST_KEY, L, U, connect, run_cli, standard_world)

REPO = Path(__file__).resolve().parents[2]


def _utc(*a):
    return dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp() * 1000


def test_snapshot_instant_rule():
    clock = rc.SnapshotClock()
    assert clock.fixed(2024, 1) == _utc(2024, 9, 8, 17)      # Sun 13:00 EDT
    assert clock.fixed(2024, 10) == _utc(2024, 11, 10, 18)   # after DST ends: 13:00 EST
    assert clock.fixed(2025, 1) == _utc(2025, 9, 7, 17)
    assert clock.fixed(2026, 1) == _utc(2026, 9, 13, 17)
    assert rc.week1_thursday(2026) == dt.date(2026, 9, 10)


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    d = tmp_path_factory.mktemp("snap") / "data"
    w = standard_world()
    code, lines = run_cli(w, d, "run")
    assert code == 0, lines
    c = connect(d)
    yield w, c, d
    c.close()


def test_add_booked_in_leg_after_the_instant_belongs_to_the_next_week(store):
    w, c, _ = store
    late = c.execute("SELECT adds_json FROM transactions WHERE league_id=? AND leg=2 AND"
                     " type='free_agent' ORDER BY status_updated DESC LIMIT 1",
                     (L(101),)).fetchone()[0]
    pid = next(iter(json.loads(late)))
    sd = rc.load_season(c, L(101))
    assert pid not in sd.snapshots[2][3] and pid in sd.snapshots[3][3]
    rows = [r for r in rc.verify_season(sd, None) if r["kind"] == "in_season"]
    assert rows and all(r["matched"] for r in rows)


def test_empty_snapshot_row_is_not_compared(store):
    w, c, _ = store
    sd = rc.load_season(c, L(101))
    assert sd.empty_rows == 1 and 8 not in sd.snapshots[3]
    assert c.execute("SELECT COUNT(*) FROM reconstruction_checks WHERE league_id=? AND"
                     " roster_id=8 AND week IN (3, 4)", (L(101),)).fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM reconstruction_checks WHERE matched=0").fetchone()[0] == 0


def test_forward_base_is_previous_final_rosters(store):
    w, c, _ = store
    prev, sd = rc.load_season(c, L(101)), rc.load_season(c, L(102))
    last = prev.snapshots[max(prev.snapshots)]
    silent = prev.final[6] - last[6]
    assert len(silent) == 1                                   # the end-of-season edit
    rows = [r for r in rc.verify_season(sd, prev) if r["kind"] == "offseason_forward"]
    assert rows and all(r["matched"] for r in rows)
    txid = w.truth_trades[L(102)][1]                          # during the draft, roster 6
    got = rc.rosters_for_trade(c, L(102), txid)
    assert got["method"] == "forward" and got["rosters"] == w.truth_pre_trade[txid]
    assert silent <= got["rosters"][6]


def test_per_player_kickoff_lock():
    kick = rc.load_kickoffs(REPO / "backend/tests/fixtures/nflverse_games_2022_2026.csv")
    assert kick[(2024, 1, "KC")] == _utc(2024, 9, 6, 0, 20)  # Thu 20:20 EDT
    team = next(t for (s, wk, t), ms in kick.items() if s == 2024 and wk == 2
                and dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).weekday() == 1)
    mon = kick[(2024, 2, team)]                               # a Monday-night team (Tue UTC)
    sd = rc.SeasonData("1", 2024, None, "complete")
    sd.snapshots = {1: {1: {"100"}}, 2: {1: {"100", "200"}}}
    sd.txns = [{"transaction_id": "9", "type": "free_agent", "leg": 2, "created": mon - 4 * 3600e3,
                "status_updated": mon - 4 * 3600e3, "adds": {"200": 1}, "drops": {}}]
    fixed = rc.verify_season(sd, None)
    assert [r["matched"] for r in fixed if r["kind"] == "in_season"] == [0]
    clock = rc.SnapshotClock(kick, {"2024": {"200": team, "100": team}})
    assert clock.rule == "player_kickoff"
    locked = rc.verify_season(sd, None, clock)
    assert [r["matched"] for r in locked if r["kind"] == "in_season"] == [1]


def _downgrade(d: Path):
    """Turn a store into what ef01a621 created and derived: the columns B
    added are absent (then added NULL by the migration), no derived_version."""
    c = sqlite3.connect(str(d / "universe.sqlite"))
    for table, cols in (("standings_checks", "league_id, status, matched, kinds_json"),
                        ("matchups", "league_id, week, roster_id, matchup_id, opponent_roster,"
                                     " paired, points, phase, played"),
                        ("pull_failures", "league_id, season, run_id, kind")):
        c.execute(f"CREATE TABLE old AS SELECT {cols} FROM {table}")
        c.execute(f"DROP TABLE {table}")
        c.execute(f"ALTER TABLE old RENAME TO {table}")
    c.execute("DELETE FROM meta WHERE key IN ('derived_version', 'snapshot_rule')")
    c.commit()
    c.close()


def test_report_on_a_store_derived_by_older_code(tmp_path):
    d = tmp_path / "data"
    assert run_cli(standard_world(), d, "run")[0] == 0
    _downgrade(d)
    code, lines = run_cli(standard_world(), d, "report", "--json", seeds=None)
    assert code == 9
    out = json.loads(lines[0])["report"]
    assert "derive_needed" in out
    assert out["standings_vs_reported"]["not_derived"] == 5
    assert out["standings_vs_reported"]["records_agree"] == 0
    assert run_cli(standard_world(), d, "derive", seeds=None)[0] == 0
    code, lines = run_cli(standard_world(), d, "report", seeds=None)
    assert code == 0 and not any("DERIVE NEEDED" in x for x in lines)


def test_ambiguous_names_are_counted_not_matched(tmp_path):
    w = standard_world()
    w.users[U(4)]["metadata"]["team_name"] = "2025"           # equals a stored season
    for lid in (L(101), L(102), L(103)):
        for m in w.routes[f"league/{lid}/users"]:
            if m["user_id"] == U(4):
                m["metadata"]["team_name"] = "2025"
    d = tmp_path / "data"
    code, lines = run_cli(w, d, "run")
    assert code == 0, lines
    c = connect(d)
    leak = json.loads(c.execute("SELECT leak_scan_json FROM runs ORDER BY run_id DESC").fetchone()[0])
    assert leak["ok"] and leak["ambiguous_names_skipped"] >= 1
    assert any(x.startswith("leak scan: PASS") and "ambiguous names skipped: " in x for x in lines)
    # a real name planted in a raw file still fails, whatever else is ambiguous
    (d / "raw" / "x.json.gz").write_bytes(gzip.compress(json.dumps(
        {"v": "by Secret Display Person 004"}).encode()))
    res = leak_scan(d, KeyRing(TEST_KEY.encode()), names=w.all_names() | {"2025"})
    assert not res["ok"] and res["ambiguous_names_skipped"] >= 1
