"""Rosters at the moment of a trade (research-plan §5.5), and the verifier.

Model. A played week's matchup snapshot (``roster_weeks``) is taken as the
roster at the END of that leg. Replaying a leg's completed transactions on
the previous snapshot should land on the next one; ``verify_season`` measures
exactly that. Events are always ordered by timestamp (``status_updated``, then
``created``, then id), never by an assumed leg: the docs do not say which leg
offseason trades are booked under.

Three methods, chosen per trade:

* ``in_season`` -- a played snapshot exists in the trade's own season at a
  leg before the trade's: start from the latest such snapshot, apply that
  season's transactions after it and before the trade.
* ``forward`` -- no such snapshot (an offseason or week-1 trade) and the
  previous season of the lineage IS in the store (or the league has no
  predecessor at all: a startup, base = empty rosters): start from the
  previous season's last snapshot, apply its later transactions, then this
  season's transactions and completed drafts before the trade, in time order.
* ``backward`` -- no in-season base and the previous season is NOT in the
  store (e.g. a 2026-only pull): start from this season's FIRST played
  snapshot and undo, newest first, every transaction up to that week dated at
  or after the trade (the trade included) and every draft not finished before
  the trade. Extra uncertainty: anything that changed a roster before week 1
  without leaving a transaction or a draft pick (a commissioner edit, a
  roster reset) is invisible to it, and a player added then dropped after the
  trade is restored correctly only if both moves are recorded.

When forward and backward are both possible both run, and ``alt_agrees``
records whether they give the same rosters for the trade's teams.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class SeasonData:
    league_id: str
    season: int | None
    previous_league_id: str | None
    snapshots: dict = field(default_factory=dict)   # week -> {roster_id: set}
    txns: list = field(default_factory=list)        # complete, time-ordered
    drafts: list = field(default_factory=list)      # dicts: status,start,end,picks
    roster_ids: set = field(default_factory=set)


def _t(t) -> tuple:
    return (t.get("status_updated") or t.get("created") or 0, t.get("created") or 0,
            str(t.get("transaction_id")))


def load_season(conn, league_id) -> SeasonData | None:
    lg = conn.execute("SELECT season, previous_league_id FROM leagues WHERE league_id=?",
                      (league_id,)).fetchone()
    if lg is None:
        return None
    sd = SeasonData(str(league_id), lg["season"], lg["previous_league_id"])
    for r in conn.execute("SELECT week, roster_id, players_json FROM roster_weeks"
                          " WHERE league_id=? AND played=1", (league_id,)):
        sd.snapshots.setdefault(r["week"], {})[r["roster_id"]] = set(json.loads(r["players_json"]))
        sd.roster_ids.add(r["roster_id"])
    for r in conn.execute("SELECT roster_id FROM rosters WHERE league_id=?", (league_id,)):
        sd.roster_ids.add(r["roster_id"])
    txns = []
    for r in conn.execute("SELECT transaction_id, type, leg, created, status_updated,"
                          " adds_json, drops_json FROM transactions WHERE league_id=?"
                          " AND status='complete'", (league_id,)):
        txns.append({"transaction_id": r["transaction_id"], "type": r["type"], "leg": r["leg"],
                     "created": r["created"], "status_updated": r["status_updated"],
                     "adds": json.loads(r["adds_json"]), "drops": json.loads(r["drops_json"])})
    sd.txns = sorted(txns, key=_t)
    for d in conn.execute("SELECT draft_id, status, start_time, last_picked FROM drafts"
                          " WHERE league_id=?", (league_id,)):
        picks = [(p["roster_id"], p["player_id"]) for p in conn.execute(
            "SELECT roster_id, player_id FROM draft_picks WHERE draft_id=?"
            " ORDER BY pick_no", (d["draft_id"],)) if p["player_id"]]
        sd.drafts.append({"draft_id": d["draft_id"], "status": d["status"],
                          "start": d["start_time"] or 0,
                          "end": d["last_picked"] or d["start_time"] or 0, "picks": picks})
    return sd


def _copy(rosters) -> dict:
    return {k: set(v) for k, v in rosters.items()}


def apply_transaction(rosters: dict, t: dict) -> None:
    for pid, rid in (t.get("drops") or {}).items():
        rosters.setdefault(int(rid), set()).discard(str(pid))
    for pid, rid in (t.get("adds") or {}).items():
        rosters.setdefault(int(rid), set()).add(str(pid))


def undo_transaction(rosters: dict, t: dict) -> None:
    for pid, rid in (t.get("adds") or {}).items():
        rosters.setdefault(int(rid), set()).discard(str(pid))
    for pid, rid in (t.get("drops") or {}).items():
        rosters.setdefault(int(rid), set()).add(str(pid))


def pick_time(draft: dict, pick) -> float:
    """When a draft pick put its player on a roster. Sleeper's pick objects
    carry no timestamp (see backend/draft_board_service.py, ``picked_at``), so
    every pick of a COMPLETED draft is timed at the draft's end
    (``last_picked``, else ``start_time``). A draft not complete never counts
    as having happened (time = +inf)."""
    return draft["end"] if draft["status"] == "complete" else float("inf")


def draft_events(sd) -> list:
    """[(time_key, 1, (roster_id, player_id))] for every draft pick."""
    return [((pick_time(d, p), 0, d["draft_id"]), 1, (p[0], p[1]))
            for d in sd.drafts for p in d["picks"]]


def apply_pick(rosters: dict, pick) -> None:
    rosters.setdefault(int(pick[0]), set()).add(str(pick[1]))


def undo_pick(rosters: dict, pick) -> None:
    rosters.setdefault(int(pick[0]), set()).discard(str(pick[1]))


def _run(r, events, undo=False):
    for _, kind, ev in sorted(events, key=lambda e: (e[0], e[1]), reverse=undo):
        if undo:
            (undo_pick if kind else undo_transaction)(r, ev)
        else:
            (apply_pick if kind else apply_transaction)(r, ev)


def _forward_base(sd, prev):
    """(rosters, base_league, base_week) at the start of sd's season, or None."""
    if prev is not None and prev.snapshots:
        w = max(prev.snapshots)
        r = _copy(prev.snapshots[w])
        for t in prev.txns:
            if (t["leg"] or 0) > w:
                apply_transaction(r, t)
        return r, prev.league_id, w
    if sd.previous_league_id is None:   # startup season: nothing came before
        return {rid: set() for rid in sd.roster_ids}, None, None
    return None


def forward_state(sd, prev, ts, exclude=None):
    base = _forward_base(sd, prev)
    if base is None:
        return None
    r, base_league, base_week = base
    events = [(_t(t), 0, t) for t in sd.txns
              if _t(t)[0] < ts and t["transaction_id"] != exclude]
    events += [e for e in draft_events(sd) if e[0][0] < ts]
    _run(r, events)
    return r, base_league, base_week


def backward_state(sd, ts, include_from=None):
    """Rosters just before time ``ts`` by undoing from the first snapshot."""
    if not sd.snapshots:
        return None
    f = min(sd.snapshots)
    r = _copy(sd.snapshots[f])
    events = [(_t(t), 0, t) for t in sd.txns if (t["leg"] or 0) <= f and _t(t)[0] >= ts]
    events += [e for e in draft_events(sd) if e[0][0] >= ts]
    _run(r, events, undo=True)
    return r, sd.league_id, f


def in_season_state(sd, leg, ts, exclude=None):
    weeks = [w for w in sd.snapshots if w < (leg or 0)]
    if not weeks:
        return None
    w = max(weeks)
    r = _copy(sd.snapshots[w])
    for t in sd.txns:
        if (t["leg"] or 0) > w and _t(t)[0] < ts and t["transaction_id"] != exclude:
            apply_transaction(r, t)
    return r, sd.league_id, w


def state_for_trade(sd: SeasonData, prev: SeasonData | None, trade: dict) -> dict:
    """Both (all) rosters of a trade just before it happened."""
    ts = _t(trade)[0]
    rids = [int(x) for x in trade.get("roster_ids") or []]
    out = {"method": "none", "rosters": {}, "base_league": None, "base_week": None,
           "alt_method": None, "alt_agrees": None}
    ins = in_season_state(sd, trade.get("leg"), ts, trade["transaction_id"])
    if ins is not None:
        r, bl, bw = ins
        out.update(method="in_season", base_league=bl, base_week=bw)
    else:
        fwd = forward_state(sd, prev, ts, trade["transaction_id"])
        bwd = backward_state(sd, ts)
        if fwd is not None:
            r, bl, bw = fwd
            out.update(method="forward", base_league=bl, base_week=bw)
            if bwd is not None:
                out["alt_method"] = "backward"
                out["alt_agrees"] = int(all(fwd[0].get(i, set()) == bwd[0].get(i, set())
                                            for i in rids))
        elif bwd is not None:
            r, bl, bw = bwd
            out.update(method="backward", base_league=bl, base_week=bw)
        else:
            return out
    out["rosters"] = {i: set(r.get(i, set())) for i in rids}
    return out


def rosters_for_trade(conn, league_id: str, transaction_id: str) -> dict:
    """Public helper: the trade's rosters just before it, plus the method."""
    sd = load_season(conn, league_id)
    if sd is None:
        raise KeyError(league_id)
    trade = next(t for t in sd.txns if t["transaction_id"] == str(transaction_id))
    row = conn.execute("SELECT roster_ids_json FROM transactions WHERE league_id=? AND"
                       " transaction_id=?", (league_id, str(transaction_id))).fetchone()
    trade = dict(trade, roster_ids=json.loads(row["roster_ids_json"]))
    prev = load_season(conn, sd.previous_league_id) if sd.previous_league_id else None
    return state_for_trade(sd, prev, trade)


def _compare(league_id, kind, week, got: dict, want: dict, events=()) -> list:
    """Per roster: matched or not, and for mismatches a likely cause.
    no_add_event: a player in the expected roster with no add (or draft pick)
    to that roster among the replayed events; no_drop_event: a player the
    replay keeps that the expected roster lacks, with no drop from it;
    wrong_roster: the player is expected on a different roster."""
    adds_to, drops_from = set(), set()
    for _, kind_e, ev in events:
        if kind_e:
            adds_to.add((str(ev[1]), int(ev[0])))
        else:
            adds_to.update((str(p), int(r)) for p, r in (ev.get("adds") or {}).items())
            drops_from.update((str(p), int(r)) for p, r in (ev.get("drops") or {}).items())
    where_got = {p: rid for rid, ps in got.items() for p in ps}
    where_want = {p: rid for rid, ps in want.items() for p in ps}
    rows = []
    for rid in sorted(set(got) | set(want)):
        g, w = got.get(rid, set()), want.get(rid, set())
        if not g and not w:
            continue
        c = {"n_no_add_event": 0, "n_no_drop_event": 0, "n_wrong_roster": 0, "n_other": 0}
        for p in w - g:
            if where_got.get(p) not in (None, rid):
                c["n_wrong_roster"] += 1
            elif (p, rid) not in adds_to:
                c["n_no_add_event"] += 1
            else:
                c["n_other"] += 1
        for p in g - w:
            if where_want.get(p) not in (None, rid):
                continue   # counted once, on the expected roster's side
            if (p, rid) not in drops_from:
                c["n_no_drop_event"] += 1
            else:
                c["n_other"] += 1
        rows.append({"league_id": league_id, "kind": kind, "week": week, "roster_id": rid,
                     "matched": int(g == w), "n_missing": len(w - g), "n_extra": len(g - w),
                     **c})
    return rows


def verify_season(sd: SeasonData, prev: SeasonData | None) -> list:
    """Replay every full week and compare with the next snapshot ('in_season').
    Every completed transaction row counts, whatever its type; failed or
    pending rows never do. Also, when the previous season is present (or for
    a startup): 'offseason_forward' -- forward base + this season's events up
    to the first snapshot vs that snapshot; and 'offseason_backward' -- the
    first snapshot undone back before every offseason event vs the forward
    base."""
    rows = []
    weeks = sorted(sd.snapshots)
    for a, b in zip(weeks, weeks[1:]):
        r = _copy(sd.snapshots[a])
        events = [(_t(t), 0, t) for t in sd.txns if a < (t["leg"] or 0) <= b]
        _run(r, events)
        rows += _compare(sd.league_id, "in_season", b, r, sd.snapshots[b], events)
    if weeks:
        f = weeks[0]
        base = _forward_base(sd, prev)
        if base is not None:
            r = _copy(base[0])
            events = [(_t(t), 0, t) for t in sd.txns if (t["leg"] or 0) <= f]
            events += [e for e in draft_events(sd) if e[0][0] != float("inf")]
            _run(r, events)
            rows += _compare(sd.league_id, "offseason_forward", f, r, sd.snapshots[f], events)
            back = backward_state(sd, float("-inf"))
            rows += _compare(sd.league_id, "offseason_backward", f, back[0], base[0])
    return rows
