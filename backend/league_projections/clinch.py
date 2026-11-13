"""Clinched / eliminated: a proof from the rules, not from the simulations (D-262).

A playoff chance printed as 100% or 0% claims there is no way to finish
otherwise. The simulation cannot prove that (250,000 seasons without a miss
is not a proof), so this module does, from the forecast's own snapshot:
current records, the remaining regular-season schedule and the number of
playoff spots. It never reads a probability and changes none.

Standings use the simulation's own definitions (`simulation.simulate`):
standing points 2 x wins + ties, then points for, points against, lottery.

Proven exactly, for a head-to-head league with every remaining week a full
schedule (one game per team) — ties inside games included, since a game's two
standing points split 2-0, 1-1 or 0-2:

- clinched: even losing every remaining game, fewer than `playoff_spots`
  other teams can finish level with or above the team on standing points (a
  level finish counts against it: the tiebreak is future points, which
  nothing can prove).
- eliminated: even winning every remaining game, at least `playoff_spots`
  other teams finish strictly above it on standing points in every outcome.

Each "can the other teams do it?" question is a small max-flow over the
remaining games, tried for every relevant set of rivals. With no games left
the final standings are known up to the seeded lottery, and the proof reads
them the way the simulation ranks them (exact ties count as not proven).

Not proven (both False, with a reason) whenever the rules are not fully
modelled here: a league that also plays the weekly median, a week that is
not a full schedule, weeks out of order, records that do not reconcile, too
many rival sets to try, or anything unexpected. Divisions, manual seeding and
best ball never reach a forecast (`provider.capture` refuses them). Never
raises.
"""
from __future__ import annotations

from collections import deque
from decimal import Decimal, InvalidOperation
from itertools import combinations

# Rival sets the whole league may try (all teams, both questions) before the
# answer is "not proven". A 12-team, 6-spot league needs at most
# 2 x 12 x C(11, 6) = 11,088; in practice a few dozen (each set is one small
# max-flow, well under a millisecond).
MAX_SETS = 20000


def _flow(games, cap):
    """Most standing points the remaining `games` (2 each, split 2-0, 1-1 or
    0-2) can hand out when team t may take at most `cap.get(t)` (no entry:
    unlimited). Max-flow: source -> game (2) -> its two teams -> sink (cap)."""
    teams = sorted({t for g in games for t in g}, key=str)
    tid = {t: 2 + len(games) + i for i, t in enumerate(teams)}
    sink = 2 + len(games) + len(teams)
    unlimited = 2 * len(games)
    graph = [dict() for _ in range(sink + 1)]

    def add(u, v, c):
        graph[u][v] = graph[u].get(v, 0) + c
        graph[v].setdefault(u, 0)
    for k, (a, b) in enumerate(games):
        add(0, 2 + k, 2)
        add(2 + k, tid[a], 2)
        add(2 + k, tid[b], 2)
    for t in teams:
        add(tid[t], sink, min(cap.get(t, unlimited), unlimited))
    flow = 0
    while True:
        parent = {0: None}
        queue = deque([0])
        while queue and sink not in parent:
            u = queue.popleft()
            for v, c in graph[u].items():
                if c > 0 and v not in parent:
                    parent[v] = u
                    queue.append(v)
        if sink not in parent:
            return flow
        push, v = unlimited, sink
        while parent[v] is not None:
            push = min(push, graph[parent[v]][v])
            v = parent[v]
        v = sink
        while parent[v] is not None:
            u = parent[v]
            graph[u][v] -= push
            graph[v][u] += push
            v = u
        flow += push


def _can_lift(games, need):
    """Can the games give every team in `need` at least that many points?"""
    if not games:
        return all(d <= 0 for d in need.values())
    cap = {t: 0 for g in games for t in g}
    cap.update({t: max(0, d) for t, d in need.items()})
    return _flow(games, cap) >= sum(max(0, d) for d in need.values())


def _can_hold(games, cap):
    """Can the games be decided with every team in `cap` gaining at most that?"""
    return _flow(games, cap) == 2 * len(games)


def _open_season(points, games, spots):
    """Clinched / eliminated with games left. `points`: standing points now.
    `games`: remaining (a, b) pairs. Returns {team: (clinched, eliminated)}
    or None when a question needs more than MAX_SETS rival sets."""
    out = {}
    teams = list(points)
    budget = [MAX_SETS]
    for x in teams:
        own = [g for g in games if x in g]
        rest = [g for g in games if x not in g]
        left = {t: sum(1 for g in rest if t in g) for t in teams}
        others = [t for t in teams if t != x]

        # Clinched? x loses out; its opponents bank the 2 points.
        low = dict(points)
        for a, b in own:
            low[b if a == x else a] += 2
        target = low[x]
        level = [t for t in others if low[t] >= target]
        reach = [t for t in others if low[t] < target and low[t] + 2 * left[t] >= target]
        short = spots - len(level)
        if short <= 0:
            clinched = False
        elif len(reach) < short:
            clinched = True
        else:
            sets = _capped(reach, short, budget)
            if sets is None:
                return None
            clinched = not any(_can_lift(rest, {t: target - low[t] for t in chosen}) for chosen in sets)

        # Eliminated? x wins out; its opponents get nothing from those games.
        high = dict(points)
        high[x] += 2 * len(own)
        target = high[x]
        above = [t for t in others if high[t] > target]
        threats = [t for t in others if high[t] <= target and high[t] + 2 * left[t] > target]
        room = spots - 1 - len(above)
        if room < 0:
            eliminated = True
        elif len(threats) <= room:
            eliminated = False
        else:
            sets = _capped(threats, room, budget)
            if sets is None:
                return None
            eliminated = not any(_can_hold(rest, {t: target - high[t] for t in threats if t not in free})
                                 for free in sets)
        out[x] = (clinched, eliminated)
    return out


def _capped(pool, size, budget):
    """combinations(pool, size), or None once the league's budget runs out."""
    out = []
    for c in combinations(pool, size):
        budget[0] -= 1
        if budget[0] < 0:
            return None
        out.append(c)
    return out


def _closed_season(teams, spots, decimals):
    """No games left: rank by (standing points, PF, PA) rounded as the
    simulation rounds them; an exact tie is the lottery, so not proven."""
    key = {t["roster_id"]: (2 * t["wins"] + t["ties"], round(float(Decimal(str(t["points_for"]))), decimals),
                            round(float(Decimal(str(t["points_against"]))), decimals)) for t in teams}
    out = {}
    for x, kx in key.items():
        at_or_above = sum(1 for t, k in key.items() if t != x and k >= kx)
        above = sum(1 for t, k in key.items() if t != x and k > kx)
        out[x] = (at_or_above < spots, above >= spots)
    return out


def prove(snapshot, *, decimals=None):
    """{"status": "exact" | "not_proven", "reason": str | None,
    "teams": {roster_id: (clinched, eliminated)}}. Never raises; on any doubt
    every team is (False, False)."""
    try:
        return _prove(snapshot, decimals)
    except Exception:
        return {"status": "not_proven", "reason": "unexpected_input", "teams": {}}


def _not(reason):
    return {"status": "not_proven", "reason": reason, "teams": {}}


def _prove(snapshot, decimals):
    if not isinstance(snapshot, dict):
        return _not("no_snapshot")
    if (snapshot.get("league_format") or {}).get("median_game"):
        return _not("median_game")
    if snapshot.get("divisions"):
        return _not("divisions")
    teams = snapshot.get("teams") or []
    ids = [t.get("roster_id") for t in teams]
    n = len(ids)
    spots = snapshot.get("playoff_spots")
    completed = snapshot.get("completed_weeks")
    if (n < 2 or len(set(ids)) != n or type(spots) is not int or not 0 < spots <= n
            or type(completed) is not int or completed < 0):
        return _not("invalid_league")
    for t in teams:
        record = [t.get(k) for k in ("wins", "losses", "ties")]
        if any(type(v) is not int or v < 0 for v in record) or sum(record) != completed:
            return _not("unreconciled_records")
    if sum(t["wins"] for t in teams) != sum(t["losses"] for t in teams):
        return _not("unreconciled_records")
    weeks = snapshot.get("weeks")
    if not isinstance(weeks, list):
        return _not("missing_schedule")
    numbers = [w.get("week") if isinstance(w, dict) else None for w in weeks]
    if numbers != list(range(completed + 1, completed + 1 + len(weeks))):
        return _not("partial_schedule")
    games = []
    for week in weeks:
        pairs = [tuple(g) for g in week.get("games") or []]
        seen = [r for g in pairs for r in g]
        if any(len(g) != 2 or g[0] == g[1] for g in pairs) or sorted(seen, key=str) != sorted(ids, key=str):
            return _not("partial_schedule")
        games.extend(pairs)
    if not games:
        if type(decimals) is not int:
            return _not("missing_precision")
        result = _closed_season(teams, spots, decimals)
    else:
        result = _open_season({t["roster_id"]: 2 * t["wins"] + t["ties"] for t in teams}, games, spots)
        if result is None:
            return _not("too_many_rival_sets")
    if any(c and e for c, e in result.values()):
        return _not("contradiction")
    return {"status": "exact", "reason": None, "teams": result}


def attach(result, snapshot):
    """`result` with `playoff_clinched` / `playoff_eliminated` on every team
    and a top-level `playoff_proof` {status, reason}. Never raises: on any
    failure the result comes back with every flag False."""
    try:
        decimals = (result.get("config") or {}).get("score_decimals")
        proof = prove(snapshot, decimals=decimals)
        flags = proof["teams"]
        teams = [{**t, "playoff_clinched": bool(flags.get(t.get("roster_id"), (False, False))[0]),
                  "playoff_eliminated": bool(flags.get(t.get("roster_id"), (False, False))[1])}
                 for t in result.get("teams") or []]
        return {**result, "teams": teams, "playoff_proof": {"status": proof["status"], "reason": proof["reason"]}}
    except Exception:
        return result


# ── Display (server-made strings) ────────────────────────────────────────
def odds_text(probability, *, clinched=False, eliminated=False, decimals=1):
    """A playoff chance as a percent at `decimals` places (1 or 0). It reads
    100% only when clinched is proven and 0% only when elimination is proven;
    otherwise ">99.9%" / "<0.1%" (">99%" / "<1%" at whole percents). Any other
    value prints exactly as before. Mirrors mobile/src/utils/playoffOdds.ts
    and web/js/playoff-odds.js (docs/cross-client-invariants.md)."""
    text = f"{probability * 100:.{decimals}f}"
    unit = 10 ** -decimals
    if float(text) >= 100 and not clinched:
        return f">{100 - unit:.{decimals}f}%"
    if float(text) <= 0 and not eliminated:
        return f"<{unit:.{decimals}f}%"
    return f"{text}%"
