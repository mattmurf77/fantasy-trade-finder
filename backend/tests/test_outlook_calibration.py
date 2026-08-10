"""Permanent internal-invariant tests for the #169 outlook odds engine.

Companion to test_outlook_odds.py (which covers per-phase contracts and the
endpoint). This file pins the *statistical* properties the Monte-Carlo engine
must hold regardless of how the strength source is swapped, plus the
correctness of the as-of rewind the offline backtest depends on:

  1. sum of playoff odds == playoff slot count (exactly, by construction)
  2. sum of title odds == 1
  3. odds are monotone in team strength (strictly ordered league)
  4. a symmetric league gives uniform odds within Monte-Carlo tolerance
  5. estimates converge as N grows (spread across seeds shrinks ~1/sqrt(N))
  6. deterministic under a fixed seed — end-to-end through run_outlook()

Plus a fixture-backed guard that the shipped engine, run as-of mid-season on
the operator's real captured leagues, beats the climatology baseline on
playoff Brier. Fixtures live in fixtures/outlook-calibration/ (captured
2026-08-09); no test here touches the network.

Full method + verdict: docs/feedback/items/169-outlook-league-summary/
calibration-report-2026-08-09.md
"""

from __future__ import annotations

import os
import statistics
import sys

import pytest

from backend.outlook.league_state import LeagueState, TeamState, compute_num_byes
from backend.outlook.pipeline import run_outlook
from backend.outlook.playoff_format import StandardFormat
from backend.outlook.simulator import simulate
from backend.outlook.strength import TeamStrength

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _league(n_teams=10, weeks=13, playoff_slots=6):
    rids = list(range(1, n_teams + 1))
    teams = [TeamState(roster_id=r, user_id="u%d" % r, username="user%d" % r,
                       display_name="Team %d" % r) for r in rids]
    return LeagueState(
        league_id="LG-INV", platform="sleeper", regular_season_weeks=weeks,
        playoff_slots=playoff_slots, num_byes=compute_num_byes(playoff_slots),
        roster_slots=[], teams=teams, schedule=_round_robin(rids, weeks),
        completed_weeks=0, weekly_scores={})


def _run(state, strengths, n_sims=4000, config_seed=0):
    fmt = StandardFormat(state.playoff_slots, state.num_byes)
    return simulate(state, strengths, fmt, n_sims=n_sims, config_seed=config_seed)


# ---------------------------------------------------------------------------
# 1 + 2 — conservation laws
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_teams,slots", [(8, 4), (10, 6), (12, 6), (14, 8)])
def test_playoff_odds_sum_to_slot_count(n_teams, slots):
    st = _league(n_teams=n_teams, playoff_slots=slots)
    rids = [t.roster_id for t in st.teams]
    strengths = {r: TeamStrength(r, 100.0 + r, 22.0) for r in rids}
    res = _run(st, strengths, n_sims=1200)
    assert sum(res.playoff_pct(r) for r in rids) == pytest.approx(slots, abs=1e-9)
    assert sum(res.bye_pct(r) for r in rids) == pytest.approx(st.num_byes, abs=1e-9)


@pytest.mark.parametrize("n_teams,slots", [(8, 4), (10, 6), (12, 6), (14, 8)])
def test_title_odds_sum_to_one(n_teams, slots):
    st = _league(n_teams=n_teams, playoff_slots=slots)
    rids = [t.roster_id for t in st.teams]
    strengths = {r: TeamStrength(r, 100.0 + 2 * r, 20.0) for r in rids}
    res = _run(st, strengths, n_sims=1200)
    assert sum(res.title_pct(r) for r in rids) == pytest.approx(1.0, abs=1e-9)


def test_only_playoff_teams_can_win_the_title():
    st = _league(n_teams=12, playoff_slots=6)
    rids = [t.roster_id for t in st.teams]
    strengths = {r: TeamStrength(r, 110.0, 25.0) for r in rids}
    res = _run(st, strengths, n_sims=1500)
    for r in rids:
        assert res.title_pct(r) <= res.playoff_pct(r) + 1e-9


# ---------------------------------------------------------------------------
# 3 — monotonicity in team strength
# ---------------------------------------------------------------------------

def test_odds_are_monotone_in_team_strength():
    """Strictly ordered league: mu increases with roster_id, sigma fixed.
    Playoff / title / bye odds must be non-decreasing in mu."""
    st = _league(n_teams=10, playoff_slots=6)
    rids = [t.roster_id for t in st.teams]
    strengths = {r: TeamStrength(r, 95.0 + 5.0 * r, 20.0) for r in rids}
    res = _run(st, strengths, n_sims=6000, config_seed=17)
    tol = 0.02  # Monte-Carlo slack between adjacent, closely-spaced teams
    for a, b in zip(rids, rids[1:]):
        assert res.playoff_pct(b) >= res.playoff_pct(a) - tol
        assert res.title_pct(b) >= res.title_pct(a) - tol
        assert res.projected_wins(b) >= res.projected_wins(a) - tol
    # extremes must separate decisively
    assert res.playoff_pct(rids[-1]) > res.playoff_pct(rids[0]) + 0.5
    assert res.title_pct(rids[-1]) > res.title_pct(rids[0]) + 0.2
    # projected seed improves (lower number) with strength
    assert res.projected_seed(rids[-1]) < res.projected_seed(rids[0])


# ---------------------------------------------------------------------------
# 4 — symmetric league is uniform
# ---------------------------------------------------------------------------

def test_symmetric_league_is_uniform_within_mc_tolerance():
    """Identical teams + a balanced round-robin => every team must get the
    same odds up to sampling error. 12 teams, N=8000: the binomial SE on a
    1/12 title share is ~0.003, so 0.02 is ~6 SE."""
    st = _league(n_teams=12, playoff_slots=6)
    rids = [t.roster_id for t in st.teams]
    strengths = {r: TeamStrength(r, 110.0, 25.0) for r in rids}
    res = _run(st, strengths, n_sims=8000, config_seed=5)
    for r in rids:
        assert res.playoff_pct(r) == pytest.approx(0.5, abs=0.05)
        assert res.title_pct(r) == pytest.approx(1.0 / 12, abs=0.02)
        assert res.bye_pct(r) == pytest.approx(2.0 / 12, abs=0.03)


# ---------------------------------------------------------------------------
# 5 — convergence as N grows
# ---------------------------------------------------------------------------

def test_estimates_converge_as_n_grows():
    """Across independent seeds, the spread of an estimate must shrink with N
    (Monte-Carlo error ~ 1/sqrt(N)). 16x more sims => ~4x tighter."""
    st = _league(n_teams=10, playoff_slots=6)
    rids = [t.roster_id for t in st.teams]
    strengths = {r: TeamStrength(r, 100.0 + 3.0 * r, 22.0) for r in rids}
    seeds = [1, 2, 3, 4, 5, 6, 7, 8]

    def spread(n):
        vals = [_run(st, strengths, n_sims=n, config_seed=s).playoff_pct(5)
                for s in seeds]
        return statistics.pstdev(vals)

    small, large = spread(250), spread(4000)
    assert large < small * 0.6, "spread %.4f -> %.4f (expected ~4x tighter)" % (
        small, large)


# ---------------------------------------------------------------------------
# 6 — determinism end-to-end through the pipeline
# ---------------------------------------------------------------------------

def test_run_outlook_is_deterministic_under_a_fixed_seed():
    st = _league(n_teams=10, playoff_slots=6)
    st.completed_weeks = 4
    st.weekly_scores = {t.roster_id: [100.0 + t.roster_id, 95.0, 120.0, 88.0]
                        for t in st.teams}
    kw = dict(player_value={}, player_pos={}, basis="consensus",
              source_override="trailing_scores", n_sims=800)
    cfg = {"outlook_seed": 42.0}
    a = run_outlook(st, model_cfg=cfg, **kw)
    b = run_outlook(st, model_cfg=cfg, **kw)
    assert a == b
    # and the seed is a real lever: a different config seed moves the numbers
    c = run_outlook(st, model_cfg={"outlook_seed": 43.0}, **kw)
    assert c["meta"]["seed"] != a["meta"]["seed"]
    assert c["teams"] != a["teams"]


def test_seed_is_process_stable_across_interpreters():
    """The payload seed must not depend on PYTHONHASHSEED (builtin hash() is
    salted; the engine uses a SHA-256 stable hash)."""
    import subprocess
    code = (
        "import sys; sys.path.insert(0, %r);"
        "from backend.outlook.simulator import stable_hash;"
        "print(stable_hash('LG-INV'))" % os.path.dirname(_SCRIPTS)
    )
    outs = set()
    for hs in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        outs.add(subprocess.run([sys.executable, "-c", code], env=env,
                                capture_output=True, text=True).stdout.strip())
    assert len(outs) == 1, "stable_hash varied with PYTHONHASHSEED: %s" % outs


# ---------------------------------------------------------------------------
# Fixture-backed: as-of rewind correctness + beats climatology
# ---------------------------------------------------------------------------

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "outlook-calibration")
_HAS_FIXTURES = os.path.isdir(FIXTURE_DIR) and bool(os.listdir(FIXTURE_DIR))
pytestmark_fixtures = pytest.mark.skipif(
    not _HAS_FIXTURES, reason="outlook-calibration fixtures not present")


@pytestmark_fixtures
@pytest.mark.parametrize("name", ["lakeview-2025", "lakeview-2024",
                                  "ffv3-2025", "ffv3-2024", "ffv3-2023",
                                  "ffv3-2022"])
def test_as_of_rewind_reproduces_sleepers_own_final_standings(name):
    """The backtest's as-of rewind is only trustworthy if replaying every week
    reproduces the final W/L/PF Sleeper itself reports on /rosters.

    Median-match leagues book two decisions per week (H2H + vs league median),
    so the replay has to add the median game to match — which is precisely the
    scale mismatch BUG-1 is about."""
    import outlook_calibration_backtest as bt
    fx = bt.load_fixture(name)
    full = bt.build_full_state(fx)
    med = bt.median_mode(fx)
    replay = bt.as_of_shipped_ingestion(full, full.regular_season_weeks, med)
    by_rid = {t.roster_id: t for t in replay.teams}
    for t in full.teams:
        r = by_rid[t.roster_id]
        assert (r.wins, r.losses, r.ties) == (t.wins, t.losses, t.ties), (
            "%s roster %d record drift" % (name, t.roster_id))
        # points_for is only approximately reconstructible: Sleeper's roster
        # fpts can drift from the sum of its own weekly matchup points when a
        # stat correction lands after the fact (lakeview-2024 roster 10 is
        # +22.20 / ~1.1%). Records are exact; PF is checked loosely.
        assert r.points_for == pytest.approx(t.points_for, rel=0.02)
        # decisions per week: 2 for median leagues, 1 otherwise
        assert r.wins + r.losses + r.ties == full.regular_season_weeks * (
            2 if med else 1)


@pytestmark_fixtures
@pytest.mark.xfail(strict=True, reason=(
    "BUG-1 (severe, open): SleeperLeagueState ignores settings."
    "league_average_match, so a median-match league's /rosters W/L counters "
    "arrive on a 2-decisions-per-week scale while simulate() adds only 1 win "
    "per remaining week. Fix = teach Phase 1 the setting and Phase 3 the "
    "median game; then delete this xfail. See calibration-report-2026-08-09.md"))
def test_median_match_leagues_are_ingested_on_the_simulated_win_scale():
    """The base standings the simulator starts from must be on the same
    win scale it increments. Currently they are not for median-match leagues."""
    import outlook_calibration_backtest as bt
    from backend.outlook.league_state import SleeperLeagueState
    fx = bt.load_fixture("lakeview-2025")          # league_average_match == 1
    assert bt.median_mode(fx), "fixture must be a median-match league"
    state = SleeperLeagueState(fetch=bt.offline_fetch(fx)).load(fx["league_id"])
    for t in state.teams:
        assert t.wins + t.losses + t.ties == state.regular_season_weeks


@pytestmark_fixtures
def test_as_of_state_carries_no_future_information():
    """A week-W state must expose exactly W weeks of scores, W weeks' worth of
    games in the standings, and W as completed_weeks."""
    import outlook_calibration_backtest as bt
    full = bt.build_full_state(bt.load_fixture("ffv3-2023"))
    for wk in (3, 6, 9, 12):
        st = bt.as_of(full, wk)
        assert st.completed_weeks == wk
        assert st.remaining_weeks() == list(range(wk + 1, st.regular_season_weeks + 1))
        for t in st.teams:
            assert t.wins + t.losses + t.ties == wk
            assert len(st.weekly_scores[t.roster_id]) == wk
            assert t.points_for < full_points(full, t.roster_id) + 1e-6


def full_points(state, rid):
    return sum(state.weekly_scores.get(rid, []))


@pytestmark_fixtures
def test_engine_beats_climatology_on_captured_seasons():
    """Regression guard on the headline calibration result: run as-of week 9
    on every captured past season; playoff Brier must beat the climatology
    baseline (playoff_slots / team_count for everyone) by a clear margin."""
    import outlook_calibration_backtest as bt
    model, clim = [], []
    for name in bt.PAST_SEASONS:
        fx = bt.load_fixture(name)
        full = bt.build_full_state(fx)
        field, _champ = bt.truth(fx, full.playoff_slots)
        st = bt.as_of(full, 9)
        payload = run_outlook(st, player_value={}, player_pos={}, model_cfg={},
                              basis="consensus", source_override="auto",
                              n_sims=1500)
        assert payload["meta"]["strength_source"] == "trailing_scores"
        base = full.playoff_slots / len(full.teams)
        for team in payload["teams"]:
            y = 1.0 if team["roster_id"] in field else 0.0
            model.append((team["odds"]["playoff_pct"] - y) ** 2)
            clim.append((base - y) ** 2)
    b_model = sum(model) / len(model)
    b_clim = sum(clim) / len(clim)
    assert len(model) == 72, "expected 6 seasons x 12 teams"
    assert b_model < b_clim * 0.75, (
        "week-9 playoff Brier %.4f vs climatology %.4f — calibration regressed"
        % (b_model, b_clim))
