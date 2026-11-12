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
  It returns the trigger that fired ("points" or "label") or False.

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
# The mirror (amended 2026-11-11, operator direction): lineup points a week a trade must
# ADD before it works against a saved Tanking / Rebuilding plan.
CONFLICT_ADD = {"jets": 0.5, "rebuilder": 1.0}
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


# Founders' review (docs/plans/founder-review/design.md §2): a founder's label override
# is the label the engine uses for that player (any of the four, for any rostered
# QB / RB / WR / TE, including one the rule leaves unlabelled); whether he starts
# (`startable`, the starter line, the lineup) stays this league's (scope.md addendum
# 2026-11-12). Scope (operator ruling 2026-11-12): a QB override holds for the leagues of one QB
# format (superflex / 2QB, or single-QB); an RB / WR / TE override holds everywhere.
OVERRIDE_LABELS = ("cornerstone", "win_now", "rebuild", "depth")
SCOPE_ALL, SCOPE_SUPERFLEX, SCOPE_SINGLE_QB = "all", "superflex", "single_qb"
OVERRIDE_SCOPES = (SCOPE_ALL, SCOPE_SUPERFLEX, SCOPE_SINGLE_QB)


def is_superflex(slots):
    """The repo's one superflex test (also `server._detect_scoring_format_from_meta`'s QB
    leg): a SUPER_FLEX slot, or two or more QB slots. BN / IR / taxi entries don't count."""
    slots = list(slots or ())
    return "SUPER_FLEX" in slots or slots.count("QB") >= 2


def qb_scope(slots):
    return SCOPE_SUPERFLEX if is_superflex(slots) else SCOPE_SINGLE_QB


def override_scope(position, slots):
    """The scope an override for a player at `position` is stored under in a league with
    these lineup slots: the league's QB format for a QB, `all` otherwise."""
    return qb_scope(slots) if position == "QB" else SCOPE_ALL


def with_label_overrides(evidence, overrides):
    """The evidence with the founder's overrides that can reach this league attached as
    `label_overrides` ({player_id: {"label", "scope"}}) and its digest recomputed over
    them. `overrides`: iterable of (player_id, scope, label) rows. Kept: players in this
    league whose row's scope is `all` or this league's QB format (`qb_scope` of the
    evidence's slots). Nothing kept (no rows, other players, the other QB format): the
    same object back, so evidence, digest and request hash are byte-identical.
    "In this league" = projected here (`players`) or rostered here without a projection
    (`unprojected`): an override labels an unprojected player too."""
    if not usable(evidence) or not overrides:
        return evidence
    known = set(evidence.get("players") or {}) | set(evidence.get("unprojected") or ())
    here = {SCOPE_ALL, qb_scope(evidence.get("slots"))}
    relevant = {}
    for pid, scope, label in sorted((str(p), s, l) for p, s, l in overrides):
        if pid in known and scope in here and label in OVERRIDE_LABELS:
            relevant[pid] = {"label": label, "scope": scope}
    if not relevant:
        return evidence
    body = {k: v for k, v in evidence.items() if k not in ("digest", "as_of")}
    body["label_overrides"] = relevant
    out = {**body, "digest": digest(body)}
    if "as_of" in evidence:
        out["as_of"] = evidence["as_of"]
    return out


def overridden_label(label, override):
    """design.md §2.1 (amended 2026-11-12): the label after a founder override is the
    override itself, whatever the rule said (a label or none) and whether or not he starts
    here. Whether he starts here (`startable`) is never changed by it."""
    return override if override in OVERRIDE_LABELS else label


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
    Founder overrides in `evidence["label_overrides"]` apply per `overridden_label` to a
    QB / RB / WR / TE (never a pick) when their scope is this player's here
    (`override_scope`: a QB's must match the league's QB format), whether he is labelled,
    borderline or unprojected here; a player whose label they change also carries
    `engine_label` (possibly None). `startable` and `future` are never changed, so a label
    can disagree with `startable`, and an unprojected player can carry a label with
    `future` None. No override: unchanged.
    """
    if not usable(evidence):
        return None
    ppg = {pid: item["ppg"] for pid, item in evidence["players"].items()}
    overrides = evidence.get("label_overrides") or {}   # founder overrides (with_label_overrides)
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
        else:
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
        entry = overrides.get(pid)
        if entry and pos in POSITIONS and entry.get("scope") == override_scope(pos, lineup_slots):
            label = players[pid]["label"]
            founder = overridden_label(label, entry.get("label"))
            if founder != label:
                players[pid] = {**players[pid], "label": founder, "engine_label": label}
    return {"rules_version": LABEL_RULES_VERSION, "line": line, "margin": margin,
            "starters": {pos: starters[pos] for pos in POSITIONS}, "players": players}


def plan_conflict(*, plan, declared, usable_evidence, pinned=False, delta_pts_week=None,
                  receive=(), give=(), profile=None, market=None):
    """The trigger by which a card works against the viewer's saved plan (PRD §5.1), or False.

    plan: the engine's resolved outlook key (championship, contender, rebuilder, jets,
    not_sure). declared: the plan was saved (`outlook_source == "declared"`).
    pinned: the search pinned a player or partner. delta_pts_week: the viewer's season
    lineup after minus before. receive/give: asset ids. profile/market: for the
    Rebuilding/Tanking label rule, which compares future value (an unprojected player's
    future counts as his whole market value: nothing is explained by this season).

    Returns "points" (All-in / Contending: the lineup falls by CONFLICT_DROP or more;
    Tanking / Rebuilding: it rises by CONFLICT_ADD or more, checked first), "label"
    (Tanking / Rebuilding: a win-now piece in for future value out), or False.
    """
    if not declared or not usable_evidence or pinned:
        return False
    if plan in CONFLICT_DROP:
        return "points" if delta_pts_week is not None and delta_pts_week <= -CONFLICT_DROP[plan] + _EPS else False
    if plan not in _MIRROR_PLANS:
        return False
    if delta_pts_week is not None and delta_pts_week >= CONFLICT_ADD[plan] - _EPS:
        return "points"
    if not receive or not give or profile is None:
        return False
    market, info = market or {}, profile["players"]

    def label(pid):
        return (info.get(pid) or {}).get("label")

    def future(pid):
        value = (info.get(pid) or {}).get("future")
        return float(market.get(pid) or 0.0) if value is None else value

    top = min(receive, key=lambda pid: (-float(market.get(pid) or 0.0), str(pid)))
    fired = (label(top) == "win_now"
             and any(label(pid) in ("rebuild", "cornerstone") for pid in give)
             and sum(map(future, receive)) < sum(map(future, give)))
    return "label" if fired else False
