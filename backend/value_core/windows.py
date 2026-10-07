"""Team windows for the value-core engine (docs/plans/value-core-engine/lld.md section 5.1).

Each team is contender / rebuilder / middle. The base signal is the legacy age+picks
score from trade_service.infer_team_outlook; the points-for index is added on top with a
weight that ramps in over the first STANDINGS_RAMP_WEEKS completed weeks. A declared
outlook always wins. No logging, no I/O; the only config reads are the two outlook cuts.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from ..trade_service import _c, infer_team_outlook
from .types import DEFAULT_WINDOW, Standing, TeamWindow, Window

STANDINGS_RAMP_WEEKS = 8
DECLARED_MAP = {"championship": "contender", "contender": "contender",
                "rebuilder": "rebuilder", "jets": "rebuilder", "not_sure": "middle"}


def standings_weight_for(completed_weeks: int, full_weight: float) -> float:
    """max(0, full_weight) * min(1, max(0, completed_weeks) / STANDINGS_RAMP_WEEKS).
    Week 0 -> 0.0; week 3 at 0.30 -> 0.1125; week >= 8 -> full_weight."""
    return max(0.0, full_weight) * min(1.0, max(0, completed_weeks) / STANDINGS_RAMP_WEEKS)


def pf_indices(standings: Mapping[str, Standing]) -> dict[str, float]:
    """Points-for index in [-1, 1] per team: pct = (#teams with lower PF
    + 0.5 * (#other teams with equal PF)) / (n - 1); index = 2*pct - 1.
    Fewer than 2 teams -> {}. PF [100, 200, 300, 400] -> [-1, -1/3, 1/3, 1]."""
    n = len(standings)
    if n < 2:
        return {}
    pfs = {t: s.points_for for t, s in standings.items()}
    out: dict[str, float] = {}
    for t, pf in pfs.items():
        lower = sum(1 for o, v in pfs.items() if o != t and v < pf)
        equal = sum(1 for o, v in pfs.items() if o != t and v == pf)
        out[t] = 2.0 * (lower + 0.5 * equal) / (n - 1) - 1.0
    return out


def window_from_declared(value: str | None) -> Window | None:
    """DECLARED_MAP lookup; unknown/None -> None."""
    return DECLARED_MAP.get(value) if value is not None else None


def infer_windows(*, team_rosters: Mapping[str, Sequence[str]], players: Mapping[str, object],
                  pick_shares: Mapping[str, float], standings: Mapping[str, Standing],
                  completed_weeks: int, declared: Mapping[str, str | None],
                  standings_weight: float) -> dict[str, TeamWindow]:
    """One TeamWindow per team in team_rosters. `players` holds duck-typed Player objects
    (position, age, search_rank, pick_value). This is what trade_service.infer_team_outlook
    reads (trade_service.py:3999, :4095-4110)."""
    n = len(team_rosters)
    w = standings_weight_for(completed_weeks, standings_weight)
    pf = pf_indices({t: s for t, s in standings.items() if t in team_rosters}) if w > 0 else {}
    out: dict[str, TeamWindow] = {}
    for t in sorted(team_rosters):
        try:
            # No starter/odds signal and no firsts ledger: the legacy age+picks vector,
            # whatever trade.outlook_composite / trade.outlook_net_firsts say.
            _label, score, _ = infer_team_outlook(
                list(team_rosters[t]), players, pick_share=pick_shares.get(t, 0.0), num_teams=n)
        except Exception:
            out[t] = DEFAULT_WINDOW
            continue
        s = score + w * pf[t] if t in pf else score
        if s >= _c("infer_contender_cut"):
            window: Window = "contender"
        elif s <= _c("infer_rebuilder_cut"):
            window = "rebuilder"
        else:
            window = "middle"
        declared_window = window_from_declared(declared.get(t))
        if declared_window is not None:
            window, source = declared_window, "declared"
        else:
            source = "inferred"
        out[t] = TeamWindow(window, round(s, 4), source, pf.get(t), w if t in pf else 0.0)
    return out
