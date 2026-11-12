"""Projected slot value — the pure leaf `pick_projection` and its pricing step
in `pick_values.priced_pool_value`.

Spec: docs/plans/pick-value-projected-slot/design.md (§4 formula, §4.5 gates,
§5 worked example, §10 sabotage targets). Every price here comes off the
pinned DP fixture `fixtures/dp_values_picks_2026-08-06.csv` (conftest), so
the worked example is reproduced to the unit:

  * full strength by default (operator ruling 2026-11-11): top-3 3349.3,
    bubble 1702.6, contender 1028.8 at ANY week >= 3; certain 1.01 / 1.12 =
    4094.4 / 690.5; the market match (slots 1-4 / 9-12 within 10 % of DP's
    "2027 Early/Late 1st"); and the original ramp still available behind
    `season_scaling` = 1 (2817.2 / 1758.6 / 1325.5 at week 10 of 14);
  * zero-sum: the league total of next-draft firsts is unchanged;
  * every gate (status, model, draft season, weeks, age + end-of-season
    exception, weight, round);
  * the ORIGINAL roster prices a traded pick;
  * league sizes 8/10/12/14 through the percentile map;
  * a missing per-slot grid falls back to Early/Mid/Late, a rolled grid is
    used as is, and malformed runs price generic without raising;
  * the projected slot shown on the label: the rounded expected slot, set
    only on picks the projection priced.
"""
import json
import random
from datetime import datetime, timedelta, timezone

import pytest

import backend.data_loader as data_loader
import backend.pick_projection as pp
from backend import pick_values as pv
from backend.pick_values import priced_pool_value, projected_pick_slot, projected_slot_curve

VERSION = "model-under-test"
NOW = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)
FMT = "1qb_ppr"


def _result(rows, *, playoff, completed=9, future=5, season=2027, status="complete",
            model=VERSION):
    """A stored forecast `result_json` dict: `rows` is {roster_id: (pick_probabilities,
    playoff_probability)}."""
    return {"status": status, "model_version": model, "completed_weeks": completed,
            "playoff_spots": playoff, "config": {"draft_season": season},
            "teams": [{"roster_id": rid, "pick_probabilities": list(picks),
                       "playoff_probability": made, "weeks": [{}] * future}
                      for rid, (picks, made) in rows.items()]}


def _projection(result, *, weight=1.0, min_weeks=3, max_age_days=8, max_round=1,
                season_scaling=0.0, created_at=None):
    summary = pp.compact(result, run_id="run-1",
                         created_at=(created_at or NOW - timedelta(days=1)).isoformat())
    return pp.usable(summary, model_version=VERSION, now=NOW, weight=weight,
                     min_weeks=min_weeks, max_age_days=max_age_days, max_round=max_round,
                     season_scaling=season_scaling)


def _row(rid, season=2027, rnd=1, owner="someone"):
    return {"pick_id": f"L_{season}_{rnd}_{rid}", "season": season, "round": rnd,
            "original_roster_id": rid, "owner_user_id": owner, "pool_value": 2117.0}


def _worlds(n, playoff, seed, worlds=400):
    """A forecast built the way the simulation builds one: in each world a
    random order, the last `playoff` positions make the playoffs, the rest
    fill slots 1..n-playoff. Rows and columns sum to 1 by construction."""
    rng = random.Random(seed)
    strength = [rng.random() for _ in range(n)]
    picks = [[0] * (n - playoff) for _ in range(n)]
    made = [0] * n
    for _ in range(worlds):
        order = sorted(range(n), key=lambda i: strength[i] + rng.gauss(0, 0.3))
        for slot, team in enumerate(order[:n - playoff]):
            picks[team][slot] += 1
        for team in order[n - playoff:]:
            made[team] += 1
    return {str(t + 1): ([c / worlds for c in picks[t]], made[t] / worlds) for t in range(n)}


def _spread(nonplayoff, made):
    return nonplayoff, made


# The design's §5 illustrative distributions, 12 teams, 6 playoff spots.
TOP3 = ([.40, .30, .15, .07, .03, 0], .05)
BUBBLE = ([.02, .04, .08, .12, .14, .15], .45)
CONTENDER = ([0, 0, 0, 0, .01, .02], .97)
GENERIC = 1859.5            # today's 2027 1st: DP Mid 1st floored by D-161


def _example_projection(weight_weeks=(9, 5), weight=1.0, season_scaling=0.0):
    """The three §5 teams; the other nine fill the remaining column mass so
    the run is a valid league (columns sum to 1)."""
    rows = {"1": TOP3, "2": BUBBLE, "3": CONTENDER}
    used = [sum(r[0][k] for r in rows.values()) for k in range(6)]
    made_used = sum(r[1] for r in rows.values())
    for rid in range(4, 13):
        rows[str(rid)] = ([(1 - u) / 9 for u in used], (6 - made_used) / 9)
    completed, future = weight_weeks
    return _projection(_result(rows, playoff=6, completed=completed, future=future), weight=weight,
                       season_scaling=season_scaling)


# ── the worked example ──────────────────────────────────────────────────────

def test_generic_price_is_todays_2027_first():
    assert priced_pool_value(_row(1), scoring_format=FMT) == GENERIC


@pytest.mark.parametrize("weeks", [(3, 11), (9, 5), (14, 0)])
def test_full_strength_at_any_week_by_default(weeks):
    """Operator ruling 2026-11-11. Sabotage: default the scaling knob to the
    ramp → week 3 and week 10 drop toward generic."""
    proj = _example_projection(weight_weeks=weeks)
    assert proj.weight == 1.0
    assert priced_pool_value(_row(1), scoring_format=FMT, projection=proj) == 3349.3
    assert priced_pool_value(_row(2), scoring_format=FMT, projection=proj) == 1702.6
    assert priced_pool_value(_row(3), scoring_format=FMT, projection=proj) == 1028.8


def test_season_scaling_knob_restores_the_weeks_ramp():
    """`season_scaling` = 1 is the design's original ramp. Sabotage: ignore
    the knob → 3349.3."""
    proj = _example_projection(season_scaling=1.0)
    assert proj.weight == pytest.approx(9 / 14)
    assert priced_pool_value(_row(1), scoring_format=FMT, projection=proj) == 2817.2
    assert priced_pool_value(_row(2), scoring_format=FMT, projection=proj) == 1758.6
    assert priced_pool_value(_row(3), scoring_format=FMT, projection=proj) == 1325.5
    half = _example_projection(season_scaling=0.5)
    assert half.weight == pytest.approx(0.5 + 0.5 * 9 / 14)


def test_full_strength_matches_the_market_early_and_late_firsts():
    """Operator: "For top end of draft picks, we should match that curve."
    A pick certain to land in slots 1-4 (9-12) of a 12-team league prices
    within 10 % of DP's own "2027 Early 1st" ("Late 1st") in engine units.
    A future curve or floor change that breaks the match goes red."""
    from backend.trade_service import elo_to_value
    slot_map = data_loader.load_pick_slot_values(FMT)
    early, late = (elo_to_value(slot_map[f"2027 {t} 1st"]) for t in ("Early", "Late"))
    rows = {}
    for r in range(1, 13):
        third = (r - 1) // 4                              # 0: 1-4, 1: 5-8, 2: 9-12
        rows[str(r)] = ([0.25 if (k // 4) == third else 0.0 for k in range(11)]
                        if third < 2 else [0.0] * 8 + [0.25] * 3, 0.0 if third < 2 else 0.25)
    proj = _projection(_result(rows, playoff=1, completed=9, future=5))
    top = priced_pool_value(_row(1), scoring_format=FMT, projection=proj)
    bottom = priced_pool_value(_row(12), scoring_format=FMT, projection=proj)
    assert top == pytest.approx(early, rel=0.10), (top, early)
    assert bottom == pytest.approx(late, rel=0.10), (bottom, late)


def test_worked_example_point_masses():
    point = {str(r): ([1.0 if k == r - 1 else 0.0 for k in range(11)], 0.0 if r < 12 else 1.0)
             for r in range(1, 13)}
    full = _projection(_result(point, playoff=1, completed=14, future=0))
    assert priced_pool_value(_row(1), scoring_format=FMT, projection=full) == 4094.4
    assert priced_pool_value(_row(12), scoring_format=FMT, projection=full) == 690.5


def test_curve_is_the_value_space_grid():
    """Sabotage: average in Elo space → the uniform mean drops below 2210."""
    curve = projected_slot_curve(12, 2027, 1, FMT)
    assert [round(c, 1) for c in curve] == [4867.1, 4024.9, 3343.4, 2792.7, 2343.2, 1978.8,
                                            1680.3, 1435.5, 1234.9, 1069.8, 933.8, 820.8]
    assert sum(curve) / 12 == pytest.approx(2210.437, abs=1e-3)


# ── zero-sum and monotonicity ───────────────────────────────────────────────

@pytest.mark.parametrize("n,playoff,seed", [(8, 4, 1), (10, 6, 2), (12, 6, 3), (12, 4, 4), (14, 6, 5)])
def test_league_total_is_unchanged(n, playoff, seed):
    """Sabotage: normalise by the tercile (generic) instead of the curve mean."""
    proj = _projection(_result(_worlds(n, playoff, seed), playoff=playoff,
                               completed=4, future=10))
    total = sum(priced_pool_value(_row(r), scoring_format=FMT, projection=proj)
                for r in range(1, n + 1))
    assert total == pytest.approx(n * GENERIC, abs=0.05 * n)
    assert len({priced_pool_value(_row(r), scoring_format=FMT, projection=proj)
                for r in range(1, n + 1)}) > 1


def test_uninformative_forecast_prices_exactly_generic():
    n, playoff = 12, 6
    rows = {str(r): ([1 / n] * (n - playoff), playoff / n) for r in range(1, n + 1)}
    proj = _projection(_result(rows, playoff=playoff, completed=13, future=1))
    for r in range(1, n + 1):
        assert priced_pool_value(_row(r), scoring_format=FMT, projection=proj) == GENERIC


def test_earlier_is_never_cheaper():
    """Sabotage: reverse the curve index → an early pick prices low."""
    proj = _example_projection()
    vals = [priced_pool_value(_row(r), scoring_format=FMT, projection=proj) for r in (1, 2, 3)]
    assert vals[0] > vals[1] > vals[2]


def test_playoff_mass_is_spread_evenly_over_playoff_slots():
    """Sabotage: ignore playoff_probability → rows no longer sum to 1, run refused."""
    summary = pp.compact(_result({"1": ([0.5, 0.0], 0.5), "2": ([0.5, 0.5], 0.0),
                                  "3": ([0.0, 0.5], 0.5), "4": ([0.0, 0.0], 1.0)}, playoff=2),
                         run_id="r", created_at=NOW.isoformat())
    assert summary.dists["1"] == (0.5, 0.0, 0.25, 0.25)
    assert summary.dists["4"] == (0.0, 0.0, 0.5, 0.5)


# ── ownership ───────────────────────────────────────────────────────────────

def test_traded_pick_follows_the_original_roster():
    """Sabotage: key the distribution by the owner → the traded pick moves."""
    proj = _example_projection()
    mine = priced_pool_value(_row(1, owner="u1"), scoring_format=FMT, projection=proj)
    traded = {**_row(1, owner="u3"), "is_traded": 1, "owner_roster_id": 3}
    assert priced_pool_value(traded, scoring_format=FMT, projection=proj) == mine == 3349.3


def test_unknown_original_roster_prices_generic():
    proj = _example_projection()
    assert priced_pool_value(_row(99), scoring_format=FMT, projection=proj) == GENERIC
    assert priced_pool_value({**_row(1), "original_roster_id": None},
                             scoring_format=FMT, projection=proj) == GENERIC


# ── league sizes ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [8, 10, 12, 14])
def test_league_sizes_map_by_percentile(n):
    """Sabotage: literal slot lookup → a 14-team curve has no slots 13-14."""
    curve = projected_slot_curve(n, 2027, 1, FMT)
    grid = projected_slot_curve(12, 2027, 1, FMT)
    assert len(curve) == n
    assert curve[0] == grid[0] and curve[-1] == grid[-1]
    assert curve == sorted(curve, reverse=True)
    from backend.draft_board_service import _basis_slot
    assert curve == [grid[_basis_slot(k, n) - 1] for k in range(1, n + 1)]


# ── gates ───────────────────────────────────────────────────────────────────

def test_every_gate_returns_generic():
    rows = _worlds(12, 6, 7)
    good = _result(rows, playoff=6)
    assert _projection(good) is not None
    assert pp.compact({**good, "status": "incomplete_projections"}, run_id="r",
                      created_at=NOW.isoformat()) is None                      # incomplete
    assert _projection({**good, "model_version": "older"}) is None             # wrong model
    assert _projection(_result(rows, playoff=6, completed=2)) is None          # too few weeks
    assert _projection(good, min_weeks=10) is None
    assert _projection(good, created_at=NOW - timedelta(days=9)) is None       # too old
    assert _projection(good, weight=0) is None                                 # knob 0
    proj = _projection(good)
    assert priced_pool_value(_row(1, season=2028), scoring_format=FMT, projection=proj) == \
        priced_pool_value(_row(1, season=2028), scoring_format=FMT)            # other season
    assert priced_pool_value(_row(1, rnd=2), scoring_format=FMT, projection=proj) == \
        priced_pool_value(_row(1, rnd=2), scoring_format=FMT)                  # round 2
    wrong_season = _projection(_result(rows, playoff=6, season=2028))
    assert priced_pool_value(_row(1), scoring_format=FMT, projection=wrong_season) == GENERIC


def test_near_season_end_run_stands_past_the_age_window():
    """The last in-season run (≤ 1 future week) is kept through the off-season.
    Sabotage: drop the exception → None."""
    rows = _worlds(12, 6, 8)
    old = NOW - timedelta(days=60)
    assert _projection(_result(rows, playoff=6, completed=13, future=1), created_at=old) is not None
    assert _projection(_result(rows, playoff=6, completed=14, future=0), created_at=old) is not None
    assert _projection(_result(rows, playoff=6, completed=12, future=2), created_at=old) is None


def test_max_round_knob_extends_to_round_two():
    proj = _projection(_result(_worlds(12, 6, 9), playoff=6), max_round=2)
    assert pp.covers(proj, 2027, 2) and not pp.covers(proj, 2027, 3)


def test_tier_ladder_mode_ignores_the_projection():
    """Bake-off arm A pin. Sabotage: apply the step before the mode check."""
    proj = _example_projection()
    assert priced_pool_value(_row(1), scoring_format=FMT, mode="tier_ladder",
                             projection=proj) == 2117.0


def test_weight_zero_is_byte_identical_to_no_projection():
    rows = _worlds(12, 6, 10)
    assert _projection(_result(rows, playoff=6), weight=0.0) is None
    for r in range(1, 13):
        assert priced_pool_value(_row(r), scoring_format=FMT, projection=None) == \
            priced_pool_value(_row(r), scoring_format=FMT)


def test_key_moves_with_every_priced_input():
    rows = _worlds(12, 6, 11)
    base = _projection(_result(rows, playoff=6)).key
    assert base.startswith(pp.KEY_PREFIX) and "run-1" not in base
    other_run = pp.usable(pp.compact(_result(rows, playoff=6), run_id="run-2",
                                     created_at=(NOW - timedelta(days=1)).isoformat()),
                          model_version=VERSION, now=NOW, weight=1, min_weeks=3,
                          max_age_days=8, max_round=1)
    assert other_run.key != base                      # a new weekly run
    assert _projection(_result(rows, playoff=6, completed=10, future=4)).key == base  # same price
    assert (_projection(_result(rows, playoff=6, completed=10, future=4), season_scaling=1).key
            != _projection(_result(rows, playoff=6), season_scaling=1).key)
    assert _projection(_result(rows, playoff=6), weight=0.5).key != base
    assert _projection(_result(rows, playoff=6), season_scaling=1.0).key != base
    assert _projection(_result(rows, playoff=6), max_round=2).key != base
    assert _projection(_result(rows, playoff=6)).key == base


# ── point mass for a resolved slot without a DP row ─────────────────────────

def test_resolved_slot_without_dp_row_is_a_point_mass():
    """D-090 resolves 2027 slot 3 but DP prices no 2027 slots: G × c[3]/mean(c)
    at full weight, rather than the generic round curve."""
    proj = _example_projection()
    curve = projected_slot_curve(12, 2027, 1, FMT)
    expected = round(GENERIC * curve[2] / (sum(curve) / 12), 1)
    assert priced_pool_value(_row(5), scoring_format=FMT, slot=3, projection=proj) == expected
    assert priced_pool_value(_row(5), scoring_format=FMT, slot=3) == GENERIC


# ── DP shapes ───────────────────────────────────────────────────────────────

def _map_without(pred):
    full = data_loader.load_pick_slot_values(FMT)
    return {k: v for k, v in full.items() if not pred(k)}


def test_missing_grid_falls_back_to_early_mid_late(monkeypatch):
    """Sabotage: return None when the grid is missing → every pick generic."""
    slim = _map_without(lambda label: " Pick " in label)
    monkeypatch.setattr(data_loader, "load_pick_slot_values", lambda fmt="1qb_ppr": slim)
    curve = projected_slot_curve(12, 2027, 1, FMT)
    assert len(set(curve)) == 3 and curve[:4] == [curve[0]] * 4 and curve[8:] == [curve[8]] * 4
    proj = _example_projection()
    generic = priced_pool_value(_row(1), scoring_format=FMT)
    assert priced_pool_value(_row(1), scoring_format=FMT, projection=proj) > generic
    assert priced_pool_value(_row(3), scoring_format=FMT, projection=proj) < generic


def test_no_grid_and_no_rungs_prices_generic(monkeypatch):
    slim = _map_without(lambda label: " Pick " in label or " Early " in label
                        or " Late " in label)
    monkeypatch.setattr(data_loader, "load_pick_slot_values", lambda fmt="1qb_ppr": slim)
    assert projected_slot_curve(12, 2027, 1, FMT) is None
    proj = _example_projection()
    assert priced_pool_value(_row(1), scoring_format=FMT, projection=proj) == \
        priced_pool_value(_row(1), scoring_format=FMT)


def test_grid_rolled_to_the_next_class_is_used(monkeypatch):
    """DP rolls its per-slot grid to 2027: the anchor moves, the 2027 grid is
    the curve, G is the 2027 tercile, and zero-sum still holds."""
    full = data_loader.load_pick_slot_values(FMT)
    rolled = {k.replace("2026 Pick", "2027 Pick"): v for k, v in full.items()
              if not k.startswith("2027 Pick")}
    monkeypatch.setattr(data_loader, "load_pick_slot_values", lambda fmt="1qb_ppr": rolled)
    assert pv.market_anchor_season(FMT) == 2027
    proj = _projection(_result(_worlds(12, 6, 12), playoff=6))
    generic = priced_pool_value(_row(1), scoring_format=FMT)
    total = sum(priced_pool_value(_row(r), scoring_format=FMT, projection=proj) for r in range(1, 13))
    assert total == pytest.approx(12 * generic, abs=0.6)


def test_dp_unreachable_prices_the_stored_ladder(monkeypatch):
    monkeypatch.setattr(data_loader, "load_pick_slot_values", lambda fmt="1qb_ppr": {})
    proj = _example_projection()
    assert priced_pool_value(_row(1), scoring_format=FMT, projection=proj) == 2117.0


# ── malformed runs ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("mutate", [
    lambda r: "not json {",
    lambda r: None,
    lambda r: {**r, "teams": None},
    lambda r: {**r, "config": {}},
    lambda r: {**r, "playoff_spots": 0},
    lambda r: {**r, "teams": r["teams"][:-1]},                          # columns no longer sum
    lambda r: {**r, "teams": [{**t, "pick_probabilities": ["x"] * 6} for t in r["teams"]]},
    lambda r: {**r, "teams": [{**t, "pick_probabilities": t["pick_probabilities"][:3]} for t in r["teams"]]},
    lambda r: {**r, "teams": [{**t, "playoff_probability": 0.9} for t in r["teams"]]},
    lambda r: {**r, "teams": [{**t, "roster_id": 1} for t in r["teams"]]},
    lambda r: {**r, "teams": [{k: v for k, v in t.items() if k != "weeks"} for t in r["teams"]]},
    lambda r: {**r, "teams": [{**t, "playoff_probability": float("nan")} for t in r["teams"]]},
])
def test_malformed_runs_are_refused_never_raised(mutate):
    bad = mutate(_result(_worlds(12, 6, 13), playoff=6))
    assert pp.compact(bad, run_id="r", created_at=NOW.isoformat()) is None
    assert pp.compact(json.dumps(bad) if isinstance(bad, dict) else bad,
                      run_id="r", created_at=NOW.isoformat()) is None


def test_rows_that_sum_but_columns_that_do_not_are_refused():
    """Two teams both certain of slot 1: every row sums to 1, but the league is
    not one world (slot 1 twice, slot 2 never), so zero-sum would break.
    Sabotage: drop the column-sum check → the run is accepted."""
    rows = {"1": ([1.0, 0.0], 0.0), "2": ([1.0, 0.0], 0.0),
            "3": ([0.0, 0.0], 1.0), "4": ([0.0, 0.0], 1.0)}
    assert pp.compact(_result(rows, playoff=2), run_id="r", created_at=NOW.isoformat()) is None


def test_bad_created_at_fails_the_age_gate():
    summary = pp.compact(_result(_worlds(12, 6, 14), playoff=6), run_id="r", created_at="garbage")
    assert pp.usable(summary, model_version=VERSION, now=NOW, weight=1, min_weeks=3,
                     max_age_days=8, max_round=1) is None


# ── the projected slot shown on the label ───────────────────────────────────

def test_projected_slot_is_the_rounded_expected_slot():
    """Sabotage: use the modal slot → the top-3 team shows 1.01, not 1.02."""
    proj = _example_projection()
    assert projected_pick_slot(_row(1), proj, FMT) == 2          # E = 2.36
    assert projected_pick_slot(_row(2), proj, FMT) == 7          # E = 6.70
    assert projected_pick_slot(_row(3), proj, FMT) == 9          # E = 9.39


def test_playoff_bound_team_shows_the_midpoint_of_the_playoff_slots():
    """Playoff mass is spread evenly, so a certain playoff team's expected slot
    is the playoff slots' midpoint: 12 teams / 6 spots → (7+12)/2 = 9.5 → 10."""
    rows = {str(r): ([1.0 if k == r - 1 else 0.0 for k in range(6)], 0.0) for r in range(1, 7)}
    rows.update({str(r): ([0.0] * 6, 1.0) for r in range(7, 13)})
    proj = _projection(_result(rows, playoff=6))
    assert pp.expected_slot(proj.dists["9"]) == pytest.approx(9.5)
    assert projected_pick_slot(_row(9), proj, FMT) == 10
    assert projected_pick_slot(_row(1), proj, FMT) == 1


def test_projected_slot_only_on_picks_the_projection_priced(monkeypatch):
    proj = _example_projection()
    assert projected_pick_slot(_row(1, season=2028), proj, FMT) is None
    assert projected_pick_slot(_row(1, rnd=2), proj, FMT) is None
    assert projected_pick_slot(_row(99), proj, FMT) is None
    assert projected_pick_slot(_row(1), None, FMT) is None
    monkeypatch.setattr(data_loader, "load_pick_slot_values", lambda fmt="1qb_ppr": {})
    assert projected_pick_slot(_row(1), proj, FMT) is None       # DP down: priced generic


@pytest.mark.parametrize("n", [8, 10, 12, 14])
def test_projected_slot_is_clamped_to_the_league(n):
    worlds = _worlds(n, n // 2, 20 + n)
    proj = _projection(_result(worlds, playoff=n // 2))
    slots = [projected_pick_slot(_row(r), proj, FMT) for r in range(1, n + 1)]
    assert all(1 <= s <= n for s in slots)
    assert pp.projected_slot((0.0,) * (n - 1) + (1.0,)) == n
    assert pp.projected_slot((1.0,) + (0.0,) * (n - 1)) == 1
