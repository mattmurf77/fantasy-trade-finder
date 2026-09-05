"""Owner contract: app feedback may reorder within a tier, never change it.

Ranking actions keep their existing rules. These tests use real configured
bands, offline services, and persisted row replay; no production data.
"""
import pytest

from backend import ranking_service as rs
from backend.ranking_service import Player, RankingService


CELLS = [(fmt, pos, tier) for fmt, positions in rs.TIER_CONFIG.items()
         for pos, tiers in positions.items() for tier in tiers]


def service(values, position="WR", scoring_format="1qb_ppr"):
    svc = RankingService(
        [Player(id=pid, name=pid, position=position, team="T", age=25)
         for pid in values], seed_ratings=values)
    svc._scoring_format = scoring_format
    return svc


def ratings(svc):
    return svc._compute_elo(list(svc._players.values()))


@pytest.mark.parametrize("fmt,pos,tier", CELLS)
def test_repeated_feedback_stays_in_each_configured_tier(fmt, pos, tier):
    lo, hi = RankingService.tier_bands_for(pos, fmt)[tier]
    svc = service({"up": hi - 0.25, "down": lo + 0.25}, pos, fmt)
    before = ratings(svc)
    for i in range(200):
        if i % 3 == 0:
            svc.record_disposition_signal(["up"], ["down"], k_factor=20)
        else:
            svc.record_trade_signal(["up"], ["down"],
                                    decision="like" if i % 2 else "pass")
    after = ratings(svc)
    assert after is not before  # every signal invalidates the memo
    assert before["up"] < after["up"] <= hi
    assert lo <= after["down"] < before["down"]
    assert {svc.tier_for_elo(v, pos, fmt) for v in after.values()} == {tier}
    assert ratings(svc) is after  # warm reads don't replay or accumulate


@pytest.mark.parametrize("value", [1149.75, 1149.94, 1149.98, 1100.0,
                                 1369.98, 1577.0, 1579.98, 2700.0])
def test_feedback_cannot_promote_unranked_or_escape_gap_and_top_tiers(value):
    svc = service({"up": value, "down": value})
    tier = svc.tier_for_elo(round(value, 1), "WR")
    for _ in range(400):
        svc.record_trade_signal(["up"], ["down"])
    after = ratings(svc)
    assert svc.tier_for_elo(round(after["up"], 1), "WR") == tier
    assert svc.tier_for_elo(round(after["down"], 1), "WR") == tier
    assert after["up"] >= value >= after["down"]
    for ranked in svc.get_rankings(position="WR").rankings:
        assert svc.tier_for_elo(ranked.elo, "WR") == tier


def test_ranking_actions_can_change_an_unplaced_tier_then_feedback_respects_it():
    svc = service({"up": 1574.0, "down": 1574.0})
    svc.record_ranking(["up", "down"])
    base = ratings(svc).copy()
    assert svc.tier_for_elo(base["up"], "WR") == "first_1"
    assert svc.tier_for_elo(base["down"], "WR") == "second"
    for _ in range(300):
        svc.record_trade_signal(["down"], ["up"])
    assert svc.tier_for_elo(ratings(svc)["up"], "WR") == "first_1"
    assert svc.tier_for_elo(ratings(svc)["down"], "WR") == "second"


def test_trade_boundary_also_applies_to_an_explicitly_released_pin(monkeypatch):
    monkeypatch.setitem(rs._cfg, "pin_unpin_on_newer_swipe", 1.0)
    svc = service({"up": 1500.0, "down": 1500.0})
    svc._elo_overrides = {"up": 1574.0}
    svc._elo_override_at = {"up": "2026-01-01T00:00:00+00:00"}
    svc.record_ranking(["up", "down"])
    base = ratings(svc).copy()
    assert svc.tier_for_elo(base["up"], "WR") == "first_1"
    for _ in range(300):
        svc.record_trade_signal(["up"], ["down"])
    for pid, value in ratings(svc).items():
        assert svc.tier_for_elo(value, "WR") == svc.tier_for_elo(base[pid], "WR")


def test_replaying_retained_rows_restores_board_without_inverse_clamp_artifacts():
    values = {"up": 1574.5, "down": 1370.5}
    rows = [{"winner_player_id": "up", "loser_player_id": "down",
             "decision_type": "trade_like", "k_factor": 8,
             "created_at": "2026-09-05T01:00:00+00:00"} for _ in range(200)]
    live = service(values)
    for _ in rows:
        live.record_disposition_signal(["up"], ["down"], k_factor=8)
    replay = service(values)
    replay.replay_from_db(rows)
    assert ratings(replay) == ratings(live)
    assert ratings(replay) == {"up": 1575.0, "down": 1370.0}

    # Correct causal reversal requires replaying retained rows, not an
    # opposite update (which cannot invert clamping). This tests that replay
    # primitive, NOT the production Undo route's selection/removal of rows.
    retained = [{**rows[0], "winner_player_id": "down", "loser_player_id": "up"}]
    undone = service(values)
    undone.replay_from_db(retained)
    reference = service(values)
    reference.record_disposition_signal(["down"], ["up"], k_factor=8)
    assert ratings(undone) == ratings(reference)
    cleared = service(values)
    cleared.replay_from_db([])
    assert ratings(cleared) == values


def test_interactions_do_not_become_explicit_ranking_comparison_evidence():
    svc = service({"up": 1500.0, "down": 1500.0})
    for _ in range(200):
        svc.record_trade_signal(["up"], ["down"])
    ratings(svc)
    assert svc.comparison_counts() == {"up": 0, "down": 0}
