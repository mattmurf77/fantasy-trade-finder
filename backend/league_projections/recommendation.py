"""Outlook suggestion from the saved playoff projection. Suggests, never sets.

Pure reads: the saved weekly result and the user's saved outlook go in, one
block comes out. Nothing here writes a preference, queues a run or calls a
provider. The block is the same on Home, Team Review and the web page, and
the clients render it as given: they never re-derive a band.

Precedence, wherever an outlook is suggested to the user:
    1. the outlook the user saved (always what the trade engine uses);
    2. this suggestion, when the saved forecast is current, complete and from
       the current model;
    3. the roster-shape reads (age, picks, starter value, the three-band
       odds), which stay as context and as the engine's fallback.
A lower rank never replaces a higher one, and none of them writes rank 1.
"""
from __future__ import annotations

import json
import math

from .core import VERSION

# The one fixed cut: exactly 45% is Rebuilding, anything above it is
# Contender or All-in. The outer two cuts are configuration.
REBUILDING_MAX = .45

SUGGESTIONS = {
    "jets": "Consider prioritizing future value and draft position.",
    "rebuilder": "Consider adding future value while keeping flexibility.",
    "contender": "Consider trades that improve your current starting lineup.",
    "championship": ("Consider a stronger push for the championship. This is a suggestion, not a guarantee: "
                     "a high playoff chance does not make a team the title favorite."),
}
UNAVAILABLE = {
    "no_forecast": "There is no saved playoff forecast for this league yet, so no outlook is suggested.",
    "update_pending": "A new forecast is being prepared. An outlook suggestion returns when it is saved.",
    "refresh_failed": "The latest forecast update failed. The last saved forecast is kept, but it is too old to suggest an outlook.",
    "stale": "The saved forecast is from an earlier week. An outlook suggestion returns after the next weekly update.",
    "old_model": "The saved forecast was made by an earlier version of the model. An outlook suggestion returns after the next update.",
    "incomplete": "A starter who has already played has no recorded score yet, so this forecast is incomplete and no outlook is suggested.",
    "team_not_found": "Your team could not be matched to the saved forecast, so no outlook is suggested.",
    "unsupported": "Playoff forecasts are not available for this league, so no outlook is suggested.",
    "missing_projections": ("The projection source had no projections for an upcoming week, "
                            "so no new forecast was made. Past scoring is never used in their place."),
    "read_failed": "The saved forecast could not be read just now, so no outlook is suggested.",
}


def thresholds(options):
    """Validated cuts from `config/league_projections.json`."""
    raw = options.get("outlook_recommendation")
    if not isinstance(raw, dict) or set(raw) != {"tanking_max", "contender_max"}:
        raise ValueError("invalid_outlook_recommendation_configuration")
    low, high = raw["tanking_max"], raw["contender_max"]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (low, high)) or not 0 <= low < REBUILDING_MAX < high <= 1:
        raise ValueError("invalid_outlook_recommendation_configuration")
    return float(low), float(high)


def classify(probability, cuts):
    """Band for an unrounded probability. Upper bounds are inclusive."""
    low, high = cuts
    if probability <= low:
        return "jets"
    if probability <= REBUILDING_MAX:
        return "rebuilder"
    if probability <= high:
        return "contender"
    return "championship"


def _unavailable(reason, current_outlook, result=None):
    return {"status": "unavailable", "reason": reason, "playoff_probability": None, "recommended_outlook": None,
            "current_outlook": current_outlook, "differs": False, "suggestion": None,
            "explanation": UNAVAILABLE[reason], "captured_at": (result or {}).get("captured_at")}


def unavailable(reason, current_outlook):
    """An unavailable block with no saved result, e.g. `read_failed`."""
    return _unavailable(reason, current_outlook)


def unusable_reason(state, result, *, failure_reason=None):
    """Why the saved forecast may not be read for an outlook, or None when it
    is current, complete and from the current model. The one definition of
    "usable": `build` (the viewer's suggestion) and the assumed outlook of a
    league-mate (`partner_outlook`) both go through it."""
    if state == "unsupported_policy":
        return "unsupported"
    missing = failure_reason == "missing_weekly_projections" and state not in {"current", "queued", "running"}
    if not result:
        if missing:
            return "missing_projections"
        return "update_pending" if state in {"queued", "running"} else "no_forecast"
    if result.get("model_version") != VERSION:
        return "old_model"
    if missing:
        return "missing_projections"
    if state != "current":
        return {"queued": "update_pending", "running": "update_pending", "stale": "stale"}.get(state, "refresh_failed")
    if (result.get("coverage") or {}).get("estimate_status") != "complete":
        return "incomplete"
    return None


def valid_probability(probability):
    return (not isinstance(probability, bool) and isinstance(probability, (int, float))
            and math.isfinite(probability) and 0 <= probability <= 1)


def build(state, result, current_outlook, cuts, *, failure_reason=None):
    """`state` is `batch.view`'s; `result` is the saved run's parsed result;
    `failure_reason` is the last attempt's reason."""
    reason = unusable_reason(state, result, failure_reason=failure_reason)
    if reason is not None:
        # An unsupported policy, or no saved result, names no capture time.
        return _unavailable(reason, current_outlook, None if reason == "unsupported" else result)
    roster_id = result.get("viewer_roster_id")
    team = next((t for t in result.get("teams") or [] if roster_id is not None and t.get("roster_id") == roster_id), None)
    probability = team.get("playoff_probability") if team else None
    if not valid_probability(probability):
        return _unavailable("team_not_found", current_outlook, result)
    outlook = classify(probability, cuts)
    return {"status": "available", "reason": None, "playoff_probability": probability, "recommended_outlook": outlook,
            "current_outlook": current_outlook, "differs": outlook != current_outlook,
            "suggestion": SUGGESTIONS[outlook],
            "explanation": (f"Your team makes the playoffs in {probability * 100:.1f}% of the simulated seasons in the saved forecast. "
                            "This is a suggestion. Your saved outlook changes only when you choose a new one."),
            "captured_at": result.get("captured_at")}


def _instant(value):
    from datetime import datetime, timezone
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def saved_chance(view, now=None):
    """The viewer's playoff chance from the saved run, shown the way Home's
    playoff tile shows it (`mobile/src/utils/homePlayoffBanner.ts`), or None.

    Shown whenever Home shows a percentage: a complete saved run that holds
    the viewer's team with a valid probability and a capture time not in the
    future. `current` is Home's test (state current, current model, before
    the next weekly update); otherwise the client marks it "last saved". No
    run, no team, or a bad probability: None, and nothing is shown.
    """
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    run = (view or {}).get("run") or {}
    if run.get("status") != "complete" or not run.get("result_json"):
        return None
    result = json.loads(run["result_json"])
    roster_id = result.get("viewer_roster_id")
    team = next((t for t in result.get("teams") or [] if roster_id is not None and t.get("roster_id") == roster_id), None)
    probability = (team or {}).get("playoff_probability")
    captured = _instant(result.get("captured_at"))
    if not valid_probability(probability) or captured is None or captured > now:
        return None
    due = _instant(view.get("next_attempt_not_before"))
    current = (view.get("state") == "current" and result.get("model_version") == VERSION
               and due is not None and now < due)
    return {"playoff_probability": probability, "captured_at": result.get("captured_at"), "current": current}


def load_chance(user_id, league_id):
    """`saved_chance` for one account and league, from the saved run only."""
    from . import batch
    return saved_chance(batch.view(user_id, league_id))


def load(user_id, league_id, current_outlook):
    """The block for one account and league, from the saved run only."""
    from . import batch
    view = batch.view(user_id, league_id)
    raw = (view.get("run") or {}).get("result_json")
    return build(view["state"], json.loads(raw) if raw else None, current_outlook, thresholds(batch.settings()),
                 failure_reason=view.get("reason"))
