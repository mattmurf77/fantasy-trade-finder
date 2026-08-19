"""With-trade playoff-odds delta — "what does this trade do to my odds?"

Feedback #357 (*"raises your playoff odds to X"*). Operator-directed
2026-08-19, reversing the deferral in [D-025], which dropped the week-6+ card
odds block ("card frame D") on its backend cost without measuring it.

WHY THIS IS CHEAPER AND MORE HONEST THAN D-025 ASSUMED
------------------------------------------------------
The simulator seeds off the LEAGUE, not the rosters:

    seed = stable_hash(state.league_id) ^ config_seed      (simulator.py)

so two runs for the same league draw the *identical* random stream. That is
common random numbers (CRN), the standard variance-reduction technique for
exactly this question, and it buys two properties that a naive "simulate
twice" would not have. Both are measured, not asserted — see
`backend/tests/test_outlook_trade_delta.py`:

  1. **An unchanged roster yields a delta of EXACTLY 0.0.** Not "small", not
     "within tolerance" — bit-identical, because the two runs are the same
     computation. A trade that changes nothing can never show a spurious
     shift. This is the honesty property the whole surface rests on.

  2. **The delta is far more stable than either absolute it is drawn from.**
     Measured on a marginal upgrade (one starter slot, +120 value): the delta
     moves 0.4 percentage points across a 10x sim reduction (10000 -> 1000),
     while the absolute `playoff_pct` it is computed from moves 1.05 points
     over the same range. The model error that makes the ABSOLUTE
     over-confident at the extremes (calibration-combined-2026-08-10.md §7)
     is common to both runs and largely cancels in the difference.

That is why this module runs at `DELTA_SIM_COUNT` (2000) rather than the
10000 the standalone outlook surface uses: 2000 sims lands within 0.3 points
of the 10000-sim delta and costs ~112 ms instead of ~689 ms. The cost D-025
balked at was real; it was a 20x overestimate of what a *delta* needs.

WHAT THIS MODULE DOES NOT DECIDE
--------------------------------
Rendering. It returns raw fractions plus the two band keys; every rule about
how a client may show them lives in `docs/cross-client-invariants.md`
§ "Playoff outlook bands" and § "Trade odds impact". In particular
`title_pct` is neither computed nor returned here — it is unrenderable at any
week on an absence of demonstrated skill, so this module does not put it
within reach.

Pure: no DB, no HTTP, no Flask. Everything is passed in, mirroring
`run_outlook` itself.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from .league_state import LeagueState
from .pipeline import run_outlook

# Sims for the DELTA path. Justified above and pinned by
# test_delta_is_stable_across_sim_counts. Deliberately a module constant
# rather than a model_config knob: it is a property of the CRN argument, not
# a product tuning dial, and lowering it silently would erode the one
# measurement this surface's honesty rests on.
DELTA_SIM_COUNT = 2000

# Band thresholds — the cross-client invariant. Mirrored here (not imported
# from a client) because the backend must be able to name the band it is
# reporting; the canonical statement is docs/cross-client-invariants.md
# § "Playoff outlook bands", and any change updates both together.
_BAND_LIKELY_MIN = 0.65
_BAND_UNLIKELY_MAX = 0.35


def playoff_band(frac: float) -> str:
    """Top-down walk, so a boundary belongs to the HIGHER band: exactly 0.65
    is `likely`, exactly 0.35 is `tossup`. Same rule as every client."""
    if frac >= _BAND_LIKELY_MIN:
        return "likely"
    if frac < _BAND_UNLIKELY_MAX:
        return "unlikely"
    return "tossup"


@dataclass(frozen=True)
class TradeOddsImpact:
    """One team's before/after playoff picture for a hypothetical trade."""

    before_pct: float
    after_pct: float
    delta_pct: float          # after - before, signed, in 0..1 fraction units
    before_band: str
    after_band: str
    band_changed: bool
    before_seed: float
    after_seed: float
    seed_delta: float         # negative = a BETTER (lower-numbered) seed
    sims: int
    is_preseason: bool
    beta: bool

    def as_dict(self) -> dict:
        return {
            "before_pct": round(self.before_pct, 4),
            "after_pct": round(self.after_pct, 4),
            "delta_pct": round(self.delta_pct, 4),
            "before_band": self.before_band,
            "after_band": self.after_band,
            "band_changed": self.band_changed,
            "before_seed": round(self.before_seed, 2),
            "after_seed": round(self.after_seed, 2),
            "seed_delta": round(self.seed_delta, 2),
            "sims": self.sims,
            "is_preseason": self.is_preseason,
            "beta": self.beta,
        }


def apply_trade_to_state(
    state: LeagueState,
    *,
    user_roster_id: int,
    opponent_roster_id: int,
    give_player_ids: list[str],
    receive_player_ids: list[str],
) -> LeagueState:
    """Return a DEEP COPY of `state` with the trade applied to both rosters.

    The input is never mutated — the caller's baseline state is reused for
    every card in a deck, so mutating it would silently corrupt every
    subsequent comparison.

    Draft picks and any id not actually on the giving roster are ignored
    rather than errored: picks cannot start, so they contribute 0 to every
    lineup by construction, and a stale id must not take down the card. Both
    `player_ids` and `starters` are updated, because `RosterValueStrength`
    re-picks the optimal lineup from `player_ids` while `TrailingScoresStrength`
    ignores rosters entirely.
    """
    new_state = copy.deepcopy(state)
    by_id = {t.roster_id: t for t in new_state.teams}
    user = by_id.get(user_roster_id)
    opp = by_id.get(opponent_roster_id)
    if user is None or opp is None:
        return new_state

    give = [p for p in give_player_ids if p in set(user.player_ids)]
    recv = [p for p in receive_player_ids if p in set(opp.player_ids)]

    def move(src, dst, ids):
        drop = set(ids)
        src.player_ids = [p for p in src.player_ids if p not in drop]
        src.starters = [p for p in src.starters if p not in drop]
        # Append rather than insert: `starters` is a convenience view, and the
        # board-reading strength providers re-derive the optimal lineup from
        # `player_ids` anyway.
        dst.player_ids = list(dst.player_ids) + list(ids)
        dst.starters = list(dst.starters) + list(ids)

    move(user, opp, give)
    move(opp, user, recv)
    return new_state


def _you_row(payload: dict, user_roster_id: int) -> dict | None:
    for t in payload.get("teams") or []:
        if t.get("roster_id") == user_roster_id:
            return t
    return None


def compute_trade_odds_impact(
    baseline_payload: dict,
    state: LeagueState,
    *,
    user_roster_id: int,
    opponent_roster_id: int,
    give_player_ids: list[str],
    receive_player_ids: list[str],
    player_value: dict[str, float],
    player_pos: dict[str, str],
    model_cfg: dict,
    basis: str = "consensus",
    scoring_format: str | None = None,
    playoff_seed_type: int | None = None,
    n_sims: int = DELTA_SIM_COUNT,
) -> TradeOddsImpact | None:
    """Baseline is passed IN, already computed and cached by the caller.

    That asymmetry is the whole performance design: within one deck the
    baseline is identical for all 30 cards, so it is computed once and only
    the with-trade half is re-simulated per card (~112 ms at 2000 sims).

    **The baseline MUST have been produced at the same `n_sims` as this call.**
    Mixing sim counts across the two halves reintroduces exactly the Monte
    Carlo noise the CRN design exists to eliminate — the two runs would no
    longer share a random stream. `resim_baseline` below is the supported way
    to get a matching baseline.

    Returns None when the delta cannot be computed honestly: no `you` row in
    either payload, or an unresolvable roster. Never raises for trade-shaped
    reasons; the caller omits the block rather than showing a wrong number.
    """
    before = _you_row(baseline_payload, user_roster_id)
    if before is None:
        return None

    after_state = apply_trade_to_state(
        state,
        user_roster_id=user_roster_id,
        opponent_roster_id=opponent_roster_id,
        give_player_ids=give_player_ids,
        receive_player_ids=receive_player_ids,
    )
    after_payload = run_outlook(
        after_state,
        player_value=player_value,
        player_pos=player_pos,
        model_cfg={**dict(model_cfg or {}), "outlook_sim_count": n_sims},
        basis=basis,
        scoring_format=scoring_format,
        you_user_id="",
        n_sims=n_sims,
        playoff_seed_type=playoff_seed_type,
    )
    after = _you_row(after_payload, user_roster_id)
    if after is None:
        return None

    b_pct = float(before["odds"]["playoff_pct"])
    a_pct = float(after["odds"]["playoff_pct"])
    b_seed = float(before["odds"].get("projected_seed") or 0.0)
    a_seed = float(after["odds"].get("projected_seed") or 0.0)
    b_band = playoff_band(b_pct)
    a_band = playoff_band(a_pct)
    meta = after_payload.get("meta") or {}

    return TradeOddsImpact(
        before_pct=b_pct,
        after_pct=a_pct,
        delta_pct=a_pct - b_pct,
        before_band=b_band,
        after_band=a_band,
        band_changed=(b_band != a_band),
        before_seed=b_seed,
        after_seed=a_seed,
        seed_delta=a_seed - b_seed,
        sims=n_sims,
        is_preseason=bool(meta.get("is_preseason")),
        beta=bool(meta.get("beta")),
    )


def resim_baseline(
    state: LeagueState,
    *,
    player_value: dict[str, float],
    player_pos: dict[str, str],
    model_cfg: dict,
    basis: str = "consensus",
    scoring_format: str | None = None,
    playoff_seed_type: int | None = None,
    n_sims: int = DELTA_SIM_COUNT,
) -> dict:
    """The matching baseline for `compute_trade_odds_impact`.

    Exists so a caller cannot accidentally difference a 10000-sim baseline
    (what `GET /api/league/outlook` serves) against a 2000-sim with-trade run.
    Cache this per (league_id, basis, completed_weeks) and reuse it across
    every card in the deck.
    """
    return run_outlook(
        state,
        player_value=player_value,
        player_pos=player_pos,
        model_cfg={**dict(model_cfg or {}), "outlook_sim_count": n_sims},
        basis=basis,
        scoring_format=scoring_format,
        you_user_id="",
        n_sims=n_sims,
        playoff_seed_type=playoff_seed_type,
    )
