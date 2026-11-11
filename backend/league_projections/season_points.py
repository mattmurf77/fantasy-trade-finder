"""Per-player projected points from a saved league-projection snapshot. Pure, no I/O.

Capture stores each rostered player's weekly inputs (`player_week_inputs`) but only
each team's chosen lineup, not per-player points. This module re-scores the stored
rows exactly as capture did (`provider.capture`, the best-available branch and the
strict branch), so the season signal reads the same numbers as the forecast.
`lineup_parity` proves it: re-optimising each team-week from the derived points
reproduces the stored lineup total.

Unknown is never zero: an unpriced row, an unavailable player, a completed game or
a row with no covered scoring key is `None`. A verified bye is `BYE`, not a number.
Free-agent rows (model v6, `free_agent: true`) are never a rostered player's
points; `free_agent_points` reads them separately. Unknown extra keys are ignored.
"""
from __future__ import annotations

from decimal import Decimal

from ..season_forecasts import normalize_scoring_for_slots
from .core import Unavailable, decimal, optimize, score
from .scoring import BEST_AVAILABLE

BYE = "bye"
_COMPLETED = {"completed_actual", "completed_actual_required"}


def _malformed(detail):
    return Unavailable("malformed_snapshot", state="read_failed", details={"field": detail})


def _is_free_agent(entry):
    return bool(entry.get("free_agent") or (entry.get("input") or {}).get("free_agent"))


def _completed(row):
    return row.get("phase") == "completed" or row.get("projection_status") in _COMPLETED


def _entry_points(row, active, best):
    """One stored row -> Decimal points, None (unknown) or BYE."""
    if _completed(row):
        return None
    if row.get("bye"):
        return BYE
    if row.get("projection_status") == "unpriced" or row.get("availability") != 1:
        return None
    stats, supported = row.get("stats") or {}, row.get("supported_keys") or []
    if best:
        # provider.capture best-available branch: score only covered keys.
        covered = {k: v for k, v in active.items() if k in stats and k in supported}
        if not covered and any(decimal(v) for v in active.values()):
            return None
        return score(stats, covered, supported)
    return score(stats, active, supported, inapplicable_keys=row.get("inapplicable_keys", []))


def _points(snapshot, free_agents):
    if not isinstance(snapshot, dict):
        raise _malformed("snapshot")
    entries, scoring, slots = snapshot.get("player_week_inputs"), snapshot.get("scoring"), snapshot.get("slots")
    if not isinstance(entries, list) or not isinstance(scoring, dict) or not isinstance(slots, list):
        raise _malformed("player_week_inputs/scoring/slots")
    active = normalize_scoring_for_slots(scoring, slots)
    best = (snapshot.get("coverage") or {}).get("scoring_contract") == BEST_AVAILABLE
    result = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("input"), dict):
            raise _malformed("player_week_inputs[]")
        if _is_free_agent(entry) != free_agents:
            continue
        try:
            week, pid = int(entry["week"]), str(entry["player_id"])
        except (KeyError, TypeError, ValueError):
            raise _malformed("player_week_inputs[].week/player_id") from None
        weekly = result.setdefault(week, {})
        if pid in weekly:
            raise _malformed("duplicate_player_week")
        weekly[pid] = _entry_points(entry["input"], active, best)
    return result


def player_points(snapshot):
    """{week: {player_id: Decimal | None | BYE}} for rostered players.

    Raises `core.Unavailable` on a malformed snapshot; the caller turns that into
    `unavailable: read_failed`.
    """
    return _points(snapshot, free_agents=False)


def free_agent_points(snapshot):
    """Same shape as `player_points`, for model v6 free-agent rows only (empty under v5)."""
    return _points(snapshot, free_agents=True)


def positions(snapshot):
    """{player_id: [fantasy positions]} as capture recorded them (rostered and free agents)."""
    return {str(e["player_id"]): list(e.get("positions") or []) for e in snapshot.get("player_week_inputs") or []}


def lineup_parity(snapshot, *, empty_policy="fill_available"):
    """Re-optimise every comparable team-week from derived points against the stored total.

    Comparable: no completed game anywhere in the week, and no locked, hypothetical
    (IDP bye fill) or free-agent player in the stored lineup. Returns counts and
    every mismatch; an empty `mismatches` list is the parity proof (invariant I10).
    """
    points, where = player_points(snapshot), positions(snapshot)
    completed_weeks = {int(e["week"]) for e in snapshot["player_week_inputs"] if _completed(e["input"])}
    rosters = {str(t["roster_id"]): t["roster"] for t in snapshot["teams"]}
    checked, skipped, mismatches = 0, 0, []
    for week in snapshot["weeks"]:
        w = int(week["week"])
        for rid, team in sorted(week["teams"].items()):
            stored = team["actual"]
            flagged = any(row.get("player") and any(row["player"].get(k) for k in ("locked_actual", "hypothetical", "free_agent"))
                          for row in stored["lineup"])
            if w in completed_weeks or flagged:
                skipped += 1
                continue
            roster = rosters[rid]
            inactive = set(roster.get("reserve", [])) | set(roster.get("taxi", []))
            pool = [{"player_id": pid, "positions": where[pid], "points": str(value)}
                    for pid in sorted(set(roster.get("players", [])) - inactive)
                    if isinstance(value := points.get(w, {}).get(pid), Decimal)]
            derived = optimize(snapshot["slots"], pool, empty_policy=empty_policy)["points"]
            checked += 1
            if decimal(derived) != decimal(stored["points"]):
                mismatches.append({"week": w, "roster_id": rid, "stored": stored["points"], "derived": derived})
    return {"checked": checked, "skipped": skipped, "mismatches": mismatches}
