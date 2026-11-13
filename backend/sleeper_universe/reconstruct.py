"""Rosters at the moment of a trade (research-plan §5.5), and the verifier.

The snapshot model (measured on the pilot, 2026-11-12). A week's matchup
``players`` list is the roster at a moment inside the week, not at the end of
the leg: replaying by leg matched 69.9% of roster-weeks, replaying by
timestamp with one instant per week matched up to 94.7%, best from Sunday
13:00 US Eastern (the main kickoff) and flat to about 17:00. So every
boundary here is a snapshot INSTANT, and transactions are placed by their
timestamp (``status_updated``; ``created`` ordered worse, 92.5%), never by
their leg:

* ``SnapshotClock.at(season, week)``: Sunday 13:00 America/New_York of NFL
  week ``week`` (week 1's Thursday is the Thursday after Labor Day; the UTC
  hour moves when US daylight time ends in November).
* With an NFL schedule and a player->team map, ``at(season, week, player)``
  is that player's own kickoff that week (a per-player lock: a Monday-night
  player can still move on Sunday afternoon). On the 2026 pilot seasons,
  with teams known for 76% of player-weeks, this matched 96.2% against 94.75%
  for the fixed rule. Without those inputs the fixed rule is used.

Measured ceiling and residual (pilot, fixed rule): 94.7% in season. Fitting
one instant per league-week (circular, an upper bound only) reaches 95.7%.
The residual is per player: moves made up to three days AFTER the player's
game that the snapshot still reflects (consistent with a matchup row being
re-saved later, e.g. on a stat correction) and moves before the instant that
it does not; there is no data to time those re-saves. Rows with an empty
``players`` list are not snapshots (a team with no lineup, a week past the
league's season): they are dropped and counted, never compared.

Three methods, chosen per trade:

* ``in_season`` -- a snapshot of the trade's own season exists before the
  trade's time: start from the latest one, apply moves after its instant and
  before the trade.
* ``forward`` -- no such snapshot, and the previous season of the lineage IS
  in the store (or the league is a startup, base = empty rosters): start from
  the previous season's FINAL ``/rosters`` (the frozen end-of-season roster;
  93.8% against week 1 on the pilot, against 83.0% for its last snapshot plus
  later moves), then this season's moves and completed drafts before the trade.
* ``backward`` -- no in-season base and the previous season is NOT in the
  store: start from this season's first snapshot and undo, newest first,
  every move up to that snapshot's instant dated at or after the trade, and
  every draft pick not finished before it. Extra uncertainty: a change before
  week 1 that left no transaction or pick (a commissioner edit, a reset) is
  invisible to it.

Draft picks are timed at the draft's end (Sleeper picks carry no time;
spreading them over the draft by pick number matched worse). Every completed
transaction counts whatever its type; failed and pending ones never do. Legs
are no longer used for reconstruction; the report still counts transactions
whose leg goes backwards in time order (``leg_time_inversions``).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass, field

INF = float("inf")


# ---------------------------------------------------------------------------
# Snapshot instants
# ---------------------------------------------------------------------------

def week1_thursday(season: int) -> dt.date:
    d = dt.date(int(season), 9, 1)
    while d.weekday() != 0:              # Labor Day: first Monday of September
        d += dt.timedelta(days=1)
    return d + dt.timedelta(days=3)


def us_daylight(day: dt.date) -> bool:
    """US daylight time by date: second Sunday of March to first Sunday of November."""
    start = dt.date(day.year, 3, 8)
    while start.weekday() != 6:
        start += dt.timedelta(days=1)
    end = dt.date(day.year, 11, 1)
    while end.weekday() != 6:
        end += dt.timedelta(days=1)
    return start <= day < end


def eastern_ms(day: dt.date, hour: int, minute: int = 0) -> float:
    utc_h = hour + (4 if us_daylight(day) else 5)
    t = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc) \
        + dt.timedelta(hours=utc_h, minutes=minute)
    return t.timestamp() * 1000


def load_kickoffs(path) -> dict:
    """{(season, week, team): epoch ms} from an nflverse games CSV (regular season)."""
    out = {}
    with open(path, newline="") as f:
        for g in csv.DictReader(f):
            if g.get("game_type") != "REG" or not g.get("gametime"):
                continue
            day = dt.date.fromisoformat(g["gameday"])
            hh, mm = (int(x) for x in g["gametime"].split(":"))
            ms = eastern_ms(day, hh, mm)
            for team in (g["away_team"], g["home_team"]):
                out[(int(g["season"]), int(g["week"]), team)] = ms
    return out


TEAM_ALIAS = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "OAK": "LV", "SD": "LAC"}


class SnapshotClock:
    """When a week's matchup snapshot was taken. Fixed rule by default;
    a per-player kickoff when ``kickoffs`` and ``teams`` are given (teams:
    {player_id: team} or {season: {player_id: team}})."""

    def __init__(self, kickoffs: dict | None = None, teams: dict | None = None):
        self.kickoffs = kickoffs or {}
        self.teams = teams or {}
        self.rule = "player_kickoff" if (self.kickoffs and self.teams) else "sunday_13_eastern"
        self._cache: dict = {}

    def fixed(self, season, week) -> float:
        key = (int(season), int(week))
        if key not in self._cache:
            sunday = week1_thursday(int(season)) + dt.timedelta(days=7 * (int(week) - 1) + 3)
            self._cache[key] = eastern_ms(sunday, 13)
        return self._cache[key]

    def _team(self, season, player):
        t = self.teams.get(str(season))
        t = t.get(player) if isinstance(t, dict) else self.teams.get(player)
        return TEAM_ALIAS.get(t, t) if isinstance(t, str) else None

    def at(self, season, week, player=None) -> float:
        if player is not None and self.rule == "player_kickoff":
            team = self._team(season, str(player))
            k = self.kickoffs.get((int(season), int(week), team)) if team else None
            if k is not None:
                return k
        return self.fixed(season, week)


DEFAULT_CLOCK = SnapshotClock()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class SeasonData:
    league_id: str
    season: int | None
    previous_league_id: str | None
    status: str | None = None
    snapshots: dict = field(default_factory=dict)   # week -> {roster_id: set}, non-empty rows
    empty_rows: int = 0                             # snapshot rows with no players (not compared)
    final: dict = field(default_factory=dict)       # roster_id -> set, /rosters as pulled
    txns: list = field(default_factory=list)        # complete, time-ordered
    drafts: list = field(default_factory=list)      # dicts: status,start,end,picks
    roster_ids: set = field(default_factory=set)


def _t(t) -> tuple:
    return (t.get("status_updated") or t.get("created") or 0, t.get("created") or 0,
            str(t.get("transaction_id")))


def load_season(conn, league_id) -> SeasonData | None:
    lg = conn.execute("SELECT season, previous_league_id, status FROM leagues WHERE league_id=?",
                      (league_id,)).fetchone()
    if lg is None:
        return None
    sd = SeasonData(str(league_id), lg["season"], lg["previous_league_id"], lg["status"])
    for r in conn.execute("SELECT week, roster_id, players_json FROM roster_weeks"
                          " WHERE league_id=? AND played=1", (league_id,)):
        players = set(json.loads(r["players_json"]))
        sd.roster_ids.add(r["roster_id"])
        if not players:
            sd.empty_rows += 1
            continue
        sd.snapshots.setdefault(r["week"], {})[r["roster_id"]] = players
    for r in conn.execute("SELECT roster_id, players_json FROM rosters WHERE league_id=?",
                          (league_id,)):
        sd.roster_ids.add(r["roster_id"])
        sd.final[r["roster_id"]] = set(json.loads(r["players_json"] or "[]"))
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


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

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


def pick_time(draft: dict) -> float:
    """Sleeper's pick objects carry no timestamp (backend/draft_board_service.py,
    ``picked_at``), so every pick of a COMPLETED draft is timed at the draft's
    end (``last_picked``, else ``start_time``). A draft not complete never
    counts as having happened (+inf)."""
    return draft["end"] if draft["status"] == "complete" else INF


def _events(sd):
    """[(time, order, kind, payload)] -- transactions and draft picks."""
    ev = [(_t(t)[0], _t(t), 0, t) for t in sd.txns]
    ev += [(pick_time(d), (pick_time(d), 0, d["draft_id"]), 1, p)
           for d in sd.drafts for p in d["picks"]]
    return ev


def _window(sd, lo, hi, *, exclude=None, undo=False):
    """Events whose entries fall in (lo(player), hi(player)], each entry
    tested with its own player's bounds; ordered by time (reversed to undo).
    Returns [(kind, payload)], transactions trimmed to their in-window entries."""
    out = []
    for tt, key, kind, ev in _events(sd):
        if kind:
            p = str(ev[1])
            if lo(p) < tt <= hi(p):
                out.append((key, kind, ev))
            continue
        if ev["transaction_id"] == exclude:
            continue
        adds = {p: r for p, r in (ev.get("adds") or {}).items() if lo(str(p)) < tt <= hi(str(p))}
        drops = {p: r for p, r in (ev.get("drops") or {}).items() if lo(str(p)) < tt <= hi(str(p))}
        if adds or drops:
            out.append((key, kind, dict(ev, adds=adds, drops=drops)))
    out.sort(key=lambda e: (e[0], e[1]), reverse=undo)
    return out


def _apply(r, events, undo=False):
    for _, kind, ev in events:
        if kind:
            (r.setdefault(int(ev[0]), set()).discard if undo
             else r.setdefault(int(ev[0]), set()).add)(str(ev[1]))
        else:
            (undo_transaction if undo else apply_transaction)(r, ev)


def _snap(clock, sd, week):
    return lambda p: clock.at(sd.season, week, p)


def _const(v):
    return lambda p: v


def _forward_base(sd, prev):
    """(rosters, base_league, base_week) at the start of sd's season, or None.
    The previous season's final /rosters; a startup starts empty."""
    if prev is not None and prev.final:
        return _copy(prev.final), prev.league_id, None
    if sd.previous_league_id is None:   # startup season: nothing came before
        return {rid: set() for rid in sd.roster_ids}, None, None
    return None


def forward_state(sd, prev, ts, exclude=None, clock=DEFAULT_CLOCK):
    base = _forward_base(sd, prev)
    if base is None:
        return None
    r, base_league, base_week = base
    _apply(r, _window(sd, _const(-INF), _const(ts - 0.5), exclude=exclude))
    return r, base_league, base_week


def backward_state(sd, ts, clock=DEFAULT_CLOCK):
    """Rosters just before time ``ts`` by undoing from the first snapshot."""
    if not sd.snapshots:
        return None
    f = min(sd.snapshots)
    r = _copy(sd.snapshots[f])
    _apply(r, _window(sd, _const(ts - 0.5), _snap(clock, sd, f), undo=True), undo=True)
    return r, sd.league_id, f


def in_season_state(sd, ts, exclude=None, clock=DEFAULT_CLOCK):
    weeks = [w for w in sd.snapshots if clock.fixed(sd.season, w) < ts]
    if not weeks or sd.season is None:
        return None
    w = max(weeks)
    r = _copy(sd.snapshots[w])
    _apply(r, _window(sd, _snap(clock, sd, w), _const(ts - 0.5), exclude=exclude))
    return r, sd.league_id, w


def state_for_trade(sd: SeasonData, prev: SeasonData | None, trade: dict,
                    clock=DEFAULT_CLOCK) -> dict:
    """Both (all) rosters of a trade just before it happened."""
    ts = _t(trade)[0]
    rids = [int(x) for x in trade.get("roster_ids") or []]
    out = {"method": "none", "rosters": {}, "base_league": None, "base_week": None,
           "alt_method": None, "alt_agrees": None}
    ins = in_season_state(sd, ts, trade["transaction_id"], clock) if sd.season else None
    if ins is not None:
        r, bl, bw = ins
        out.update(method="in_season", base_league=bl, base_week=bw)
    else:
        fwd = forward_state(sd, prev, ts, trade["transaction_id"], clock)
        bwd = backward_state(sd, ts, clock) if sd.season else None
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


def rosters_for_trade(conn, league_id: str, transaction_id: str, clock=DEFAULT_CLOCK) -> dict:
    """Public helper: the trade's rosters just before it, plus the method."""
    sd = load_season(conn, league_id)
    if sd is None:
        raise KeyError(league_id)
    trade = next(t for t in sd.txns if t["transaction_id"] == str(transaction_id))
    row = conn.execute("SELECT roster_ids_json FROM transactions WHERE league_id=? AND"
                       " transaction_id=?", (league_id, str(transaction_id))).fetchone()
    trade = dict(trade, roster_ids=json.loads(row["roster_ids_json"]))
    prev = load_season(conn, sd.previous_league_id) if sd.previous_league_id else None
    return state_for_trade(sd, prev, trade, clock)


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

def _compare(league_id, kind, week, got: dict, want: dict, events=()) -> list:
    """Per roster with a non-empty expected roster: matched or not, and for
    mismatches a likely cause. no_add_event: a player in the expected roster
    with no add (or draft pick) to that roster among the replayed events;
    no_drop_event: a player the replay keeps that the expected roster lacks,
    with no drop from it; wrong_roster: the player is expected on a different
    roster."""
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
    for rid in sorted(want):
        g, w = got.get(rid, set()), want.get(rid, set())
        if not w:
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


def verify_season(sd: SeasonData, prev: SeasonData | None, clock=DEFAULT_CLOCK) -> list:
    """'in_season': each snapshot replayed to the next one's instant, compared
    roster by roster (only rosters present, non-empty, in both). When the
    previous season is present (or for a startup): 'offseason_forward' -- the
    forward base plus this season's moves and completed drafts up to the first
    snapshot's instant, vs that snapshot; 'offseason_backward' -- the first
    snapshot undone back before every one of those, vs the forward base."""
    rows = []
    if sd.season is None:
        return rows
    weeks = sorted(sd.snapshots)
    for a, b in zip(weeks, weeks[1:]):
        r = _copy(sd.snapshots[a])
        events = _window(sd, _snap(clock, sd, a), _snap(clock, sd, b))
        _apply(r, events)
        want = {rid: ps for rid, ps in sd.snapshots[b].items() if rid in sd.snapshots[a]}
        rows += _compare(sd.league_id, "in_season", b, r, want, events)
    if weeks:
        f = weeks[0]
        base = _forward_base(sd, prev)
        if base is not None:
            r = _copy(base[0])
            events = _window(sd, _const(-INF), _snap(clock, sd, f))
            _apply(r, events)
            rows += _compare(sd.league_id, "offseason_forward", f, r, sd.snapshots[f], events)
            back = _copy(sd.snapshots[f])
            _apply(back, _window(sd, _const(-INF), _snap(clock, sd, f), undo=True), undo=True)
            want = {rid: ps for rid, ps in base[0].items() if rid in sd.snapshots[f]}
            rows += _compare(sd.league_id, "offseason_backward", f, back, want)
    return rows
