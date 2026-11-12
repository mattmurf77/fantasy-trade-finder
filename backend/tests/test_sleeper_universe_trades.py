"""Sleeper trade universe crawler: trades, assets, picks, cleaning flags (research-plan §5.4, 5.7, 5.8).

Covers: a trade with players, a pick and FAAB normalises to one asset row each
with from and to roster (the committed manager-profiles fixture); a
three-team trade; a pending trade is not a trade; a traded pick resolves to
its slot and drafted player once that draft happened, else to the original
team's standing (this season, or the prior season's final for an offseason
trade); the cleaning flags (reversed within a day, orphaned side, during a
draft, low-trade league, unusual scoring) are set and nothing is deleted.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.sleeper_universe import derive, identity, normalise
from backend.tests.support.sleeper_universe_world import L, connect, run_cli, standard_world

REPO = Path(__file__).resolve().parents[2]
MP = REPO / "backend/tests/fixtures/sleeper/manager-profiles"


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    d = tmp_path_factory.mktemp("trades")
    w = standard_world()
    assert run_cli(w, d, "run")[0] == 0
    c = connect(d)
    yield w, c
    c.close()


def _assets(c, lid, txid):
    return [dict(r) for r in c.execute("SELECT * FROM trade_assets WHERE league_id=? AND"
                                       " transaction_id=? ORDER BY asset_idx", (lid, txid))]


def test_players_pick_and_faab_from_committed_fixture():
    txns = json.loads((MP / "transactions_1.json").read_text())
    ring = identity.KeyRing(b"k" * 32)
    stripped = identity.strip_transactions(txns, ring)
    t = next(x for x in stripped if x["type"] == "trade" and x["status"] == "complete")
    row = normalise.bundle_rows({"league": {"league_id": "1", "season": "2026"},
                                 "transactions": {"1": [t]}})["transactions"][0]
    assets = derive.trade_assets(row)
    assert {(a["asset_type"], a.get("player_id"), a["from_roster"], a["to_roster"]) for a in assets} == {
        ("player", "1001", 1, 2), ("player", "1002", 2, 1), ("pick", None, 1, 2),
        ("faab", None, 2, 1)}
    pick = next(a for a in assets if a["asset_type"] == "pick")
    assert (pick["pick_season"], pick["pick_round"], pick["pick_orig_roster"]) == ("2027", 1, 1)
    assert next(a for a in assets if a["asset_type"] == "faab")["faab_amount"] == 10
    assert t["creator_key"] == ring.user_key("9000000000000000001")


def test_three_team_trade(store):
    w, c = store
    txid = w.truth_trades[L(101)][1]
    a = _assets(c, L(101), txid)
    moves = {(x["asset_type"], x["from_roster"], x["to_roster"]) for x in a}
    assert moves == {("player", 5, 6), ("player", 6, 7), ("player", 7, 5), ("faab", 7, 5)}
    t = c.execute("SELECT n_rosters, n_players, faab_total FROM trades WHERE transaction_id=?",
                  (txid,)).fetchone()
    assert tuple(t) == (3, 3, 7)


def test_pending_trade_is_not_a_trade(store):
    w, c = store
    assert c.execute("SELECT COUNT(*) FROM trades WHERE league_id=?", (L(101),)).fetchone()[0] == 2
    assert c.execute("SELECT COUNT(*) FROM transactions WHERE league_id=? AND type='trade'"
                     " AND status='pending'", (L(101),)).fetchone()[0] == 1


def test_pick_resolved_to_slot_and_player_once_drafted(store):
    w, c = store
    txid = w.truth_trades[L(101)][0]          # 2025 round 1, original roster 3
    pick = next(a for a in _assets(c, L(101), txid) if a["asset_type"] == "pick")
    assert pick["pick_resolution"] == "drafted"
    slot = 8 + 1 - 3                          # the world's slot_to_roster: slot s -> 9 - s
    truth = next(p for p in w.draft_picks_truth[L(102)] if p["round"] == 1 and p["draft_slot"] == slot)
    assert (pick["pick_slot"], pick["pick_no"], pick["pick_player_id"]) == (
        slot, truth["pick_no"], truth["player_id"])
    assert truth["roster_id"] == 1            # the acquiring roster made the pick


def test_future_pick_records_original_team_standing(store):
    w, c = store
    t1 = w.truth_trades[L(103)][1]            # in season, week 2: 2027 1st of roster 1
    pick = next(a for a in _assets(c, L(103), t1) if a["asset_type"] == "pick")
    st = c.execute("SELECT * FROM standings_weeks WHERE league_id=? AND week=1 AND roster_id=1",
                   (L(103),)).fetchone()
    assert pick["pick_resolution"] == "standing" and pick["standing_basis"] == "current_season"
    assert (pick["orig_rank_at_trade"], pick["orig_wins"]) == (st["rank"], st["wins"])
    off = w.truth_trades[L(102)][0]           # offseason: 2027 1st of roster 2
    pick = next(a for a in _assets(c, L(102), off) if a["asset_type"] == "pick"
                and a["pick_season"] == "2027")
    final = c.execute("SELECT * FROM standings_weeks WHERE league_id=? AND roster_id=2"
                      " ORDER BY week DESC LIMIT 1", (L(101),)).fetchone()
    assert pick["standing_basis"] == "prior_season"
    assert pick["orig_rank_at_trade"] == final["rank"]


def _flags(c, txid):
    return set(json.loads(c.execute("SELECT flags_json FROM trades WHERE transaction_id=?",
                                    (txid,)).fetchone()[0]))


def test_cleaning_flags(store):
    w, c = store
    a25 = w.truth_trades[L(102)]
    a26 = w.truth_trades[L(103)]
    assert "during_draft" in _flags(c, a25[1])
    assert "during_draft" not in _flags(c, a25[0])
    assert "orphan_side" in _flags(c, a25[2])
    assert "reversed_within_day" in _flags(c, a26[1])
    assert "reversed_within_day" not in _flags(c, a26[3])
    assert "low_trade_league" in _flags(c, w.truth_trades[L(201)][0])
    assert "low_trade_league" not in _flags(c, a26[0])
    total = sum(len(v) for v in w.truth_trades.values())
    assert c.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == total   # flagged, kept


def test_unusual_scoring_rule():
    assert normalise.unusual_scoring({"rec": 1.5})
    assert normalise.unusual_scoring({"bonus_rec_te": 1.5})
    assert not normalise.unusual_scoring({"rec": 0.5, "pass_td": 6, "bonus_rec_te": 0.5})
