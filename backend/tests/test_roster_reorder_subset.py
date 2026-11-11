"""Roster-first setup (D-212) — the inline "rank my roster" step.

docs/plans/roster-first-trade-setup/prd.md §5, AC-5, AC-6. The setup screen
posts `POST /api/rankings/reorder {position, ordered_ids}` with NO `via`,
once per position, containing only that position's ROSTER player IDs. The
route is reused unchanged; this file pins the contract the screen relies on:
  1. Only the posted IDs' Elos move (board diff == posted subset), even when
     the subset spans tiers and is interleaved with non-roster players.
  2. No `via` ⇒ `ranking_reorder` fires and `quickrank_completed` does NOT.
  3. Every posted ID resolves to source `explicit` — in `_ranking_confidence`
     (`_placed`) and in the next owner context's `user_sources` — while a
     roster player at another position stays non-explicit.

Harness mirrors test_fair_packages: Flask test client, a real RankingService
in an in-memory session, isolated in-memory SQLite, `record_event` mocked.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
import backend.trade_service as ts
from backend.database import metadata
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

ME, OPP = "user_rs_me", "user_rs_opp"
LEAGUE = "league_roster_setup"
TOKEN = "test-token-roster-setup"

# Distinct Elos (no tie-breaker noise), RBs spread across several tiers, with
# league-mates' RBs interleaved between mine.
SEED = {
    "rb1": 1880., "rb2": 1820., "rb3": 1700., "rb4": 1640.,
    "rb5": 1520., "rb6": 1430., "rb7": 1330., "rb8": 1260.,
    "wr1": 1800., "wr2": 1600.,
}
POS = {pid: pid[:2].upper() for pid in SEED}
MY_ROSTER = ["rb1", "rb3", "rb5", "rb7", "wr1"]
MY_RBS = [p for p in MY_ROSTER if POS[p] == "RB"]
THEIR_ROSTER = ["rb2", "rb4", "rb6", "rb8", "wr2"]


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    players = [Player(id=pid, name=pid.upper(), position=POS[pid], team="AAA", age=25)
               for pid in SEED]
    service = RankingService(players=players, seed_ratings=dict(SEED))
    trade_svc = TradeService(players={p.id: p for p in players})
    league = League(league_id=LEAGUE, name="Roster Setup League", platform="sleeper", members=[
        LeagueMember(user_id=ME, username="me", roster=list(MY_ROSTER), elo_ratings={}),
        LeagueMember(user_id=OPP, username="opp", roster=list(THEIR_ROSTER), elo_ratings={}),
    ])
    trade_svc.add_league(league)
    sess = {"verified": True, "user_id": ME, "league": league, "players": players,
            "user_roster": list(MY_ROSTER), "services": {"1qb_ppr": service},
            "service": service, "trade_svcs": {"1qb_ppr": trade_svc}, "trade_svc": trade_svc,
            "active_format": "1qb_ppr", "last_active": 0.0}
    server.app.config["TESTING"] = True
    old_flags, old_cfg = ff._flags_cache, dict(ts._cfg)
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.preference_lists": True}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "record_event", MagicMock()) as events:
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield server.app.test_client(), sess, trade_svc, league, events
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            ff._flags_cache = old_flags
            ts._cfg.clear()
            ts._cfg.update(old_cfg)


def _board(service):
    return {rp.player.id: rp.elo for rp in service.get_rankings(position=None).rankings}


def _reorder(client, ordered_ids, position="RB"):
    return client.post("/api/rankings/reorder", headers={"X-Session-Token": TOKEN},
                       json={"position": position, "ordered_ids": ordered_ids})


def test_roster_subset_reorder_moves_only_the_posted_ids(harness):
    client, sess, *_ = harness
    service = sess["service"]
    before = _board(service)
    tiers = {RankingService.tier_for_elo(before[p], "RB", "1qb_ppr") for p in MY_RBS}
    assert len(tiers) >= 3, "fixture must span tiers at one position"

    posted = list(reversed(MY_RBS))          # bottom-of-roster RB to the top
    res = _reorder(client, posted)
    assert res.status_code == 200 and res.get_json()["ok"] is True

    after = _board(service)
    moved = {pid for pid in before if after[pid] != pytest.approx(before[pid])}
    assert moved == set(MY_RBS)
    # A pure permutation of the subset's own Elos, dealt out in posted order.
    assert sorted(after[p] for p in MY_RBS) == pytest.approx(sorted(before[p] for p in MY_RBS))
    assert [after[p] for p in posted] == sorted((after[p] for p in posted), reverse=True)
    assert set(service._elo_overrides) == set(MY_RBS)


def test_no_via_fires_ranking_reorder_but_not_quickrank_completed(harness):
    client, _, _, _, events = harness
    assert _reorder(client, list(reversed(MY_RBS))).status_code == 200
    names = [c.args[1] for c in events.call_args_list]
    assert names.count("ranking_reorder") == 1
    assert "quickrank_completed" not in names


def test_posted_ids_resolve_to_explicit_in_the_next_owner_context(harness):
    client, sess, trade_svc, league, _ = harness
    service = sess["service"]
    assert _reorder(client, list(reversed(MY_RBS))).status_code == 200

    placed = server._ranking_confidence(service)["_placed"]
    assert set(MY_RBS) <= placed and "wr1" not in placed

    user_elo = _board(service)
    context = server._owner_generation_context(
        sess=sess, service=service, league=league, players=trade_svc._players,
        seed_map=dict(SEED), user_elo=user_elo, user_roster=list(MY_ROSTER),
        scoring_format="1qb_ppr", fairness_threshold=.5, captured_rankings={})
    sources = context["user_sources"]
    assert {sources[p] for p in MY_RBS} == {"explicit"}
    assert sources["wr1"] != "explicit"          # untouched position stays as it was
    assert all(sources[p] != "explicit" for p in THEIR_ROSTER)
