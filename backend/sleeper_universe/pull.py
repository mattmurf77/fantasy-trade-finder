"""Pull one league-season (about 44 requests) and checkpoint it.

Everything is fetched into memory, stripped by the allow-lists, then written
in one transaction with the raw file (``Store.save_league_season``). A kill
anywhere before that commit leaves no checkpoint and the league-season is
redone whole on the next run.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import identity as ident
from .client import RequestFailed
from .normalise import bundle_rows

LEGS = range(1, 19)
WEEKS = range(1, 19)


class LeagueGone(Exception):
    pass


def fetch_bundle(client, ring, col, league_id: str) -> dict:
    def get(path):
        obj = client.get(path)
        ident.harvest(obj, col)
        return obj

    lid = str(league_id)
    league = get(f"/league/{lid}")
    if not isinstance(league, dict):
        raise LeagueGone(lid)
    bundle = {"league": ident.strip_league(league, ring, col)}
    bundle["rosters"] = ident.strip_rosters(get(f"/league/{lid}/rosters"), ring, col)
    bundle["users"] = ident.strip_users(get(f"/league/{lid}/users"), ring, col)
    bundle["transactions"] = {
        str(leg): ident.strip_transactions(get(f"/league/{lid}/transactions/{leg}"), ring, col)
        for leg in LEGS}
    bundle["matchups"] = {
        str(w): ident.strip_matchups(get(f"/league/{lid}/matchups/{w}"), ring, col)
        for w in WEEKS}
    drafts = ident.strip_drafts(get(f"/league/{lid}/drafts"), ring, col)
    bundle["drafts"] = drafts
    bundle["draft_picks"] = {
        str(d["draft_id"]): ident.strip_draft_picks(get(f"/draft/{d['draft_id']}/picks"), ring, col)
        for d in drafts if d.get("draft_id") is not None}
    bundle["traded_picks"] = ident.strip_traded_picks(get(f"/league/{lid}/traded_picks"), ring, col)
    bundle["winners_bracket"] = ident.strip_bracket(get(f"/league/{lid}/winners_bracket"), ring, col)
    bundle["losers_bracket"] = ident.strip_bracket(get(f"/league/{lid}/losers_bracket"), ring, col)
    return bundle


def fetch_nfl_state(client) -> dict | None:
    """``/state/nfl`` once per run: which NFL week is in progress."""
    st = client.get("/state/nfl")
    if not isinstance(st, dict):
        return None
    keep = ("season", "week", "season_type", "leg", "display_week", "previous_season",
            "league_season", "season_start_date")
    return {k: ident._token(st.get(k)) for k in keep if st.get(k) is not None}


def pull(store, client, ring, col, *, seasons, run_id, limit=None,
         refresh_incomplete=False, nfl_state=None, log=print,
         clock=time.monotonic) -> dict:
    todo = store.leagues_to_pull(seasons, refresh_incomplete)
    if limit is not None:
        todo = todo[:limit]
    stats = {"pulled": 0, "failed": 0, "gone": 0, "queued": len(todo)}
    for i, row in enumerate(todo, 1):
        lid, season = row["league_id"], row["season"]
        before = client.total_requests
        t0 = clock()
        try:
            bundle = fetch_bundle(client, ring, col, lid)
        except LeagueGone:
            store.record_failure(lid, season, run_id, "not_found")
            stats["gone"] += 1
            continue
        except RequestFailed as e:
            store.record_failure(lid, season, run_id, f"{e.endpoint}:{e.status}")
            stats["failed"] += 1
            log(f"[{i}/{len(todo)}] league {lid}: failed ({e.endpoint} {e.status})")
            continue
        rows = bundle_rows(bundle, nfl_state)
        keys = set()
        for r in bundle["rosters"]:
            keys.add(r["owner_key"])
            keys.update(r["co_owner_keys"])
        keys.update(u["user_key"] for u in bundle["users"])
        for ts in bundle["transactions"].values():
            keys.update(t["creator_key"] for t in ts)
        for ps in bundle["draft_picks"].values():
            keys.update(p["picked_by_key"] for p in ps)
        for d in bundle["drafts"]:
            keys.update(d["draft_order"])
        store.save_league_season(
            bundle, rows, run_id=run_id, requests=client.total_requests - before,
            seconds=round(clock() - t0, 3),
            completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            user_keys={k for k in keys if k})
        stats["pulled"] += 1
        n_trades = sum(1 for t in rows["transactions"]
                       if t["type"] == "trade" and t["status"] == "complete")
        log(f"[{i}/{len(todo)}] league {lid} season {season}: "
            f"{client.total_requests - before} requests, {n_trades} trades")
    return stats
