"""error_alerts.py — server error alerts through Sentry (GNG-1) and the
"feedback received" alert (SUP-M7). Dark until SENTRY_DSN is set.

Scope: docs/plans/server-error-alerts/scope.md (+ scope-feedback-alert.md).
Operator steps: docs/runbook.md § "Server error alerts (Sentry)".

With no SENTRY_DSN nothing here does anything, and `sentry_sdk` is never
imported: `init_error_alerts` returns False, and the request hooks and
`notify` return at a module-flag check.

With a DSN, what becomes an event:
  * every ERROR+ log record (LoggingIntegration; no breadcrumbs).
    Route exceptions arrive this way: server.handle_unexpected_error handles
    every exception, so Flask's got_request_exception never fires, and its
    log.exception carries the stack. So do the _cleanup_loop step guards and
    daily_tick.run's per-step guard;
  * `http_5xx`, once, for a 5xx response that produced no event of its own
    (report_5xx, from server's after_request hook), at most once per route
    and status per worker per hour. 4xx and 501 never report;
  * `notify(...)` messages (feedback_received), carrying their tags only.

What is sent is built from an allowlist (legal R28.23; scope.md has the
conditions table): scrub_event (before_send) keeps the SDK's own fields, the
request as method + route pattern, exception type/module/frames (file,
function, line; no message, locals or source lines), the log template (from
our own loggers only; every param [Filtered]), our own message constants,
allowlisted tags and the runtime/os contexts. Anything else, unknown keys
included, is dropped; if building it raises, nothing is sent. No trace
context: its ids and the dynamic sampling context come from an inbound
sentry-trace / baggage header any caller can write, and the SDK builds the
envelope header's `trace` from contexts.trace after before_send
(sentry_sdk/client.py:959, then :1202-1211); with no tracing they link
nothing. Breadcrumbs are off. Sentry locates an error; its detail stays in
the Render logs. The pattern scrub (_PATTERNS, the shapes api_observability and
analytics_ingest already redact, copied so this module needs no database
import) is a second layer over the templates.

Beyond the init options GNG-1 names:
  * auto_enabling_integrations=False: the SQLAlchemy integration would add a
    breadcrumb per query with its parameters, and the Anthropic one would
    capture handled API errors;
  * trace_propagation_targets=[]: the stdlib integration would otherwise add
    sentry-trace/baggage headers to every outbound Sleeper/ESPN/MFL/Anthropic
    request (mobile sets the same);
  * ThreadingIntegration(propagate_scope=False): _cleanup_loop is started
    from the first request's before_request hook, so with propagation every
    cleanup-loop event would carry that first request;
  * auto_session_tracking=False: release-health sessions would send an
    envelope each minute of traffic, errors or not.

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
import threading
import time

from flask import g, has_request_context, request

log = logging.getLogger(__name__)

_initialized = False

_FILTERED = "[Filtered]"

# The only tags sent (alert rules match on them); values as set by our code.
_ALLOWED_TAGS = frozenset({"route", "status", "method", "feedback_id", "kind"})

# The only capture_message texts sent; any other becomes [Filtered].
_MESSAGES = frozenset({"http_5xx", "feedback_received"})

# The only contexts sent: the SDK's runtime / os (not trace: see the module doc).
_CONTEXTS = frozenset({"runtime", "os"})

# Loggers whose templates are sent: ours (backend.* from getLogger(__name__),
# trade_finder, ftf.*), whose templates test_error_log_templates.py
# keeps constant, and gunicorn's error log. A name matches itself or a child.
# Any other logger's template becomes [Filtered]; its name and level still go.
_OUR_LOGGERS = ("backend", "trade_finder", "ftf", "gunicorn.error")

_DIGIT, _LOWER, _UPPER = re.compile(r"\d"), re.compile(r"[a-z]"), re.compile(r"[A-Z]")


def _token_shaped(match) -> str:
    """A 24+ run is a token only with a digit, or with both cases: snake_case
    identifiers (prepared_trade_inventories, _drop_stale_deck_evidence) in an
    error message survive."""
    run = match.group(0)
    if _DIGIT.search(run) or (_LOWER.search(run) and _UPPER.search(run)):
        return _FILTERED
    return run


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
    # (with a digit or both cases; _token_shaped)
    (re.compile(r"[A-Za-z0-9_-]{24,}"), _token_shaped),
    # any run of 9+ digits: Sleeper user and league ids are 18-19
    (re.compile(r"\d{9,}"), _FILTERED),
)

# Top-level event keys the SDK fills from code or config, never from request
# data: sent as they are. Not server_name (the host name), nor _meta (it
# names what the SDK trimmed, header names among them).
_PASS_KEYS = frozenset({
    "event_id", "timestamp", "start_timestamp", "level", "logger", "platform",
    "release", "environment", "dist", "sdk", "modules",
    "fingerprint", "transaction", "transaction_info", "type", "debug_meta",
})

# The parts of an exception or thread entry sent: the code-derived ones (type
# and module group the issue; frames are file/function/line, no source:
# include_source_context=False). Never
# `value`, the exception's text.
_CODE_KEYS = frozenset({"type", "module", "mechanism", "stacktrace"})

# The parts of a frame sent: not abs_path (the checkout path; on a laptop, the
# user's home), vars, or source lines.
_FRAME_KEYS = frozenset({"filename", "module", "function", "lineno", "in_app"})

# report_5xx sends one http_5xx per (route, status) per worker per this many
# seconds. About 37 handled 5xx returns log no ERROR (a Sleeper outage's 503s,
# a platform write's 502s), so without a cap an outage is one event per
# request. Sentry is the alarm; the count is in the Render access log.
_HTTP_5XX_EVERY_S = 3600.0
_http_5xx_last: dict = {}
_http_5xx_lock = threading.Lock()


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
            include_source_context=False,       # frames: file, function, line; no code lines
            max_request_body_size="never",
            # No tracing or profiling: traces/profiles_sample_rate stay unset.
            auto_enabling_integrations=False,
            trace_propagation_targets=[],
            auto_session_tracking=False,
            integrations=[
                FlaskIntegration(),
                # No breadcrumbs, and no log lines shipped as Sentry Logs.
                LoggingIntegration(level=None, event_level=logging.ERROR, sentry_logs_level=None),
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


def _first_in_window(route: str, status: int) -> bool:
    now = time.monotonic()
    with _http_5xx_lock:
        last = _http_5xx_last.get((route, status))
        if last is not None and now - last < _HTTP_5XX_EVERY_S:
            return False
        _http_5xx_last[(route, status)] = now
        return True


def report_5xx(status: int) -> None:
    """after_request, for a status >= 500: one `http_5xx` event tagged with
    route, status and method, unless this request already captured an event
    (handle_unexpected_error's log.exception, or any other ERROR log on the
    way to the 5xx), so a 500 is never counted twice; and not for a 501 (our
    "not available for this platform or basis" answer, not a fault), or when
    this route and status already sent one within _HTTP_5XX_EVERY_S. Never
    raises."""
    if not _initialized or status == 501:
        return
    try:
        import sentry_sdk
        # The request's isolation scope inherits its parent's last id, hence
        # the comparison with the id noted at request start, not with None.
        if sentry_sdk.last_event_id() != g.get("_error_alerts_last_event"):
            return
        route = request.url_rule.rule if request.url_rule else "<unmatched>"
        if not _first_in_window(route, status):
            return
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("route", route)
            scope.set_tag("status", str(status))
            scope.set_tag("method", request.method)
            scope.fingerprint = ["http_5xx", route, str(status)]
            sentry_sdk.capture_message("http_5xx", level="error")
    except Exception as e:
        log.warning("error_alerts: http_5xx report failed: %s", type(e).__name__)


# ---------------------------------------------------------------------------
# The event allowlist (legal R28.23)
# ---------------------------------------------------------------------------

def _scrub_str(text: str) -> str:
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    return text


def _ours(logger) -> bool:
    return isinstance(logger, str) and any(
        logger == name or logger.startswith(name + ".") for name in _OUR_LOGGERS)


def _logentry(entry: dict, logger, record=None) -> dict:
    """The template (record.msg) only from a logger we control, and only when
    it is a str (log.error(exc) logs the exception's text), pattern-scrubbed
    as a second layer; otherwise [Filtered]. Every param is [Filtered],
    numbers too (a match_id is a /s/trade/ link code); `formatted` is rebuilt
    from those two, and dropped when they don't format (a %d)."""
    if not _ours(logger) or (record is not None and not isinstance(record.msg, str)):
        return {"message": _FILTERED}
    template = _scrub_str(entry["message"])
    raw = entry.get("params") or []
    params = {k: _FILTERED for k in raw} if isinstance(raw, dict) else [_FILTERED] * len(raw)
    out = {"message": template, "params": params}
    try:
        out["formatted"] = (template % (params if isinstance(params, dict) else tuple(params))
                            if params else template)
    except Exception:
        pass
    return out


def _stack(block: dict) -> dict:
    """`exception` / `threads`: per entry its type, module, mechanism and
    frames, each frame as _FRAME_KEYS. Never the value: an exception's text can
    carry a username or SQL parameters."""
    entries = []
    for entry in block.get("values") or []:
        kept = {k: v for k, v in entry.items() if k in _CODE_KEYS}
        if isinstance(kept.get("stacktrace"), dict):
            kept["stacktrace"] = {"frames": [
                {k: v for k, v in frame.items() if k in _FRAME_KEYS}
                for frame in kept["stacktrace"].get("frames") or []]}
        entries.append(kept)
    return {"values": entries}


def _route():
    """The request as sent: its method and Flask route pattern, never the path
    or query (a path can hold a username, an id or a bearer link such as
    /s/trade/<match_id>; share links carry ?ref=<username>). before_send runs
    on the capturing thread, so this is that thread's request; None outside
    one."""
    if not has_request_context():
        return None
    rule = request.url_rule
    return {"method": request.method, "url": rule.rule if rule else "<unmatched>"}


def _allowlisted(event: dict, hint) -> dict:
    out = {k: v for k, v in event.items() if k in _PASS_KEYS}
    if "request" in event:
        req = _route()
        if req is not None:
            out["request"] = req
    for key in ("exception", "threads"):
        if isinstance(event.get(key), dict):
            out[key] = _stack(event[key])
    if "logentry" in event:
        out["logentry"] = _logentry(event["logentry"], event.get("logger"),
                                    (hint or {}).get("log_record"))
    if "message" in event:
        out["message"] = event["message"] if event["message"] in _MESSAGES else _FILTERED
    if isinstance(event.get("tags"), dict):
        out["tags"] = {k: v for k, v in event["tags"].items() if k in _ALLOWED_TAGS}
    if isinstance(event.get("contexts"), dict):
        out["contexts"] = {k: v for k, v in event["contexts"].items() if k in _CONTEXTS}
    return out


def scrub_event(event, hint=None):
    """before_send: the event rebuilt from the allowlist above (extra, user,
    breadcrumbs and every unknown key dropped); None, so nothing is sent, when
    building it raises."""
    try:
        return _allowlisted(event, hint)
    except Exception:
        return None


def scrub_breadcrumb(crumb, hint=None):
    """before_breadcrumb: breadcrumbs are off. Logging records none
    (LoggingIntegration(level=None)); every other source, outbound HTTP
    among them, is dropped here."""
    return None
