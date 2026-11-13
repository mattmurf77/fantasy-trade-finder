"""Pure pieces of the Max PF moves leave-one-out backtest
(docs/plans/league-projections/max-pf-trade-away/backtest/). Hand-built rosters
with known answers; no network, no database, no cache.

- hindsight drops on a flex chain, an only tight end (the slot is lost) and a
  negative-scoring only kicker (a wrong-sign drop is possible);
- the exhaustive dynamic programme agrees with `core.optimize` (the solver check
  the backtest runs on real data);
- the simple rule, both readings, against the exact re-solve;
- one synthetic league-week through `league_week`: the predicted drop is the
  product's own `maxpf_moves.resolve` on the rebuilt snapshot, bye and
  unpriced players are classified, and the realised drop uses actual points;
- buckets, calibration table, rank correlation, list agreement, league bootstrap.
"""
from __future__ import annotations

import importlib.util
import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[2] / "docs/plans/league-projections/max-pf-trade-away/backtest"
sys.path.insert(0, str(_DIR))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bs = _load("backtest_stats")
bt = _load("backtest")

SLOTS = ["QB", "RB", "WR", "FLEX"]
POSITIONS = {"qb1": ["QB"], "qb2": ["QB"], "rb1": ["RB"], "rb2": ["RB"], "wr1": ["WR"], "wr2": ["WR"]}
POINTS = {"qb1": 20, "qb2": 15, "rb1": 12, "rb2": 9, "wr1": 10, "wr2": 8}


def _players(points=POINTS, positions=POSITIONS):
    return [{"player_id": pid, "positions": positions[pid], "points": Decimal(v)} for pid, v in points.items()]


def test_hindsight_drops_follow_the_flex_chain():
    total, starters, drops, gaps = bt.hindsight_drops(SLOTS, _players())
    assert total == 51  # qb1 20 + rb1 12 + wr1 10 + rb2 9 in the flex
    assert starters == {"qb1": "QB", "rb1": "RB", "wr1": "WR", "rb2": "FLEX"}
    # rb1 out: rb2 moves to RB, wr2 takes the flex -> 47.
    assert drops == {"qb1": 5, "qb2": 0, "rb1": 4, "rb2": 1, "wr1": 2, "wr2": 0}
    assert not any(gaps.values())


def test_only_tight_end_loses_the_slot_and_a_negative_kicker_gives_a_wrong_sign():
    slots = ["TE", "K"]
    players = [{"player_id": "te", "positions": ["TE"], "points": Decimal("7.5")},
               {"player_id": "k", "positions": ["K"], "points": Decimal("-2")}]
    total, _starters, drops, gaps = bt.hindsight_drops(slots, players)
    assert total == Decimal("5.5")
    assert drops == {"te": Decimal("7.5"), "k": Decimal("-2")}
    assert gaps == {"te": True, "k": True}


def test_exhaustive_check_agrees_with_the_optimizer():
    rng = random.Random(4)
    slots = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"]
    pos = [["QB"], ["RB"], ["WR"], ["TE"], ["RB", "WR"]]
    for _ in range(40):
        players = [{"player_id": str(i), "positions": rng.choice(pos), "points": Decimal(rng.randint(-20, 300)) / 10}
                   for i in range(rng.randint(3, 16))]
        total, _s, drops, _g = bt.hindsight_drops(slots, players)
        assert bt.exhaustive_best(slots, [(p["positions"], p["points"]) for p in players]) == total
        for p in players:
            rest = [(q["positions"], q["points"]) for q in players if q is not p]
            assert bt.exhaustive_best(slots, rest) == total - drops[p["player_id"]]


def test_simple_rule_both_readings():
    starters = {"qb1": "QB", "rb1": "RB", "wr1": "WR", "rb2": "FLEX"}
    rules = bt.simple_rules(starters, {k: Decimal(v) for k, v in POINTS.items()}, POSITIONS)
    # (same position, slot eligible). No bench RB: both RB starters "lose" everything
    # under the same-position reading; the flex RB is covered by wr2 under the other.
    assert rules["qb1"] == (5, 5)
    assert rules["rb1"] == (12, 12)   # exact re-solve: 4 (the chain)
    assert rules["rb2"] == (9, 1)     # exact: 1
    assert rules["wr1"] == (2, 2)
    assert rules["qb2"] == (0, 0) and rules["wr2"] == (0, 0)


def _league_week():
    league = {"roster_positions": ["QB", "RB", "FLEX", "BN", "BN", "BN"],
              "scoring_settings": {"rush_yd": 0.1, "pass_yd": 0.04}}
    metadata = {"q": {"fantasy_positions": ["QB"], "position": "QB", "team": "AAA"},
                "r1": {"fantasy_positions": ["RB"], "position": "RB", "team": "AAA"},
                "r2": {"fantasy_positions": ["RB"], "position": "RB", "team": "AAA"},
                "r3": {"fantasy_positions": ["RB"], "position": "RB", "team": "AAA"},
                "bye": {"fantasy_positions": ["RB"], "position": "RB", "team": "BBB"},
                "hurt": {"fantasy_positions": ["RB"], "position": "RB", "team": "AAA"}}
    payload = [{"player_id": "q", "team": "AAA", "stats": {"gp": 1, "pass_yd": 250}},
               {"player_id": "r1", "team": "AAA", "stats": {"gp": 1, "rush_yd": 100}},
               {"player_id": "r2", "team": "AAA", "stats": {"gp": 1, "rush_yd": 80}},
               {"player_id": "r3", "team": "AAA", "stats": {"gp": 1, "rush_yd": 50}},
               {"player_id": "hurt", "team": "AAA", "stats": {"adp_dd_ppr": 999}}]
    matchups = [{"roster_id": 1, "matchup_id": 1, "points": 30.0, "custom_points": None,
                 "players": ["q", "r1", "r2", "r3", "bye", "hurt"], "starters": ["q", "r1", "r2"],
                 "starters_points": [10.0, 4.0, 16.0],
                 "players_points": {"q": 10.0, "r1": 4.0, "r2": 16.0, "r3": 12.0, "bye": 0, "hurt": 0}},
                {"roster_id": 2, "matchup_id": 1, "points": 0.0, "custom_points": None,
                 "players": [], "starters": [], "starters_points": [], "players_points": {}}]
    return bt.league_week(league, matchups, payload, metadata, 3, 0, True)


def test_league_week_runs_the_product_resolve_and_actual_points():
    rows, teams, _ = _league_week()
    by = {r["player"]: r for r in rows if r["roster"] == 1}
    # Projected: q 10, r1 10, r2 8, r3 5 -> lineup q + r1 + r2 = 28.
    assert {p: by[p]["pred"] for p in ("q", "r1", "r2", "r3")} == {"q": 10, "r1": 5, "r2": 3, "r3": 0}
    assert by["bye"]["status"] == "bye" and by["bye"]["pred"] == 0
    assert by["hurt"]["status"] == "unknown"
    # Actual: q 10, r2 16, r3 12 start (38); r1 (4) is benched in hindsight; r2 out -> r3 at RB, r1 at flex (26); r3 out -> r1 at flex (30).
    assert {p: by[p]["real"] for p in ("q", "r1", "r2", "r3")} == {"q": 10, "r1": 0, "r2": 12, "r3": 8}
    assert by["r1"]["projected_starter"] and not by["r1"]["realised_starter"]
    team = next(t for t in teams if t["roster"] == 1)
    assert team["projected_best"] == 28 and team["realised_best"] == 38
    assert team["projected_ok"] and team["realised_ok"]
    assert by["r1"]["rule_pos"] == 5 and by["r2"]["rule_slot"] == 3


def test_buckets_and_calibration_table():
    edges = (2, 5)
    assert [bs.bucket_of(v, edges) for v in (-1, 0, 0.1, 2, 2.01, 5, 9)] == [0, 0, 1, 1, 2, 2, 3]
    assert bs.bucket_labels(edges) == ["0", "0-2", "2-5", ">5"]
    table = bs.calibration_table([(0, 0), (0, 3), (1, 2), (4, -1), (6, 6)], edges)
    assert [c["n"] for c in table] == [2, 1, 1, 1]
    assert table[0]["mean_realised"] == 1.5 and table[0]["share_realised_zero_or_less"] == .5
    assert table[2]["share_realised_negative"] == 1


def test_summary_and_rank_correlation():
    s = bs.summary([(1, 2), (2, 4), (3, 6)])
    assert s["bias"] == -2 and s["mae"] == 2 and s["realised_over_predicted"] == 2
    assert s["spearman"] == pytest.approx(1)
    assert bs.rankdata([5, 1, 5, 3]) == [3.5, 1, 3.5, 2]
    assert bs.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1)
    assert bs.spearman([0, 0, 0], [1, 2, 3]) is None


def test_list_agreement():
    pred = {"a": 9, "b": 8, "c": 7, "d": 1, "e": 0, "f": 0}
    real = {"a": 1, "b": 9, "c": 8, "d": 7, "e": 0, "f": 3}
    out = bs.list_agreement(pred, real, k=3)
    assert out["overlap"] == 2                 # {a,b,c} vs {b,c,d}
    assert out["first_in_real_top3"] is False  # a is 5th in reality
    assert bs.top_k({"x": 1, "w": 1, "y": 2}, 2) == ["y", "w"]  # ties by id


def test_bootstrap_resamples_whole_leagues():
    groups = [[{"v": 1}] * 10, [{"v": 3}] * 10]
    out = bs.bootstrap(groups, lambda rows: {"m": sum(r["v"] for r in rows) / len(rows)}, reps=400, seed=1)
    assert out["m"]["value"] == 2
    # With two leagues the only possible means are 1, 2 and 3.
    assert out["m"]["ci95"] == [1, 3]
