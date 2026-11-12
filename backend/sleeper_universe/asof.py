"""Everything an outlook rebuild needs for a trade, as of the trade.

``outlook_inputs(conn, league_id, transaction_id)`` returns, for each side:

* roster: the reconstructed roster just before the trade (``reconstruct``),
  each player's league points in the weeks already played, and the weeks he
  started (for this roster, and for any roster);
* standings: record, points for, rank, games back and weeks left after the
  last regular-season week completed before the trade (``standings``);
* schedule: opponents already played with results, and the opponents still
  to play in the regular season with THEIR record and points for at the same
  date.

The as-of rule: a week counts as known only if it is a played regular-season
week strictly before the trade's leg. No points, results or standings from
the trade's own week or later are returned; remaining weeks carry only the
week number and the opponent (the schedule is fixed before the season). No
playoff odds are computed here.

Exception, stated in the output: a roster reconstructed by the ``backward``
method is DERIVED from a later snapshot (the roster it returns is still the
roster at the trade's time; no later points or results are included).
"""
from __future__ import annotations

import json
from collections import defaultdict

from . import reconstruct as rc
from . import standings as stnd
from .report import BACKWARD_NOTE


def outlook_inputs(conn, league_id, transaction_id) -> dict:
    lid, txid = str(league_id), str(transaction_id)
    t = conn.execute("SELECT leg, status_updated, created, roster_ids_json FROM transactions"
                     " WHERE league_id=? AND transaction_id=?", (lid, txid)).fetchone()
    if t is None:
        raise KeyError(txid)
    lg = conn.execute("SELECT * FROM leagues WHERE league_id=?", (lid,)).fetchone()
    pws = lg["playoff_week_start"]
    leg = t["leg"] or 0
    known = [r[0] for r in conn.execute(
        "SELECT DISTINCT week FROM standings_weeks WHERE league_id=? AND week<? ORDER BY week",
        (lid, leg))]
    as_of = known[-1] if known else None
    recon = rc.rosters_for_trade(conn, lid, txid)
    standing = stnd.standing_for_trade(conn, lid, txid)
    table = {}
    if as_of is not None:
        table = {r["roster_id"]: dict(r) for r in conn.execute(
            "SELECT * FROM standings_weeks WHERE league_id=? AND week=?", (lid, as_of))}
    pts = defaultdict(lambda: defaultdict(float))       # player -> week -> points
    started_any = defaultdict(int)
    started_by = defaultdict(int)                       # (roster, player)
    if as_of is not None:
        for r in conn.execute("SELECT week, roster_id, starters_json, players_points_json"
                              " FROM roster_weeks WHERE league_id=? AND played=1 AND week<=?"
                              " AND week IN (SELECT DISTINCT week FROM standings_weeks"
                              " WHERE league_id=?)", (lid, as_of, lid)):
            for p, v in json.loads(r["players_points_json"]).items():
                pts[p][r["week"]] += v or 0.0
            for p in json.loads(r["starters_json"]):
                if p and p != "0":
                    started_any[p] += 1
                    started_by[(r["roster_id"], p)] += 1
    sides = {}
    for rid in json.loads(t["roster_ids_json"]):
        rid = int(rid)
        players = sorted(recon["rosters"].get(rid, set()))
        played = []
        if as_of is not None:
            for s in conn.execute("SELECT s.week, s.week_opponent, s.week_result, m.points,"
                                  " o.points AS opp_points FROM standings_weeks s"
                                  " LEFT JOIN matchups m ON m.league_id=s.league_id AND"
                                  " m.week=s.week AND m.roster_id=s.roster_id"
                                  " LEFT JOIN matchups o ON o.league_id=s.league_id AND"
                                  " o.week=s.week AND o.roster_id=s.week_opponent"
                                  " WHERE s.league_id=? AND s.roster_id=? AND s.week<=?"
                                  " ORDER BY s.week", (lid, rid, as_of)):
                played.append({"week": s["week"], "opponent": s["week_opponent"],
                               "result": s["week_result"], "points": s["points"],
                               "opponent_points": s["opp_points"]})
        remaining = []
        for m in conn.execute("SELECT week, opponent_roster, paired FROM matchups WHERE"
                              " league_id=? AND roster_id=? AND week>? AND phase='regular'"
                              " ORDER BY week", (lid, rid, as_of or 0)):
            o = table.get(m["opponent_roster"])
            remaining.append({
                "week": m["week"], "opponent": m["opponent_roster"], "paired": m["paired"],
                "opponent_record": ([o["wins"], o["losses"], o["ties"]] if o
                                    else ([0, 0, 0] if m["opponent_roster"] is not None else None)),
                "opponent_points_for": o["points_for"] if o else (0.0 if m["opponent_roster"] is not None else None)})
        sides[rid] = {
            "roster": [{"player_id": p,
                        "points_so_far": round(sum(pts[p].values()), 2),
                        "weekly_points": {str(w): v for w, v in sorted(pts[p].items())},
                        "started_weeks": started_any[p],
                        "started_weeks_this_roster": started_by[(rid, p)]} for p in players],
            "standing": standing.get(rid),
            "played": played,
            "remaining": remaining,
        }
    return {"league_id": lid, "transaction_id": txid, "leg": t["leg"],
            "trade_ts": t["status_updated"] or t["created"], "as_of_week": as_of,
            "playoff_week_start": pws, "recon_method": recon["method"],
            "recon_note": BACKWARD_NOTE if recon["method"] == "backward" else None,
            "rank_rule": stnd.RANK_RULE, "sides": sides}
