"""Retro-link historical executed trades to logged suggestions
(operator directive 2026-08-16; companion to backfill_sleeper_trades.py).

For every not-yet-linked executed trade in `sleeper_trades` belonging to a
CURRENT-SEASON synced league (prior-season chain leagues predate the app and
have no impressions), reconstruct the suggestion trade_hash the serving path
would have stamped for that exact asset exchange — via the imported
server-side _deck_trade_hash, in both service directions — and link the trade
to the most recent deck_impressions row carrying that hash, served within the
standard lookback window (model_config suggestion_match_lookback_days,
default 14) BEFORE execution.

Why exact-hash-only: historical deck_impressions rows carry trade_hash but
NOT assets_json (that column starts 2026-08-16 with suggestion.telemetry),
so the live matcher's partial/overlap semantics are impossible retroactively.
Consequences, documented rather than fuzzed around:
  * links UNDERCOUNT — near-miss executions (partial overlaps) are invisible;
  * suggestions whose pick side used generic-ladder ids
    ("generic_pick_<round>_<tier>") can never hash-match an executed trade,
    because the executed pick reconstructs to the owned-pick pseudo-id.

Marking: matched rows get match_type/ghost_match_type 'retro_exact' (vs the
live matcher's 'exact'/'partial'). The schema has no match_basis/matched_via
column, and adding one for an ops backfill would cross the schema bright
line; the distinct match_type string is the distinguisher instead. No-match
rows keep match_type NULL exactly like the live matcher (denominator rows).

Safety rails:
  * trades executed at/after the first assets_json impression (the telemetry
    era) are SKIPPED — they belong to the live matcher, which can do richer
    partial matching there; retro rows must never preempt it;
  * all writes go through database.save_suggestion_trade_links (insert-only,
    idempotent on transaction_id) — rows the live matcher already wrote are
    never touched;
  * --dry-run computes and prints everything, writes nothing.

    python3 scripts/backfill_suggestion_links.py --dry-run
    python3 scripts/backfill_suggestion_links.py
    python3 scripts/backfill_suggestion_links.py --league 1180999595377590272
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import and_, func, or_, select  # noqa: E402

from backend import database as db  # noqa: E402
from backend import suggestion_telemetry as st  # noqa: E402
from backend.server import _deck_trade_hash  # noqa: E402  (the single hash definition)

MATCH_TYPE_RETRO = "retro_exact"


def executed_sides_asset_ids(trade_row: dict) -> dict[str, list[str]] | None:
    """Per-ROSTER outgoing asset ids for a captured 2-team sleeper_trades
    row: {roster_id: [asset ids the roster SENT]}, in the suggestion
    vocabulary _deck_trade_hash was computed over at serve time — players by
    Sleeper player_id, owned picks as the database.py pick pseudo-id
    "{league_id}_{season}_{round}_{original_roster_id}". None when the trade
    is not a resolvable 2-team asset trade. (Sibling of
    suggestion_telemetry.executed_trade_sides, which emits matcher TOKENS —
    a different vocabulary that can't reproduce the serve-time hash.)"""
    try:
        roster_ids = json.loads(trade_row.get("roster_ids") or "[]")
        adds = json.loads(trade_row.get("adds") or "{}")
        picks = json.loads(trade_row.get("draft_picks") or "[]")
    except (TypeError, ValueError):
        return None
    if len(roster_ids) != 2:
        return None
    league_id = str(trade_row.get("league_id"))
    rid_a, rid_b = (str(r) for r in roster_ids)
    sent: dict[str, list[str]] = {rid_a: [], rid_b: []}
    # adds: {player_id: receiving roster_id} — the OTHER roster sent it.
    for pid, recv_rid in (adds or {}).items():
        recv_rid = str(recv_rid)
        if recv_rid not in sent:
            return None
        sender = rid_b if recv_rid == rid_a else rid_a
        sent[sender].append(str(pid))
    # picks move previous_owner_id -> owner_id; roster_id = original owner.
    for pk in picks or []:
        try:
            season = str(pk.get("season"))
            rnd = int(pk.get("round"))
            orig = str(pk.get("roster_id"))
        except (TypeError, ValueError):
            continue
        prev = str(pk.get("previous_owner_id"))
        if not season or not orig or prev not in sent:
            continue
        sent[prev].append(f"{league_id}_{season}_{rnd}_{orig}")
    if not any(sent.values()):
        return None
    return sent


def candidate_hashes(
    sides: dict[str, list[str]], roster_map: dict[str, str]
) -> dict[str, str]:
    """{trade_hash: user_id the impression would have been served to}. One
    hash per direction: an impression served to user U hashes (U's give,
    U's receive, partner)."""
    (rid_a, rid_b) = list(sides)
    user_a, user_b = roster_map.get(rid_a), roster_map.get(rid_b)
    if not user_a or not user_b:
        return {}
    return {
        _deck_trade_hash(sides[rid_a], sides[rid_b], user_b): str(user_a),
        _deck_trade_hash(sides[rid_b], sides[rid_a], user_a): str(user_b),
    }


def telemetry_start_iso() -> str | None:
    """First served_at with assets_json — the live matcher's era boundary.
    None = telemetry has never stamped an impression in this DB."""
    with db.engine.connect() as conn:
        return conn.execute(
            select(func.min(db.deck_impressions_table.c.served_at))
            .where(db.deck_impressions_table.c.assets_json.isnot(None))
        ).scalar()


def load_impressions_by_hash(
    league_id: str, hashes: list[str], since_iso: str, until_iso: str
) -> list[dict]:
    """deck_impressions rows in the window carrying one of these hashes —
    the exact-hash retro pool (assets_json NOT required, unlike the live
    matcher's load_impressions_for_matching)."""
    if not hashes:
        return []
    with db.engine.connect() as conn:
        rows = conn.execute(
            select(
                db.deck_impressions_table.c.impression_id,
                db.deck_impressions_table.c.user_id,
                db.deck_impressions_table.c.trade_hash,
                db.deck_impressions_table.c.is_ghost,
                db.deck_impressions_table.c.served_at,
            ).where(and_(
                db.deck_impressions_table.c.league_id == league_id,
                db.deck_impressions_table.c.trade_hash.in_(list(hashes)),
                db.deck_impressions_table.c.served_at >= since_iso,
                db.deck_impressions_table.c.served_at <= until_iso,
            ))
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def retro_link_for_trade(
    tr: dict,
    roster_map: dict[str, str],
    *,
    lookback_days: int,
    now_iso: str,
    imps_loader=load_impressions_by_hash,
) -> dict:
    """One suggestion_trade_links row (live-matcher shape) for one captured
    trade. Non-2-team / unresolvable trades yield a match_type NULL
    denominator row, same as match_league_trades."""
    link = {
        "transaction_id":        tr["transaction_id"],
        "league_id":             tr["league_id"],
        "was_recommended":       0,
        "matched_impression_id": None,
        "match_type":            None,
        "overlap_score":         None,
        "ghost_impression_id":   None,
        "ghost_match_type":      None,
        "ghost_overlap_score":   None,
        "traded_at":             tr.get("traded_at"),
        "computed_at":           now_iso,
    }
    traded_at = st._parse_iso(tr.get("traded_at")) or st._parse_iso(tr.get("synced_at"))
    sides = executed_sides_asset_ids(tr)
    if sides is None or traded_at is None:
        return link
    hashes = candidate_hashes(sides, roster_map)
    if not hashes:
        return link
    since = (traded_at - timedelta(days=lookback_days)).isoformat()
    imps = imps_loader(tr["league_id"], list(hashes), since, traded_at.isoformat())
    best: dict[bool, dict] = {}
    for imp in imps:
        served_to = hashes.get(imp.get("trade_hash"))
        # Direction check: the hash encodes give/receive/partner from ONE
        # user's perspective — the impression must have been served to them.
        if served_to is None or str(imp.get("user_id")) != served_to:
            continue
        is_ghost = bool(imp.get("is_ghost"))
        cur = best.get(is_ghost)
        if cur is None or (imp.get("served_at") or "") > (cur.get("served_at") or ""):
            best[is_ghost] = imp
    if False in best:
        link.update({
            "was_recommended":       1,
            "matched_impression_id": best[False]["impression_id"],
            "match_type":            MATCH_TYPE_RETRO,
            "overlap_score":         1.0,
        })
    if True in best:
        link.update({
            "ghost_impression_id": best[True]["impression_id"],
            "ghost_match_type":    MATCH_TYPE_RETRO,
            "ghost_overlap_score": 1.0,
        })
    return link


def link_league(
    league_id: str,
    *,
    dry_run: bool,
    cutoff_iso: str | None,
    lookback_days: int,
    roster_map: dict[str, str] | None = None,
) -> dict:
    """Retro-link one league's unlinked captured trades. Returns a stats
    dict; writes only via save_suggestion_trade_links (never on dry-run).
    `roster_map` injects the roster->user map in tests (no network)."""
    stats = {"unlinked": 0, "skipped_telemetry_era": 0, "examined": 0,
             "recommended": 0, "ghost": 0, "no_match": 0, "written": 0,
             "roster_fetch_failed": False}
    trades = db.load_unlinked_league_trades(league_id)
    stats["unlinked"] = len(trades)
    eligible = []
    for tr in trades:
        ref = tr.get("traded_at") or tr.get("synced_at") or ""
        if cutoff_iso is not None and ref >= cutoff_iso:
            stats["skipped_telemetry_era"] += 1  # live matcher's territory
            continue
        eligible.append(tr)
    if not eligible:
        return stats
    if roster_map is None:
        try:
            roster_map = st.fetch_league_roster_map(league_id)
        except Exception as e:
            print(f"  ! roster fetch failed for {league_id}: {e} — skipped")
            stats["roster_fetch_failed"] = True
            return stats
    now_iso = datetime.now(timezone.utc).isoformat()
    links = []
    for tr in eligible:
        link = retro_link_for_trade(
            tr, roster_map, lookback_days=lookback_days, now_iso=now_iso)
        links.append(link)
        stats["examined"] += 1
        if link["was_recommended"]:
            stats["recommended"] += 1
        if link["ghost_impression_id"]:
            stats["ghost"] += 1
        if not link["was_recommended"] and not link["ghost_impression_id"]:
            stats["no_match"] += 1
    if not dry_run:
        stats["written"] = db.save_suggestion_trade_links(links)
    return stats


def current_season_league_ids() -> list[str]:
    """Distinct numeric Sleeper league ids from the synced leagues table —
    the only leagues that can carry impressions."""
    with db.engine.connect() as conn:
        rows = conn.execute(
            select(db.leagues_table.c.sleeper_league_id).where(
                or_(
                    db.leagues_table.c.platform.is_(None),
                    db.leagues_table.c.platform == "sleeper",
                )
            ).distinct()
        ).fetchall()
    return sorted({str(r.sleeper_league_id) for r in rows
                   if str(r.sleeper_league_id).isdigit()})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print only; write nothing")
    ap.add_argument("--league", help="link only this league id")
    ap.add_argument("--sleep", type=float, default=0.2,
                    help="seconds between per-league roster fetches (default 0.2)")
    args = ap.parse_args()

    league_ids = [args.league] if args.league else current_season_league_ids()
    cutoff = telemetry_start_iso()
    lookback = st.match_lookback_days()
    mode = "DRY-RUN" if args.dry_run else "REAL"
    cutoff_desc = cutoff or "never (no assets_json impressions — all trades eligible)"
    print(f"[{mode}] {len(league_ids)} current-season league(s); lookback "
          f"{lookback}d; telemetry era starts {cutoff_desc}\n")

    totals: dict[str, int] = {}
    for lid in league_ids:
        stats = link_league(lid, dry_run=args.dry_run, cutoff_iso=cutoff,
                            lookback_days=lookback)
        for k, v in stats.items():
            if isinstance(v, bool):
                totals[k] = totals.get(k, 0) + (1 if v else 0)
            else:
                totals[k] = totals.get(k, 0) + v
        if stats["unlinked"]:
            print(f"league {lid}: {stats['unlinked']} unlinked, "
                  f"{stats['skipped_telemetry_era']} left to live matcher, "
                  f"{stats['examined']} examined -> {stats['recommended']} "
                  f"recommended, {stats['ghost']} ghost, "
                  f"{stats['no_match']} no-match, {stats['written']} written")
        if stats["examined"] or stats["roster_fetch_failed"]:
            time.sleep(args.sleep)  # pace the per-league roster fetches

    verb = "would write" if args.dry_run else "wrote"
    examined = totals.get("examined", 0)
    rec = totals.get("recommended", 0)
    print(f"\nTOTAL: {totals.get('unlinked', 0)} unlinked trades, "
          f"{totals.get('skipped_telemetry_era', 0)} left to live matcher, "
          f"{examined} examined, {rec} recommended "
          f"(ratio {round(rec / examined, 4) if examined else 'n/a'}), "
          f"{totals.get('ghost', 0)} ghost links, "
          f"{totals.get('no_match', 0)} no-match, "
          f"{verb} {totals.get('written', 0)} rows, "
          f"{totals.get('roster_fetch_failed', 0)} leagues skipped on "
          f"roster-fetch failure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
