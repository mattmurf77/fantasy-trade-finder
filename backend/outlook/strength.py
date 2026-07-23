"""Phase 2 — StrengthProvider (THE key swap seam).

A StrengthProvider turns a `LeagueState` into a per-team weekly-scoring model:
`{roster_id: TeamStrength(mu, sigma)}`, where a team's weekly fantasy score is
modeled as Normal(mu, sigma). The Monte-Carlo simulator (Phase 3) consumes
only this — it never knows *how* mu/sigma were derived.

This is the seam the operator cares about most. Replacing the projection/points
source — trailing scores → Sleeper projections → an own nflverse model — is a
NEW class registered in `STRENGTH_PROVIDERS` plus one config value
(`outlook_strength_source`). Nothing downstream imports a concrete provider.

Implemented
-----------
  - RosterValueStrength   : preseason default. mu from starting-lineup roster
                            value (consensus-or-personal board), affine-mapped
                            to a fantasy-points scale. Works at completed_weeks==0.
  - TrailingScoresStrength: in-season. mu/sigma straight from completed weekly
                            scores. Requires >= K completed weeks.
  - BlendedStrength       : minimal real blend of the two, weighted by how many
                            weeks are in the books (used by `auto` in the early
                            season window).

Registered stubs (seam is real, work deferred)
  - SleeperProjectionsStrength : mu from Sleeper weekly projections.
  - OwnModelStrength           : mu/sigma from an FTF nflverse projection model.

CALIBRATION — FLAGGED FOR OPERATOR REVIEW
-----------------------------------------
The roster-value → weekly-points mapping is a documented heuristic, NOT an
empirically fit model:
    mu_i = MEAN_POINTS + POINTS_PER_VALUE_SD * z(starting_lineup_value_i)
    sigma_i = SIGMA_DEFAULT
where z() is the cross-league z-score of starting-lineup value. Defaults live
in model_config (outlook_mean_points=110, outlook_points_per_value_sd=12,
outlook_sigma_default=25). These spreads are plausible but unvalidated; the
backtest scaffold (tests/test_outlook_odds.py) is where they should be tuned.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .league_state import LeagueState

# Which base positions each flex-style slot can draw from.
_FLEX_ELIGIBLE: dict[str, tuple[str, ...]] = {
    "FLEX": ("RB", "WR", "TE"),
    "WRRB_FLEX": ("RB", "WR"),
    "REC_FLEX": ("WR", "TE"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
    "SUPERFLEX": ("QB", "RB", "WR", "TE"),
}


@dataclass(frozen=True)
class TeamStrength:
    roster_id: int
    mu: float
    sigma: float


@dataclass
class StrengthContext:
    """Everything a provider might need beyond the LeagueState.

    Providers use only the fields they care about (trailing ignores the value
    maps; roster-value ignores nothing). Kept as one object so every provider
    satisfies the same Protocol signature."""
    player_value: dict[str, float]        # pid -> dynasty value (basis-resolved)
    player_pos: dict[str, str]            # pid -> position
    cfg: dict[str, float]                 # calibration knobs (model_config)


# ---- default knobs (mirrors model_config seeds; used when a key is absent) ----
_DEFAULTS = {
    "outlook_mean_points": 110.0,
    "outlook_points_per_value_sd": 12.0,
    "outlook_sigma_default": 25.0,
    "outlook_trailing_min_weeks": 3.0,
}


def _knob(cfg: dict[str, float], key: str) -> float:
    val = cfg.get(key)
    return float(val) if val is not None else _DEFAULTS[key]


def starting_lineup_value(
    player_ids: list[str],
    player_value: dict[str, float],
    player_pos: dict[str, str],
    roster_slots: list[str],
) -> float:
    """Greedy best-lineup value: fill each dedicated slot with the highest-value
    eligible unused player, then flex slots from the remaining pool. Falls back
    to summing the whole roster's value when the league exposes no starting
    slots (e.g. an ESPN-imported league without roster_positions)."""
    if not roster_slots:
        return sum(player_value.get(str(p), 0.0) for p in player_ids)

    # players grouped by position, value-desc
    by_pos: dict[str, list[float]] = {}
    for pid in player_ids:
        pid = str(pid)
        pos = player_pos.get(pid, "?")
        by_pos.setdefault(pos, []).append(player_value.get(pid, 0.0))
    for vals in by_pos.values():
        vals.sort(reverse=True)

    total = 0.0
    # dedicated (non-flex) slots first so flex draws from true leftovers
    dedicated = [s for s in roster_slots if s not in _FLEX_ELIGIBLE]
    flex = [s for s in roster_slots if s in _FLEX_ELIGIBLE]
    for slot in dedicated:
        pool = by_pos.get(slot)
        if pool:
            total += pool.pop(0)
    for slot in flex:
        elig = _FLEX_ELIGIBLE[slot]
        # pick the single best available value across eligible positions
        best_pos, best_val = None, None
        for pos in elig:
            pool = by_pos.get(pos)
            if pool and (best_val is None or pool[0] > best_val):
                best_pos, best_val = pos, pool[0]
        if best_pos is not None:
            by_pos[best_pos].pop(0)
            total += best_val
    return total


@runtime_checkable
class StrengthProvider(Protocol):
    """Stable Phase-2 interface."""
    name: str

    def estimate(self, state: LeagueState,
                 ctx: StrengthContext) -> dict[int, TeamStrength]:
        ...


class RosterValueStrength:
    """Preseason default — mu from starting-lineup roster value. Works when
    completed_weeks == 0 (uses no game results)."""
    name = "roster_value"

    def estimate(self, state, ctx):
        mean_pts = _knob(ctx.cfg, "outlook_mean_points")
        pts_per_sd = _knob(ctx.cfg, "outlook_points_per_value_sd")
        sigma = _knob(ctx.cfg, "outlook_sigma_default")

        values = {
            t.roster_id: starting_lineup_value(
                t.player_ids, ctx.player_value, ctx.player_pos, state.roster_slots
            )
            for t in state.teams
        }
        vlist = list(values.values())
        mean_v = statistics.fmean(vlist) if vlist else 0.0
        sd_v = statistics.pstdev(vlist) if len(vlist) > 1 else 0.0

        out: dict[int, TeamStrength] = {}
        for rid, v in values.items():
            z = (v - mean_v) / sd_v if sd_v > 0 else 0.0
            out[rid] = TeamStrength(rid, mu=mean_pts + pts_per_sd * z, sigma=sigma)
        return out


class TrailingScoresStrength:
    """In-season — mu/sigma from completed weekly scores. Requires >= K weeks."""
    name = "trailing_scores"

    def estimate(self, state, ctx):
        k = int(_knob(ctx.cfg, "outlook_trailing_min_weeks"))
        if state.completed_weeks < k:
            raise ValueError(
                f"TrailingScoresStrength needs >= {k} completed weeks "
                f"(have {state.completed_weeks})"
            )
        sigma_default = _knob(ctx.cfg, "outlook_sigma_default")
        out: dict[int, TeamStrength] = {}
        for t in state.teams:
            scores = state.weekly_scores.get(t.roster_id) or []
            if not scores:
                out[t.roster_id] = TeamStrength(
                    t.roster_id, _knob(ctx.cfg, "outlook_mean_points"),
                    sigma_default)
                continue
            mu = statistics.fmean(scores)
            sigma = statistics.pstdev(scores) if len(scores) >= 2 else sigma_default
            out[t.roster_id] = TeamStrength(t.roster_id, mu, sigma or sigma_default)
        return out


class BlendedStrength:
    """Minimal real blend of roster-value and trailing scores, weighted by how
    much of the season is complete. Used by `auto` in the 1..K-1 week window
    where trailing alone is too noisy. Not a tuned model — flagged for review."""
    name = "blended"

    def estimate(self, state, ctx):
        base = RosterValueStrength().estimate(state, ctx)
        if state.completed_weeks == 0:
            return base
        k = max(1, int(_knob(ctx.cfg, "outlook_trailing_min_weeks")))
        w = min(state.completed_weeks / k, 1.0)  # weight toward trailing
        sigma_default = _knob(ctx.cfg, "outlook_sigma_default")
        out: dict[int, TeamStrength] = {}
        for t in state.teams:
            rv = base[t.roster_id]
            scores = state.weekly_scores.get(t.roster_id) or []
            if scores:
                tr_mu = statistics.fmean(scores)
                tr_sigma = (statistics.pstdev(scores)
                            if len(scores) >= 2 else sigma_default)
            else:
                tr_mu, tr_sigma = rv.mu, rv.sigma
            out[t.roster_id] = TeamStrength(
                t.roster_id,
                mu=(1 - w) * rv.mu + w * tr_mu,
                sigma=(1 - w) * rv.sigma + w * tr_sigma,
            )
        return out


class _StubStrength:
    name = "?"

    def estimate(self, state, ctx):
        raise NotImplementedError(
            f"StrengthProvider {self.name!r} is a registered stub (feedback "
            f"#169). Implement estimate() and it drops in behind the Protocol "
            f"with no downstream change."
        )


class SleeperProjectionsStrength(_StubStrength):
    """mu from Sleeper weekly projections (future data source)."""
    name = "sleeper_projections"


class OwnModelStrength(_StubStrength):
    """mu/sigma from an FTF-owned nflverse projection model (future)."""
    name = "own_model"


# Registry: source key → provider factory (zero-arg callable). Add a new
# StrengthProvider by writing the class and adding ONE line here.
STRENGTH_PROVIDERS: dict[str, type] = {
    "roster_value": RosterValueStrength,
    "trailing_scores": TrailingScoresStrength,
    "blended": BlendedStrength,
    "sleeper_projections": SleeperProjectionsStrength,
    "own_model": OwnModelStrength,
}


def resolve_strength_source(source: str, state: LeagueState,
                            cfg: dict[str, float]) -> str:
    """Map the config value to a concrete source key.

    'auto' (default): roster_value when preseason; trailing_scores once >= K
    weeks are complete; blended in the early-season window between."""
    source = (source or "auto").lower()
    if source != "auto":
        return source
    if state.completed_weeks == 0:
        return "roster_value"
    k = int(_knob(cfg, "outlook_trailing_min_weeks"))
    return "trailing_scores" if state.completed_weeks >= k else "blended"


def get_strength_provider(source_key: str) -> StrengthProvider:
    factory = STRENGTH_PROVIDERS.get(source_key)
    if factory is None:
        raise KeyError(f"no StrengthProvider registered for {source_key!r}")
    return factory()
