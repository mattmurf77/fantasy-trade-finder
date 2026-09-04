"""Win Now proposal §9: roster sensitivity, paired worlds, legal lineups and full league invariants."""
from copy import deepcopy
import math
import pytest

from backend.season_forecasts import import_projection_snapshot
from backend.season_simulator import (simulate_season, evaluate_trade, select_projected_lineup,
                                     projected_lineup_points, _champion, _player_worlds)


def fixture(teams=6, playoffs=4, completed=3, regular=6, sigma=4):
    league = {"league_id": "test", "season": 2026, "teams": [], "roster_slots": ["WR"],
              "scoring_settings": {"rec": 1}, "schedule": {}, "completed_weeks": completed,
              "regular_season_weeks": regular, "playoff_slots": playoffs,
              "num_byes": 2 if playoffs == 6 else 0, "num_divisions": 0,
              "median_match": False, "playoff_seed_type": 0, "playoff_start_week": regular + 1,
              "status": "in_season", "current_week_started": False}
    rows = []
    for rid in range(1, teams + 1):
        ids = [f"p{rid}", f"b{rid}"]
        league["teams"].append({"roster_id": rid, "user_id": f"user{rid}", "username": f"Team {rid}",
                                "player_ids": ids, "starters": ids[:1], "wins": 1, "losses": completed - 1,
                                "ties": 0, "points_for": 30, "division": None})
        for week in range(completed + 1, regular + (2 if playoffs == 4 else 3) + 1):
            for pid, mu in zip(ids, [10 + rid, 2]):
                rows.append({"player_id": pid, "season": 2026, "week": week, "positions": ["WR"],
                             "stats": {"rec": mu}, "availability": 1, "bye": False, "point_stddev": sigma})
    for week in range(completed + 1, regular + 1):
        league["schedule"][week] = [[rid, teams + 1 - rid] for rid in range(1, teams // 2 + 1)]
    forecasts = import_projection_snapshot(2026, sorted({r["week"] for r in rows}), rows,
                                          provider="fixture", captured_at="2026-09-04T18:00:00Z")
    return league, forecasts


@pytest.mark.parametrize("playoffs,teams", [(4, 6), (6, 8), (8, 10)])
@pytest.mark.parametrize("reseed", [0, 1])
def test_distributions_reconcile_one_champion_and_exact_slots(playoffs, teams, reseed):
    league, forecasts = fixture(teams=teams, playoffs=playoffs)
    league["playoff_seed_type"] = reseed
    result = simulate_season(league, forecasts, n_sims=120)
    assert result["meta"]["supported"]
    assert math.isclose(sum(t["championship_probability"] for t in result["teams"]), 1)
    assert math.isclose(sum(t["playoff_probability"] for t in result["teams"]), playoffs)
    assert math.isclose(sum(t["bye_probability"] for t in result["teams"]), league["num_byes"])
    for team in result["teams"]:
        assert math.isclose(sum(team["finish_distribution"].values()), 1)
        assert math.isclose(team["expected_wins"] + team["expected_losses"] + team["expected_ties"], 6)
        assert team["expected_wins"] >= 1
        assert team["expected_losses"] >= 2


def test_noop_exact_zero_including_sampling_error():
    league, forecasts = fixture()
    result = evaluate_trade(league, forecasts, 1, 2, [], [], n_sims=100)
    assert result["supported"]
    for side in ["buyer", "partner"]:
        assert set(result[side]["delta"].values()) == {0}
        assert all(u["standard_error"] == 0 for u in result[side]["uncertainty"].values())
        assert result[side]["lineup_gain"] == 0


def test_week_three_starter_upgrade_changes_both_rosters_and_wins():
    league, forecasts = fixture(sigma=0)
    result = evaluate_trade(league, forecasts, 1, 6, ["p1"], ["p6"], n_sims=20)
    assert result["supported"]
    assert result["buyer"]["delta"]["expected_remaining_wins"] == 3
    assert result["buyer"]["delta"]["next_three_week_expected_wins"] == 3
    assert result["partner"]["delta"]["expected_remaining_wins"] == -3
    assert result["buyer"]["after"]["expected_wins"] == 4
    assert result["buyer"]["after"]["expected_losses"] == 2
    assert result["buyer"]["lineup_gain"] == 5
    assert result["buyer"]["uncertainty"]["expected_remaining_wins"]["lower_bound"] == 3


def test_bench_exchange_has_zero_points_effect_unless_bye_replacement():
    league, forecasts = fixture(sigma=0)
    for row in forecasts["forecasts"]:
        if row["player_id"] == "b6":
            row["stats"]["rec"] = 8
    before = evaluate_trade(league, forecasts, 1, 6, ["b1"], ["b6"], n_sims=20)
    assert before["buyer"]["lineup_gain"] == 0
    for row in forecasts["forecasts"]:
        if row["player_id"] == "p1" and row["week"] == 4:
            row.update(bye=True, availability=0, stats={})
    after = evaluate_trade(league, forecasts, 1, 6, ["b1"], ["b6"], n_sims=20)
    assert after["buyer"]["lineup_gain"] == 2
    assert after["buyer"]["before"]["projected_lineups"]["4"] == ["b1"]
    assert after["buyer"]["after"]["projected_lineups"]["4"] == ["b6"]


def test_legal_flex_matching_handles_multieligibility_without_double_counting():
    rows = {"dual": {"positions": ["RB", "WR"], "stats": {"rec": 20}, "availability": 1},
            "rb": {"positions": ["RB"], "stats": {"rec": 19}, "availability": 1},
            "wr": {"positions": ["WR"], "stats": {"rec": 1}, "availability": 1}}
    result = select_projected_lineup(rows, ["WR", "RB"], rows, {"rec": 1})
    assert result["projected_points"] == 39
    assert result["slots"] == [{"slot": "WR", "player_id": "dual"}, {"slot": "RB", "player_id": "rb"}]


def test_no_best_ball_hindsight_unused_volatile_bench_does_not_change_odds():
    league, forecasts = fixture()
    baseline = simulate_season(league, forecasts, n_sims=100)
    for row in forecasts["forecasts"]:
        if row["player_id"].startswith("b"):
            row["point_stddev"] = 10000
    changed = simulate_season(league, forecasts, n_sims=100)
    assert changed["teams"] == baseline["teams"]


def test_player_week_worlds_do_not_depend_on_roster_or_bracket_order():
    a = _player_worlds("x", 2026, "p1", 15, 100, 42)
    _player_worlds("x", 2026, "p9", 17, 100, 42)
    assert a == _player_worlds("x", 2026, "p1", 15, 100, 42)
    assert a != _player_worlds("x", 2026, "p1", 16, 100, 42)
    league, forecasts = fixture()
    original = simulate_season(league, forecasts, n_sims=100)
    league["teams"].reverse()
    changed = simulate_season(league, forecasts, n_sims=100)
    assert sorted(original["teams"], key=lambda t: t["roster_id"]) == sorted(changed["teams"], key=lambda t: t["roster_id"])


def test_fixed_bracket_and_reseed_use_actual_next_week_not_new_draw_per_match():
    scores = {15: {i: float(i) for i in range(1, 9)},
              16: {i: float(-i) for i in range(1, 9)},
              17: {i: float(i) for i in range(1, 9)}}
    assert _champion(list(range(1, 9)), 8, 0, scores, 15) == 6
    assert _champion(list(range(1, 9)), 8, 1, scores, 15) == 6
    # Six seeds: 1 and 2 do not play week 15; week 16 scores decide semis.
    assert _champion(list(range(1, 7)), 6, 0, scores, 15) == 2
    assert _champion(list(range(1, 7)), 6, 1, scores, 15) == 2


def test_median_matches_preserve_actual_records_and_add_two_decisions():
    league, forecasts = fixture(sigma=0)
    league["median_match"] = True
    for team in league["teams"]:
        team.update(wins=2, losses=4)
    result = simulate_season(league, forecasts, n_sims=10)
    for team in result["teams"]:
        assert team["expected_wins"] + team["expected_losses"] + team["expected_ties"] == 12
    assert result["teams"][-1]["next_three_week_expected_wins"] == 6


def test_missing_deep_bench_warns_but_missing_starter_fails():
    league, forecasts = fixture()
    league["teams"][0]["player_ids"].append("retired")
    result = simulate_season(league, forecasts, n_sims=10)
    assert result["meta"]["supported"]
    assert result["meta"]["warnings"] == ["unprojected_bench_excluded"]
    assert result["teams"][0]["coverage"]["excluded_bench_ids"]["4"] == ["retired"]
    league["teams"][0]["starters"] = ["retired"]
    assert not simulate_season(league, forecasts, n_sims=10)["meta"]["supported"]


def test_unknown_availability_contributor_fails_but_ir_bench_does_not_block():
    league, forecasts = fixture()
    for row in forecasts["forecasts"]:
        if row["player_id"] == "b1":
            row["availability"] = None
    assert simulate_season(league, forecasts, n_sims=10)["meta"]["supported"]
    for row in forecasts["forecasts"]:
        if row["player_id"] == "b1":
            row["stats"]["rec"] = 100
    result = simulate_season(league, forecasts, n_sims=10)
    assert not result["meta"]["supported"]
    assert "unknown_contributor_availability" in result["meta"]["reasons"][0]


@pytest.mark.parametrize("change,reason", [
    ({"current_week_started": True}, "unsupported_live"),
    ({"completed_weeks": 6}, "unsupported_postseason"),
    ({"num_divisions": 2}, "unsupported_division"),
    ({"playoff_round_weeks": 2}, "unsupported_playoff_rounds"),
    ({"playoff_seed_type": 7}, "unsupported_playoff_seed_type"),
    ({"roster_slots": ["K"]}, "unsupported_roster_slots"),
    ({"scoring_settings": {"bonus_pass_yd_300": 3}}, "unsupported_scoring"),
])
def test_unsupported_rules_fail_closed(change, reason):
    league, forecasts = fixture()
    league.update(change)
    result = simulate_season(league, forecasts, n_sims=10)
    assert not result["meta"]["supported"]
    assert any(reason in r for r in result["meta"]["reasons"])
    assert result["teams"] == []


def test_missing_schedule_or_postseason_forecast_fails_closed():
    league, forecasts = fixture()
    del league["schedule"][5]
    assert not simulate_season(league, forecasts, n_sims=10)["meta"]["supported"]
    league, forecasts = fixture()
    forecasts["forecasts"] = [r for r in forecasts["forecasts"] if r["week"] != 8]
    assert not simulate_season(league, forecasts, n_sims=10)["meta"]["supported"]


def test_dynasty_elo_and_picks_do_not_drive_points():
    league, forecasts = fixture()
    baseline = simulate_season(league, forecasts, n_sims=40)
    league["personal_elo"] = {"p1": 9999999}
    league["dynasty_values"] = {"p1": 9999999}
    league["pick_values"] = {"2027_first": 9999999}
    assert simulate_season(league, forecasts, n_sims=40)["teams"] == baseline["teams"]


def test_trade_ownership_and_stale_baseline_rejected():
    league, forecasts = fixture()
    assert not evaluate_trade(league, forecasts, 1, 2, ["p6"], ["p2"], n_sims=10)["supported"]
    baseline = simulate_season(league, forecasts, n_sims=10)
    league["teams"][0]["points_for"] += 1
    result = evaluate_trade(league, forecasts, 1, 2, [], [], n_sims=10, baseline=baseline)
    assert result["reasons"] == ["baseline_revision_mismatch"]


def test_paired_standard_error_matches_empirical_difference_and_is_not_model_claim():
    league, forecasts = fixture(sigma=8)
    result = evaluate_trade(league, forecasts, 1, 6, ["p1"], ["p6"], n_sims=200)
    u = result["buyer"]["uncertainty"]["playoff_probability"]
    assert u["paired"] and u["standard_error"] > 0
    assert u["lower_bound"] < result["buyer"]["delta"]["playoff_probability"] < u["upper_bound"]
    assert u["kind"] == "monte_carlo_only"
    assert result["meta"]["calibrated"] is False


def test_ties_and_clinched_eliminated_teams_respect_locked_record():
    league, forecasts = fixture(completed=10, regular=11, sigma=0)
    for row in forecasts["forecasts"]:
        row["stats"] = {"rec": 10}
    league["teams"][0].update(wins=10, losses=0)
    league["teams"][-1].update(wins=0, losses=10)
    for team in league["teams"][1:-1]:
        team.update(wins=5, losses=5)
    result = simulate_season(league, forecasts, n_sims=10)
    assert result["teams"][0]["playoff_probability"] == 1
    assert result["teams"][-1]["playoff_probability"] == 0
    assert result["teams"][0]["expected_ties"] == 1
    assert result["teams"][0]["win_credit"] == 10.5
    assert result["teams"][0]["weekly_tie_probabilities"] == {"11": 1}


def test_unavailable_player_zero_points_even_with_huge_variance():
    league, forecasts = fixture(sigma=0)
    for row in forecasts["forecasts"]:
        if row["player_id"] == "p1":
            row.update(availability=0, point_stddev=100000)
    result = simulate_season(league, forecasts, n_sims=30)
    assert result["teams"][0]["projected_lineups"]["4"] == ["b1"]
    assert result["teams"][0]["projected_lineup_points"]["4"] == 2


def test_doubleheader_and_duplicate_ownership_fail_closed():
    league, forecasts = fixture()
    league["schedule"][4].append([1, 2])
    assert not simulate_season(league, forecasts, n_sims=10)["meta"]["supported"]
    league, forecasts = fixture()
    league["teams"][1]["player_ids"].append("p1")
    assert not simulate_season(league, forecasts, n_sims=10)["meta"]["supported"]


def test_certified_bye_for_sole_qb_is_supported_exact_zero_not_unknown_coverage():
    league, forecasts = fixture(sigma=0)
    league["roster_slots"] = ["QB"]
    for team in league["teams"]:
        team["player_ids"] = team["starters"]
    for row in forecasts["forecasts"]:
        row["positions"] = ["QB"]
        if row["player_id"] == "p1":
            row.update(bye=True, availability=0, stats={})
    result = simulate_season(league, forecasts, n_sims=10)
    assert result["meta"]["supported"]
    assert result["teams"][0]["projected_lineup_points"]["4"] == 0
    assert result["teams"][0]["expected_remaining_wins"] == 0


def test_fully_known_roster_hole_scores_zero_but_unknown_hole_fails_coverage():
    league, forecasts = fixture(sigma=0)
    league["roster_slots"] = ["QB", "WR"]
    result = simulate_season(league, forecasts, n_sims=10)
    assert result["meta"]["supported"]
    assert result["teams"][0]["coverage"]["empty_slots_by_week"]["4"] == 1
    assert result["teams"][0]["projected_lineup_points"]["4"] == 11
    league["teams"][0]["player_ids"].append("unprojected_qb")
    result = simulate_season(league, forecasts, n_sims=10)
    assert not result["meta"]["supported"]
    assert "incomplete_lineup_coverage" in result["meta"]["reasons"][0]
