"""Trio variety + anti-repeat.

Two operator asks:
  1. Trios should VARY between strategies (boundary / within-tier / tightest)
     rather than running the same kind over and over.
  2. Add a "top vs bottom of the SAME tier" variety so intra-tier order is solid.
  3. Fix the observed bug: ~10 trios in a row reusing 2 of the same players.

Plan: docs/plans/trios-tier-calibration-plan-2026-07-08.md
"""

import random

import pytest

import backend.ranking_service as rs
from backend.ranking_service import Player, RankingService

# WR 1qb_ppr bands (2026-07-10 consensus recalibration). Pack ~6 players into
# each band so within-tier trios have >=3 members and the pool is large enough
# for anti-repeat to breathe.
_BANDS = {
    "elite":   (1700, 1800),
    "starter": (1505, 1695),
    "solid":   (1360, 1500),
    "depth":   (1220, 1355),
    "bench":   (1150, 1215),
}


def _big_pool_service():
    seeds = {}
    for tier, (lo, hi) in _BANDS.items():
        for i in range(6):
            seeds[f"{tier}{i}"] = lo + (hi - lo) * i / 5.0
    players = [Player(id=p, name=p, position="WR", team="A", age=25) for p in seeds]
    s = RankingService(players=players, seed_ratings=seeds)
    s._scoring_format = "1qb_ppr"
    return s, seeds


def _ids(trio):
    return {trio.player_a.id, trio.player_b.id, trio.player_c.id}


def test_within_tier_trio_spans_one_tier_top_to_bottom(monkeypatch):
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.0)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 1.0)  # force within-tier
    trio = s.get_next_trio(position="WR")
    assert trio.reasoning.startswith("Within-tier spread:")
    elo = s._compute_elo(s._pool("WR"))
    tiers = {RankingService.tier_for_elo(elo[p.id], "WR", "1qb_ppr")
             for p in (trio.player_a, trio.player_b, trio.player_c)}
    assert len(tiers) == 1, f"within-tier trio must stay in one tier, got {tiers}"
    # a = top of tier, c = bottom.
    assert elo[trio.player_a.id] >= elo[trio.player_c.id]


def test_no_two_consecutive_trios_reuse_two_players(monkeypatch):
    """The core bug: never surface 2 of the same players back-to-back."""
    random.seed(1234)
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.4)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.35)
    monkeypatch.setitem(rs._cfg, "trio_repeat_avoid", 3.0)

    prev = None
    for _ in range(14):
        trio = s.get_next_trio(position="WR")
        cur = _ids(trio)
        if prev is not None:
            assert len(cur & prev) < 2, f"repeated {cur & prev} back-to-back"
        prev = cur
        # advance state as if the user ranked them
        s.record_ranking([trio.player_a.id, trio.player_b.id, trio.player_c.id])


def test_strategy_rotates_over_a_session(monkeypatch):
    """Over a run we should see more than one KIND of trio (variety)."""
    random.seed(7)
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.4)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.35)

    kinds = set()
    for _ in range(16):
        trio = s.get_next_trio(position="WR")
        kinds.add(trio.reasoning.split(":")[0])   # "Boundary probe" / "Within-tier spread" / "Tightest uncompared trio by Elo."
        s.record_ranking([trio.player_a.id, trio.player_b.id, trio.player_c.id])
    assert len(kinds) >= 2, f"expected varied trio kinds, only saw {kinds}"


def test_pick_variety_never_repeats_immediately(monkeypatch):
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.4)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.35)
    random.seed(99)
    last = None
    for _ in range(30):
        v = s._pick_trio_variety("WR")
        if last is not None:
            assert v != last, "strategy repeated immediately despite alternatives"
        last = v
        s._trio_last_variety = v


def test_within_tier_cursor_covers_multiple_tiers(monkeypatch):
    """Successive within-tier trios should target DIFFERENT tiers over time."""
    s, _ = _big_pool_service()
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.0)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 1.0)
    monkeypatch.setitem(rs._cfg, "trio_repeat_avoid", 0.0)
    seen_tiers = set()
    for _ in range(5):
        trio = s.get_next_trio(position="WR")
        seen_tiers.add(trio.reasoning.split(": ", 1)[1])
        s.record_ranking([trio.player_a.id, trio.player_b.id, trio.player_c.id])
    assert len(seen_tiers) >= 3, f"within-tier trios clustered on {seen_tiers}"
