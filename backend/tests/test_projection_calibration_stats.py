"""Pure pieces of the playoff-odds calibration check
(docs/plans/league-projections/calibration-check/calibration_stats.py), on
synthetic data with a known answer. Standard library only."""
import importlib.util
import math
import random
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "docs/plans/league-projections/calibration-check/calibration_stats.py"
_spec = importlib.util.spec_from_file_location("calibration_stats", _PATH)
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)


def test_independent_errors_have_no_team_component():
    panel = cs.synthetic_panel(random.Random(1), leagues=150, teams=12, weeks=9, tau=0, residual_sd=25, week_sd=8)
    parts = cs.variance_components(panel)
    assert abs(parts["team"]) < 15            # points^2, against a weekly variance of 625
    assert parts["residual"] == pytest.approx(625, rel=.08)
    assert math.sqrt(max(parts["league_week"], 0)) == pytest.approx(8, abs=2)
    assert abs(cs.lag_correlation(panel, 1)) < .05
    for window in (3, 5, 9):
        assert cs.sum_variance_ratio(panel, window)["ratio"] == pytest.approx(1, abs=.12)


def test_planted_persistent_effect_is_recovered():
    tau, resid = 12., 22.
    panel = cs.synthetic_panel(random.Random(2), leagues=60, teams=12, weeks=9, tau=tau, residual_sd=resid, week_sd=6)
    parts = cs.variance_components(panel)
    assert parts["tau"] == pytest.approx(tau, abs=1.5)
    assert parts["residual"] == pytest.approx(resid ** 2, rel=.08)
    rho = tau ** 2 / (tau ** 2 + resid ** 2)
    assert cs.lag_correlation(panel, 1) == pytest.approx(rho, abs=.05)
    assert cs.lag_correlation(panel, 2) == pytest.approx(rho, abs=.05)
    assert cs.sum_variance_ratio(panel, 9)["ratio"] == pytest.approx(1 + 8 * rho, rel=.12)


def test_shuffle_across_teams_removes_the_team_effect_and_within_team_keeps_it():
    panel = cs.synthetic_panel(random.Random(3), leagues=40, teams=12, weeks=9, tau=12, residual_sd=22)
    rng = random.Random(4)
    assert abs(cs.variance_components(cs.shuffle_across_teams(panel, rng))["team"]) < 20
    within = cs.shuffle_within_team(panel, rng)
    # A within-team shuffle keeps every team's total, so the 9-week ratio barely moves
    # (only the league-week means it subtracts change).
    assert cs.sum_variance_ratio(within, 9)["ratio"] == pytest.approx(cs.sum_variance_ratio(panel, 9)["ratio"], rel=.05)


def test_win_overdispersion_near_one_when_probabilities_are_right():
    games = cs.synthetic_games(random.Random(5), teams=2000, weeks=9, tau=0, sd=25)
    for window in (5, 9):
        assert cs.win_overdispersion(games, window)["ratio"] == pytest.approx(1, abs=.06)


def test_win_overdispersion_detects_a_planted_team_effect():
    games = cs.synthetic_games(random.Random(6), teams=2000, weeks=9, tau=15, sd=25)
    assert cs.win_overdispersion(games, 9)["ratio"] > 1.4


def test_win_probability_and_interval():
    assert cs.win_probability(100, 100, 25) == .5
    assert cs.win_probability(125, 100, 25) == pytest.approx(cs.phi(1 / math.sqrt(2)))
    assert cs.interval(list(range(101))) == [2, 98]


def test_unbalanced_league_is_refused():
    with pytest.raises(ValueError):
        cs.variance_components([[[1., 2.], [1.]]])


def test_semivariogram_recovers_a_planted_random_walk_and_stays_flat_without_one():
    rng = random.Random(7)
    walk, still = [], []
    for _ in range(80):
        league_walk, league_still = [], []
        for _ in range(12):
            level, path = 0., []
            for _ in range(9):
                level += rng.gauss(0, 4)
                path.append(level + rng.gauss(0, 6))
            league_walk.append(path)
            league_still.append([rng.gauss(0, 6) for _ in range(9)])
        walk.append(league_walk)
        still.append(league_still)
    assert cs.drift_step_variance(cs.semivariogram(walk, 5)) == pytest.approx(16, rel=.2)
    assert abs(cs.drift_step_variance(cs.semivariogram(still, 5))) < 3
