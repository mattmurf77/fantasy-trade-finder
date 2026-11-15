"""Playoff targets: which players on selling teams would raise the viewer's playoff chance most.

The mirror of Max PF moves (`maxpf_moves.py`), for a team that wants to make
the playoffs. Contract: docs/plans/league-projections/playoff-targets/contract.md.
Flag `league.playoff_targets` (callers check it; nothing here reads a flag).

Only players on a SELLING team are ever suggested. A team is selling when
its playoff chance in this forecast is below `SELLER_MAX_PLAYOFF`, or its
manager's saved outlook is Rebuilding or Tanking (`SELLING_OUTLOOKS`).
`is_seller` is the one definition; the weekly job applies it to choose
candidates and the read applies it again with the outlooks saved at that
moment, so a row is never served for a team that is not selling now.
"""
from __future__ import annotations

from decimal import Decimal
import json

from . import season_points, simulation
from .core import Unavailable, decimal
from .maxpf_moves import (CONFIG_PATH, _Context, _after_teams, _lowered, _replacement, _whole, settings_hash,
                          short_name)

VERSION = 1
# The operator's rule (2026-11-14): strictly below 50% on the unrounded
# probability, or a SAVED outlook of Rebuilding (`rebuilder`) / Tanking
# (`jets`). An inferred outlook never counts.
SELLER_MAX_PLAYOFF = .5
SELLING_OUTLOOKS = frozenset({"rebuilder", "jets"})

SETTINGS_KEYS = {
    # key: (type, low, high)
    "simulations_per_candidate": (int, 100, 250000),
    "candidates": (int, 1, 20),
    "min_playoff_gain": ((int, float), 0, 1),
    "near_certain_min": ((int, float), .5, 1),
    "time_budget_seconds": ((int, float), 1, 400),
}
_EPSILON = 1e-9  # float noise at a threshold edge never decides a row


def parse_settings(raw):
    """Validated `playoff_targets` settings. Raises ValueError on a missing,
    unknown or out-of-range key (booleans are never numbers here)."""
    if not isinstance(raw, dict) or set(raw) != set(SETTINGS_KEYS):
        raise ValueError("invalid_playoff_targets_configuration")
    out = {}
    for key, (kind, low, high) in SETTINGS_KEYS.items():
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, kind) or not low <= value <= high:
            raise ValueError("invalid_playoff_targets_configuration")
        out[key] = value
    return out


def settings():
    """The `playoff_targets` object of `config/league_projections.json`. Read
    only while the flag is on; `batch.settings()` never looks at it."""
    return parse_settings(json.loads(CONFIG_PATH.read_text()).get("playoff_targets"))


def is_seller(playoff_probability, saved_outlook):
    """The eligibility rule, in one place: a playoff chance strictly below
    50% in the forecast run, or a saved Rebuilding / Tanking outlook."""
    return bool(playoff_probability < SELLER_MAX_PLAYOFF or saved_outlook in SELLING_OUTLOOKS)


def sellers_now(sellers, live_outlooks):
    """The roster ids (as saved, strings) of the saved `sellers` that are
    selling under `live_outlooks` ({roster_id: saved outlook id or None})."""
    live = {str(k): v for k, v in (live_outlooks or {}).items()}
    return {rid for rid, s in sellers.items() if is_seller(s["playoff_probability"], live.get(rid))}


# ---------------------------------------------------------------------------
# The calculation (contract §6). Pure: no I/O, no flags, no clock.
# ---------------------------------------------------------------------------

def _floor(actual):
    """The lowest starter's points when every slot holds a rostered player,
    else None. With a full lineup of rostered players, a player who projects
    no higher than this cannot enter it (the legal lineups form a matroid, so
    the best one is found greedily from the top), and the re-solve is skipped."""
    rows = actual["lineup"]
    if actual["gaps"] or any(not r["player"] or r["player"].get("free_agent") or r["player"].get("hypothetical")
                             for r in rows):
        return None
    return min(decimal(r["player"]["points"]) for r in rows)


def _starters(lineup):
    return {(str(r["player"]["player_id"]), bool(r["player"].get("free_agent")))
            for r in lineup["lineup"] if r["player"] and not r["player"].get("hypothetical")}


def lineup_gains(ctx, roster_id, base, player_id, *, prune=True):
    """{week: lineup-lane gain} for `player_id` joining `roster_id`, over the
    unplayed weeks in `base` ({week: (detail, lineup, max PF lineup)}), or
    None when a week has no usable projection for him (unknown is not zero).
    A bye or a week the provider says he will not play is a known 0. `prune`
    skips the re-solve where `_floor` proves it cannot change; the answer is
    the same with or without it."""
    gains = {}
    for w, (detail, actual, _maximum) in base.items():
        value = ctx.points.get(w, {}).get(player_id)
        if not isinstance(value, Decimal):
            if value != season_points.BYE and (w, player_id) not in ctx.out:
                return None
            gains[w] = Decimal(0)
            continue
        floor = _floor(actual) if prune else None
        if floor is not None and value <= floor:
            gains[w] = Decimal(0)
            continue
        added, _ = ctx.lineups(roster_id, w, detail, add={player_id})
        gains[w] = decimal(added["points"]) - decimal(actual["points"])
    return gains


def _base(ctx, snapshot, roster_id):
    """({week: (detail, lineup, max PF lineup)} for the unplayed weeks, [played weeks])."""
    base, played = {}, []
    for week in sorted(snapshot["weeks"], key=lambda w: int(w["week"])):
        w, detail = int(week["week"]), week["teams"][str(roster_id)]
        if ctx.played(roster_id, w, detail):
            played.append(w)
        else:
            base[w] = (detail, *ctx.lineups(roster_id, w, detail))
    return base, played


def joined(ctx, roster_id, base, player_id):
    """The exact re-solve with `player_id` on `roster_id`, both lanes, every
    unplayed week in `base`, no pruning. Returns {"changes": {week: (dA, dM)}
    in `_lowered`'s sign (negative = the projection rises), "gain" (lineup
    lane, Decimal), "weeks_affected", "replaces": who leaves the starting
    lineup for him, with the number of weeks, most weeks first}."""
    changes, counts, affected, total = {}, {}, 0, Decimal(0)
    for w, (detail, actual, maximum) in base.items():
        if not isinstance(ctx.points.get(w, {}).get(player_id), Decimal):
            continue
        actual2, maximum2 = ctx.lineups(roster_id, w, detail, add={player_id})
        gain = decimal(actual2["points"]) - decimal(actual["points"])
        changes[w] = (-gain, decimal(maximum["points"]) - decimal(maximum2["points"]))
        total += gain
        if not gain:
            continue
        affected += 1
        left = sorted(_starters(actual) - _starters(actual2))
        # A slot nobody held (or a hypothetical bye fill) that he now fills.
        opened = max(0, len(_starters(actual2)) - len(_starters(actual)))
        for rep in [_replacement(ctx, p, fa) for p, fa in left] + [_replacement(ctx, None, False)] * opened:
            key = (rep["player_id"], rep["free_agent"])
            counts[key] = (rep, counts.get(key, (rep, 0))[1] + 1)
    replaces = sorted(({**rep, "weeks": n} for rep, n in counts.values()),
                      key=lambda r: (-r["weeks"], r["name"] is None, r["name"] or ""))
    return {"changes": changes, "gain": total, "weeks_affected": affected, "replaces": replaces}


def departed(ctx, roster_id, base, player_id):
    """{week: (dA, dM)} for `player_id` leaving `roster_id` with no starter
    coming back: Max PF moves' removal re-solve, over `base`'s unplayed weeks."""
    lost = {}
    for w, (detail, actual, maximum) in base.items():
        actual2, maximum2 = ctx.lineups(roster_id, w, detail, remove={player_id})
        lost[w] = (decimal(actual["points"]) - decimal(actual2["points"]),
                   decimal(maximum["points"]) - decimal(maximum2["points"]))
    return lost


def _candidate_ids(ctx, roster_id):
    roster = ctx.rosters[roster_id]
    reserve = set(roster.get("reserve", []))
    return sorted((set(roster.get("players", [])) | set(roster.get("taxi", [])) | reserve)
                  - (set() if ctx.include_reserve else reserve))


def compute(snapshot, result, free_agent_pool, options, *, names=None, trade_deadline=None, roster_id=None,
            seller_outlooks=None, owners=None, cancelled=lambda: False):
    """The saved playoff targets block for one team (contract §6). Pure.

    Inputs as `maxpf_moves.compute`, plus:
      seller_outlooks {roster_id: saved outlook id or None} for the other
                      teams, read by the caller when the job runs
      owners          {str(roster_id): [owner user ids]} (capture side
                      channel), saved so the read can look the outlooks up again
    Two steps. (1) For every player on a selling team, the exact lineup
    re-solve with him added to the viewer's roster, summed over the unplayed
    weeks. (2) For the `candidates` largest gains only: the same re-solve
    with him removed from his own team, then one paired re-simulation.
    Nothing given up is modelled: the viewer's roster loses no one.
    Output: a JSON-ready dict. "computed" is False with "reason":
    "not_eligible" when the team is not in the run. A malformed input or a
    cancellation raises `core.Unavailable` (callers record it).
    """
    roster_id = int(snapshot.get("viewer_roster_id") if roster_id is None else roster_id)
    cfg = result["config"]
    team = next((t for t in result["teams"] if t["roster_id"] == roster_id), None)
    block = {"version": VERSION, "computed": False, "reason": "not_eligible", "settings": dict(options),
             "settings_hash": settings_hash(options), "viewer_roster_id": roster_id,
             "trade_deadline": trade_deadline, "baseline": None, "sellers": {}, "skipped": None,
             "pool_size": 0, "candidates_total": 0, "rows": []}
    if team is None or roster_id not in {int(t["roster_id"]) for t in snapshot["teams"]}:
        return block
    ctx = _Context(snapshot, cfg, free_agent_pool, names)
    base, played = _base(ctx, snapshot, roster_id)
    weeks = sorted(int(w["week"]) for w in snapshot["weeks"])
    block["baseline"] = {"weeks_remaining": len(weeks), "first_week": weeks[0] if weeks else None,
                         "last_week": weeks[-1] if weeks else None, "weeks_excluded_played": len(played)}
    outlooks = {int(k): v for k, v in (seller_outlooks or {}).items()}
    for other in result["teams"]:
        rid = int(other["roster_id"])
        if rid != roster_id:
            block["sellers"][str(rid)] = {
                "name": other["name"], "playoff_probability": other["playoff_probability"],
                "eligible": is_seller(other["playoff_probability"], outlooks.get(rid)),
                "owner_ids": list((owners or {}).get(str(rid)) or [])}
    selling = sorted(int(rid) for rid, s in block["sellers"].items() if s["eligible"])
    now = team["playoff_probability"]
    # Nothing to compute: the read reaches the same answer from the same
    # saved figures, so `skipped` is a record, not an input.
    skipped = ("season_over" if not weeks else
               "after_trade_deadline" if trade_deadline and result.get("completed_weeks", 0) >= trade_deadline else
               "clinched" if team.get("playoff_clinched") else
               "eliminated" if team.get("playoff_eliminated") else
               "near_certain" if now >= options["near_certain_min"] - _EPSILON else
               "no_sellers" if not selling else None)
    block.update(computed=True, reason=None, skipped=skipped)
    if skipped:
        return block
    gains = []
    for seller in selling:
        for n, pid in enumerate(_candidate_ids(ctx, seller)):
            if n % 8 == 0 and cancelled():
                raise Unavailable("cancelled", state="cancelled")
            block["pool_size"] += 1
            by_week = lineup_gains(ctx, roster_id, base, pid)
            total = sum(by_week.values(), Decimal(0)) if by_week is not None else Decimal(0)
            if total > 0:
                gains.append((total, pid, seller))
    block["candidates_total"] = len(gains)
    chosen = sorted(gains, key=lambda g: (-g[0], g[1]))[:options["candidates"]]
    rows = []
    if chosen:
        small = {**cfg, "iterations": options["simulations_per_candidate"]}
        before = simulation.simulate(snapshot, small, cancelled=cancelled)
        seller_base = {}
        for _total, pid, seller in chosen:
            mine_with = joined(ctx, roster_id, base, pid)
            if seller not in seller_base:
                seller_base[seller] = _base(ctx, snapshot, seller)[0]
            # He joins the viewer and leaves his own team, which gets no starter back.
            shifted = _lowered(_lowered(snapshot, seller, departed(ctx, seller, seller_base[seller], pid)),
                               roster_id, mine_with["changes"])
            after = simulation.simulate(shifted, small, cancelled=cancelled)
            chance = _after_teams(result, before, after)[roster_id]["playoff_probability"]
            if chance <= now:
                continue
            name, reps, d_a = ctx.name(pid), mine_with["replaces"], mine_with["gain"]
            rows.append({
                "player_id": pid, "name": name, "short_name": short_name(name),
                "position": (ctx.positions.get(pid) or ["?"])[0], "seller_roster_id": seller,
                "lineup_gain": _whole(d_a), "lineup_gain_exact": str(d_a.quantize(Decimal("0.01"))),
                "weeks_affected": mine_with["weeks_affected"],
                "replaces": reps[:3], "replaces_more": max(0, len(reps) - 3),
                "playoff_probability": {"now": now, "after": chance},
                "passes_threshold": bool(chance - now >= options["min_playoff_gain"] - _EPSILON)})
        rows.sort(key=lambda r: (-(r["playoff_probability"]["after"] - now), -Decimal(r["lineup_gain_exact"]),
                                 r["player_id"]))
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
    block["rows"] = rows
    return block


# ---------------------------------------------------------------------------
# The read (contract §3-§4). Pure: every live value is passed in.
# ---------------------------------------------------------------------------

_ROW_KEYS = ("rank", "player_id", "name", "short_name", "position", "lineup_gain", "lineup_gain_exact",
             "weeks_affected", "replaces", "replaces_more", "playoff_probability", "passes_threshold")


def compose(view_state, saved, *, failure_reason=None, saved_outlook=None, live_outlooks=None, cuts=None):
    """The `playoff_targets` block served on the forecast read (contract §3, §4).

    view_state     the read's forecast state (`batch.view` after the model check)
    saved          the saved run's parsed `result_json` with its raw block, or None
    failure_reason the last attempt's reason (as `recommendation.unusable_reason` takes it)
    saved_outlook  the viewer's saved outlook id, or None
    live_outlooks  {roster_id: saved outlook id or None} for the other teams,
                   read now: the eligibility rule is applied again with it
    cuts           `recommendation.thresholds(...)` for the playoff band
    """
    from . import recommendation
    block = {"version": VERSION, "state": "unavailable", "reason": None, "viewer_roster_id": None, "captured_at": None,
             "saved_outlook": saved_outlook, "baseline": None, "eligible_teams": 0, "sellers_changed": False,
             "candidates_total": 0, "rows": []}
    reason = recommendation.unusable_reason(view_state, saved, failure_reason=failure_reason)
    if reason:
        return {**block, "reason": reason}
    viewer = saved.get("viewer_roster_id")
    teams = {t["roster_id"]: t for t in saved.get("teams", [])}
    team = teams.get(viewer)
    if team is None:
        return {**block, "reason": "team_not_found"}
    block.update(viewer_roster_id=viewer, captured_at=saved.get("captured_at"))
    raw = saved.get("playoff_targets")
    if not isinstance(raw, dict) or not raw.get("computed") or raw.get("version") != VERSION:
        return {**block, "reason": "not_computed"}
    base = raw["baseline"]
    if not base["weeks_remaining"]:
        return {**block, "state": "season_over"}
    deadline = raw.get("trade_deadline")
    if deadline and saved.get("completed_weeks", 0) >= deadline:
        return {**block, "state": "after_trade_deadline"}
    now = team["playoff_probability"]
    block["baseline"] = {
        "weeks_remaining": base["weeks_remaining"], "first_week": base["first_week"], "last_week": base["last_week"],
        "weeks_excluded_played": base["weeks_excluded_played"], "playoff_probability": now,
        "playoff_band": recommendation.classify(now, cuts) if cuts else None,
        # D-262: proven from the rules and roster-independent, so they hold
        # for every row's "after" too. Absent on an older run: not proven.
        "playoff_clinched": bool(team.get("playoff_clinched")),
        "playoff_eliminated": bool(team.get("playoff_eliminated"))}
    if block["baseline"]["playoff_clinched"]:
        return {**block, "state": "clinched"}
    if block["baseline"]["playoff_eliminated"]:
        return {**block, "state": "eliminated"}
    if now >= raw["settings"]["near_certain_min"] - _EPSILON:
        return {**block, "state": "near_certain"}
    sellers = raw.get("sellers") or {}
    selling = sellers_now(sellers, live_outlooks)
    block.update(eligible_teams=len(selling), candidates_total=raw.get("candidates_total", 0),
                 sellers_changed=selling != {rid for rid, s in sellers.items() if s["eligible"]})
    if not selling:
        return {**block, "state": "no_sellers"}
    rows = []
    for saved_row in raw.get("rows", []):
        rid = saved_row["seller_roster_id"]
        if str(rid) not in selling:
            continue
        seller = teams.get(rid) or {}
        rows.append({**{k: saved_row[k] for k in _ROW_KEYS},
                     "seller": {"roster_id": rid, "name": sellers[str(rid)]["name"],
                                "playoff_probability": sellers[str(rid)]["playoff_probability"],
                                "playoff_clinched": bool(seller.get("playoff_clinched")),
                                "playoff_eliminated": bool(seller.get("playoff_eliminated"))}})
    state = "ready" if any(r["passes_threshold"] for r in rows) else "no_targets"
    return {**block, "state": state, "rows": rows}
