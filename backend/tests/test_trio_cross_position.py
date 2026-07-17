"""#132 — cross-position trio lane.

Once the user has unlocked the trade finder (all four positional thresholds
met), a small share of trios compare SAME-TIER players from DIFFERENT
positions — the comparison the cross-position trade finder relies on.

Pins:
  1. The lane is gated: pre-unlock it never serves, even at rate 1.0.
  2. Post-unlock it serves 3 same-tier players spanning >= 2 positions.
  3. The knob defaults small and comes out of the tightest remainder —
     boundary / within-tier keep their tuned rates.
  4. Anti-repeat holds across consecutive cross-position trios.
  5. The tier cursor rotates so successive serves cover different tiers.
"""

import random

import pytest

import backend.ranking_service as rs
from backend.ranking_service import Player, RankingService

# Three mid-ladder bands (2026-07-12 8-tier ladder, uniform across positions),
# 3 players per (position, band) so every band spans all four positions.
_BANDS = {
    "first_1": (1580, 1785),
    "second":  (1400, 1575),
    "third":   (1280, 1395),
}
_POSITIONS = ("QB", "RB", "WR", "TE")


def _mixed_pool_service():
    seeds = {}
    players = []
    for pos in _POSITIONS:
        for tier, (lo, hi) in _BANDS.items():
            for i in range(3):
                pid = f"{pos}_{tier}{i}"
                seeds[pid] = lo + (hi - lo) * (i + 0.5) / 3.0
                players.append(Player(id=pid, name=pid, position=pos, team="T", age=25))
    s = RankingService(players=players, seed_ratings=seeds)
    s._scoring_format = "1qb_ppr"
    return s, seeds


def _unlock(s: RankingService) -> None:
    for pos in _POSITIONS:
        s._interactions[pos] = s.POSITION_THRESHOLDS[pos]


def _ids(trio):
    return {trio.player_a.id, trio.player_b.id, trio.player_c.id}


def _force_cross(monkeypatch):
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.0)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.0)
    monkeypatch.setitem(rs._cfg, "trio_cross_pos_rate", 1.0)


def test_gate_closed_pre_unlock(monkeypatch):
    """Pre-unlock, the lane must never serve — even forced to rate 1.0."""
    random.seed(0)
    s, _ = _mixed_pool_service()
    _force_cross(monkeypatch)
    for _ in range(6):
        trio = s.get_next_trio(position="WR")
        assert not trio.reasoning.startswith("Cross-position"), (
            f"cross-position trio served pre-unlock: {trio.reasoning}"
        )
        s.record_ranking([trio.player_a.id, trio.player_b.id, trio.player_c.id])


def test_post_unlock_same_tier_multiple_positions(monkeypatch):
    """Post-unlock the lane serves 3 SAME-TIER players from >= 2 positions."""
    random.seed(1)
    s, _ = _mixed_pool_service()
    _unlock(s)
    _force_cross(monkeypatch)
    trio = s.get_next_trio(position="WR")
    assert trio.reasoning.startswith("Cross-position tier check:")
    players = (trio.player_a, trio.player_b, trio.player_c)
    positions = {p.position for p in players}
    assert len(positions) >= 2, f"expected >= 2 positions, got {positions}"
    elo = s._compute_elo(s._pool(None))
    tiers = {RankingService.tier_for_elo(elo[p.id], p.position, "1qb_ppr")
             for p in players}
    assert len(tiers) == 1, f"cross-position trio must stay in one tier, got {tiers}"
    # a..c ordered by elo desc (matches the within-tier lane's convention).
    assert elo[trio.player_a.id] >= elo[trio.player_c.id]


def test_default_rate_is_small_and_leaves_calibration_lanes_alone():
    """The knob defaults small; its share comes out of the tightest
    remainder, never out of boundary / within-tier."""
    assert 0.0 < rs._DEFAULT_CFG["trio_cross_pos_rate"] <= 0.2
    # boundary + within + cross must still leave a tightest remainder > 0.
    total = (rs._DEFAULT_CFG["trio_boundary_rate"]
             + rs._DEFAULT_CFG["trio_within_tier_rate"]
             + rs._DEFAULT_CFG["trio_cross_pos_rate"])
    assert total < 1.0


def test_variety_mix_includes_cross_pos_only_post_unlock(monkeypatch):
    """_pick_trio_variety offers cross_pos post-unlock (alongside the other
    lanes) and never pre-unlock, at the shipped default weights (pinned via
    monkeypatch — the live _cfg can drift within a full-suite run)."""
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate",
                        rs._DEFAULT_CFG["trio_boundary_rate"])
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate",
                        rs._DEFAULT_CFG["trio_within_tier_rate"])
    monkeypatch.setitem(rs._cfg, "trio_cross_pos_rate",
                        rs._DEFAULT_CFG["trio_cross_pos_rate"])
    random.seed(2)
    s, _ = _mixed_pool_service()
    pre = set()
    for _ in range(40):
        v = s._pick_trio_variety("WR")
        pre.add(v)
        s._trio_last_variety = v
    assert "cross_pos" not in pre

    _unlock(s)
    post = set()
    for _ in range(80):
        v = s._pick_trio_variety("WR")
        post.add(v)
        s._trio_last_variety = v
    assert "cross_pos" in post
    # The calibration + legacy lanes all survive the new entrant.
    assert {"boundary", "within_tier", "tightest"} <= post


def test_cross_pos_respects_anti_repeat(monkeypatch):
    """Consecutive cross-position trios never reuse 2 of the same players."""
    random.seed(3)
    s, seeds = _mixed_pool_service()
    _unlock(s)
    _force_cross(monkeypatch)
    monkeypatch.setitem(rs._cfg, "trio_repeat_avoid", 3.0)
    prev = None
    for _ in range(10):
        trio = s.get_next_trio(position="WR")
        cur = _ids(trio)
        if prev is not None:
            assert len(cur & prev) < 2, f"repeated {cur & prev} back-to-back"
        prev = cur
        s.record_ranking(sorted(cur, key=lambda p: seeds[p], reverse=True))


def test_cross_pos_cursor_covers_multiple_tiers(monkeypatch):
    """Successive cross-position trios target DIFFERENT tiers over time."""
    random.seed(4)
    s, seeds = _mixed_pool_service()
    _unlock(s)
    _force_cross(monkeypatch)
    monkeypatch.setitem(rs._cfg, "trio_repeat_avoid", 0.0)
    seen_tiers = set()
    for _ in range(6):
        trio = s.get_next_trio(position="WR")
        assert trio.reasoning.startswith("Cross-position tier check:")
        seen_tiers.add(trio.reasoning.split(": ", 1)[1])
        s.record_ranking([trio.player_a.id, trio.player_b.id, trio.player_c.id])
    assert len(seen_tiers) >= 2, f"cross-position trios clustered on {seen_tiers}"


def test_single_position_pool_falls_back(monkeypatch):
    """A pool with one position can never produce a cross-position trio —
    the lane returns None and the serve degrades to tightest."""
    random.seed(5)
    seeds = {f"WR{i}": 1580 + i * 20 for i in range(8)}
    players = [Player(id=p, name=p, position="WR", team="T", age=25) for p in seeds]
    s = RankingService(players=players, seed_ratings=seeds)
    s._scoring_format = "1qb_ppr"
    _unlock(s)
    _force_cross(monkeypatch)
    trio = s.get_next_trio(position="WR")
    assert not trio.reasoning.startswith("Cross-position")
