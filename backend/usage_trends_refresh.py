"""Usage Trends weekly data update — the ONE writer of the usage_* tables.

Spec: docs/plans/usage-trends/weekly-update.md. Three callers share
`refresh_usage_weeks`, and it is idempotent, so they can overlap safely:

  * the daily cron tick (server.py `_kickoff_usage_refresh`, flag
    `usage_trends.enabled`) — the steady-state weekly update;
  * `POST /api/cron/usage-trends-refresh` — the operator's manual lever
    (backfill, a forced re-fetch);
  * `scripts/refresh_usage_trends.py` — the same run from a terminal.

What a run does:
  1. Read Sleeper's NFL state -> the season and its COMPLETED regular-season
     weeks (`completed_weeks`).
  2. Plan (`plan_weeks`): every completed week not yet stored (backfill), plus
     re-fetches of recently loaded weeks for stat corrections. A week is
     re-fetched at most once per CORRECTION_MIN_AGE_HOURS, and only while it
     is younger than CORRECTION_WINDOW_DAYS since its first load. After that
     it is frozen.
  3. For each planned week: fetch, normalize (usage_trends.normalize_week),
     sanity-check (MIN_TEAMS_PER_WEEK), hash, and replace the stored week only
     when the content changed. Otherwise just mark it fetched.
A failed or implausible week is reported and skipped, never stored half-done.
The transport is injected; this module imports `database` and never `server`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import database as db
from . import usage_trends as ut

SOURCE = "sleeper_stats"
# A real NFL week has 26-32 teams playing (at most 6 on bye). Fewer means the
# feed is not finished for that week, so nothing is stored.
MIN_TEAMS_PER_WEEK = 24
# Stat corrections land in the days after a game (usually by Thursday).
CORRECTION_WINDOW_DAYS = 7
CORRECTION_MIN_AGE_HOURS = 20


completed_weeks = ut.completed_weeks   # one calendar for the route and the job


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def plan_weeks(completed: list[int], loads: dict[int, dict], now: datetime) -> list[int]:
    """Weeks to fetch this run: missing ones, then corrections due."""
    plan = [w for w in completed if w not in loads]
    for w in completed:
        load = loads.get(w)
        if not load:
            continue
        young = now - _ts(load["first_fetched_at"]) < timedelta(days=CORRECTION_WINDOW_DAYS)
        stale = now - _ts(load["fetched_at"]) >= timedelta(hours=CORRECTION_MIN_AGE_HOURS)
        if young and stale:
            plan.append(w)
    return sorted(set(plan))


def content_hash(teams: dict, players: dict) -> str:
    blob = json.dumps({"teams": teams, "players": players}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def refresh_usage_weeks(fetch_json: Callable, *, now: datetime | None = None,
                        weeks: list[int] | None = None, force: bool = False,
                        dry_run: bool = False) -> dict:
    """Run one update. `weeks` restricts the run to those completed weeks
    (an operator backfill/re-fetch); `force` re-fetches them even if fresh;
    `dry_run` fetches and reports but writes nothing. Never raises for a
    single bad week; a failed state read is reported as `error`."""
    now = now or datetime.now(timezone.utc)
    summary: dict = {"season": None, "planned": [], "stored": [], "changed": [],
                     "unchanged": [], "skipped": {}, "dry_run": dry_run}
    try:
        season, done = completed_weeks(fetch_json(ut.state_url()))
    except Exception as e:  # noqa: BLE001 — reported, never raised
        summary["error"] = f"state_unavailable: {e}"
        return summary
    summary["season"] = season
    if season is None or not done:
        return summary
    loads = db.load_usage_week_loads(season)
    if weeks:
        wanted = [w for w in done if w in {int(x) for x in weeks}]
        plan = wanted if force else plan_weeks(wanted, loads, now)
    else:
        plan = plan_weeks(done, loads, now)
    summary["planned"] = plan
    for w in plan:
        try:
            rows = fetch_json(ut.stats_url(season, w))
        except Exception as e:  # noqa: BLE001
            summary["skipped"][w] = f"fetch_failed: {e}"
            continue
        if not isinstance(rows, list):
            summary["skipped"][w] = "invalid_response"
            continue
        teams, players = ut.normalize_week(rows)
        if len(teams) < MIN_TEAMS_PER_WEEK:
            summary["skipped"][w] = f"incomplete: {len(teams)} teams"
            continue
        digest = content_hash(teams, players)
        prev = loads.get(w)
        if prev and prev["content_hash"] == digest:
            summary["unchanged"].append(w)
            if not dry_run:
                db.touch_usage_week(season, w, now=now.isoformat())
            continue
        if not dry_run:
            db.replace_usage_week(season, w, teams, players, content_hash=digest,
                                  source=SOURCE, now=now.isoformat())
        summary["stored"].append(w)
        if prev:
            summary["changed"].append(w)
    return summary
