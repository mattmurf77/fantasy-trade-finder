"""TC-RNK-001 — Elo math golden fixtures (input-quality for the trade engine).

The trade engine is only as good as the personal Elo it consumes. This pins the
Elo update to its documented spec with hand-computed values:

  - Single pairwise update: exact logistic expected score + K·(S−E).
  - K-factor by decision type: rank=elo_k(32), like=8, pass=4 — movement scales
    linearly with K.
  - Zero-sum conservation: without overrides, total Elo is invariant per swipe.
  - 3-player decomposition: [A,B,C] → exactly 3 pairwise (A>B, A>C, B>C),
    final order preserved.
  - Override pinning: a tier-placed player's Elo doesn't move; the partner still
    evolves against the anchor.
  - Replay determinism: same swipe sequence → identical Elo.

Complements test_elo_memoization.py (which covers caching/parity, not the
arithmetic).
"""

import math

import backend.ranking_service as rs
from backend.ranking_service import RankingService, Player

K = rs._c("elo_k")           # 32.0
INIT = RankingService.ELO_INITIAL  # 1500.0


def _players(ids, position="RB"):
    return [Player(id=i, name=f"P{i}", position=position, team="T", age=24) for i in ids]


def _svc(ids, position="RB"):
    return RankingService(players=_players(ids, position))


def _elo(svc, position="RB"):
    return {r.player.id: r.elo for r in svc.get_rankings(position=position).rankings}


def _expected(ra, rb):
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


# ── 1. Single pairwise update is exact ──────────────────────────────────────

def test_single_pairwise_exact():
    svc = _svc(["a", "b"])
    svc.record_ranking(["a", "b"])           # a > b, both seed 1500
    elo = _elo(svc)
    # ea = 0.5 -> winner +16, loser -16 at K=32.
    assert elo["a"] == 32 * 0.5 + INIT       # 1516.0
    assert elo["b"] == INIT - 32 * 0.5       # 1484.0
    assert elo["a"] + elo["b"] == 2 * INIT   # zero-sum


# ── 2. K-factor scales movement linearly by decision type ───────────────────

def _winner_gain_after(kind):
    svc = _svc(["a", "b"])
    if kind == "rank":
        svc.record_ranking(["a", "b"])
    else:
        svc.record_trade_signal(winner_ids=["a"], loser_ids=["b"], decision=kind)
    return _elo(svc)["a"] - INIT


def test_k_factor_by_decision_type():
    g_rank = _winner_gain_after("rank")   # K=32 -> +16
    g_like = _winner_gain_after("like")   # K=8  -> +4
    g_pass = _winner_gain_after("pass")   # K=4  -> +2
    assert g_rank == 16.0 and g_like == 4.0 and g_pass == 2.0
    # Linear in K: rank:like:pass = 32:8:4 = 4:1 and 8:1.
    assert g_rank / g_like == rs._c("elo_k") / rs._c("trade_k_like") == 4.0
    assert g_like / g_pass == rs._c("trade_k_like") / rs._c("trade_k_pass") == 2.0


# ── 3. 3-player decomposition + conservation ────────────────────────────────

def test_three_player_decomposition_and_conservation():
    svc = _svc(["a", "b", "c"])
    rank_set = svc.record_ranking(["a", "b", "c"])
    # [A,B,C] -> 3 pairwise swipes.
    assert len(svc._swipes) == 3
    assert {(s.winner_id, s.loser_id) for s in svc._swipes} == {("a", "b"), ("a", "c"), ("b", "c")}
    elo = _elo(svc)
    # Total Elo conserved (every pairwise update is zero-sum, no overrides).
    assert math.isclose(sum(elo.values()), 3 * INIT, abs_tol=1e-6)
    # Submitted order preserved in final ranking.
    assert elo["a"] > elo["b"] > elo["c"]


def test_three_player_exact_sequential():
    """Hand-trace the sequential updates for [a,b,c] all at 1500."""
    svc = _svc(["a", "b", "c"])
    svc.record_ranking(["a", "b", "c"])
    elo = _elo(svc)
    # Reproduce the engine's documented sequential math independently.
    r = {"a": INIT, "b": INIT, "c": INIT}
    for w, l in [("a", "b"), ("a", "c"), ("b", "c")]:
        ea = _expected(r[w], r[l])
        r[w] += K * (1 - ea)
        r[l] += K * (0 - (1 - ea))
    # get_rankings rounds displayed Elo to 1 decimal — and that rounded value
    # is what gets published to member_rankings and fed to the trade engine.
    for pid in ("a", "b", "c"):
        assert math.isclose(elo[pid], round(r[pid], 1), abs_tol=1e-6), (pid, elo[pid], r[pid])


# ── 4. Override pinning ─────────────────────────────────────────────────────

def test_override_pins_winner_partner_still_moves():
    svc = _svc(["a", "b"])
    svc.apply_tiers(position="RB", tiers={"elite": ["a"]}, scoring_format="1qb_ppr")
    pinned = _elo(svc)["a"]
    svc.record_ranking(["a", "b"])           # a wins but is pinned
    elo = _elo(svc)
    assert elo["a"] == pinned, "overridden player's Elo must not move"
    assert elo["b"] < INIT, "non-overridden loser must still drop against the anchor"


# ── 5. Replay determinism ───────────────────────────────────────────────────

def test_replay_determinism():
    seq = [["a", "b", "c"], ["b", "c", "d"], ["a", "d", "c"]]
    e1 = _elo_after(seq)
    e2 = _elo_after(seq)
    assert e1 == e2


def _elo_after(seq):
    svc = _svc(["a", "b", "c", "d"])
    for ordered in seq:
        svc.record_ranking(ordered)
    return _elo(svc)
