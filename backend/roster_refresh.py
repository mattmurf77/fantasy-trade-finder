"""S0 — the Sleeper roster refresh record, and the non-blocking floor kick.

The main refresh is the read `/api/session/init` already makes at app open
and foreground (`session_input.resolve_session_input`). This module records
its outcome in `league_roster_state`, so trades-eng's serve path can tell
fresh rows from last good ones, and offers `maybe_refresh_async` (Product's
P41): a single-flight background re-read when a league is past the roster
bound. Scope: docs/plans/trade-time-to-suggestion/scope-eng-s0-fetch.md §B.1,
§B.3.

Never raises: a bookkeeping failure must never block session init or the tap.
PR-B adds the fingerprint stamp (roster_snapshot → CAS → on_roster_change)
to `_refresh_league`, the one internal refresh both entry points share.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from . import database as db
from . import sleeper_http

log = logging.getLogger(__name__)

PICKS_UNAVAILABLE = "picks_unavailable"
WRITE_FAILED = "write_failed"

# Single-flight for maybe_refresh_async. The lock guards ONLY the set's
# check-and-add / remove: no Sleeper call and no DB write ever runs under it.
_inflight_lock = threading.Lock()
_inflight: set[str] = set()


def fetch_started_at() -> str:
    """ISO UTC with fixed microsecond precision, so values compare as strings."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def record_failure(league_id: str, exc_or_code) -> str | None:
    """A Sleeper read for this league failed. Keeps the last good rows.

    `exc_or_code` is the exception (classified by `sleeper_http.classify`) or
    a ready error code. Returns the status written (always 'stale'), or None
    when the write itself failed.
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


# ---------------------------------------------------------------------------
# P41 — the non-blocking floor kick
# ---------------------------------------------------------------------------

def _younger_than(stamp, seconds: float) -> bool:
    """True when the ISO `stamp` is between 0 and `seconds` old.

    A missing, unparseable or future stamp is never "young": callers then
    refresh rather than trust it, and a cooldown never blocks on it.
    """
    if not stamp:
        return False
    try:
        when = datetime.fromisoformat(str(stamp))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - when).total_seconds()
    return 0.0 <= age < float(seconds)


def _within_bound(state: dict | None, max_age_s: float) -> bool:
    """True when the last full refresh (`refreshed_at`) is younger than `max_age_s`.

    No row or a NULL / unparseable / future stamp counts as past the bound.
    """
    return _younger_than((state or {}).get("refreshed_at"), max_age_s)


def _cooling_down(state: dict | None, retry_after_s: float) -> bool:
    """True when the last attempt FAILED less than `retry_after_s` ago.

    `mark_league_roster_failed` writes `status='stale'` and stamps
    `updated_at`, so a league whose reads keep failing (5xx, timeouts — the
    circuit only catches 429s) is retried at most once per `retry_after_s`
    instead of on every tap. An unparseable stamp never blocks.
    """
    state = state or {}
    return (state.get("status") == db.ROSTER_STATE_STALE
            and _younger_than(state.get("updated_at"), retry_after_s))


def maybe_refresh_async(league_id: str, max_age_s: float, *,
                        retry_after_s: float = 60.0) -> bool:
    """Start one background Sleeper roster refresh if the league is past the bound.

    Returns at once: True only when it started a refresh. No-ops (False, no
    thread) for a linked platform league or an id that isn't a Sleeper league
    id, while the 429 circuit is open, when `refreshed_at` is within
    `max_age_s`, when the last attempt failed less than `retry_after_s` ago
    (status 'stale', `updated_at`), or when a refresh for this league is
    already in flight. The caller (trades-eng's `/generate`) invokes it after
    the response is built and never under a lock; its checks are two small DB
    reads (platform link, then the one state row).

    Budget: ≤ 4 Sleeper reads per kick (rosters, users, traded_picks,
    drafts), 5 when the league meta isn't cached; only past the bound; one
    in flight per league. A league whose reads keep failing costs at most
    one kick (≤ 4–5 reads) per `retry_after_s`.
    """
    lid = str(league_id or "")
    try:
        if not lid.isdigit() or db.is_linked_platform_league(lid):
            return False                  # platform-linked (G-014/G-030) or demo/sentinel id
        if sleeper_http.is_open():
            return False
        state = db.get_league_roster_state(lid)
        if _within_bound(state, max_age_s) or _cooling_down(state, retry_after_s):
            return False
    except Exception as exc:
        log.warning("roster refresh kick skipped league=%s error=%s", lid, type(exc).__name__)
        return False
    with _inflight_lock:
        if lid in _inflight:
            return False
        _inflight.add(lid)
    try:
        threading.Thread(target=_run_refresh, args=(lid,),
                         name=f"roster-refresh-{lid}", daemon=True).start()
    except Exception as exc:
        with _inflight_lock:
            _inflight.discard(lid)
        log.warning("roster refresh kick failed league=%s error=%s", lid, type(exc).__name__)
        return False
    return True


def _run_refresh(league_id: str) -> None:
    """Thread body: one refresh, never raising, always leaving the in-flight set."""
    try:
        _refresh_league(league_id, fetch_started_at())
    except Exception as exc:
        log.warning("roster refresh crashed league=%s error=%s", league_id, type(exc).__name__)
    finally:
        with _inflight_lock:
            _inflight.discard(league_id)


def _refresh_league(league_id: str, started: str) -> str | None:
    """One Sleeper roster refresh for a league: the session-init daemon's
    Sleeper segment, re-run outside a session. Returns the status recorded.

    Reads rosters and users (circuit-guarded `_sleeper_get`), replace-syncs
    `league_members` in session init's row shape, syncs owned picks (meta from
    the 15-min cache, else one read), then records the outcome. PR-B extends
    this function with the fingerprint stamp and `on_roster_change`.
    """
    from . import server                  # lazy: server imports this module's siblings
    from .feature_flags import is_enabled

    base = f"https://api.sleeper.app/v1/league/{league_id}"
    try:
        rosters = server._sleeper_get(base + "/rosters")
        users = server._sleeper_get(base + "/users")
        if not isinstance(rosters, list) or not isinstance(users, list):
            raise ValueError("invalid Sleeper response")
    except Exception as exc:
        return record_failure(league_id, exc)

    names = {str(u.get("user_id")): (u.get("display_name") or u.get("username") or "")
             for u in users if isinstance(u, dict)}
    owned = [r for r in rosters if isinstance(r, dict) and r.get("owner_id")]
    members = [{"user_id": str(r["owner_id"]),
                "username": names.get(str(r["owner_id"]), ""),
                "display_name": names.get(str(r["owner_id"]), ""),
                # G-004: Sleeper can send null slots; never store "None".
                "player_ids": [str(p) for p in (r.get("players") or []) if p not in (None, "")]}
               for r in owned]
    try:
        members_ok = db.replace_league_members_snapshot(league_id, members)
    except Exception as exc:
        log.warning("roster refresh members write failed league=%s error=%s",
                    league_id, type(exc).__name__)
        members_ok = False
    if members_ok:
        try:
            server._invalidate_league_members_cache(league_id)
        except Exception:
            pass

    picks_ok = True
    if is_enabled("picks.owned_sync"):            # the same gate session init uses
        try:
            hit = server._FA_LEAGUE_META_CACHE.get(league_id)
            meta = hit[1] if hit and hit[1] else None
            if meta is None:
                meta = server._fetch_sleeper_league_meta(league_id)
                if meta:
                    server._FA_LEAGUE_META_CACHE[league_id] = (time.time(), meta)
            scoring = db.get_league_scoring(league_id) or db.DEFAULT_SCORING
            uid_to_name = {str(r["owner_id"]): names.get(str(r["owner_id"]), "") for r in owned}
            picks_ok = server._sync_sleeper_owned_picks(
                league_id, uid_to_name, scoring, rosters=rosters, meta=meta) is not None
        except Exception as exc:                  # None above = failed (R10)
            log.warning("roster refresh pick sync failed league=%s error=%s",
                        league_id, type(exc).__name__)
            picks_ok = False

    return record_outcome(league_id, started, members_ok=members_ok, picks_ok=picks_ok)
