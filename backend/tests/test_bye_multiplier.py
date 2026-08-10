"""Tests for backend/outlook/bye_multiplier.py — the EVALUATED (not shipped)
per-week bye-week mu multiplier, feedback #169 operator directive 2026-08-09.

Covers:
  - weekly_value_fraction_on_bye: correct fraction-of-starting-lineup-VALUE
    math, using the same greedy lineup selection as the shipped strength
    provider.
  - mu_multipliers: linear scale + zero floor.
  - Both-sides application through simulator.simulate()'s weekly_mu_multiplier
    seam — a MUTUAL bye (both sides equally affected) cancels out in the
    head-to-head win probability; a ONE-SIDED bye shifts it. This is the
    operator's explicit "both sides" requirement, verified directly rather
    than just asserted.
  - simulate() is byte-identical to before this change when
    weekly_mu_multiplier is omitted (the live path never passes it).

All offline — the nflverse fetch is stubbed via `_byes_opener`/`_opener`
(same injection pattern as bye_weeks tests).
"""

from __future__ import annotations

import pytest

import backend.outlook.bye_weeks as bw
from backend.outlook.bye_multiplier import (
    mu_multipliers,
    simulate_with_bye_multiplier,
    weekly_value_fraction_on_bye,
)
from backend.outlook.league_state import LeagueState, TeamState, compute_num_byes
from backend.outlook.playoff_format import StandardFormat
from backend.outlook.simulator import simulate
from backend.outlook.strength import TeamStrength

_SCHEDULE_CSV = (
    "season,game_type,week,home_team,away_team\n"
    "2030,REG,1,AAA,CCC\n"
    "2030,REG,2,BBB,CCC\n"
    "2030,REG,3,AAA,BBB\n"
)
# Derived byes for this synthetic schedule: BBB misses wk1, AAA misses wk2,
# CCC misses wk3.


@pytest.fixture(autouse=True)
def _clean_bye_cache():
    bw.reset_cache()
    yield
    bw.reset_cache()


def _byes_opener(request, timeout=None):
    class _R:
        def read(self):
            return _SCHEDULE_CSV.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    return _R()


def _round_robin(rids, weeks):
    ids = list(rids)
    if len(ids) % 2:
        ids.append(-1)
    n = len(ids)
    rounds, arr = [], ids[:]
    for _ in range(n - 1):
        rounds.append([(arr[i], arr[n - 1 - i]) for i in range(n // 2)
                       if arr[i] != -1 and arr[n - 1 - i] != -1])
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return {w: rounds[(w - 1) % len(rounds)] for w in range(1, weeks + 1)}


def _state(n_teams=2, weeks=3, player_ids_by_roster=None, roster_slots=None):
    rids = list(range(1, n_teams + 1))
    teams = []
    for rid in rids:
        teams.append(TeamState(
            roster_id=rid, user_id=f"u{rid}", username=f"user{rid}",
            display_name=f"Team {rid}",
            player_ids=(player_ids_by_roster or {}).get(rid, []),
        ))
    return LeagueState(
        league_id="LG-BYE-TEST", platform="sleeper",
        regular_season_weeks=weeks, playoff_slots=2,
        num_byes=compute_num_byes(2), roster_slots=roster_slots or [],
        teams=teams, schedule=_round_robin(rids, weeks), completed_weeks=0,
    )


# ---------------------------------------------------------------------------
# weekly_value_fraction_on_bye
# ---------------------------------------------------------------------------

def test_weekly_value_fraction_on_bye_basic():
    state = _state(
        n_teams=1,
        player_ids_by_roster={1: ["p1", "p2"]},
        roster_slots=["QB", "RB"],
    )
    player_value = {"p1": 100.0, "p2": 50.0}
    player_pos = {"p1": "QB", "p2": "RB"}
    player_team = {"p1": "AAA", "p2": "BBB"}

    frac = weekly_value_fraction_on_bye(
        state, player_value, player_pos, player_team, season="2030",
        weeks=[1, 2, 3], _byes_opener=_byes_opener,
    )
    # BBB (p2, value 50) is on bye week 1 -> 50/150
    assert frac[1][1] == pytest.approx(50.0 / 150.0)
    # AAA (p1, value 100) is on bye week 2 -> 100/150
    assert frac[2][1] == pytest.approx(100.0 / 150.0)
    # CCC's bye (week 3) touches no rostered player -> 0
    assert frac[3][1] == pytest.approx(0.0)


def test_weekly_value_fraction_on_bye_skips_teams_with_no_roster_slots():
    state = _state(
        n_teams=1, player_ids_by_roster={1: ["p1"]}, roster_slots=[],
    )
    frac = weekly_value_fraction_on_bye(
        state, {"p1": 100.0}, {"p1": "QB"}, {"p1": "AAA"}, season="2030",
        weeks=[1, 2, 3], _byes_opener=_byes_opener,
    )
    # No roster_slots -> select_starting_lineup returns [] -> the team is
    # skipped entirely rather than reported at fraction 0.0 (callers must
    # treat a missing entry as "no-op", not "confirmed no bye impact").
    assert frac == {}


# ---------------------------------------------------------------------------
# mu_multipliers
# ---------------------------------------------------------------------------

def test_mu_multipliers_default_scale_is_linear_haircut():
    frac = {1: {10: 1 / 3.0}, 2: {10: 2 / 3.0}}
    mult = mu_multipliers(frac, cfg={})
    assert mult[1][10] == pytest.approx(2 / 3.0)
    assert mult[2][10] == pytest.approx(1 / 3.0)


def test_mu_multipliers_respects_scale_knob():
    frac = {1: {10: 0.4}}
    mult = mu_multipliers(frac, cfg={"outlook_bye_multiplier_scale": 0.5})
    assert mult[1][10] == pytest.approx(1.0 - 0.5 * 0.4)


def test_mu_multipliers_floors_at_zero():
    frac = {1: {10: 0.9}}
    mult = mu_multipliers(frac, cfg={"outlook_bye_multiplier_scale": 2.0})
    assert mult[1][10] == 0.0


# ---------------------------------------------------------------------------
# Both-sides application via simulator.simulate()
# ---------------------------------------------------------------------------

def test_mutual_bye_cancels_head_to_head():
    """Both teams equally bye-heavy in the (only) remaining week -> the
    head-to-head win probability should be unchanged from a no-bye baseline,
    within Monte Carlo tolerance. This is the operator's 'both sides' claim,
    checked directly rather than asserted from the code."""
    st = _state(n_teams=2, weeks=1)
    rids = [1, 2]
    strengths = {rid: TeamStrength(rid, mu=110.0, sigma=25.0) for rid in rids}
    fmt = StandardFormat(st.playoff_slots, st.num_byes)

    baseline = simulate(st, strengths, fmt, n_sims=6000, config_seed=42)
    equal_mult = {1: {1: 0.5, 2: 0.5}}
    with_mult = simulate(st, strengths, fmt, n_sims=6000, config_seed=42,
                         weekly_mu_multiplier=equal_mult)

    # Both sides shrink identically -> the win split shouldn't meaningfully
    # move even though absolute scores drop.
    base_wins_1 = baseline.projected_wins(1)
    mult_wins_1 = with_mult.projected_wins(1)
    assert abs(base_wins_1 - mult_wins_1) < 0.06


def test_one_sided_bye_shifts_head_to_head():
    """Only team 1 loses mu that week -> team 2 should win more often than
    the symmetric baseline."""
    st = _state(n_teams=2, weeks=1)
    rids = [1, 2]
    strengths = {rid: TeamStrength(rid, mu=110.0, sigma=25.0) for rid in rids}
    fmt = StandardFormat(st.playoff_slots, st.num_byes)

    baseline = simulate(st, strengths, fmt, n_sims=6000, config_seed=42)
    one_sided = {1: {1: 0.5}}  # team 2 absent from the map -> multiplier 1.0
    with_mult = simulate(st, strengths, fmt, n_sims=6000, config_seed=42,
                         weekly_mu_multiplier=one_sided)

    assert with_mult.projected_wins(2) > baseline.projected_wins(2)
    assert with_mult.projected_wins(1) < baseline.projected_wins(1)


def test_simulate_is_unchanged_when_multiplier_omitted():
    """The live pipeline never passes weekly_mu_multiplier — confirm that
    leaving it out (or passing None/{}) reproduces byte-identical results,
    i.e. this seam cannot silently perturb the shipped engine."""
    st = _state(n_teams=4, weeks=5)
    rids = [t.roster_id for t in st.teams]
    strengths = {rid: TeamStrength(rid, mu=110.0, sigma=25.0) for rid in rids}
    fmt = StandardFormat(st.playoff_slots, st.num_byes)

    a = simulate(st, strengths, fmt, n_sims=2000, config_seed=5)
    b = simulate(st, strengths, fmt, n_sims=2000, config_seed=5,
                 weekly_mu_multiplier=None)
    c = simulate(st, strengths, fmt, n_sims=2000, config_seed=5,
                 weekly_mu_multiplier={})
    assert a.titles == b.titles == c.titles
    assert a.made_playoffs == b.made_playoffs == c.made_playoffs
    assert a.sum_wins == b.sum_wins == c.sum_wins


def test_run_outlook_pipeline_ignores_bye_multiplier_model_config_keys():
    """The public pipeline entry point (`run_outlook`, what `server.py`'s
    `/api/league/outlook` route actually calls) must be byte-identical
    whether or not `outlook_bye_multiplier_enabled`/`outlook_bye_multiplier_scale`
    are present in `model_cfg` — `pipeline.py` does not import
    `bye_multiplier` at all, so these knobs are inert until someone wires
    them in. This pins that fact at the PUBLIC entry point, not just at the
    low-level `simulate()` seam covered above."""
    import json

    from backend.outlook.pipeline import run_outlook

    st = _state(n_teams=6, weeks=8)
    for t in st.teams:
        t.player_ids = []
    st.roster_slots = []

    cfg_without = {"outlook_sim_count": 1500.0, "outlook_seed": 3.0}
    cfg_with_defaults = {
        **cfg_without,
        "outlook_bye_multiplier_enabled": 0.0,
        "outlook_bye_multiplier_scale": 1.0,
    }
    cfg_with_nonzero = {
        **cfg_without,
        "outlook_bye_multiplier_enabled": 1.0,
        "outlook_bye_multiplier_scale": 0.5,
    }

    payload_without = run_outlook(st, player_value={}, player_pos={},
                                  model_cfg=cfg_without, basis="consensus")
    payload_with_defaults = run_outlook(st, player_value={}, player_pos={},
                                        model_cfg=cfg_with_defaults, basis="consensus")
    payload_with_nonzero = run_outlook(st, player_value={}, player_pos={},
                                       model_cfg=cfg_with_nonzero, basis="consensus")

    assert json.dumps(payload_without, sort_keys=True) == \
        json.dumps(payload_with_defaults, sort_keys=True)
    # Even a NON-zero value for these keys changes nothing today, because
    # pipeline.py never reads them — this is the concrete evidence that
    # "not wired into the live path" holds, not just that the default is 0.
    assert json.dumps(payload_without, sort_keys=True) == \
        json.dumps(payload_with_nonzero, sort_keys=True)


# ---------------------------------------------------------------------------
# simulate_with_bye_multiplier — end-to-end entry point
# ---------------------------------------------------------------------------

def test_simulate_with_bye_multiplier_runs_end_to_end():
    state = _state(
        n_teams=2, weeks=3,
        player_ids_by_roster={1: ["p1"], 2: ["p2"]},
        roster_slots=["QB"],
    )
    player_value = {"p1": 100.0, "p2": 100.0}
    player_pos = {"p1": "QB", "p2": "QB"}
    player_team = {"p1": "AAA", "p2": "BBB"}  # different byes: wk2 vs wk1
    strengths = {1: TeamStrength(1, 110.0, 25.0), 2: TeamStrength(2, 110.0, 25.0)}
    fmt = StandardFormat(state.playoff_slots, state.num_byes)

    res = simulate_with_bye_multiplier(
        state, strengths, fmt,
        player_value=player_value, player_pos=player_pos,
        player_team=player_team, season="2030", cfg={},
        n_sims=2000, config_seed=1, _byes_opener=_byes_opener,
    )
    assert res.n_sims == 2000
    assert abs(res.playoff_pct(1) + res.playoff_pct(2) - state.playoff_slots) < 1e-9
