"""
sleeper_trades_service.py — capture executed Sleeper league trades.

Market-data readiness (operator directive 2026-07-26; PRD #43 Phase-1 data
foundation / backlog #26). Sleeper's documented public v1 API exposes every
completed transaction per league per leg:

    GET https://api.sleeper.app/v1/league/<league_id>/transactions/<week>

Rows with type="trade" and status="complete" are the raw material for a
future observed-market value model and league-specific market signals.
FTF previously threw these away on every sync — this module stores them,
RAW plus lightly normalized, into `sleeper_trades`
(database.record_sleeper_trades — idempotent on transaction_id).

Capture ONLY: no scoring, no aggregation, no UI. Called from
session_init's background daemon behind flag `market.trade_capture`,
same best-effort contract as trade_block_service / owned-pick sync —
a Sleeper flake just misses one pass; the next sync self-heals because
inserts are idempotent.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone

from .database import record_sleeper_trades

log = logging.getLogger(__name__)

SLEEPER_API_BASE = "https://api.sleeper.app/v1"

# Sleeper legs run 1..18 (regular season + playoffs); offseason trades land
# on leg 1. A full sweep every sync keeps capture complete regardless of
# when in the season a league is first synced; idempotent inserts make the
# re-sweep free on the DB side.
WEEKS = range(1, 19)

# Same rationale as trade_block_service — Cloudflare 1010-bans naked
# urllib UAs.
_HEADERS = {
    "accept": "application/json",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}


def fetch_week_transactions(
    league_id: str, week: int, *, _opener=None, timeout: int = 15
) -> list:
    """Fetch one leg's raw transaction list. Public read — no auth.

    `_opener` injects a fake urlopen in tests (same pattern as
    trade_block_service / sleeper_write / espn_service).
    """
    url = f"{SLEEPER_API_BASE}/league/{league_id}/transactions/{week}"
    request = urllib.request.Request(url)
    for k, v in _HEADERS.items():
        request.add_header(k, v)
    opener = _opener or urllib.request.urlopen
    # obs.api_events — `_sleeper_get` bypass site #3 (sleeper.md §6.3). The
    # 18-week sweep makes this the highest-frequency Sleeper class; success
    # sampling (obs_success_sample_n) keeps its volume bounded.
    from . import api_observability as _api_obs
    with _api_obs.observe_call("sleeper", "league.transactions",
                               active=_opener is None,
                               league_id=league_id, week=week) as _ob:
        with opener(request, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
        _ob.ok(status=200, response_bytes=len(raw))
    return payload if isinstance(payload, list) else []


def parse_trade_transactions(txns: list, league_id: str) -> list[dict]:
    """Filter a raw transaction list to completed trades and normalize into
    `sleeper_trades` rows. Pure — no I/O.

    The full payload is retained in `raw`; the normalized columns are a
    convenience projection (adds/drops maps, traded picks, FAAB moves),
    never the source of truth.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for t in txns or []:
        if not isinstance(t, dict):
            continue
        if t.get("type") != "trade" or t.get("status") != "complete":
            continue
        txid = t.get("transaction_id")
        if not txid:
            continue
        traded_at = None
        try:
            ms = t.get("status_updated")
            if ms:
                traded_at = datetime.fromtimestamp(
                    int(ms) / 1000.0, tz=timezone.utc
                ).isoformat()
        except (TypeError, ValueError, OSError):
            traded_at = None
        week = None
        try:
            week = int(t.get("leg")) if t.get("leg") is not None else None
        except (TypeError, ValueError):
            week = None
        rows.append({
            "transaction_id": str(txid),
            "league_id":      str(league_id),
            "week":           week,
            "traded_at":      traded_at,
            "synced_at":      now_iso,
            "roster_ids":     json.dumps(t.get("roster_ids") or []),
            "adds":           json.dumps(t.get("adds") or {}),
            "drops":          json.dumps(t.get("drops") or {}),
            "draft_picks":    json.dumps(t.get("draft_picks") or []),
            "waiver_budget":  json.dumps(t.get("waiver_budget") or []),
            "raw":            json.dumps(t),
        })
    return rows


def sync_league_trades(league_id: str, *, _opener=None) -> int:
    """Sweep all legs for a league, store completed trades. Returns the
    number of NEW trades captured (0 in steady state).

    Per-week fetch failures are logged and skipped — one bad leg must not
    drop the rest of the sweep.
    """
    rows: list[dict] = []
    for week in WEEKS:
        try:
            txns = fetch_week_transactions(league_id, week, _opener=_opener)
        except Exception as e:
            log.warning("trade capture: league %s week %d fetch failed: %s",
                        league_id, week, e)
            continue
        rows.extend(parse_trade_transactions(txns, league_id))
    return record_sleeper_trades(rows)
