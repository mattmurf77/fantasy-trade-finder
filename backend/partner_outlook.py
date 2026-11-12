"""A league-mate's ASSUMED outlook: the one place that decides it and its source.

Flag `trade.partner_outlook_projection` (scope:
docs/plans/league-projections/partner-outlook-scope.md). Precedence, per
league-mate:

    1. their saved outlook (`declared`), which always wins;
    2. their own playoff probability in the viewer's saved weekly forecast
       (`projection`), when that forecast is usable by the same test the
       viewer's outlook suggestion applies
       (`league_projections.recommendation.unusable_reason`) and their roster
       maps to exactly one forecast team;
    3. the roster read (`roster`), today's behaviour, unchanged.

Two bands, not four: at or below `recommendation.REBUILDING_MAX` (45%) is
`rebuilder`, above it `contender`, on the unrounded probability. The engine
never ASSUMES the extremes for another manager: Tanking carries hard rules (no
outgoing own next-year pick, no RB without a long-term case) that must not be
applied to someone on a guess.

The viewer's own outlook is not decided here (D-230 governs it).

Reads only. `read_forecast` is called once per trade request / job / Team
Review request; it never queues a run and never calls a provider. The forecast
is keyed by Sleeper `roster_id`, league-mates by the roster's owner id; the
mapping uses `sleeper_roster.owns_roster` (the one roster→user predicate, so a
co-owner is an alias of the primary owner) over the rosters the session read.
"""
from __future__ import annotations

import json
import logging
import threading

from .sleeper_roster import co_owner_ids, owns_roster

log = logging.getLogger(__name__)

FLAG = "trade.partner_outlook_projection"
SOURCES = ("declared", "projection", "roster")

# Parsed forecast fields by run id: a saved run's result never changes, so the
# (possibly large) result JSON is parsed once per process, not per request.
_PARSED: dict[str, dict] = {}
_PARSED_LOCK = threading.Lock()
_PARSED_MAX = 256


def enabled(is_enabled) -> bool:
    """The flag, and the projections feature it reads from (with that off there
    is no forecast to read)."""
    return bool(is_enabled(FLAG) and is_enabled("league.projections"))


def assumed_from_probability(probability):
    """`rebuilder` at or below 45%, `contender` above it; None when invalid."""
    from .league_projections.recommendation import REBUILDING_MAX, valid_probability
    if not valid_probability(probability):
        return None
    return "rebuilder" if probability <= REBUILDING_MAX else "contender"


def roster_index(rosters):
    """The Sleeper rosters' ownership facts, compact enough to keep on the
    session: `[[roster_id, owner_id, [co_owner, ...]], ...]`, or None."""
    if not isinstance(rosters, (list, tuple)):
        return None
    out = []
    for r in rosters:
        if isinstance(r, dict) and r.get("roster_id") is not None:
            out.append([r.get("roster_id"), str(r.get("owner_id") or ""), co_owner_ids(r)])
    return out


def _parsed(run):
    run_id, raw = run.get("run_id"), run.get("result_json")
    with _PARSED_LOCK:
        hit = _PARSED.get(run_id)
    if hit is not None:
        return hit
    result = json.loads(raw) if raw else None
    if not isinstance(result, dict):
        return None
    hit = {"model_version": result.get("model_version"),
           "coverage": {"estimate_status": (result.get("coverage") or {}).get("estimate_status")},
           "captured_at": result.get("captured_at"),
           "probabilities": {str(t.get("roster_id")): t.get("playoff_probability")
                             for t in result.get("teams") or [] if isinstance(t, dict)}}
    with _PARSED_LOCK:
        if len(_PARSED) >= _PARSED_MAX:
            _PARSED.clear()
        _PARSED[run_id] = hit
    return hit


def read_forecast(user_id, league_id, *, platform="sleeper"):
    """The usable saved forecast for this account and league as
    `{"captured_at", "probabilities": {roster_id: p}}`, or None (not Sleeper,
    nothing saved, stale, incomplete, an older model, an unsupported policy, a
    run pending, or a read failure, which logs one line). Read only."""
    if str(platform or "sleeper").lower() != "sleeper" or not str(league_id).isdigit():
        return None
    try:
        from .league_projections import batch
        from .league_projections.recommendation import unusable_reason
        view = batch.view(str(user_id), str(league_id))
        run = view.get("run") or {}
        result = _parsed(run) if run.get("result_json") else None
        if unusable_reason(view["state"], result, failure_reason=view.get("reason")) is not None:
            return None
        return {"captured_at": result.get("captured_at"),
                "probabilities": dict(result["probabilities"])}
    except Exception as exc:
        log.warning("partner outlook: saved forecast unreadable for league %s (roster reads kept): %s",
                    league_id, exc)
        return None


def projection_reads(forecast, rosters, member_ids):
    """`{member_id: "rebuilder" | "contender"}` for every member whose roster
    maps to exactly one forecast team with a valid probability. A member with
    no probability, or no roster or more than one under the predicate, is left
    out (they keep the roster read)."""
    if not forecast or not rosters:
        return {}
    rows = [{"roster_id": r[0], "owner_id": r[1], "co_owners": list(r[2] or ())}
            for r in rosters if isinstance(r, (list, tuple)) and len(r) == 3]
    probabilities = forecast.get("probabilities") or {}
    out = {}
    for uid in member_ids:
        owned = [r for r in rows if owns_roster(r, uid)]
        if len(owned) != 1:
            continue
        outlook = assumed_from_probability(probabilities.get(str(owned[0]["roster_id"])))
        if outlook is not None:
            out[str(uid)] = outlook
    return out


def assumed(uid, *, declared, projection, roster=None):
    """`(outlook, source)` for one league-mate: declared, then projection, then
    the roster read (`roster`, which may be None when the caller resolves it
    later exactly as before)."""
    if declared.get(uid):
        return declared[uid], "declared"
    if projection.get(uid) is not None:
        return projection[uid], "projection"
    return roster, "roster"


def public(uid, *, declared, projection, roster):
    """`(read, source)` SHOWN about a league-mate (the card's "Them" tag, Team
    Review's partner groups). A saved outlook is never shown, so a declared
    league-mate shows the roster read; everyone else shows `assumed`."""
    outlook, source = assumed(uid, declared=declared, projection=projection, roster=roster)
    return (roster, "roster") if source == "declared" else (outlook, source)


def session_reads(sess, user_id, league_id, member_ids, *, platform="sleeper"):
    """One forecast read for a request: `{"captured_at", "reads"}` or None.
    The rosters are the ones this session's init read (`sleeper_roster_index`
    on the session), so the mapping matches the session's league members."""
    index = (sess or {}).get("sleeper_roster_index") or {}
    if str(index.get("league_id")) != str(league_id) or not index.get("rosters"):
        return None
    forecast = read_forecast(user_id, league_id, platform=platform)
    if forecast is None:
        return None
    return {"captured_at": forecast["captured_at"],
            "reads": projection_reads(forecast, index["rosters"], member_ids)}
