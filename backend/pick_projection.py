"""Next-draft firsts priced by the projected draft order (`picks.projected_slot_value`).

A pure leaf: no I/O, no flags, no logging, no imports from the rest of the
backend. `server._league_pick_projection` reads the league's saved forecast
(`league_projection_runs.result_json`), hands it to `compact`, and applies the
live knobs through `usable`; `pick_values.priced_pool_value` prices with the
result. Design: docs/plans/pick-value-projected-slot/design.md §4.

For a round-1 pick of the forecast's draft season, originally owned by roster
*r* of an *n*-team league:

    p_r[1..n]  the slot distribution: the forecast's non-playoff slot
               probabilities as stored, plus the team's playoff probability
               spread evenly over the playoff slots (the forecast does not
               project playoff finish). Every row and every column sums to 1.
    c[1..n]    the per-slot curve, engine value units (built by pick_values).
    ratio_r  = sum_k p_r[k] * c[k] / mean(c)
    w        = pick_projection_weight, times the weeks-played share
               completed / (completed + future weeks) only when
               pick_projection_season_scaling is on (operator ruling
               2026-11-11: full strength by default; the forecast's own slot
               odds carry the early-season uncertainty)
    value    = G * (1 + w * (ratio_r - 1))       G = today's generic price

Because every column sums to 1, sum_r ratio_r = n: the league's total value
of next-draft firsts is unchanged (zero-sum), and a forecast that knows
nothing (uniform rows) prices every pick at exactly G.

Anything malformed returns None and the pick prices generically; nothing in
this module raises on bad input.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

KEY_PREFIX = "pp1:"
_SUM_TOLERANCE = 1e-6


@dataclass(frozen=True)
class RunSummary:
    """One complete forecast run, reduced to what pricing needs. Knob-free,
    so it can be cached across knob changes."""
    run_id: str
    created_at: str
    model_version: str
    draft_season: int
    teams: int
    completed_weeks: int
    future_weeks: int
    dists: Mapping[str, tuple]          # str(roster_id) -> n slot probabilities


@dataclass(frozen=True)
class PickProjection:
    """A usable projection with the live knobs applied. `key` identifies
    every input that can move a price or a label, and nothing else (the run
    id enters it only hashed)."""
    season: int
    max_round: int
    teams: int
    weight: float                       # w, in (0, 1]
    dists: Mapping[str, tuple]
    key: str


def _num(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _int(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def compact(result_json: Any, *, run_id: str, created_at: str) -> RunSummary | None:
    """The run's slot distributions, or None when the run is not a complete,
    well-formed forecast. `result_json` is the stored text or the parsed dict."""
    try:
        result = json.loads(result_json) if isinstance(result_json, (str, bytes)) else result_json
        if not isinstance(result, dict) or result.get("status") != "complete":
            return None
        teams = result.get("teams")
        config = result.get("config") or {}
        season = _int(config.get("draft_season"))
        completed = _int(result.get("completed_weeks"))
        playoff = _int(result.get("playoff_spots"))
        if not isinstance(teams, list) or season is None or completed is None or playoff is None:
            return None
        n = len(teams)
        if n < 2 or not 0 < playoff <= n:
            return None
        future = None
        dists: dict[str, tuple] = {}
        for team in teams:
            rid = team.get("roster_id")
            picks = team.get("pick_probabilities")
            made = _num(team.get("playoff_probability"))
            weeks = team.get("weeks")
            if rid is None or not isinstance(picks, list) or made is None or not isinstance(weeks, list):
                return None
            if future is None:
                future = len(weeks)
            elif future != len(weeks):
                return None
            if len(picks) != n - playoff:
                return None
            probs = [_num(p) for p in picks]
            if any(p is None or p < 0 or p > 1 for p in probs) or not 0 <= made <= 1:
                return None
            row = tuple(probs + [made / playoff] * playoff)
            if abs(sum(row) - 1.0) > _SUM_TOLERANCE:
                return None
            if str(rid) in dists:
                return None
            dists[str(rid)] = row
        for k in range(n):
            if abs(sum(row[k] for row in dists.values()) - 1.0) > _SUM_TOLERANCE:
                return None
        return RunSummary(run_id=str(run_id), created_at=str(created_at),
                          model_version=str(result.get("model_version") or ""),
                          draft_season=season, teams=n, completed_weeks=completed,
                          future_weeks=future or 0, dists=dists)
    except Exception:
        return None


def _age_days(created_at: str, now: datetime) -> float | None:
    try:
        stamp = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (now - stamp).total_seconds() / 86400.0


def usable(summary: RunSummary | None, *, model_version: str, now: datetime,
           weight: float, min_weeks: float, max_age_days: float,
           max_round: float, season_scaling: float = 0.0) -> PickProjection | None:
    """The gates of design §4.5 and the live knobs. None means "price generic".

    Gates: the current forecast model; at least `min_weeks` completed weeks;
    younger than `max_age_days`, unless the run had at most one future week
    left (the last in-season run stands until the real order is known); and a
    positive weight. The draft-season gate is per pick (`covers`).

    `season_scaling` in [0, 1] blends in the weeks-played ramp: 0 (default)
    is full strength once the gates pass, 1 is `completed / season weeks`."""
    if summary is None or summary.model_version != model_version:
        return None
    if summary.completed_weeks < min_weeks:
        return None
    season_weeks = summary.completed_weeks + summary.future_weeks
    if season_weeks <= 0:
        return None
    if summary.future_weeks > 1:
        age = _age_days(summary.created_at, now)
        if age is None or age > max_age_days:
            return None
    scaling = max(0.0, min(1.0, float(season_scaling)))
    ramp = 1.0 - scaling + scaling * summary.completed_weeks / season_weeks
    w = max(0.0, min(1.0, float(weight))) * ramp
    if w <= 0.0:
        return None
    rounds = int(max_round)
    key = KEY_PREFIX + hashlib.sha256(json.dumps(
        [summary.run_id, summary.model_version, summary.draft_season,
         round(w, 9), rounds]).encode()).hexdigest()[:16]
    return PickProjection(season=summary.draft_season, max_round=rounds,
                          teams=summary.teams, weight=w, dists=summary.dists,
                          key=key)


def covers(projection: PickProjection | None, season, round_) -> bool:
    """Is a pick of `(season, round_)` priced by this projection?"""
    if projection is None:
        return False
    season, round_ = _int(season), _int(round_)
    return (season == projection.season and round_ is not None
            and 1 <= round_ <= projection.max_round)


def distribution(projection: PickProjection, original_roster_id) -> tuple | None:
    """The ORIGINAL team's slot distribution, never the current holder's."""
    if original_roster_id is None:
        return None
    return projection.dists.get(str(original_roster_id))


def ratio(dist, curve) -> float:
    """Expected curve value under `dist`, over the curve's uniform mean."""
    mean = sum(curve) / len(curve)
    return sum(p * c for p, c in zip(dist, curve)) / mean


def factor(projection: PickProjection, dist, curve) -> float:
    """The multiplier on the generic price: 1 + w * (ratio - 1)."""
    return 1.0 + projection.weight * (ratio(dist, curve) - 1.0)


def expected_slot(dist) -> float:
    return sum((k + 1) * p for k, p in enumerate(dist))


def projected_slot(dist) -> int:
    """The slot shown for a projected pick (operator ruling 2026-11-11): the
    expected slot under the same distribution that set the price, rounded to
    the nearest whole slot (halves up) and clamped to 1..league size."""
    return max(1, min(len(dist), math.floor(expected_slot(dist) + 0.5)))
