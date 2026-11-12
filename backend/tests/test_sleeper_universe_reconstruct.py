"""Sleeper trade universe crawler: rosters at the moment of a trade (research-plan §5.5).

Covers: in-season reconstruction; offseason FORWARD from the previous season
(startup and rookie drafts included); offseason BACKWARD when the previous
season is not in the store (a 2026-only pull), with a rookie draft between
the trade and week 1; forward and backward agree when both run; every
completed transaction row counts whatever its type (a commissioner row, an
unknown type), a failed waiver never does; startup and rookie drafts put
players on rosters; the verifier matches every roster-week on a consistent
world, catches a deliberately broken replay, and attributes a missing event
to 'no add event'. Truth comes from the simulator, not from the code under test.
"""
from __future__ import annotations

import json

import pytest

from backend.sleeper_universe import reconstruct as rc
from backend.tests.support.sleeper_universe_world import L, connect, run_cli, standard_world


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    d = tmp_path_factory.mktemp("recon")
    w = standard_world()
    assert run_cli(w, d, "run")[0] == 0
    c = connect(d)
    yield w, c
    c.close()


@pytest.fixture(scope="module")
def only2026(tmp_path_factory):
    d = tmp_path_factory.mktemp("recon2026")
    w = standard_world()
    assert run_cli(w, d, "run", "--seasons", "2026")[0] == 0
    c = connect(d)
    yield w, c
    c.close()


def _check(w, c, lid, txid, method):
    got = rc.rosters_for_trade(c, lid, txid)
    assert got["method"] == method
    assert got["rosters"] == w.truth_pre_trade[txid]
    return got


def test_in_season_trades_match_truth(full):
    w, c = full
    for lid, idx in ((L(101), 0), (L(101), 1), (L(102), 2), (L(103), 1), (L(103), 2),
                     (L(103), 3), (L(201), 0)):
        _check(w, c, lid, w.truth_trades[lid][idx], "in_season")


def test_offseason_forward_and_backward_agree(full):
    w, c = full
    for lid, idx in ((L(102), 0), (L(102), 1), (L(103), 0)):
        got = _check(w, c, lid, w.truth_trades[lid][idx], "forward")
        assert got["alt_method"] == "backward" and got["alt_agrees"] == 1


def test_backward_when_previous_season_missing_rookie_draft_in_between(only2026):
    w, c = only2026
    txid = w.truth_trades[L(103)][0]          # 40 days before kickoff; rookie draft at 30
    got = _check(w, c, L(103), txid, "backward")
    rookies = {p["player_id"] for p in w.draft_picks_truth[L(103)]}
    assert rookies and not (set().union(*got["rosters"].values()) & rookies)
    row = c.execute("SELECT recon_method FROM trades WHERE transaction_id=?", (txid,)).fetchone()
    assert row[0] == "backward"


def test_every_complete_row_counts_whatever_its_type(full):
    w, c = full
    com = c.execute("SELECT adds_json FROM transactions WHERE league_id=? AND type='commissioner'",
                    (L(103),)).fetchone()
    pid = next(iter(json.loads(com[0])))
    txid = w.truth_trades[L(103)][3]          # week 3 trade, roster 4 involved
    got = _check(w, c, L(103), txid, "in_season")
    assert pid in got["rosters"][4]
    mys = c.execute("SELECT drops_json FROM transactions WHERE type='mystery_move'").fetchone()
    dropped = next(iter(json.loads(mys[0])))
    sd = rc.load_season(c, L(103))
    assert any(t["type"] == "mystery_move" for t in sd.txns)
    assert dropped not in sd.snapshots[3][6]


def test_failed_waiver_never_changes_a_roster(full):
    w, c = full
    failed = [next(iter(json.loads(r[0]))) for r in c.execute(
        "SELECT adds_json FROM transactions WHERE type='waiver' AND status='failed'")]
    assert failed
    sd = rc.load_season(c, L(103))
    assert all(t["transaction_id"] for t in sd.txns)
    held = set().union(*(set().union(*s.values()) for s in sd.snapshots.values()))
    assert not (held & set(failed))
    r = rc.forward_state(sd, rc.load_season(c, L(102)), float("inf"))[0]
    assert not (set().union(*r.values()) & set(failed))


def test_startup_and_rookie_drafts_put_players_on_rosters(full):
    w, c = full
    rows = {(r["league_id"], r["kind"]): r for r in c.execute(
        "SELECT league_id, kind, SUM(matched) m, COUNT(*) n FROM reconstruction_checks"
        " GROUP BY league_id, kind")}
    startup = rows[(L(101), "offseason_forward")]          # empty base + 80-pick startup
    rookie = rows[(L(102), "offseason_forward")]           # 2024 final + rookie draft
    assert startup["m"] == startup["n"] == 8 and rookie["m"] == rookie["n"] == 8
    sd = rc.load_season(c, L(101))
    startup_ids = {p["player_id"] for p in w.draft_picks_truth[L(101)]}
    assert len(startup_ids) == 80
    assert startup_ids <= set().union(*rc.forward_state(sd, None, sd.snapshots and
                                                        min(rc._t(t)[0] for t in sd.txns))[0].values())


def test_verifier_matches_every_roster_week(full):
    w, c = full
    bad = c.execute("SELECT COUNT(*) FROM reconstruction_checks WHERE matched=0").fetchone()[0]
    assert bad == 0
    assert c.execute("SELECT COUNT(*) FROM reconstruction_checks WHERE kind='in_season'"
                     ).fetchone()[0] > 100


def test_verifier_catches_a_broken_replay(full, monkeypatch):
    w, c = full
    sd = rc.load_season(c, L(103))
    prev = rc.load_season(c, L(102))
    assert all(r["matched"] for r in rc.verify_season(sd, prev))

    def ignore_drops(rosters, t):
        for pid, rid in (t.get("adds") or {}).items():
            rosters.setdefault(int(rid), set()).add(str(pid))
    monkeypatch.setattr(rc, "apply_transaction", ignore_drops)
    assert any(not r["matched"] for r in rc.verify_season(sd, prev))


def test_missing_event_is_attributed(full):
    w, c = full
    sd = rc.load_season(c, L(103))
    sd.txns = [t for t in sd.txns if t["type"] != "commissioner"]
    rows = [r for r in rc.verify_season(sd, rc.load_season(c, L(102)))
            if r["kind"] == "in_season" and r["week"] == 2 and r["roster_id"] == 4]
    assert rows[0]["matched"] == 0 and rows[0]["n_no_add_event"] == 1
