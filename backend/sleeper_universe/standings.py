"""Standings as they stood after each week, playoff outcomes, and the check
of derived records against what Sleeper's rosters endpoint reports.

Rules applied (stored inputs let anyone recompute them):

* Regular season = played weeks before ``settings.playoff_week_start``
  (all played weeks when it is 0 or missing: a league with no playoffs). Weeks from the
  playoff start on never enter the record; they are in ``matchups`` with
  phase 'playoff' or 'consolation'.
* Head-to-head: the two rosters sharing a ``matchup_id`` that week; higher
  points win, equal points tie. A roster with no opponent gets no H2H result.
* Median (``settings.league_average_match == 1``): each roster also wins if
  its points are above the median of all rosters' points that week, loses if
  below, ties if equal. H2H, median and combined records are stored apart.
* Rank (RANK_RULE): combined win percentage ((W + T/2) / games), then points
  for, then roster id. This is Sleeper's common default; Sleeper exposes no
  tiebreak setting in the payloads read, and divisions are not used for rank
  (``division_rank`` is stored separately, so a division-first seeding can be
  recomputed).
* Games back of the last playoff spot: against the roster ranked
  ``playoff_teams`` that week, ((Wc - W) + (L - Lc)) / 2 on the combined
  record with a tie counting half a win and half a loss. Negative = ahead.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict

RANK_RULE = "combined win pct, then points for, then roster id"


def _wins_eq(r):
    return r["wins"] + 0.5 * r["ties"], r["losses"] + 0.5 * r["ties"]


def compute(conn, league_id) -> list:
    """``standings_weeks`` rows for one league-season (regular season only;
    playoff and consolation weeks are in ``matchups`` with their phase)."""
    lg = conn.execute("SELECT playoff_week_start, median_game, playoff_teams FROM leagues"
                      " WHERE league_id=?", (league_id,)).fetchone()
    pws, median, cut = lg["playoff_week_start"], lg["median_game"] == 1, lg["playoff_teams"]
    division = {r["roster_id"]: r["division"] for r in conn.execute(
        "SELECT roster_id, division FROM rosters WHERE league_id=?", (league_id,))}
    by_week = defaultdict(list)
    for r in conn.execute("SELECT week, roster_id, matchup_id, points FROM roster_weeks"
                          " WHERE league_id=? AND played=1 ORDER BY week, roster_id", (league_id,)):
        by_week[r["week"]].append(dict(r))
    keys = ("h2h_wins", "h2h_losses", "h2h_ties", "median_wins", "median_losses",
            "median_ties", "points_for", "points_against", "games")
    cum = {}
    out = []
    for week in sorted(by_week):
        rows = by_week[week]
        if pws and week >= pws:
            continue
        for r in rows:
            cum.setdefault(r["roster_id"], dict.fromkeys(keys, 0))
        res = {}
        groups = defaultdict(list)
        for r in rows:
            if r["matchup_id"] is not None:
                groups[r["matchup_id"]].append(r)
        for g in groups.values():
            if len(g) != 2:
                continue
            a, b = g
            pa, pb = a["points"] or 0.0, b["points"] or 0.0
            for me, them, pm, pt in ((a, b, pa, pb), (b, a, pb, pa)):
                c = cum[me["roster_id"]]
                c["points_against"] += pt
                c["games"] += 1
                k = "h2h_wins" if pm > pt else "h2h_losses" if pm < pt else "h2h_ties"
                c[k] += 1
                res[me["roster_id"]] = [k.split("_")[1][0].upper(), them["roster_id"]]
        med = statistics.median([r["points"] or 0.0 for r in rows]) if (median and rows) else None
        for r in rows:
            c = cum[r["roster_id"]]
            p = r["points"] or 0.0
            c["points_for"] += p
            if med is not None:
                c["games"] += 1
                c["median_wins" if p > med else "median_losses" if p < med else "median_ties"] += 1
        table = {}
        for rid, c in cum.items():
            w = c["h2h_wins"] + c["median_wins"]
            l = c["h2h_losses"] + c["median_losses"]
            t = c["h2h_ties"] + c["median_ties"]
            table[rid] = {"wins": w, "losses": l, "ties": t}
        def pct(rid):
            g = sum(table[rid].values())
            return (table[rid]["wins"] + 0.5 * table[rid]["ties"]) / g if g else 0.0
        order = sorted(cum, key=lambda rid: (-pct(rid), -cum[rid]["points_for"], rid))
        rank = {rid: i for i, rid in enumerate(order, 1)}
        div_rank = {}
        for d in {division.get(rid) for rid in order}:
            members = [rid for rid in order if division.get(rid) == d]
            for i, rid in enumerate(members, 1):
                div_rank[rid] = i
        cut_rid = order[cut - 1] if cut and len(order) >= cut else None
        for rid in order:
            c, tr = cum[rid], table[rid]
            gb = None
            if cut_rid is not None:
                cw, cl = _wins_eq(table[cut_rid])
                w, l = _wins_eq(tr)
                gb = ((cw - w) + (l - cl)) / 2
            wr = res.get(rid)
            out.append({
                "league_id": league_id, "week": week, "roster_id": rid,
                **{k: c[k] for k in keys[:6]}, **tr,
                "points_for": round(c["points_for"], 2),
                "points_against": round(c["points_against"], 2),
                "rank": rank[rid], "division": division.get(rid),
                "division_rank": div_rank.get(rid), "games_back": gb,
                "week_result": wr[0] if wr else None,
                "week_opponent": wr[1] if wr else None})
    return out


def outcome_rows(conn, league_id, final_standings: list) -> list:
    """Seed (inferred: final regular-season rank among the playoff teams),
    winners-bracket result, losers-bracket place, final finish, champion."""
    lg = conn.execute("SELECT playoff_teams, teams, status FROM leagues WHERE league_id=?",
                      (league_id,)).fetchone()
    cut = lg["playoff_teams"] or 0
    br = [dict(r) for r in conn.execute("SELECT * FROM brackets WHERE league_id=?", (league_id,))]
    win = [b for b in br if b["bracket"] == "winners"]
    lose = [b for b in br if b["bracket"] == "losers"]
    rank = {r["roster_id"]: r["rank"] for r in final_standings}
    wplace, lplace, max_round = {}, {}, {}
    for b in win:
        if b["p"] and b["w"] is not None and b["l"] is not None:
            wplace[b["w"]], wplace[b["l"]] = b["p"], b["p"] + 1
        for x in (b["t1"], b["t2"]):
            if x is not None:
                max_round[x] = max(max_round.get(x, 0), b["r"] or 0)
    for b in lose:
        if b["p"] and b["w"] is not None and b["l"] is not None:
            lplace[b["w"]], lplace[b["l"]] = b["p"], b["p"] + 1
    rids = [r[0] for r in conn.execute("SELECT roster_id FROM rosters WHERE league_id=?"
                                       " ORDER BY roster_id", (league_id,))]
    playoff = set(max_round)
    seeds = sorted((rid for rid in rids if rid in playoff), key=lambda r: rank.get(r, 99))
    seed = {rid: i for i, rid in enumerate(seeds, 1)}
    out = []
    for rid in rids:
        if lg["status"] != "complete":
            # A bracket published before the playoffs only projects seeds.
            finish, basis = None, "season_in_progress"
        elif rid in wplace:
            finish, basis = wplace[rid], "winners_bracket"
        elif rid in lplace and cut:
            finish, basis = cut + lplace[rid], "losers_bracket"
        elif rank.get(rid) is not None and not win:
            # No playoff bracket at all (playoffs off: playoff_week_start 0,
            # bracket null): the finish is the final regular-season rank, so
            # labelled; no playoff result is recorded, not even "missed".
            finish, basis = rank[rid], "regular_season_rank"
        else:
            finish, basis = None, "unknown"
        has_bracket = bool(win)
        done = lg["status"] == "complete" and has_bracket
        out.append({"league_id": league_id, "roster_id": rid,
                    "seed": seed.get(rid) if done else None,
                    "made_playoffs": int(rid in playoff) if done else None,
                    "playoff_round_reached": max_round.get(rid),
                    "winners_place": wplace.get(rid), "losers_place": lplace.get(rid),
                    "final_place": finish, "finish_basis": basis,
                    "champion": int(wplace.get(rid) == 1) if done else None})
    return out


def check_reported(conn, league_id, final_standings: list) -> dict:
    """Derived final regular-season record vs ``/rosters`` settings."""
    status = conn.execute("SELECT status FROM leagues WHERE league_id=?",
                          (league_id,)).fetchone()["status"]
    derived = {r["roster_id"]: r for r in final_standings}
    kinds = defaultdict(int)
    for r in conn.execute("SELECT * FROM rosters WHERE league_id=?", (league_id,)):
        d = derived.get(r["roster_id"])
        if d is None:
            if (r["wins"] or 0) + (r["losses"] or 0) + (r["ties"] or 0) > 0:
                kinds["roster_missing_from_matchups"] += 1
            continue
        for k in ("wins", "losses", "ties"):
            if r[k] is not None and int(r[k]) != int(d[k]):
                kinds[k] += 1
        for k, dk in (("fpts", "points_for"), ("fpts_against", "points_against")):
            if r[k] is not None and abs(float(r[k]) - float(d[dk])) > 0.011:
                kinds[dk] += 1
    rec = not any(k in kinds for k in ("wins", "losses", "ties", "roster_missing_from_matchups"))
    pts = not any(k in kinds for k in ("points_for", "points_against"))
    # Records and points are judged apart: a stat correction after the week
    # moves Sleeper's fpts without any bug here, and never changes a record.
    return {"league_id": league_id, "status": status, "matched": int(not kinds),
            "record_matched": int(rec), "points_matched": int(pts),
            "kinds_json": json.dumps(dict(sorted(kinds.items())), sort_keys=True)}


def standing_for_trade(conn, league_id, transaction_id) -> dict:
    """Each side's standing at the trade's date.

    In season: the record after the last played regular-season week before
    the trade's leg. Before any played week: the previous season's final
    regular-season standing and finish if that season is in the store, else
    ``basis = 'prior_season_not_in_store'``."""
    t = conn.execute("SELECT leg, roster_ids_json FROM transactions WHERE league_id=? AND"
                     " transaction_id=?", (league_id, str(transaction_id))).fetchone()
    if t is None:
        raise KeyError(transaction_id)
    lg = conn.execute("SELECT previous_league_id, playoff_week_start FROM leagues"
                      " WHERE league_id=?", (league_id,)).fetchone()
    out = {}
    for rid in json.loads(t["roster_ids_json"]):
        s = conn.execute("SELECT * FROM standings_weeks WHERE league_id=? AND roster_id=? AND"
                         " week<? ORDER BY week DESC LIMIT 1",
                         (league_id, rid, t["leg"] or 0)).fetchone()
        if s is not None:
            pws = lg["playoff_week_start"]
            out[rid] = {"basis": "current_season", "week": s["week"],
                        "wins": s["wins"], "losses": s["losses"], "ties": s["ties"],
                        "points_for": s["points_for"], "rank": s["rank"],
                        "games_back": s["games_back"],
                        # With no playoffs (pws 0) every scheduled week is regular
                        # season: count the scheduled weeks still to come.
                        "weeks_remaining": (pws - 1 - s["week"]) if pws else conn.execute(
                            "SELECT COUNT(DISTINCT week) FROM matchups WHERE league_id=? AND"
                            " roster_id=? AND week>? AND phase='regular'",
                            (league_id, rid, s["week"])).fetchone()[0]}
            continue
        prev = lg["previous_league_id"]
        have = prev and conn.execute("SELECT 1 FROM pull_checkpoints WHERE league_id=?",
                                     (prev,)).fetchone()
        if not have:
            out[rid] = {"basis": "prior_season_not_in_store"}
            continue
        s = conn.execute("SELECT * FROM standings_weeks WHERE league_id=? AND roster_id=?"
                         " ORDER BY week DESC LIMIT 1", (prev, rid)).fetchone()
        o = conn.execute("SELECT final_place, champion, made_playoffs FROM outcomes WHERE"
                         " league_id=? AND roster_id=?", (prev, rid)).fetchone()
        out[rid] = {"basis": "prior_season_final", "league_id": prev,
                    "wins": s["wins"] if s else None, "losses": s["losses"] if s else None,
                    "ties": s["ties"] if s else None,
                    "points_for": s["points_for"] if s else None,
                    "rank": s["rank"] if s else None,
                    "final_place": o["final_place"] if o else None,
                    "made_playoffs": o["made_playoffs"] if o else None,
                    "champion": o["champion"] if o else None}
    return out
