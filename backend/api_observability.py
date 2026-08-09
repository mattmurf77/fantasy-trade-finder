"""
api_observability.py — inbound + outbound API event capture (flag `obs.api_events`).

Operator-directed observability program (docs/feedback/items/api-observability/
status.md): every external HTTP call the backend makes, and every inbound
/api/* request it serves, lands as a structured event in the EXISTING analytics
store (`user_events`) so failures are diagnosable from stored data without a
manual session. Spec corpus: docs/integrations/ (per-service "instrumentation
guidance" sections are binding — their MUST-REDACT rules are enforced here by
key-denylist + value-shape scrubbing, never by hoping a value doesn't appear).

Two event types, both server-fired (registered in analytics_taxonomy.py):

  api_call    — one outbound HTTP call to an external service. Wrapped via
                `observe_call(service, endpoint, ...)` around every egress
                chokepoint (Sleeper REST `_sleeper_get`, Sleeper GraphQL
                `_post_graphql` + the trade_block / sleeper_trades bypass
                sites, ESPN `fetch_league`, MFL `_fetch_one`/`login`/
                `fetch_my_leagues`/`resolve_host`, Fleaflicker `_get`,
                DynastyProcess CSVs + KTC scrape in data_loader/espn_service,
                Anthropic messages.create, Expo push, Apple/Google JWKS +
                Apple token endpoint in accounts.py).
  api_request — one inbound request to our own /api/* surface, recorded by
                Flask after_request/teardown hooks in server.py. Route PATTERN
                only (never the raw path — no ids/PII in URLs), excluding
                static assets and the analytics ingest route itself.

Storage discipline
------------------
* Rows are written through `db.ingest_engine` (150 ms lock budget on SQLite,
  BEGIN IMMEDIATE) so an observability burst sheds instead of stalling
  product writes — same isolation posture as /api/events ingest.
* `user_id` is the constant "system:api" so observability rows can never leak
  into user-scoped analytics (DAU/journeys/retention). The authenticated user
  behind an inbound request rides in props["user"] for diagnosis only. Both
  event types are additionally listed in analytics_queries.NON_INTENT_EVENTS.
* `screen` carries "{service}.{endpoint}" (outbound) / the route pattern
  (inbound) so reports can group without cross-dialect JSON extraction.

Volume policy (operator sign-off doc: the status.md above)
----------------------------------------------------------
* Errors (status >= 400, exceptions, timeouts) are ALWAYS captured.
* Successes are 1-in-N counter-sampled per (direction, endpoint-class); N
  comes from model_config `obs_success_sample_n` (default 10, cached 60 s,
  fail-open). Every sampled success row carries props["sample_n"] so call
  volumes can be re-scaled honestly (estimated_calls = Σ sample_n + errors).
* Retention: `purge_observability_events()` deletes rows older than
  FTF_OBS_RETENTION_DAYS (default 30; 0 = keep forever), riding server.py's
  existing `_cleanup_loop` with an internal 6 h throttle.

Kill switch
-----------
Flag `obs.api_events` (shipped ON). Off ⇒ `observe_call` yields a no-op
observer and `record_inbound` returns immediately — zero event writes, zero
overhead beyond the flag check, byte-identical responses.

Failure isolation (hard rule)
-----------------------------
Instrumentation must NEVER break the instrumented path. Every event write is
wrapped: an analytics failure prints to stderr and the real call/request
proceeds untouched. `observe_call` re-raises the wrapped call's own exception
exactly as-is after recording it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, text

from . import database as db
from .database import user_events_table
from .feature_flags import is_enabled

FLAG = "obs.api_events"
OUTBOUND_EVENT = "api_call"
INBOUND_EVENT = "api_request"
OBS_USER_ID = "system:api"

# ---------------------------------------------------------------------------
# Success sampling — 1-in-N counter per endpoint class (deterministic, so
# tests and rescaling are exact). N from model_config `obs_success_sample_n`
# (docs/config-reference.md), cached 60 s, fail-open to the default.
# ---------------------------------------------------------------------------

_SAMPLE_FALLBACK = 10
_SAMPLE_TTL_S = 60.0
_sample_cache: tuple[float, int] = (0.0, _SAMPLE_FALLBACK)

_counter_lock = threading.Lock()
_counters: dict[str, int] = {}
_COUNTER_DICT_MAX = 2_000  # endpoint classes are code-controlled; belt+braces


def _sample_n() -> int:
    global _sample_cache
    now = time.time()
    ts, val = _sample_cache
    if now - ts < _SAMPLE_TTL_S:
        return val
    try:
        val = int(db.get_config().get("obs_success_sample_n", _SAMPLE_FALLBACK))
        if val < 1:
            val = 1
    except Exception:
        val = _SAMPLE_FALLBACK
    _sample_cache = (now, val)
    return val


def _sampled(key: str) -> tuple[bool, int]:
    """Bump `key`'s counter; return (record_this_one, N)."""
    n = _sample_n()
    if n <= 1:
        return True, 1
    with _counter_lock:
        c = _counters.get(key, 0)
        _counters[key] = c + 1
        if len(_counters) > _COUNTER_DICT_MAX:
            _counters.clear()
    return (c % n == 0), n


# ---------------------------------------------------------------------------
# Redaction — the docs' MUST-REDACT rules, enforced structurally. Redact by
# KEY NAME (the codebase's own convention — server._sleeper_record) plus
# value-shape scrubbing for credential-shaped strings that slip through.
# Unknown prop keys are STRIPPED against the taxonomy spec (OBS_EVENT_PROPS),
# so a call site can never smuggle a new unreviewed property into the store.
# ---------------------------------------------------------------------------

_REDACT_KEY_SUBSTRINGS = (
    "token", "cookie", "secret", "password", "authorization", "auth_header",
    "swid_value", "espn_s2", "jwt", "api_key", "apikey", "credential",
    "set-cookie", "prompt_text", "reasoning", "username", "email",
)
_VALUE_SHAPE_RES = (
    # JWT shapes (Sleeper session token, Apple/Google identity tokens)
    re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]+)?"),
    # bearer-style credentials
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"),
    # espn_s2-shaped long percent-encoded blobs (the exact encoding IS the
    # credential — never let one ride in an error string)
    re.compile(r"[A-Za-z0-9%]{80,}"),
    # anthropic key shape
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
)
_REDACTED = "[redacted]"
_MAX_STR = 200


def _scrub_value(v):
    if isinstance(v, str):
        for rx in _VALUE_SHAPE_RES:
            v = rx.sub(_REDACTED, v)
        return v[:_MAX_STR]
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return v
    return _scrub_value(str(v))


def _scrub_props(props: dict, event_type: str) -> dict:
    from .analytics_taxonomy import OBS_EVENT_PROPS
    allowed = OBS_EVENT_PROPS.get(event_type, frozenset())
    clean: dict = {}
    for k, v in props.items():
        lk = str(k).lower()
        if k not in allowed:
            continue
        if any(s in lk for s in _REDACT_KEY_SUBSTRINGS):
            continue
        if v is None:
            continue
        clean[k] = _scrub_value(v)
    return clean


# ---------------------------------------------------------------------------
# Writer — the single sink. NEVER raises.
# ---------------------------------------------------------------------------

def _write_event(event_type: str, props: dict, *, league_id=None,
                 screen: str | None = None) -> None:
    try:
        clean = _scrub_props(props, event_type)
        with db.ingest_engine.begin() as conn:
            conn.execute(insert(user_events_table).values(
                user_id=OBS_USER_ID,
                event_type=event_type,
                occurred_at=db._now(),
                league_id=str(league_id)[:64] if league_id else None,
                source="server",
                platform="server",
                screen=(screen or "")[:64] or None,
                props=json.dumps(clean) if clean else None,
            ))
    except Exception as e:  # failure isolation: stderr + move on
        print(f"[api_observability] event write failed (non-fatal): {e}",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Outbound wrapper — the one idiom every egress chokepoint uses.
# ---------------------------------------------------------------------------

class _Observer:
    """Mutable per-call capture handle. Call sites set outcome via ok()/note()."""

    __slots__ = ("status", "response_bytes", "extra", "_ok_called")

    def __init__(self):
        self.status = None
        self.response_bytes = None
        self.extra: dict = {}
        self._ok_called = False

    def ok(self, status=None, response_bytes=None, **extra) -> None:
        """Declare the call completed (status < 400 = success)."""
        self._ok_called = True
        if status is not None:
            self.status = status
        if response_bytes is not None:
            self.response_bytes = response_bytes
        if extra:
            self.extra.update(extra)

    def note(self, **extra) -> None:
        """Attach additional safe context (retry=True, rows=…, …)."""
        self.extra.update(extra)


class _NoopObserver:
    __slots__ = ()

    def ok(self, *a, **k) -> None:
        pass

    def note(self, **k) -> None:
        pass


_NOOP = _NoopObserver()


@contextmanager
def observe_call(service: str, endpoint: str, *, method: str = "GET",
                 active: bool = True, league_id=None, **context):
    """Wrap ONE outbound HTTP call.

    Usage:
        with observe_call("espn", "league_read", league_id=lid) as ob:
            ... perform the call ...
            ob.ok(status=200, response_bytes=len(raw))

    * An exception inside the block is recorded (always — errors are never
      sampled) and re-raised untouched.
    * A completed block records a success, subject to 1-in-N sampling.
    * `active=False` (test-injected `_opener` seams) or flag-off yields a
      no-op observer with no side effects.
    * `context` kwargs become event props (scrubbed + spec-filtered).
    """
    if not active or not is_enabled(FLAG):
        yield _NOOP
        return

    obs = _Observer()
    t0 = time.perf_counter()
    try:
        yield obs
    except BaseException as e:
        ms = int((time.perf_counter() - t0) * 1000)
        status = obs.status
        if status is None and isinstance(e, urllib.error.HTTPError):
            status = e.code
        if status is None:
            # Service modules convert HTTPError → typed errors (EspnAuthError,
            # MflError, …) via `raise X from e`; recover the HTTP status.
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            if isinstance(cause, urllib.error.HTTPError):
                status = cause.code
        props = {
            "service": service, "endpoint": endpoint, "method": method,
            "ok": False, "ms": ms, "status": status,
            "error_class": type(e).__name__,
            "error_kind": getattr(e, "kind", None),
            "response_bytes": obs.response_bytes,
            **context, **obs.extra,
        }
        _write_event(OUTBOUND_EVENT, props, league_id=league_id,
                     screen=f"{service}.{endpoint}")
        raise
    ms = int((time.perf_counter() - t0) * 1000)
    status = obs.status
    ok = status is None or (isinstance(status, int) and status < 400)
    props = {
        "service": service, "endpoint": endpoint, "method": method,
        "ok": ok, "ms": ms, "status": status,
        "response_bytes": obs.response_bytes,
        **context, **obs.extra,
    }
    if not ok:
        _write_event(OUTBOUND_EVENT, props, league_id=league_id,
                     screen=f"{service}.{endpoint}")
        return
    record, n = _sampled(f"out:{service}.{endpoint}")
    if record:
        props["sample_n"] = n
        _write_event(OUTBOUND_EVENT, props, league_id=league_id,
                     screen=f"{service}.{endpoint}")


# ---------------------------------------------------------------------------
# Sleeper REST URL → endpoint class (route template, never ids/usernames).
# ---------------------------------------------------------------------------

def sleeper_endpoint_class(url: str) -> tuple[str, str | None]:
    """('league.rosters', '123…') style class + league_id for a v1 URL.

    Usernames (user/<name>) and all numeric ids are structurally dropped —
    only code-controlled path words survive into the class string.
    """
    try:
        path = url.split("api.sleeper.app/v1/", 1)[1].split("?", 1)[0].strip("/")
    except IndexError:
        return "other", None
    segs = [s for s in path.split("/") if s]
    if not segs:
        return "other", None
    head = segs[0]
    if head == "user":
        return ("user.leagues" if "leagues" in segs[1:] else "user"), None
    if head in ("league", "draft"):
        lid = segs[1] if len(segs) > 1 and segs[1].isdigit() else None
        sub = segs[2] if len(segs) > 2 and not segs[2].isdigit() else None
        cls = head + (f".{sub}" if sub else "")
        return cls, (lid if head == "league" else None)
    if head == "players":
        return ("players.adp" if segs[-1] == "adp" else "players"), None
    # Future endpoints: keep only the leading code-controlled word.
    return re.sub(r"[^a-z_]", "", head.lower())[:32] or "other", None


# ---------------------------------------------------------------------------
# Inbound capture — called from server.py's after_request/teardown hooks.
# ---------------------------------------------------------------------------

# The ingest route must never observe itself; static assets and anything
# outside /api/ are excluded by the server-side hook before calling here.
EXCLUDED_ROUTES = frozenset({"/api/events"})


def record_inbound(*, route: str, method: str, status: int,
                   ms: int | None = None, user: str | None = None,
                   error_code: str | None = None,
                   error_class: str | None = None,
                   response_bytes: int | None = None) -> None:
    """Record one inbound request. Never raises; flag-off = immediate no-op."""
    try:
        if not is_enabled(FLAG):
            return
        if route in EXCLUDED_ROUTES:
            return
        ok = status < 400
        props = {
            "route": route, "method": method, "status": status,
            "ok": ok, "ms": ms, "user": user,
            "error_code": error_code, "error_class": error_class,
            "response_bytes": response_bytes,
        }
        if not ok:
            _write_event(INBOUND_EVENT, props, screen=route)
            return
        record, n = _sampled(f"in:{method} {route}")
        if record:
            props["sample_n"] = n
            _write_event(INBOUND_EVENT, props, screen=route)
    except Exception as e:  # belt+braces — record_inbound itself never breaks a request
        print(f"[api_observability] inbound capture failed (non-fatal): {e}",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Retention — rides server.py's _cleanup_loop (5-min tick) with an internal
# throttle so the DELETE runs at most every 6 h. Purges regardless of the
# flag state (old rows must age out even while capture is off).
# ---------------------------------------------------------------------------

_RETENTION_DAYS_DEFAULT = 30
_PURGE_MIN_INTERVAL_S = 6 * 3600
_purge_lock = threading.Lock()
_last_purge_at = 0.0


def retention_days() -> int:
    try:
        return int(os.environ.get("FTF_OBS_RETENTION_DAYS",
                                  str(_RETENTION_DAYS_DEFAULT)))
    except Exception:
        return _RETENTION_DAYS_DEFAULT


def purge_observability_events(*, force: bool = False) -> int:
    """Delete api_call/api_request rows older than the retention window.

    Returns rows deleted (0 when throttled, disabled via days<=0, or on
    failure — never raises)."""
    global _last_purge_at
    days = retention_days()
    if days <= 0:
        return 0
    now = time.time()
    with _purge_lock:
        if not force and now - _last_purge_at < _PURGE_MIN_INTERVAL_S:
            return 0
        _last_purge_at = now
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with db.engine.begin() as conn:
            res = conn.execute(
                text("DELETE FROM user_events "
                     "WHERE event_type IN (:a, :b) AND occurred_at < :cutoff"),
                {"a": OUTBOUND_EVENT, "b": INBOUND_EVENT, "cutoff": cutoff})
            return res.rowcount or 0
    except Exception as e:
        print(f"[api_observability] retention purge failed (non-fatal): {e}",
              file=sys.stderr)
        return 0
