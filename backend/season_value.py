"""Win-now season signal: season evidence, league profile, labels, the conflict predicate.

A leaf (docs/plans/win-now-season-signal/lld.md §1.2, §2, §3.5): no database, flag,
server or provider imports, no I/O. Everything here is a pure function of a saved
league-projection snapshot and the engine's own market values.

- `build_evidence` turns a snapshot into points per game over the upcoming
  regular-season weeks, or `unavailable(reason)`. Unknown is never zero: a player
  with no usable row is listed in `unprojected` and has no `ppg`.
- `require_viewer_projected` is PRD §2.5 rule 5 (the viewer's lineup must be known).
- `league_profile` computes the league's starter line per position and each
  rostered player's label (`win_now`, `cornerstone`, `rebuild`, `depth`, or None).
- `plan_conflict` is the one conflict predicate (PRD §5.1). Nothing else decides one.

Constants marked *starting value* are to be graded by the operator (PRD §4.6), not defended.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json

from .deck_quality import FILLER_FLOOR
from .league_projections.core import VERSION as PROJECTION_MODEL_VERSION, Unavailable, digest
from .league_projections import season_points
from .trade_roster import ELIGIBILITY, Asset, assign

EVIDENCE_SCHEMA = "season-evidence-1"
RULES_VERSION = "season-signal-1"
LABEL_RULES_VERSION = "season-labels-1"
POSITIONS = ("QB", "RB", "WR", "TE")
REASONS = frozenset({"platform_unsupported", "no_forecast", "old_model", "stale", "league_changed",
                     "no_upcoming_week", "viewer_unprojected_asset", "read_failed"})

RATE = 400.0           # value points per point a week above the starter line (starting value)
FUTURE_FLOOR = 1500.0  # future value at or above which a startable player is a cornerstone (starting value)
MARGIN_MIN, MARGIN_SHARE = 0.5, 0.05  # starter-line band: max(0.5, 5% of the line) (starting values)
# Lineup points a week a trade must cost before it works against a saved plan (PRD §5.1).
CONFLICT_DROP = {"championship": 0.5, "contender": 1.0}
_MIRROR_PLANS = ("rebuilder", "jets")
_EPS = 1e-9


def unavailable(reason):
    """The evidence object for a request with no usable forecast: today's behaviour."""
    if reason not in REASONS:
        raise ValueError(f"unknown season evidence reason: {reason}")
    return {"schema": EVIDENCE_SCHEMA, "state": "unavailable", "reason": reason,
            "source": "league_projections", "rules_version": RULES_VERSION}


def _time(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed


def _horizon(snapshot, as_of):
    """Weeks whose earliest kickoff, across every row, is later than `as_of`."""
    first = {}
    for entry in snapshot["player_week_inputs"]:
        kickoff = entry["input"].get("kickoff_at")
        if kickoff is not None:
            week, kick = int(entry["week"]), _time(kickoff)
            first[week] = min(first.get(week, kick), kick)
    return sorted(week for week, kick in first.items() if kick > as_of)


def _ppg(points, weeks):
    """{player_id: (ppg, games)} over the horizon; byes and unknown weeks are not games."""
    totals = {}
    for week in weeks:
        for pid, value in points.get(week, {}).items():
            if value is not None and value != season_points.BYE:
                total, games = totals.get(pid, (0, 0))
                totals[pid] = (total + value, games + 1)
    return {pid: (round(float(total / games), 2), games) for pid, (total, games) in totals.items()}


def build_evidence(snapshot, *, as_of, league_id, slots, platform, run_id=None, model_version=None, current=True):
    """Season evidence for one trade search, or `unavailable(reason)`.

    `snapshot` is the parsed (or raw JSON) `league_projection_runs.snapshot_json` of the
    league's last successful weekly baseline run; `model_version` is that run's
    `result.model_version`; `current` is `batch.view(...)["state"] == "current"`.
    `league_id` and `slots` are the trade job's. Pure: same inputs, same output.
    """
    if platform != "sleeper":
        return unavailable("platform_unsupported")
    if snapshot is None:
        return unavailable("no_forecast")
    if model_version != PROJECTION_MODEL_VERSION:
        return unavailable("old_model")
    if not current:
        return unavailable("stale")
    try:
        if isinstance(snapshot, (str, bytes)):
            snapshot = json.loads(snapshot)
        if str(snapshot.get("league_id")) != str(league_id) or sorted(snapshot.get("slots") or []) != sorted(slots or []):
            return unavailable("league_changed")
        as_of_time = _time(as_of)
        points = season_points.player_points(snapshot)
        weeks = _horizon(snapshot, as_of_time)
        free_points = season_points.free_agent_points(snapshot)
        where = season_points.positions(snapshot)
        rostered = {str(pid) for team in snapshot["teams"]
                    for key in ("players", "reserve", "taxi") for pid in team["roster"].get(key) or []}
        rostered |= {pid for rows in points.values() for pid in rows}
    except (Unavailable, KeyError, TypeError, ValueError, AttributeError):
        return unavailable("read_failed")
    if not weeks:
        return unavailable("no_upcoming_week")
    ppg = _ppg(points, weeks)
    free = _ppg(free_points, weeks)
    evidence = {
        "schema": EVIDENCE_SCHEMA, "state": "usable", "reason": None, "source": "league_projections",
        "run_id": run_id, "model_version": model_version,
        "captured_at": snapshot.get("captured_at"), "season": snapshot.get("season"),
        "weeks": weeks, "slots": list(snapshot["slots"]),
        "players": {pid: {"ppg": value, "games": games} for pid, (value, games) in sorted(ppg.items()) if pid in rostered},
        "unprojected": sorted(rostered - set(ppg)),
        "free_agent_level": {pos: max([value for pid, (value, _) in free.items() if pos in where.get(pid, ())] or [0.0])
                             for pos in POSITIONS},
        "rules_version": RULES_VERSION,
    }
    evidence["digest"] = digest(evidence)
    evidence["as_of"] = _time(as_of).isoformat()
    return evidence


def usable(evidence):
    return bool(evidence) and evidence.get("state") == "usable"


def require_viewer_projected(evidence, *, roster, position, market, inactive=()):
    """PRD §2.5 rule 5: a healthy, unprojected viewer player worth 450+ makes the
    viewer's season lineup unknown, so the request falls back. Picks never count."""
    if not usable(evidence):
        return evidence
    players, out = evidence["players"], set(inactive)
    for pid in roster:
        if (position.get(pid) in POSITIONS and pid not in out and pid not in players
                and (market.get(pid) or 0.0) >= FILLER_FLOOR):
            return unavailable("viewer_unprojected_asset")
    return evidence


def past_cliff(pos, age):
    """Past his position's age cliff on the engine's production curve: RB 27+, WR 30+,
    TE 32+, never a QB (`trade_service.age_now_mult`). Not `_now_lean`."""
    from .trade_service import age_now_mult  # lazy: trade_service reads flags at import
    return bool(age) and age > 25 and age_now_mult(pos, age) < age_now_mult(pos, 25)


def young(pos, age):
    from .trade_gen_bilateral import _YOUNG  # lazy: keeps this module a leaf
    return age is not None and pos in _YOUNG and age <= _YOUNG[pos]


def league_profile(evidence, *, rosters, position, market, age, slots=None, inactive=()):
    """The league's starter line and every rostered player's label. None without usable evidence.

    rosters: {team_id: [asset ids]} (picks included); position: {id: "QB"|"RB"|"WR"|"TE"|"PICK"|…};
    market: {id: dynasty market value}; age: {id: age or None}; inactive: ids that cannot
    start (injured out, reserve, taxi). Slots default to the evidence's.
    """
    if not usable(evidence):
        return None
    ppg = {pid: item["ppg"] for pid, item in evidence["players"].items()}
    lineup_slots = tuple(s for s in (slots if slots is not None else evidence["slots"]) if s in ELIGIBILITY)
    out = set(inactive)
    starters = Counter()
    for roster in rosters.values():
        usable_assets = [Asset(pid, frozenset([position.get(pid)]), ppg[pid]) for pid in roster
                         if pid in ppg and pid not in out and position.get(pid) in POSITIONS]
        starters.update(position[pid] for pid in assign(lineup_slots, usable_assets) if pid)
    rostered = sorted({pid for roster in rosters.values() for pid in roster})
    line, margin = {}, {}
    for pos in POSITIONS:
        ranked = sorted((ppg[pid] for pid in rostered if position.get(pid) == pos and pid in ppg), reverse=True)
        n = starters[pos]
        line[pos] = ranked[n - 1] if n and len(ranked) >= n else None
        margin[pos] = None if line[pos] is None else max(MARGIN_MIN, MARGIN_SHARE * line[pos])
    players = {}
    for pid in rostered:
        pos, value = position.get(pid), float(market.get(pid) or 0.0)
        if pos == "PICK":
            players[pid] = {"label": "rebuild", "future": value, "startable": None}
            continue
        if pid not in ppg or pos not in POSITIONS or line[pos] is None:
            players[pid] = {"label": None, "future": None, "startable": None}
            continue
        pts = ppg[pid]
        future = round(max(0.0, value - RATE * max(0.0, pts - line[pos])), 2)
        if pts >= line[pos] + margin[pos] - _EPS:
            startable = True
            label = "win_now" if future < FUTURE_FLOOR or past_cliff(pos, age.get(pid)) else "cornerstone"
        elif pts <= line[pos] - margin[pos] + _EPS:
            startable = False
            label = "rebuild" if value >= FILLER_FLOOR and young(pos, age.get(pid)) else "depth"
        else:
            startable, label = None, None  # borderline
        players[pid] = {"label": label, "future": future, "startable": startable}
    return {"rules_version": LABEL_RULES_VERSION, "line": line, "margin": margin,
            "starters": {pos: starters[pos] for pos in POSITIONS}, "players": players}


def plan_conflict(*, plan, declared, usable_evidence, pinned=False, delta_pts_week=None,
                  receive=(), give=(), profile=None, market=None):
    """True when a card works against the viewer's saved plan (PRD §5.1).

    plan: the engine's resolved outlook key (championship, contender, rebuilder, jets,
    not_sure). declared: the plan was saved (`outlook_source == "declared"`).
    pinned: the search pinned a player or partner. delta_pts_week: the viewer's season
    lineup after minus before. receive/give: asset ids. profile/market: for the
    Rebuilding/Tanking mirror, which compares future value (an unprojected player's
    future counts as his whole market value: nothing is explained by this season).
    """
    if not declared or not usable_evidence or pinned:
        return False
    if plan in CONFLICT_DROP:
        return delta_pts_week is not None and delta_pts_week <= -CONFLICT_DROP[plan] + _EPS
    if plan not in _MIRROR_PLANS or not receive or not give or profile is None:
        return False
    market, info = market or {}, profile["players"]

    def label(pid):
        return (info.get(pid) or {}).get("label")

    def future(pid):
        value = (info.get(pid) or {}).get("future")
        return float(market.get(pid) or 0.0) if value is None else value

    top = min(receive, key=lambda pid: (-float(market.get(pid) or 0.0), str(pid)))
    return (label(top) == "win_now"
            and any(label(pid) in ("rebuild", "cornerstone") for pid in give)
            and sum(map(future, receive)) < sum(map(future, give)))
