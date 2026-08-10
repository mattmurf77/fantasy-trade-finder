"""Bye-week mu multiplier — EVALUATED variant, NOT wired into the live path
(feedback #169, operator directive 2026-08-09).

Problem: `strength.py` gives each team ONE flat mu for the whole rest of
season, so a team resting half its starting lineup for a bye week looks
identical to a team at full strength that week. "Middle path" per the
operator: keep the validated trailing-scores/roster-value mu, then apply a
PER-WEEK multiplier reflecting how much of a team's starting-lineup VALUE is
on bye that week.

Both-sides handling (operator requirement — verify, don't just assert)
------------------------------------------------------------------------
The multiplier computed here is a property of ONE team in ONE week. It is
applied to `simulator.simulate()`'s regular-season draw via the
`weekly_mu_multiplier` seam, which multiplies EACH side's mu independently
before drawing that side's score:

    ma = mu[a] * week_mult.get(a, 1.0);  sa = gauss(ma, sig[a])
    mb = mu[b] * week_mult.get(b, 1.0);  sb = gauss(mb, sig[b])

Both team A and team B look up their OWN multiplier for that week from the
SAME per-week map — so if A and B are playing each other and BOTH have (say)
30% of their lineup value on bye that week, both mu's shrink by the same
factor and the head-to-head win probability is unchanged versus a
no-bye week (a mutual bye cancels). If only A is bye-heavy that week, only
A's mu shrinks — B's edge widens. No special-casing is needed in the
simulator; this falls out of drawing both sides from the same map.
`backend/tests/test_bye_multiplier.py::test_mutual_bye_cancels_head_to_head`
and `::test_one_sided_bye_shifts_head_to_head` exercise both cases directly
against `simulator.simulate()`.

Data dependency: `backend/outlook/bye_weeks.py` (nflverse schedule -> bye
weeks) + a pid -> NFL-team map (`player_team`, e.g. `Player.team` from
`ranking_service.py`, which the live `/api/league/outlook` route already has
in-memory via the universal player pool — NOT wired here on purpose).

Ship gate: docs/feedback/items/169-outlook-league-summary/
bye-week-multiplier-2026-08-09.md records the backtest verdict. Flip
`outlook_bye_multiplier_enabled` in `model_config` (currently 0 = OFF, and
NOT consulted by `pipeline.py`) only if that doc's verdict is ship.
"""

from __future__ import annotations

from .bye_weeks import get_byes
from .league_state import LeagueState
from .simulator import SimResult, simulate
from .strength import TeamStrength, select_starting_lineup

# Documented heuristic (same status as the RosterValueStrength calibration
# knobs in strength.py) — NOT empirically fit. scale=1.0: a team with 100% of
# its starting-lineup value on bye draws at mu=0 that week; a team with 30%
# on bye draws at 0.7x mu. Floored at 0 so mu never goes negative. In
# practice a fantasy starting lineup is diversified across many NFL teams, so
# fraction_on_bye rarely exceeds ~0.3-0.4 even in a bad bye week.
_DEFAULTS = {"outlook_bye_multiplier_scale": 1.0}


def _knob(cfg: dict[str, float], key: str) -> float:
    val = cfg.get(key)
    return float(val) if val is not None else _DEFAULTS[key]


def weekly_value_fraction_on_bye(
    state: LeagueState,
    player_value: dict[str, float],
    player_pos: dict[str, str],
    player_team: dict[str, str],
    season: str,
    weeks: list[int] | None = None,
    _byes_opener=None,
) -> dict[int, dict[int, float]]:
    """week -> roster_id -> fraction (0..1) of that team's starting-lineup
    VALUE belonging to players whose NFL team has a bye that week.

    Uses the SAME greedy starting-lineup selection the shipped
    RosterValueStrength uses (`select_starting_lineup`) so "on bye" value is
    a share of the lineup that actually plays, not the whole bench-included
    roster (a bench player's bye costs the team nothing). Teams with no
    resolvable starting lineup (empty `roster_slots`, e.g. an ESPN import) or
    zero total lineup value are omitted from the result — callers should
    treat a missing (week, roster_id) entry as multiplier 1.0 (no-op), which
    is exactly what `simulator.simulate()`'s `weekly_mu_multiplier` seam
    already does."""
    weeks = weeks if weeks is not None else state.remaining_weeks()
    byes_for_season = get_byes(_opener=_byes_opener).get(str(season), {})

    out: dict[int, dict[int, float]] = {}
    for t in state.teams:
        selected = select_starting_lineup(
            t.player_ids, player_value, player_pos, state.roster_slots
        )
        if not selected:
            continue
        total = sum(player_value.get(pid, 0.0) for pid in selected)
        if total <= 0:
            continue
        pid_bye_week = {
            pid: byes_for_season.get(player_team.get(pid, ""))
            for pid in selected
        }
        for week in weeks:
            on_bye_value = sum(
                player_value.get(pid, 0.0)
                for pid in selected
                if pid_bye_week.get(pid) == week
            )
            out.setdefault(week, {})[t.roster_id] = on_bye_value / total
    return out


def mu_multipliers(
    fraction_on_bye: dict[int, dict[int, float]], cfg: dict[str, float]
) -> dict[int, dict[int, float]]:
    """Linear haircut from value-fraction-on-bye to a mu multiplier, scaled
    by `outlook_bye_multiplier_scale` and floored at 0."""
    scale = _knob(cfg, "outlook_bye_multiplier_scale")
    return {
        week: {rid: max(0.0, 1.0 - scale * frac) for rid, frac in by_team.items()}
        for week, by_team in fraction_on_bye.items()
    }


def simulate_with_bye_multiplier(
    state: LeagueState,
    strengths: dict[int, TeamStrength],
    fmt,
    *,
    player_value: dict[str, float],
    player_pos: dict[str, str],
    player_team: dict[str, str],
    season: str,
    cfg: dict[str, float],
    n_sims: int = 10000,
    config_seed: int = 0,
    _byes_opener=None,
) -> SimResult:
    """The evaluated variant's entry point: compute both-sides weekly mu
    multipliers and run the SAME `simulator.simulate()` the live pipeline
    uses, just with the multiplier seam populated. Used by the calibration
    backtest and by tests — never by `pipeline.run_outlook()`."""
    fraction = weekly_value_fraction_on_bye(
        state, player_value, player_pos, player_team, season,
        _byes_opener=_byes_opener,
    )
    mult = mu_multipliers(fraction, cfg)
    return simulate(
        state, strengths, fmt,
        n_sims=n_sims, config_seed=config_seed,
        weekly_mu_multiplier=mult,
    )
