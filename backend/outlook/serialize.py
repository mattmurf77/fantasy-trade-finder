"""Phase 5 — serialize SimResult + LeagueState into the /api/league/outlook
payload. The payload contract is the FIXED public surface; providers vary
behind it. Teams are returned playoff_pct-desc (title_pct, points_for tiebreak).
"""

from __future__ import annotations

from typing import Protocol

from .league_state import LeagueState
from .simulator import SimResult
from .strength import TeamStrength


class OutlookSerializer(Protocol):
    def serialize(self, state: LeagueState, result: SimResult,
                  strengths: dict[int, TeamStrength], *,
                  strength_source: str, basis: str,
                  you_user_id: str = "") -> dict:
        ...


class StandardSerializer:
    def serialize(self, state, result, strengths, *,
                  strength_source, basis, you_user_id=""):
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
                "beta": preseason,
            },
            "teams": teams,
        }


SERIALIZERS: dict[str, type] = {"standard": StandardSerializer}


def get_serializer(key: str = "standard") -> OutlookSerializer:
    factory = SERIALIZERS.get((key or "standard").lower())
    if factory is None:
        raise KeyError(f"no OutlookSerializer registered for {key!r}")
    return factory()
