"""Pure pieces of the score-spread study
(docs/plans/league-projections/score-spread-study/spread_stats.py), on synthetic
data with a known answer. Standard library only."""
import importlib.util
import math
import random
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "docs/plans/league-projections/score-spread-study/spread_stats.py"
_spec = importlib.util.spec_from_file_location("spread_stats", _PATH)
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)


def _games(rng, n, true_sd, bases=lambda: (1., 1.)):
    games = []
    for _ in range(n):
        pa, pb = rng.gauss(130, 20), rng.gauss(130, 20)
        ba, bb = bases()
        a = pa + true_sd * math.sqrt(ba) * rng.gauss(0, 1)
        b = pb + true_sd * math.sqrt(bb) * rng.gauss(0, 1)
        games.append((pa - pb, ba, bb, 1 if a > b else 0))
    return games


def test_fit_scale_recovers_a_planted_flat_sd():
    for true_sd in (18., 25., 35.):
        fitted = ss.fit_scale(_games(random.Random(int(true_sd)), 20000, true_sd), 5, 80)
        assert fitted == pytest.approx(true_sd, rel=.06)


def test_fit_scale_recovers_a_per_team_multiplier():
    rng = random.Random(3)
    games = _games(rng, 20000, 1.3, bases=lambda: (rng.uniform(300, 900), rng.uniform(300, 900)))
    assert ss.fit_scale(games, .2, 5) == pytest.approx(1.3, rel=.06)


def test_win_probability_and_bucket():
    assert ss.win_probability((0., 1., 1., 1), 25) == pytest.approx(.5)
    # 25 points ahead with SD 25 per team: Phi(25 / (25 * sqrt 2)) = Phi(0.7071)
    assert ss.win_probability((25., 1., 1., 1), 25) == pytest.approx(.76025, abs=1e-4)
    # unequal bases: spread sqrt(100 + 300) = 20, so Phi(10 / 20) = Phi(0.5)
    assert ss.win_probability((10., 100., 300., 1), 1.) == pytest.approx(.69146, abs=1e-4)
    assert [ss.bucket(x) for x in (-2, 0, 4.99, 5, 12, 19.9, 24, 25, 40)] == [0, 0, 0, 1, 2, 3, 4, 5, 5]


def test_reliability_is_calibrated_at_the_true_sd_and_not_at_a_wrong_one():
    games = _games(random.Random(4), 30000, 25.)
    right = ss.reliability(games, 25.)
    assert sum(row["games"] for row in right) == len(games)
    assert all(row["mean_model_probability"] >= .5 for row in right)
    for row in right:
        assert row["favourite_won"] == pytest.approx(row["mean_model_probability"], abs=.025)
    top_wrong = ss.reliability(games, 12.)[-1]   # too narrow: overconfident favourites
    assert top_wrong["favourite_won"] < top_wrong["mean_model_probability"] - .03


def test_moments_and_variance_components():
    m = ss.moments(4, 10., 30.)   # values 1, 2, 3, 4
    assert m["mean"] == pytest.approx(2.5)
    assert m["sd"] == pytest.approx(math.sqrt(5 / 3))
    rng = random.Random(5)
    groups = []
    for _ in range(800):
        bias = rng.gauss(0, 3)
        xs = [bias + rng.gauss(0, 6) for _ in range(rng.randint(3, 12))]
        groups.append((len(xs), sum(xs), sum(x * x for x in xs)))
    parts = ss.variance_components(groups)
    assert parts["within_var"] == pytest.approx(36, rel=.06)
    assert parts["between_var"] == pytest.approx(9, rel=.25)
    assert parts["between_share"] == pytest.approx(9 / 45, abs=.04)


def test_implied_correlation():
    # four players, SD 5 each: independent team variance 100; rho 0.1 adds 0.1 * 12 * 25 = 30
    assert ss.implied_correlation(130., [25.] * 4) == pytest.approx(.1)
    assert ss.implied_correlation(100., [25.] * 4) == pytest.approx(0.)


def test_window_stats_detects_a_persistent_draw():
    rng = random.Random(6)
    independent = [[rng.gauss(0, 25) for _ in range(5)] for _ in range(8000)]
    w = ss.window_stats(independent)
    assert w["sum_variance_ratio"] == pytest.approx(1, abs=.06)
    assert abs(w["mean_offdiagonal_covariance"]) < 20
    persistent = []
    for _ in range(8000):
        u = rng.gauss(0, 10)
        persistent.append([u + rng.gauss(0, 22) for _ in range(5)])
    w = ss.window_stats(persistent)
    assert w["mean_offdiagonal_covariance"] == pytest.approx(100, abs=20)
    assert w["sum_variance_ratio"] == pytest.approx((25 * 100 + 5 * 484) / (5 * 584), rel=.06)


def test_interval_and_wilson():
    assert ss.interval(list(range(101))) == [2, 97]
    lo, hi = ss.wilson(50, 100)
    assert lo < .5 < hi and hi - lo == pytest.approx(.19, abs=.01)
