"""Stripped bundle -> base-table rows (pure, no I/O)."""
from __future__ import annotations

import json

NON_STARTER_SLOTS = {"BN", "TAXI", "IR"}
IDP_SLOTS = {"DL", "LB", "DB", "IDP_FLEX", "DE", "DT", "CB", "S"}


def _j(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def unusual_scoring(scoring: dict) -> bool:
    """Fixed rule (research-plan §5.8 'unusual scoring'): reception points not
    in {0, 0.25, 0.5, 1}; passing TD not in {4, 5, 6}; rushing or receiving TD
    not 6; tight-end bonus above 1.0 per catch. Missing keys are not unusual."""
    def off(key, allowed):
        v = scoring.get(key)
        return v is not None and float(v) not in allowed
    return (off("rec", {0.0, 0.25, 0.5, 1.0}) or off("pass_td", {4.0, 5.0, 6.0})
            or off("rush_td", {6.0}) or off("rec_td", {6.0})
            or float(scoring.get("bonus_rec_te") or 0) > 1.0)


def league_features(lg: dict) -> dict:
    s = lg.get("settings") or {}
    sc = lg.get("scoring_settings") or {}
    pos = lg.get("roster_positions") or []
    season = lg.get("season")
    return {
        "league_id": str(lg["league_id"]),
        "season": int(season) if season is not None else None,
        "previous_league_id": (str(lg["previous_league_id"])
                               if lg.get("previous_league_id") not in (None, "", "0", 0) else None),
        "status": lg.get("status"),
        "teams": lg.get("total_rosters") or s.get("num_teams"),
        "roster_positions_json": _j(pos),
        "n_starters": sum(1 for p in pos if p not in NON_STARTER_SLOTS),
        "bench_slots": sum(1 for p in pos if p == "BN"),
        "taxi_slots": s.get("taxi_slots"),
        "reserve_slots": s.get("reserve_slots"),
        "superflex": int("SUPER_FLEX" in pos),
        "two_qb": int(pos.count("QB") >= 2),
        "idp": int(any(p in IDP_SLOTS for p in pos)),
        "te_premium": sc.get("bonus_rec_te") or 0,
        "ppr": sc.get("rec"),
        "pass_td": sc.get("pass_td"),
        "median_game": s.get("league_average_match"),
        "playoff_teams": s.get("playoff_teams"),
        "playoff_week_start": s.get("playoff_week_start"),
        "trade_deadline": s.get("trade_deadline"),
        "waiver_type": s.get("waiver_type"),
        "faab": int(s.get("waiver_type") == 2),
        "faab_budget": s.get("waiver_budget"),
        "best_ball": s.get("best_ball"),
        "league_type": s.get("type"),
        "unusual_scoring": int(unusual_scoring(sc)),
        "scoring_settings_json": _j(sc),
        "settings_json": _j(s),
    }


def week_complete(season, week, state) -> bool | None:
    """Is this NFL week over, per ``/state/nfl`` (one read per run)? None
    when the state is unknown. ``state.week`` is the week in progress."""
    if not isinstance(state, dict) or season is None:
        return None
    try:
        ss, sw = int(state.get("season")), int(state.get("week") or 0)
    except (TypeError, ValueError):
        return None
    st = state.get("season_type")
    if season < ss:
        return True
    if season > ss or st == "pre":
        return False
    if st in ("post", "off"):
        return True
    return week < sw


def matchup_phase(week, roster_id, pws, winners: list) -> str:
    """regular before the playoff start week; from it on, 'playoff' if the
    roster has a winners-bracket game in round (week - pws + 1), else
    'consolation'. One week per round is assumed; two-week rounds would be
    labelled 'consolation' in their second week (a pilot check)."""
    if not pws or week < pws:
        return "regular"
    rnd = week - pws + 1
    if any(b.get("r") == rnd and roster_id in (b.get("t1"), b.get("t2")) for b in winners):
        return "playoff"
    return "consolation"


def bundle_rows(bundle: dict, nfl_state: dict | None = None) -> dict:
    """Map one stripped league-season bundle to rows for every base table.

    ``played`` (a week usable as a roster snapshot and a standings result):
    the NFL state says the week is over AND some roster scored. A completed
    week where nobody scored is a week with no fantasy games (after the
    league's season). Without a state, scored weeks count as played."""
    lg = bundle["league"]
    lid = str(lg["league_id"])
    feats = league_features(lg)
    season, pws = feats["season"], feats["playoff_week_start"]
    rows: dict[str, list] = {"leagues": [feats]}
    rows["league_members"] = [
        {"league_id": lid, "user_key": u["user_key"], "is_commissioner": int(u["is_owner"])}
        for u in bundle.get("users") or []]
    rows["rosters"] = []
    for r in bundle.get("rosters") or []:
        if r.get("roster_id") is None:
            continue
        st = r.get("settings") or {}
        rows["rosters"].append({
            "league_id": lid, "roster_id": r["roster_id"], "owner_key": r["owner_key"],
            "co_owner_keys_json": _j(r["co_owner_keys"]), "players_json": _j(r["players"]),
            "starters_json": _j(r["starters"]), "reserve_json": _j(r["reserve"]),
            "taxi_json": _j(r["taxi"]), "wins": st.get("wins"), "losses": st.get("losses"),
            "ties": st.get("ties"),
            "fpts": (st.get("fpts") or 0) + (st.get("fpts_decimal") or 0) / 100.0,
            "fpts_against": (st.get("fpts_against") or 0) + (st.get("fpts_against_decimal") or 0) / 100.0,
            "ppts": ((st.get("ppts") or 0) + (st.get("ppts_decimal") or 0) / 100.0
                     if st.get("ppts") is not None else None),
            "division": st.get("division"),
            "waiver_budget_used": st.get("waiver_budget_used"),
        })
    winners = bundle.get("winners_bracket") or []
    rows["roster_weeks"], rows["matchups"] = [], []
    for week, ms in sorted((bundle.get("matchups") or {}).items(), key=lambda kv: int(kv[0])):
        week = int(week)
        has_points = int(any((m.get("points") or 0) > 0 for m in ms))
        done = week_complete(season, week, nfl_state)
        played = has_points if done is None else int(bool(done) and bool(has_points))
        by_mid: dict = {}
        for m in ms:
            if m.get("matchup_id") is not None:
                by_mid.setdefault(m["matchup_id"], []).append(m["roster_id"])
        for m in ms:
            if m.get("roster_id") is None:
                continue
            rid = m["roster_id"]
            pair = by_mid.get(m.get("matchup_id"), [])
            opp = [x for x in pair if x != rid] if len(pair) == 2 else []
            rows["roster_weeks"].append({
                "league_id": lid, "week": week, "roster_id": rid,
                "matchup_id": m.get("matchup_id"), "players_json": _j(m["players"]),
                "starters_json": _j(m["starters"]),
                "players_points_json": _j(m.get("players_points") or {}),
                "starters_points_json": _j(m.get("starters_points") or []),
                "points": m.get("points"), "played": played, "has_points": has_points})
            rows["matchups"].append({
                "league_id": lid, "week": week, "roster_id": rid,
                "matchup_id": m.get("matchup_id"), "opponent_roster": opp[0] if opp else None,
                "paired": int(bool(opp)), "points": m.get("points"),
                "phase": matchup_phase(week, rid, pws, winners), "played": played})
    rows["transactions"] = []
    seen = set()
    for leg, ts in sorted((bundle.get("transactions") or {}).items(), key=lambda kv: int(kv[0])):
        for t in ts:
            tid = t.get("transaction_id")
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            rows["transactions"].append({
                "league_id": lid, "transaction_id": str(tid), "type": t.get("type"),
                "status": t.get("status"),
                "leg": t["leg"] if t.get("leg") is not None else int(leg),
                "created": t.get("created"), "status_updated": t.get("status_updated"),
                "creator_key": t.get("creator_key"), "roster_ids_json": _j(t["roster_ids"]),
                "consenter_ids_json": _j(t["consenter_ids"]), "adds_json": _j(t["adds"]),
                "drops_json": _j(t["drops"]), "draft_picks_json": _j(t["draft_picks"]),
                "waiver_budget_json": _j(t["waiver_budget"]),
                "waiver_bid": (t.get("settings") or {}).get("waiver_bid"),
                "notes_code": t.get("notes_code")})
    rows["drafts"], rows["draft_picks"] = [], []
    for d in bundle.get("drafts") or []:
        if d.get("draft_id") is None:
            continue
        ds = d.get("settings") or {}
        rows["drafts"].append({
            "draft_id": str(d["draft_id"]), "league_id": lid,
            "season": None if d.get("season") is None else str(d["season"]),
            "type": d.get("type"), "status": d.get("status"),
            "start_time": d.get("start_time"), "last_picked": d.get("last_picked"),
            "rounds": ds.get("rounds"), "teams": ds.get("teams"),
            "slot_to_roster_json": _j(d.get("slot_to_roster_id") or {}),
            "draft_order_json": _j(d.get("draft_order") or {})})
        for p in (bundle.get("draft_picks") or {}).get(str(d["draft_id"]), []):
            if p.get("pick_no") is None:
                continue
            rows["draft_picks"].append({
                "draft_id": str(d["draft_id"]), "pick_no": p["pick_no"], "round": p["round"],
                "draft_slot": p["draft_slot"], "roster_id": p["roster_id"],
                "player_id": None if p.get("player_id") is None else str(p["player_id"]),
                "picked_by_key": p.get("picked_by_key"), "is_keeper": int(p["is_keeper"]),
                "position": p.get("position")})
    rows["traded_picks"] = [{
        "league_id": lid, "season": None if p.get("season") is None else str(p["season"]),
        "round": p["round"], "orig_roster": p["roster_id"], "owner_roster": p["owner_id"],
        "previous_owner_roster": p["previous_owner_id"]}
        for p in bundle.get("traded_picks") or []]
    rows["brackets"] = []
    for name in ("winners_bracket", "losers_bracket"):
        for b in bundle.get(name) or []:
            if b.get("m") is None:
                continue
            rows["brackets"].append({
                "league_id": lid, "bracket": name.split("_")[0], "r": b["r"], "m": b["m"],
                "t1": b["t1"], "t2": b["t2"], "w": b["w"], "l": b["l"], "p": b["p"]})
    return rows
