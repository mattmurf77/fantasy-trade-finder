"""S0 — record each Sleeper roster refresh in `league_roster_state`.

The refresh itself is the read `/api/session/init` already makes at app open
and foreground (`session_input.resolve_session_input`). This module only
records its outcome, so trades-eng's serve path can tell fresh rows from last
good ones. Scope: docs/plans/trade-time-to-suggestion/scope-eng-s0-fetch.md
§B.3.

Never raises: a bookkeeping failure must never block session init or the tap.
PR-B adds the fingerprint stamp (roster_snapshot → CAS → on_roster_change).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import database as db
from . import sleeper_http

log = logging.getLogger(__name__)

PICKS_UNAVAILABLE = "picks_unavailable"
WRITE_FAILED = "write_failed"


def fetch_started_at() -> str:
    """ISO UTC with fixed microsecond precision, so values compare as strings."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def record_failure(league_id: str, exc_or_code) -> str | None:
    """A Sleeper read for this league failed. Keeps the last good rows.

    `exc_or_code` is the exception (classified by `sleeper_http.classify`) or
    a ready error code. Returns the status written ('stale' | 'missing'), or
    None when the write itself failed.
    """
    code = exc_or_code if isinstance(exc_or_code, str) else sleeper_http.classify(exc_or_code)
    try:
        status = db.mark_league_roster_failed(league_id, code)
    except Exception as err:
        log.warning("roster refresh state write failed league=%s: %s", league_id, err)
        return None
    log.info("roster refresh failed league=%s code=%s status=%s", league_id, code, status)
    return status


def record_outcome(league_id: str, refreshed_at: str | None, *,
                   members_ok: bool, picks_ok: bool) -> str | None:
    """The session-init daemon finished its Sleeper roster writes.

    'fresh' needs both the members write and the owned-pick sync to have
    committed; otherwise the league is marked stale with the reason and
    `refreshed_at` does not move. Returns the status written, or None.
    """
    if not members_ok:
        return record_failure(league_id, WRITE_FAILED)
    if not picks_ok:
        return record_failure(league_id, PICKS_UNAVAILABLE)
    if not refreshed_at:
        return None
    try:
        db.mark_league_roster_fresh(league_id, refreshed_at)
    except Exception as err:
        log.warning("roster refresh state write failed league=%s: %s", league_id, err)
        return None
    return db.ROSTER_STATE_FRESH
