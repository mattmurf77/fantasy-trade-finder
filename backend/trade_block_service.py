"""
trade_block_service.py — import Sleeper trade-block state (FB-147).

Sleeper's Trade Center lets a manager flag players (and picks) as "on the
block". That state is NOT in the documented v1 REST API, but it IS
publicly readable — no auth token — via the same GraphQL endpoint the
Sleeper app uses:

    POST https://sleeper.com/graphql
    query { league_players(league_id: "<id>") { player_id settings } }

Each returned row's `settings` carries `otb` (the roster_id that flagged
the asset "on the block") and `otb_added_at` (epoch ms; absent on leagues
from before Sleeper added the timestamp). Verified live 2026-07-17
against the operator's leagues — see
docs/feedback/items/147-trade-blocks/status.md for the probe evidence.

Caveats handled here:
  * Stale flags: Sleeper never clears `otb` when the player is later
    traded/dropped, so a flag only counts if the flagging roster still
    owns the player (validated against v1 rosters).
  * Pick assets: pick rows use `"<roster>,<season>,<round>"` player_ids.
    Ownership validation for picks needs traded-picks resolution, so
    they are skipped in v1 of this import (documented follow-up).

This module only READS public data (unlike sleeper_write.py, which
drives the authenticated write surface).

Storage: `trade_block` table (database.replace_trade_block /
load_trade_block), replace-on-sync snapshot per league.

Engine note: this is a data-import + display module. Trade-generation
weighting of the signal is owned by the trade-logic thread; the engine's
read hook is `database.load_trade_block(league_id)`.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone

from .database import replace_trade_block

log = logging.getLogger(__name__)

SLEEPER_GRAPHQL_URL = "https://sleeper.com/graphql"
SLEEPER_API_BASE = "https://api.sleeper.app/v1"

# Look like an ordinary sleeper.com fetch (same rationale as
# sleeper_write.py — Cloudflare 1010-bans naked urllib UAs).
_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "origin": "https://sleeper.com",
    "referer": "https://sleeper.com/",
}


def fetch_league_players(league_id: str, *, _opener=None, timeout: int = 15) -> list[dict]:
    """Fetch raw `league_players` rows (player_id + settings) via GraphQL.

    Public read — no authorization header. `_opener` injects a fake
    urlopen in tests (same pattern as sleeper_write / espn_service).
    """
    op = "league_players"
    query = (
        'query %s { league_players(league_id: "%s") { player_id settings } }'
        % (op, league_id)
    )
    body = json.dumps({"operationName": op, "query": query, "variables": {}}).encode()
    request = urllib.request.Request(SLEEPER_GRAPHQL_URL, data=body, method="POST")
    for k, v in _HEADERS.items():
        request.add_header(k, v)
    request.add_header("x-sleeper-graphql-op", op)
    opener = _opener or urllib.request.urlopen
    with opener(request, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"Sleeper GraphQL error: {payload['errors'][:1]}")
    rows = (payload.get("data") or {}).get("league_players")
    return rows if isinstance(rows, list) else []


def _fetch_rosters(league_id: str, *, _opener=None, timeout: int = 15) -> list[dict]:
    """Fetch v1 rosters (roster_id → owner_id + players) for validation."""
    request = urllib.request.Request(
        f"{SLEEPER_API_BASE}/league/{league_id}/rosters",
        headers={"User-Agent": "FTF/1.0"},
    )
    opener = _opener or urllib.request.urlopen
    with opener(request, timeout=timeout) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    return rows if isinstance(rows, list) else []


def parse_trade_block(league_players: list[dict], rosters: list[dict]) -> list[dict]:
    """Pure parse: raw GraphQL rows + v1 rosters → validated block entries.

    Keeps a flag only when the flagging roster (settings.otb) still owns
    the player, which drops Sleeper's stale flags. Pick pseudo-ids
    (contain ",") are skipped — see module docstring.

    Returns entries shaped for database.replace_trade_block:
        {player_id, user_id, roster_id, flagged_at}
    """
    by_roster: dict[int, dict] = {}
    for r in rosters or []:
        rid = r.get("roster_id")
        if isinstance(rid, int):
            by_roster[rid] = r

    entries: list[dict] = []
    for row in league_players or []:
        settings = row.get("settings") or {}
        otb = settings.get("otb")
        pid = str(row.get("player_id") or "")
        if not pid or "," in pid or not isinstance(otb, int):
            continue
        roster = by_roster.get(otb)
        if not roster or not roster.get("owner_id"):
            continue
        if pid not in {str(p) for p in (roster.get("players") or [])}:
            continue  # stale flag — player no longer on the flagging roster
        added_ms = settings.get("otb_added_at")
        flagged_at = None
        if isinstance(added_ms, (int, float)) and added_ms > 0:
            flagged_at = datetime.fromtimestamp(
                added_ms / 1000, tz=timezone.utc
            ).isoformat()
        entries.append({
            "player_id": pid,
            "user_id":   str(roster["owner_id"]),
            "roster_id": otb,
            "flagged_at": flagged_at,
        })
    return entries


def sync_league_trade_block(league_id: str, *, _opener=None) -> int:
    """Fetch + validate + store the league's trade block. Returns row count.

    No-op (returns 0 without touching the table) for non-Sleeper league
    ids (ESPN imports, demo leagues) — same digit guard as
    server._fetch_sleeper_league_meta.
    """
    if not league_id or not str(league_id).isdigit():
        return 0
    league_players = fetch_league_players(league_id, _opener=_opener)
    rosters = _fetch_rosters(league_id, _opener=_opener)
    entries = parse_trade_block(league_players, rosters)
    replace_trade_block(league_id, entries)
    return len(entries)
