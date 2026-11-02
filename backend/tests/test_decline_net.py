"""BL-004: a declined match nets -trade_k_decline_net (12) at any like K.

record_match_disposition builds a decliner's correction per (give, receive)
pair at K = trade_k_decline_net + the K the user's 'Interested' swipe on
that pair was stored with (database._decline_signals). Before, it was a
fixed trade_k_decline_correction 20, designed against a +8 like: -20 net
while trade swipes were frozen (K 0), -16 at half K, -12 only at full K.
"""
import json

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
from backend.database import metadata, swipe_decisions_table, trade_matches_table
from backend.ranking_service import Player, RankingService

A, B = "user_a", "user_b"
GIVE, RECEIVE = ["g1", "g2"], ["r1", "r2"]       # user_a's side; user_b's is the mirror


@pytest.fixture()
def eng(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "_K_ACCEPT", lambda: 20.0)
    monkeypatch.setattr(db_module, "_K_DECLINE_NET", lambda: 12.0)
    return engine


def _match(engine, *, a_decision="decline", b_decision=None) -> int:
    with engine.begin() as conn:
        return conn.execute(insert(trade_matches_table).values(
            league_id="lg", user_a_id=A, user_b_id=B,
            user_a_give=json.dumps(GIVE), user_a_receive=json.dumps(RECEIVE),
            matched_at="2026-10-27T00:00:00", status="pending",
            user_a_decision=a_decision, user_b_decision=b_decision)).inserted_primary_key[0]


def _swipe(engine, user, winner, loser, k, at="2026-10-26T00:00:00", kind="trade"):
    with engine.begin() as conn:
        conn.execute(insert(swipe_decisions_table).values(
            user_id=user, winner_player_id=winner, loser_player_id=loser,
            decision_type=kind, k_factor=k, created_at=at, scoring_format="1qb_ppr"))


def _decline_ks(result, user) -> dict:
    """(give, receive) -> K of the user's correction signals."""
    out = {}
    for s in result["elo_signals"]:
        if s["user_id"] == user:
            assert s["decision_type"] == "disposition"
            (w,), (l,) = s["winner_ids"], s["loser_ids"]
            out[(w, l)] = s["k_factor"]
    return out


@pytest.mark.parametrize("like_k", [0.0, 2.0, 4.0, 4.8, 8.0],
                         ids=["frozen", "half_pass", "half_k", "fit_scaled", "full_k"])
def test_a_decline_nets_minus_12_at_any_like_k(eng, like_k):
    for g in GIVE:
        for r in RECEIVE:
            _swipe(eng, A, r, g, like_k)                 # A's like: receive over give
    result = db_module.record_match_disposition(_match(eng), B, "accept")
    ks = _decline_ks(result, A)
    assert set(ks) == {(g, r) for g in GIVE for r in RECEIVE}
    for k in ks.values():
        assert like_k - k == pytest.approx(-12.0)        # the net, in K
    assert result["outcome"] == "declined"


def test_each_pair_takes_its_own_likes_k_and_none_reads_0(eng):
    _swipe(eng, A, "r1", "g1", 8.0)
    _swipe(eng, A, "r2", "g1", 4.0)
    _swipe(eng, A, "r1", "g2", 2.0)                       # (g2, r2): never liked
    ks = _decline_ks(db_module.record_match_disposition(_match(eng), B, "accept"), A)
    assert ks == {("g1", "r1"): 20.0, ("g1", "r2"): 16.0,
                  ("g2", "r1"): 14.0, ("g2", "r2"): 12.0}


def test_the_latest_like_wins_and_a_pass_or_another_user_is_not_the_like(eng):
    _swipe(eng, A, "r1", "g1", 8.0, at="2026-10-01T00:00:00")
    _swipe(eng, A, "r1", "g1", 0.0, at="2026-10-20T00:00:00")   # latest: frozen
    _swipe(eng, A, "g1", "r1", 4.0, at="2026-10-25T00:00:00")   # a pass: give over receive
    _swipe(eng, B, "r1", "g1", 8.0, at="2026-10-26T00:00:00")   # someone else's row
    _swipe(eng, A, "r1", "g1", 8.0, at="2026-10-26T00:00:00", kind="disposition")
    ks = _decline_ks(db_module.record_match_disposition(_match(eng), B, "accept"), A)
    assert ks[("g1", "r1")] == 12.0


def test_both_declining_correct_each_from_their_own_likes(eng):
    _swipe(eng, A, "r1", "g1", 8.0)
    _swipe(eng, B, "g1", "r1", 4.0)                       # B's like on the mirror card
    result = db_module.record_match_disposition(_match(eng), B, "decline")
    assert _decline_ks(result, A)[("g1", "r1")] == 20.0
    assert _decline_ks(result, B)[("r1", "g1")] == 16.0


def test_an_accept_is_unchanged(eng):
    result = db_module.record_match_disposition(_match(eng, a_decision="accept"), B, "accept")
    assert result["outcome"] == "accepted"
    assert sorted((s["user_id"], s["winner_ids"], s["loser_ids"], s["k_factor"])
                  for s in result["elo_signals"]) == [
        (A, RECEIVE, GIVE, 20.0), (B, GIVE, RECEIVE, 20.0)]


def test_the_net_is_the_knob(eng, monkeypatch):
    monkeypatch.setattr(db_module, "_K_DECLINE_NET", lambda: 10.0)
    _swipe(eng, A, "r1", "g1", 4.0)
    ks = _decline_ks(db_module.record_match_disposition(_match(eng), B, "accept"), A)
    assert ks[("g1", "r1")] == 14.0 and ks[("g2", "r2")] == 10.0


def test_like_then_decline_moves_the_board_like_a_12_k_decline(eng):
    """On a board, a like at K then the decline lands within 1 Elo of a
    single K-12 decline, at every like K (models-lead's bar: -12 +/- 1)."""
    def board(*swipes):
        svc = RankingService(players=[Player(id=p, name=p, position="RB", team="T", age=25)
                                      for p in ("g1", "r1")])
        for winner, loser, k in swipes:
            svc.record_disposition_signal(winner_ids=[winner], loser_ids=[loser], k_factor=k)
        return {rp.player.id: rp.elo for rp in svc.get_rankings(position=None).rankings}

    direct = board(("g1", "r1", 12.0))
    for like_k in (0.0, 4.0, 8.0):
        _swipe(eng, A, "r1", "g1", like_k, at=f"2026-10-2{int(like_k)}T00:00:00")
        result = db_module.record_match_disposition(_match(eng), B, "accept")
        k = _decline_ks(result, A)[("g1", "r1")]
        net = board(("r1", "g1", like_k), ("g1", "r1", k))
        for pid in ("g1", "r1"):
            assert net[pid] == pytest.approx(direct[pid], abs=1.0), (like_k, pid)
