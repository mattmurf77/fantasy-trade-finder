#!/usr/bin/env python3
"""refresh_usage_trends.py — run the Usage Trends weekly data update by hand.

Spec: docs/plans/usage-trends/weekly-update.md. The same writer the daily
cron tick runs (backend/usage_trends_refresh.refresh_usage_weeks), so a
manual run and the scheduled one can never disagree. Idempotent: weeks that
are stored and past their correction window are not re-fetched.

Usage (from the repo root):
    python3 scripts/refresh_usage_trends.py                  # update the local DB
    python3 scripts/refresh_usage_trends.py --dry-run        # fetch + report, write nothing
    python3 scripts/refresh_usage_trends.py --weeks 1-4 --force   # re-fetch those weeks
    python3 scripts/refresh_usage_trends.py --status         # what the local DB holds
    python3 scripts/refresh_usage_trends.py --remote [--weeks 3,4 --force]
        # run it on the deployed server via POST /api/cron/usage-trends-refresh

Local runs write the DB `backend.database` points at (DATABASE_URL, default
data/trade_finder.db). For production use --remote: the server runs the job,
writes its own Postgres and drops its in-process cache, so the app shows the
new numbers at once (a direct DB write from here would wait out a 6-hour
cache). --remote reads CRON_SECRET (and optional FTF_API_BASE) from the
gitignored secrets.local.env or the environment; never from a CLI arg.

Network: public Sleeper endpoints only (api.sleeper.app/v1/state/nfl and
api.sleeper.app/stats/nfl/<season>/<week>).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SECRETS = REPO / "secrets.local.env"
DEFAULT_BASE = "https://fantasy-trade-finder.onrender.com"


def _from_secrets(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    if SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return ""


def _parse_weeks(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        out.extend(range(int(a), int(b) + 1) if b else [int(a)])
    return sorted(set(out))


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "FantasyTradeFinder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _remote(args) -> int:
    secret = _from_secrets("CRON_SECRET")
    if not secret:
        print("CRON_SECRET is not set — fill it in secrets.local.env", file=sys.stderr)
        return 2
    base = (_from_secrets("FTF_API_BASE") or DEFAULT_BASE).rstrip("/")
    body = {"force": args.force, "dry_run": args.dry_run}
    weeks = _parse_weeks(args.weeks)
    if weeks:
        body["weeks"] = weeks
    req = urllib.request.Request(
        f"{base}/api/cron/usage-trends-refresh", data=json.dumps(body).encode(),
        method="POST", headers={"Content-Type": "application/json", "X-Cron-Secret": secret})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(r.read().decode())
    print("Started on the server; the result is in its log ('usage-refresh (cron_route)') "
          "and in usage_week_loads.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--weeks", help="limit to these completed weeks, e.g. 1-4 or 3,4")
    ap.add_argument("--force", action="store_true", help="re-fetch the --weeks even if fresh")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report; write nothing")
    ap.add_argument("--status", action="store_true", help="print the stored weeks and exit")
    ap.add_argument("--remote", action="store_true", help="run on the deployed server")
    args = ap.parse_args()
    if args.remote:
        return _remote(args)

    sys.path.insert(0, str(REPO))
    from backend import database as db
    from backend import usage_trends as ut
    from backend.usage_trends_refresh import completed_weeks, refresh_usage_weeks
    db.metadata.create_all(db.engine, tables=[
        db.usage_week_loads_table, db.usage_team_weeks_table, db.usage_player_weeks_table])

    if args.status:
        season, done = completed_weeks(_fetch_json(ut.state_url()))
        loads = db.load_usage_week_loads(season) if season else {}
        print(f"season {season}: {len(done)} completed weeks, {len(loads)} stored")
        for w in done:
            row = loads.get(w)
            print(f"  week {w:>2}: " + (
                f"{row['team_count']} teams, {row['player_count']} players, "
                f"fetched {row['fetched_at'][:16]}, changed {row['changed_at'][:16]}"
                if row else "NOT STORED"))
        return 0

    summary = refresh_usage_weeks(_fetch_json, weeks=_parse_weeks(args.weeks),
                                  force=args.force, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, default=str))
    return 1 if summary.get("error") or summary.get("skipped") else 0


if __name__ == "__main__":
    sys.exit(main())
