"""Backfill the organic executed-trade corpus (operator directive 2026-08-16).

For EVERY Sleeper league in the synced `leagues` table this script:

  1. sweeps the current league's transactions (legs 1-18, completed trades
     only) via the existing sleeper_trades_service helpers, and
  2. walks the league's `previous_league_id` chain backwards up to
     --max-prior-seasons (default 3) prior seasons and sweeps those leagues
     too — trades are stored under the HISTORICAL league id they happened in.

Explicitly flag-independent: the `market.trade_capture` flag gates only the
session-init background daemon; this is an operator-run backfill. All writes
go through database.record_sleeper_trades (append-only, idempotent on
transaction_id), so re-running is always safe. Reads/writes whatever DB
backend.database resolves — export DATABASE_URL before running to target
prod (see docs/runbook.md § Organic trade backfill).

    python3 scripts/backfill_sleeper_trades.py --dry-run   # fetch + count only
    python3 scripts/backfill_sleeper_trades.py             # real run
    python3 scripts/backfill_sleeper_trades.py --league 1180999595377590272
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_, select  # noqa: E402

from backend import database as db  # noqa: E402
from backend.sleeper_trades_service import (  # noqa: E402
    SLEEPER_API_BASE,
    WEEKS,
    _HEADERS,
    fetch_week_transactions,
    parse_trade_transactions,
)


def fetch_league_object(league_id: str, *, _opener=None, timeout: int = 15) -> dict:
    """GET /v1/league/<id> — the league object (season, previous_league_id).
    `_opener` injects a fake urlopen in tests (house pattern)."""
    url = f"{SLEEPER_API_BASE}/league/{league_id}"
    request = urllib.request.Request(url)
    for k, v in _HEADERS.items():
        request.add_header(k, v)
    opener = _opener or urllib.request.urlopen
    with opener(request, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def walk_prior_chain(
    league_id: str, *, max_prior: int = 3, _opener=None
) -> list[tuple[str, str | None]]:
    """[(league_id, season), ...] — the root league first, then up to
    `max_prior` prior-season leagues via Sleeper's previous_league_id
    pointer ("0"/null terminates the chain). A fetch failure mid-chain
    stops the walk but never raises; the root is always returned so the
    transaction sweep can still try it."""
    chain: list[tuple[str, str | None]] = []
    current = str(league_id)
    for hop in range(max_prior + 1):
        try:
            obj = fetch_league_object(current, _opener=_opener)
        except Exception as e:  # Sleeper flake — keep what we have
            print(f"  ! league object fetch failed for {current}: {e}")
            if hop == 0:
                chain.append((current, None))
            break
        chain.append((current, obj.get("season")))
        prev = obj.get("previous_league_id")
        if not prev or str(prev) == "0":
            break
        current = str(prev)
    return chain


def synced_sleeper_league_ids() -> dict[str, tuple[str | None, str | None]]:
    """{league_id: (name, season)} for every distinct Sleeper league in the
    synced `leagues` table (platform NULL reads as 'sleeper'; non-numeric
    ids like league_demo are excluded)."""
    with db.engine.connect() as conn:
        rows = conn.execute(
            select(
                db.leagues_table.c.sleeper_league_id,
                db.leagues_table.c.name,
                db.leagues_table.c.season,
            ).where(
                or_(
                    db.leagues_table.c.platform.is_(None),
                    db.leagues_table.c.platform == "sleeper",
                )
            )
        ).fetchall()
    out: dict[str, tuple[str | None, str | None]] = {}
    for r in rows:
        lid = str(r.sleeper_league_id)
        if lid.isdigit():
            out.setdefault(lid, (r.name, r.season))
    return out


def count_existing_txids(txids: list[str]) -> int:
    """How many of these transaction_ids are already captured (dry-run's
    'already present' arithmetic). Read-only."""
    if not txids:
        return 0
    existing = 0
    with db.engine.connect() as conn:
        for i in range(0, len(txids), 500):
            chunk = txids[i:i + 500]
            existing += len(conn.execute(
                select(db.sleeper_trades_table.c.transaction_id)
                .where(db.sleeper_trades_table.c.transaction_id.in_(chunk))
            ).fetchall())
    return existing


def sweep_league(
    league_id: str, *, dry_run: bool, sleep_s: float = 0.2, _opener=None
) -> tuple[int, int, int]:
    """Sweep all legs of one league. Returns (trades_found, trades_new,
    failed_weeks). Per-week failures are skipped and counted, never raised —
    same resilience contract as sync_league_trades. Dry-run fetches and
    counts but writes nothing."""
    rows: list[dict] = []
    failed = 0
    for week in WEEKS:
        try:
            txns = fetch_week_transactions(league_id, week, _opener=_opener)
        except Exception as e:
            print(f"  ! league {league_id} week {week} fetch failed: {e}")
            failed += 1
            continue
        rows.extend(parse_trade_transactions(txns, league_id))
        if _opener is None and sleep_s:
            time.sleep(sleep_s)  # courteous pacing on the live API
    if dry_run:
        already = count_existing_txids([r["transaction_id"] for r in rows])
        return len(rows), len(rows) - already, failed
    new = db.record_sleeper_trades(rows)
    return len(rows), new, failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + count only; write nothing")
    ap.add_argument("--league", help="sweep only this league id (and its chain)")
    ap.add_argument("--max-prior-seasons", type=int, default=3,
                    help="previous_league_id hops to follow (default 3)")
    ap.add_argument("--sleep", type=float, default=0.2,
                    help="seconds between Sleeper calls (default 0.2)")
    args = ap.parse_args()

    leagues = synced_sleeper_league_ids()
    if args.league:
        if args.league not in leagues:
            leagues = {args.league: (None, None)}  # explicit id: sweep anyway
        else:
            leagues = {args.league: leagues[args.league]}
    if not leagues:
        print("No synced Sleeper leagues found in the leagues table.")
        return 0

    mode = "DRY-RUN" if args.dry_run else "REAL"
    print(f"[{mode}] {len(leagues)} synced Sleeper league(s); "
          f"chain depth {args.max_prior_seasons}\n")

    visited: set[str] = set()
    chain_map: dict[str, list[tuple[str, str | None]]] = {}
    tot_found = tot_new = tot_failed = 0
    for root, (name, season) in sorted(leagues.items()):
        chain = walk_prior_chain(root, max_prior=args.max_prior_seasons)
        chain_map[root] = chain
        print(f"league {root} ({name or '?'}, season {season or '?'}) — "
              f"chain: {' <- '.join(f'{lid}[{s or '?'}]' for lid, s in chain)}")
        for lid, s in chain:
            if lid in visited:  # chains from co-synced leagues converge
                print(f"  = {lid} (season {s or '?'}): already swept this run")
                continue
            visited.add(lid)
            found, new, failed = sweep_league(
                lid, dry_run=args.dry_run, sleep_s=args.sleep)
            tot_found += found
            tot_new += new
            tot_failed += failed
            verb = "would insert" if args.dry_run else "inserted"
            print(f"  - {lid} (season {s or '?'}): {found} completed trades, "
                  f"{verb} {new} new, {found - new} already present"
                  + (f", {failed} week fetches failed" if failed else ""))

    print(f"\nTOTAL: {len(visited)} league-seasons swept, {tot_found} trades "
          f"found, {tot_new} {'would be ' if args.dry_run else ''}new, "
          f"{tot_failed} failed week fetches")
    print("\nchain map (root -> historical):")
    for root, chain in sorted(chain_map.items()):
        print(f"  {root}: " + " <- ".join(f"{lid}[{s or '?'}]" for lid, s in chain))
    return 0


if __name__ == "__main__":
    sys.exit(main())
