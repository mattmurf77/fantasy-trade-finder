"""
wrapped_collector.py — silent event collection for Fantasy Trade Wrapped.

Exposes a single function, record_event(), that appends rows to the
wrapped_events table.  Every DB interaction is wrapped in try/except so
a collector failure never propagates up into user-facing flows.

No UI consumes this data yet — the end-of-season recap feature reads
straight from the table when it ships.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from .database import engine, wrapped_events_table
from sqlalchemy import insert

log = logging.getLogger("trade_finder.wrapped")

VALID_EVENT_TYPES = {
    "swipe",
    "trade_match",
    "trade_accepted",
    "trade_declined",
    "tier_save",
    "ranking_reorder",
    "league_sync",
}


def record_event(
    user_id: Optional[str],
    league_id: Optional[str],
    event_type: str,
    payload_dict: Optional[dict] = None,
    season: int = 2026,
) -> None:
    """
    Fire-and-forget event recorder.  Never raises — swallows and logs
    any DB error so callers in hot paths can use a bare single-line call.
    """
    try:
        if event_type not in VALID_EVENT_TYPES:
            # Don't reject — just warn. Schema is forward-compatible so we
            # prefer permissive recording over dropped events.
            log.debug("record_event: unknown event_type=%r", event_type)

        payload_json = "{}"
        if payload_dict is not None:
            try:
                payload_json = json.dumps(payload_dict, default=str)
            except (TypeError, ValueError):
                payload_json = "{}"

        row = {
            "user_id":      user_id,
            "league_id":    league_id,
            "season":       season,
            "event_type":   event_type,
            "payload_json": payload_json,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }
        with engine.begin() as conn:
            conn.execute(insert(wrapped_events_table).values(**row))
    except Exception as e:   # pragma: no cover — intentionally broad
        log.warning("wrapped_collector.record_event failed: %s", e)
