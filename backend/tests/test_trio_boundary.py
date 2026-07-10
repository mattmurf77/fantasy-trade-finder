"""Lever A — boundary-probing trio selection (trios → tier calibration).

The legacy selector picks the *tightest* uncompared trio, so it only ever
compares near-equals and never asks the cross-tier question that moves a player
across a value band. `_boundary_trio` deliberately pairs a player just below a
tier edge against one just above it, drawn from the FULL pool.

Plan: docs/plans/trios-tier-calibration-plan-2026-07-08.md
"""

import pytest

import backend.ranking_service as rs
from backend.ranking_service import Player, RankingService


# WR 1qb_ppr bands (2026-07-10 consensus recalibration): elite 1700–1800,
# starter 1505–1695, solid 1360–1500, depth 1220–1355, bench 1150–1215.
# Seed players so several edges are contested within the ±60 margin
# (e.g. the starter/elite edge at 1700).
_SEEDS = {
    "elite_a":   1755,   # elite
    "elite_b":   1710,   # elite (just above the 1700 edge)
    "star_a":    1690,   # starter (just below the 1700 edge)
    "star_b":    1600,   # starter
    "star_c":    1515,   # starter (just above the 1505 edge)
    "solid_a":   1495,   # solid (just below the 1505 edge)
    "solid_b":   1400,   # solid
    "depth_a":   1300,   # depth
}


@pytest.fixture()
def svc(monkeypatch):
    players = [Player(id=pid, name=pid.upper(), position="WR", team="AAA", age=25)
               for pid in _SEEDS]
    s = RankingService(players=players, seed_ratings=dict(_SEEDS))
    s._scoring_format = "1qb_ppr"
    # Deterministic boundary path: 100% boundary, 0% within-tier.
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 1.0)
    monkeypatch.setitem(rs._cfg, "trio_within_tier_rate", 0.0)
    return s


def _tiers_of(s: RankingService, trio) -> set:
    elo = s._compute_elo(s._pool("WR"))
    return {
        RankingService.tier_for_elo(elo[p.id], "WR", "1qb_ppr")
        for p in (trio.player_a, trio.player_b, trio.player_c)
    }


def test_boundary_trio_straddles_a_tier_edge(svc):
    trio = svc._boundary_trio("WR")
    assert trio is not None
    # The two headline players (a=above edge, b=below) must be in different tiers.
    elo = svc._compute_elo(svc._pool("WR"))
    ta = RankingService.tier_for_elo(elo[trio.player_a.id], "WR", "1qb_ppr")
    tb = RankingService.tier_for_elo(elo[trio.player_b.id], "WR", "1qb_ppr")
    assert ta != tb, f"expected a cross-tier pair, got {ta}/{tb}"
    assert trio.reasoning.startswith("Boundary probe")


def test_get_next_trio_uses_boundary_when_rate_high(svc):
    trio = svc.get_next_trio(position="WR")
    assert trio.reasoning.startswith("Boundary probe")
    # Trio spans at least two tiers — the whole point.
    assert len(_tiers_of(svc, trio)) >= 2


def test_rate_zero_falls_back_to_legacy_tightest(svc, monkeypatch):
    monkeypatch.setitem(rs._cfg, "trio_boundary_rate", 0.0)
    trio = svc.get_next_trio(position="WR")
    assert trio.reasoning == "Tightest uncompared trio by Elo."


def test_boundary_trio_none_for_overall_mode(svc):
    # Overall (position=None) has no single positional band set.
    assert svc._boundary_trio(None) is None


def test_boundary_trio_none_when_single_tier(monkeypatch):
    # All players packed inside one band → no contested edge → None (caller
    # falls back to the tightest-trio selector).
    seeds = {f"s{i}": 1400 + i for i in range(6)}  # all 'solid' (1360–1500)
    players = [Player(id=pid, name=pid, position="WR", team="A", age=25) for pid in seeds]
    s = RankingService(players=players, seed_ratings=seeds)
    s._scoring_format = "1qb_ppr"
    assert s._boundary_trio("WR") is None


def test_boundary_trio_players_are_distinct(svc):
    trio = svc._boundary_trio("WR")
    ids = {trio.player_a.id, trio.player_b.id, trio.player_c.id}
    assert len(ids) == 3
