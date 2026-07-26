"""FB-161 — Quick Set demotion semantics (`demoted_pids` on /api/tiers/save).

Rule (documented in the route + apply_tiers): when a Quick Set tier is
explicitly SAVED, players who were visible-but-unselected and previously
belonged to that tier (or a higher one) are demoted to UNRANKED — pinned
below every band at RankingService.DEMOTED_ELO — instead of silently
keeping the old higher tier. Skip never demotes (the client only sends
demoted_pids on an explicit save); cleared_pids keeps its distinct
"restore the suggested tier" meaning; demotion wins over a clear for the
same pid, and a tier assignment in the same save wins over a demotion.
"""

import pytest

from backend.ranking_service import Player, RankingService

FMT = "1qb_ppr"
POS = "WR"


def _svc():
    # Seeds put jamo squarely in first_1 (band floor 1580) and the rest
    # spread across the ladder — mirrors the tester's Jameson Williams case.
    players = [
        Player(id="stud", name="Stud",   position=POS, team="AAA", age=25),
        Player(id="jamo", name="Jamo",   position=POS, team="DET", age=24),
        Player(id="mid",  name="Mid",    position=POS, team="BBB", age=26),
        Player(id="deep", name="Deep",   position=POS, team="CCC", age=27),
    ]
    seeds = {"stud": 1800.0, "jamo": 1650.0, "mid": 1450.0, "deep": 1250.0}
    svc = RankingService(players=players, seed_ratings=seeds)
    svc._scoring_format = FMT
    return svc


def _tier_of(svc, pid):
    pool = svc._pool(POS)
    elo = svc._compute_elo(pool)
    return RankingService.tier_for_elo(elo[pid], POS, FMT)


def test_demoted_pid_reads_unranked():
    svc = _svc()
    assert _tier_of(svc, "jamo") == "first_1"          # consensus suggestion
    # Explicit first_1 save that picks stud and passes jamo over.
    svc.apply_tiers(POS, {"first_1": ["stud"]}, FMT, demoted_pids=["jamo"])
    assert _tier_of(svc, "stud") == "first_1"
    assert _tier_of(svc, "jamo") is None               # unranked, not deeper
    assert svc._elo_overrides["jamo"] == RankingService.DEMOTED_ELO
    # Untouched players keep their consensus tier.
    assert _tier_of(svc, "mid") == "second"


def test_demotion_wins_over_clear_for_same_pid():
    svc = _svc()
    # Earlier in the run jamo was saved into first_1…
    svc.apply_tiers(POS, {"first_1": ["jamo", "stud"]}, FMT)
    assert _tier_of(svc, "jamo") == "first_1"
    # …then deselected on a revisit-and-save: the client sends him in both
    # cleared (legacy bookkeeping) and demoted. Demote must win — a bare
    # clear would snap him straight back into first_1 off his seed.
    svc.apply_tiers(POS, {"first_1": ["stud"]}, FMT,
                    cleared_pids=["jamo"], demoted_pids=["jamo"])
    assert _tier_of(svc, "jamo") is None


def test_tier_assignment_wins_over_demotion_in_same_save():
    svc = _svc()
    svc.apply_tiers(POS, {"second": ["jamo"]}, FMT, demoted_pids=["jamo"])
    assert _tier_of(svc, "jamo") == "second"


def test_unknown_pids_ignored():
    svc = _svc()
    svc.apply_tiers(POS, {"first_1": ["stud"]}, FMT, demoted_pids=["ghost"])
    assert "ghost" not in svc._elo_overrides


def test_no_demoted_pids_is_todays_behavior():
    svc = _svc()
    svc.apply_tiers(POS, {"first_1": ["stud"]}, FMT)
    assert _tier_of(svc, "jamo") == "first_1"          # pre-#161 status quo
