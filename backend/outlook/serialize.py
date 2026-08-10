"""Phase 5 — serialize SimResult + LeagueState into the /api/league/outlook
payload. The payload contract is the FIXED public surface; providers vary
behind it. Teams are returned playoff_pct-desc (title_pct, points_for tiebreak).

`meta.is_preseason` vs `meta.beta`
-----------------------------------
These are deliberately SEPARATE signals (2026-08-09 fix — see the "meta.beta
aliasing problem" in
docs/feedback/items/169-outlook-league-summary/status.md §Productionization
and the transition-week evidence in
docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md):

  - `is_preseason` = `completed_weeks == 0` — a pure fact about the season.
  - `beta` = model-CONFIDENCE, independently computed from `completed_weeks`.
    `beta` used to be a plain alias of `is_preseason`, which meant the "beta"
    label vanished at week 1 even though the model was still uncalibrated.
    The 2026-08-09 revalidation found preseason playoff Brier (0.1959) is
    statistically indistinguishable from the week-3 in-season model (0.1972);
    the engine only pulls clearly ahead at week 6 (0.120) and is well
    calibrated by week 12 (0.055). So `beta` stays true through week 5 and
    only clears at `_BETA_UNTIL_COMPLETED_WEEKS` (6) — independent of
    `is_preseason`, which clears at week 1. Both fields ship on every
    payload; clients may use either or both.

`meta.priced_slot_coverage`
---------------------------
BUG-5: the DynastyProcess value board carries QB/RB/WR/TE only, so in an IDP
or kicker league a large share of the starting lineup prices at exactly 0.0 —
8 of 15 slots in the operator's FFv3 league. `strength.lineup_pricing()`
measures that; this block is what puts it on the wire (2026-08-10) so a client
can say *"based on your offensive starters"* instead of presenting a
whole-lineup number it cannot back up. It changes no prediction.

`affects_strength` is the honesty half: only the board-reading strength
sources (`roster_value`, `blended`) actually consume the value map, so a
`trailing_scores` payload carries the coverage fact with `affects_strength:
false` — the odds in that payload do not depend on the board at all. See
docs/feedback/items/169-outlook-league-summary/idp-pricing-2026-08-09.md.
"""

from __future__ import annotations

from typing import Protocol

from .league_state import LeagueState
from .simulator import SimResult
from .strength import LineupPricing, TeamStrength

# Strength sources whose estimate actually reads the value board. Anything
# else derives mu/sigma from game results, so unpriced slots cannot bias it.
_BOARD_BACKED_SOURCES = frozenset({"roster_value", "blended"})

# See module docstring — the week-6 line is where the 2026-08-09 calibration
# revalidation found the engine first pulls clearly away from the
# statistically-indistinguishable-from-preseason week-3 reading.
_BETA_UNTIL_COMPLETED_WEEKS = 6


def _coverage_block(pricing: "LineupPricing | None",
                    strength_source: str) -> "dict | None":
    """`meta.priced_slot_coverage` — see the module docstring.

    `None` when the caller supplied no `LineupPricing` (the measurement was
    not taken), which is honest about absence rather than reporting a
    fabricated 1.0."""
    if pricing is None:
        return None
    return {
        "fraction": round(pricing.coverage, 4),
        "total_slots": pricing.total_slots,
        "priced_slots": pricing.priceable_slots,
        "unpriced_slots": list(pricing.unpriceable_slots),
        "affects_strength": strength_source in _BOARD_BACKED_SOURCES,
    }


class OutlookSerializer(Protocol):
    def serialize(self, state: LeagueState, result: SimResult,
                  strengths: dict[int, TeamStrength], *,
                  strength_source: str, basis: str,
                  you_user_id: str = "",
                  pricing: "LineupPricing | None" = None) -> dict:
        ...


class StandardSerializer:
    def serialize(self, state, result, strengths, *,
                  strength_source, basis, you_user_id="", pricing=None):
        teams = []
        for t in state.teams:
            rid = t.roster_id
            s = strengths.get(rid)
            teams.append({
                "roster_id": rid,
                "user_id": t.user_id,
                "username": t.username,
                "display_name": t.display_name,
                "is_you": bool(you_user_id) and t.user_id == you_user_id,
                "wins": t.wins,
                "losses": t.losses,
                "ties": t.ties,
                "points_for": round(t.points_for, 2),
                "strength": {
                    "mu": round(s.mu, 2) if s else None,
                    "sigma": round(s.sigma, 2) if s else None,
                },
                "odds": {
                    "playoff_pct": round(result.playoff_pct(rid), 4),
                    "bye_pct": round(result.bye_pct(rid), 4),
                    "title_pct": round(result.title_pct(rid), 4),
                    "projected_wins": round(result.projected_wins(rid), 2),
                    "projected_seed": round(result.projected_seed(rid), 2),
                },
            })
        teams.sort(key=lambda x: (
            -x["odds"]["playoff_pct"],
            -x["odds"]["title_pct"],
            -x["points_for"],
            x["roster_id"],
        ))
        preseason = state.is_preseason
        beta = state.completed_weeks < _BETA_UNTIL_COMPLETED_WEEKS
        return {
            "league_id": state.league_id,
            "platform": state.platform,
            "basis": basis,
            "scoring_format": getattr(state, "scoring_format", None),
            "meta": {
                "strength_source": strength_source,
                "completed_weeks": state.completed_weeks,
                "regular_season_weeks": state.regular_season_weeks,
                "playoff_slots": state.playoff_slots,
                "byes": state.num_byes,
                "sims": result.n_sims,
                "seed": result.seed,
                "is_preseason": preseason,
                "beta": beta,
                "priced_slot_coverage": _coverage_block(pricing, strength_source),
            },
            "teams": teams,
        }


SERIALIZERS: dict[str, type] = {"standard": StandardSerializer}


def get_serializer(key: str = "standard") -> OutlookSerializer:
    factory = SERIALIZERS.get((key or "standard").lower())
    if factory is None:
        raise KeyError(f"no OutlookSerializer registered for {key!r}")
    return factory()
