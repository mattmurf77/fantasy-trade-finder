"""error_alerts.py — server error alerts through Sentry (GNG-1) and the
"feedback received" alert (SUP-M7). Dark until SENTRY_DSN is set.

Scope: docs/plans/server-error-alerts/scope.md (+ scope-feedback-alert.md).
Operator steps: docs/runbook.md § "Server error alerts (Sentry)".

With no SENTRY_DSN nothing here does anything, and `sentry_sdk` is never
imported: `init_error_alerts` returns False, and the request hooks and
`notify` return at a module-flag check.

With a DSN, what becomes an event:
  * every ERROR+ log record (LoggingIntegration; INFO+ become breadcrumbs).
    Route exceptions arrive this way: server.handle_unexpected_error handles
    every exception, so Flask's got_request_exception never fires, and its
    log.exception carries the stack. So do the _cleanup_loop step guards and
    daily_tick.run's per-step guard;
  * `http_5xx`, once, for a 5xx response that produced no event of its own
    (report_5xx, from server's after_request hook). 4xx never reports;
  * `notify(...)` messages (feedback_received), carrying their tags only.

Scrubbing mirrors the mobile S0 scrub (mobile/src/observability/sentry.ts)
and goes further, since server events can carry credentials and ids:
scrub_event (before_send) and scrub_breadcrumb (before_breadcrumb), both
fail closed. The value shapes are the ones api_observability._VALUE_SHAPE_RES
and analytics_ingest._PII_VALUE_RES already redact, plus the rest of the
GNG-1 list; copied, not imported, so this module needs no database import.

Beyond the init options GNG-1 names:
  * auto_enabling_integrations=False: the SQLAlchemy integration would add a
    breadcrumb per query with its parameters, and the Anthropic one would
    capture handled API errors;
  * trace_propagation_targets=[]: the stdlib integration would otherwise add
    sentry-trace/baggage headers to every outbound Sleeper/ESPN/MFL/Anthropic
    request (mobile sets the same);
  * ThreadingIntegration(propagate_scope=False): _cleanup_loop is started
    from the first request's before_request hook, so with propagation every
    cleanup-loop event would carry that first request.

Fork safety under gunicorn --preload: init runs in the master, and starts no
thread. sentry-sdk 2.72.0's BackgroundWorker (the HTTP transport's sender)
restarts its thread when the pid changes: sentry_sdk/worker.py:59, `is_alive`
is False for another pid; :65 `_ensure_thread` calls :86 `start`, which
records the new pid at :95; `submit` (:140) calls `_ensure_thread` first. So
the forked worker sends from its own thread. The session flusher
(sessions.py:193) and backpressure monitor (monitor.py:50-58) restart per
pid too.
"""
from __future__ import annotations

import logging
import os
import re

from flask import g, request

log = logging.getLogger(__name__)

_initialized = False

_FILTERED = "[Filtered]"

# Tag keys alert rules match on: their values pass through unscrubbed.
# feedback_id is an autoincrement row id; the 9-digit rule never sees it.
_ALLOWED_TAGS = frozenset({"route", "status", "method", "feedback_id", "kind"})

# A dict value under a key containing one of these (case-insensitive) is
# replaced wholesale.
_SENSITIVE_KEYS = (
    "token", "secret", "password", "passwd", "cookie", "auth", "session", "dsn",
    "api_key", "apikey", "swid", "espn_s2", "jwt", "credential",
    "user_id", "owner_id", "partner", "email", "username",
)

# In order: the specific credential shapes first, then the generic runs.
# Event strings have no length cap (the SDK default), so every unanchored
# run before a literal is bounded: an unbounded one is quadratic on a long
# blob, on the thread that logged it.
_PATTERNS = (
    # bearer credentials
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*"), _FILTERED),
    # JWTs (Sleeper session token, Apple/Google identity tokens)
    (re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]+)?"), _FILTERED),
    # key=value, "key": "value", Header: value, where the key names a
    # credential: also Cookie: espn_s2=…; SWID={…}, MFL_USER_ID=…, ?token=…
    # The match starts at the keyword ("X-Cron-" stays, "Secret: …" goes).
    (re.compile(r"""(?i)((?:token|secret|passw(?:or)?d|cookie|auth|session|dsn|api_?key"""
                r"""|swid|espn_s2|mfl_user_id|jwt|credential)[\w.-]{0,40})"""
                r"""(\s*["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s"'&;,]+)"""), rf"\1\2{_FILTERED}"),
    # email addresses
    (re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,}"), _FILTERED),
    # UUIDs, and ESPN's SWID {GUID} with its braces
    (re.compile(r"\{?\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
                r"-[0-9A-Fa-f]{12}\b\}?"), _FILTERED),
    # espn_s2-shaped blobs, percent-encoded or not
    (re.compile(r"[A-Za-z0-9%+/=]{80,}"), _FILTERED),
    # long hex / base64url runs: session tokens, Fernet ciphertext, API keys
    (re.compile(r"[A-Za-z0-9_-]{24,}"), _FILTERED),
    # any run of 9+ digits: Sleeper user and league ids are 18-19
    (re.compile(r"\d{9,}"), _FILTERED),
)

# Top-level event keys the SDK fills from code or config, never from request
# data. Every other key is scrubbed (unknown ones included).
_PASS_KEYS = frozenset({
    "event_id", "timestamp", "start_timestamp", "level", "logger", "platform",
    "release", "environment", "dist", "server_name", "sdk", "modules",
    "fingerprint", "transaction", "transaction_info", "type", "debug_meta", "_meta",
})

# The code-derived parts of an exception or thread entry (type and module
# group the issue; frames are file/function/line/source).
_CODE_KEYS = frozenset({"type", "module", "mechanism", "stacktrace"})


def init_error_alerts() -> bool:
    """Start the Sentry SDK when SENTRY_DSN is set; False (and nothing done)
    when it's unset or empty. Idempotent. A failed init (a malformed DSN, the
    package missing) logs and returns False rather than failing boot."""
    global _initialized
    if _initialized:
        return True
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.threading import ThreadingIntegration
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT") or "production",
            release=os.environ.get("RENDER_GIT_COMMIT") or None,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            max_breadcrumbs=30,
            # No tracing or profiling: traces/profiles_sample_rate stay unset.
            auto_enabling_integrations=False,
            trace_propagation_targets=[],
            integrations=[
                FlaskIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
                ThreadingIntegration(propagate_scope=False),
            ],
            before_send=scrub_event,
            before_breadcrumb=scrub_breadcrumb,
        )
    except Exception as e:
        log.error("error_alerts: Sentry init failed (%s); alerts stay off", type(e).__name__)
        return False
    _initialized = True
    return True


def _active() -> bool:
    if not _initialized:
        return False
    import sentry_sdk
    return sentry_sdk.get_client().is_active()


def notify(message: str, **tags) -> None:
    """One info-level message event carrying only `tags`, on a fresh
    isolation scope: no breadcrumbs, request or user. A no-op unless the SDK
    client is active; never raises into the caller."""
    try:
        if not _active():
            return
        import sentry_sdk
        from sentry_sdk.scope import Scope, ScopeType, use_isolation_scope, use_scope
        with use_isolation_scope(Scope(ty=ScopeType.ISOLATION)) as scope, \
                use_scope(Scope(ty=ScopeType.CURRENT)):
            for key, value in tags.items():
                scope.set_tag(key, str(value))
            sentry_sdk.capture_message(message, level="info")
    except Exception as e:
        log.warning("error_alerts: notify(%s) failed: %s", message, type(e).__name__)


def request_started() -> None:
    """before_request: note this request's last event id, so report_5xx can
    tell whether the request has already produced an event."""
    if _initialized:
        import sentry_sdk
        g._error_alerts_last_event = sentry_sdk.last_event_id()


def report_5xx(status: int) -> None:
    """after_request, for a status >= 500: one `http_5xx` event tagged with
    route, status and method, unless this request already captured an event
    (handle_unexpected_error's log.exception, or any other ERROR log on the
    way to the 5xx), so a 500 is never counted twice. Never raises."""
    if not _initialized:
        return
    try:
        import sentry_sdk
        # The request's isolation scope inherits its parent's last id, hence
        # the comparison with the id noted at request start, not with None.
        if sentry_sdk.last_event_id() != g.get("_error_alerts_last_event"):
            return
        route = request.url_rule.rule if request.url_rule else "<unmatched>"
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("route", route)
            scope.set_tag("status", str(status))
            scope.set_tag("method", request.method)
            scope.fingerprint = ["http_5xx", route, str(status)]
            sentry_sdk.capture_message("http_5xx", level="error")
    except Exception as e:
        log.warning("error_alerts: http_5xx report failed: %s", type(e).__name__)


# ---------------------------------------------------------------------------
# Scrubbing
# ---------------------------------------------------------------------------

def _scrub_str(text: str) -> str:
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    return text


def _sensitive(key) -> bool:
    k = str(key).lower()
    return any(s in k for s in _SENSITIVE_KEYS)


def _scrub(value):
    """Every string pattern-scrubbed, every dict value under a sensitive key
    replaced, recursively. A number whose digits match is replaced too."""
    if isinstance(value, str):
        return _scrub_str(value)
    if isinstance(value, dict):
        return {k: _FILTERED if _sensitive(k) else _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if _scrub_str(repr(value)) == repr(value) else _FILTERED
    return _scrub_str(repr(value))


def _scrub_stack_entries(block: dict) -> dict:
    """`exception` / `threads`: each entry's value (the message) scrubbed,
    its code-derived parts kept, any frame locals dropped."""
    entries = []
    for entry in block.get("values") or []:
        entry = {k: v if k in _CODE_KEYS else _scrub(v) for k, v in entry.items()}
        for frame in (entry.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
        entries.append(entry)
    return {**block, "values": entries}


def _scrub_event(event: dict) -> dict:
    out = {}
    for key, value in event.items():
        if key in _PASS_KEYS:
            out[key] = value
        elif key == "user":
            continue
        elif key == "request":
            url = value.get("url")
            out[key] = {k: v for k, v in (
                ("method", value.get("method")),
                ("url", _scrub_str(url.split("?", 1)[0].split("#", 1)[0])
                 if isinstance(url, str) else None)) if v is not None}
        elif key == "tags" and isinstance(value, dict):
            out[key] = {k: v if k in _ALLOWED_TAGS else _FILTERED if _sensitive(k) else _scrub(v)
                        for k, v in value.items()}
        elif key == "contexts" and isinstance(value, dict):
            out[key] = {k: v if k == "trace" else _scrub(v) for k, v in value.items()}
        elif key in ("exception", "threads") and isinstance(value, dict):
            out[key] = _scrub_stack_entries(value)
        else:
            out[key] = _scrub(value)
    return out


def scrub_event(event, hint=None):
    """before_send: the event with request reduced to method + url (no query),
    user removed, every string in its content scrubbed; None (dropped) when
    scrubbing raises."""
    try:
        return _scrub_event(event)
    except Exception:
        return None


def scrub_breadcrumb(crumb, hint=None):
    """before_breadcrumb: outbound-HTTP breadcrumbs dropped (the backend twin
    of mobile's sleeper.com drop); others get message and data scrubbed. None
    (dropped) when scrubbing raises."""
    try:
        if crumb.get("category") == "httplib" or crumb.get("type") == "http":
            return None
        for key in ("message", "data"):
            if key in crumb:
                crumb[key] = _scrub(crumb[key])
        return crumb
    except Exception:
        return None
