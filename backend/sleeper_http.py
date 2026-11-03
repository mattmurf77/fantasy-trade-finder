"""Per-process Sleeper 429 circuit (S0, launch §3a).

Sleeper's public API rate-limits by IP. Before this module nothing on any
Sleeper read path handled a 429: `server._sleeper_get` retried only on an SSL
failure, so one throttled IP kept firing every consumer's reads into the
limit. Scope: docs/plans/trade-time-to-suggestion/scope-eng-s0-fetch.md §B.7.

THE RULE:
  * A 429 opens the circuit for
        min(CEILING_S, max(Retry-After, uniform(b/2, b))),  b = min(SOFT_CAP_S, BASE_S * 2**(n-1))
    where n counts consecutive throttling EPISODES (equal jitter: never near
    zero). A 429 arriving while the circuit is already open is the same
    episode: no new strike, it only extends the window to its own
    Retry-After when that ends later. A Retry-After above the soft cap is
    honored up to the ceiling.
  * While it is open, every guarded read fails fast with `SleeperRateLimited`
    BEFORE any network call. There are no in-line retries or sleeps: the app
    runs one sync worker, and a sleeping request thread would stall every tap.
  * Any successful read resets n.

Reads only. Sleeper writes (`sleeper_write.py`) are not guarded here.

Leaf module: stdlib imports only, safe to import from `database`-adjacent
leaves (`suggestion_telemetry`) and from `server`. Logs carry the league id
and the HTTP status only, never a URL.
"""
from __future__ import annotations

import contextlib
import email.utils
import logging
import random
import socket
import threading
import time
import urllib.error

log = logging.getLogger(__name__)

BASE_S = 2.0
SOFT_CAP_S = 600.0
CEILING_S = 3600.0

# Injectable for tests (monotonic for the window, wall clock for HTTP dates).
_monotonic = time.monotonic
_wall = time.time
_uniform = random.uniform

_lock = threading.Lock()
_open_until = 0.0
_strikes = 0


class SleeperRateLimited(urllib.error.URLError):
    """Raised instead of a network call while the circuit is open.

    A `URLError` subclass so every existing `except URLError` / `except
    Exception` fail-soft path treats it as "Sleeper unreachable".
    """

    def __init__(self, retry_in_s: float):
        self.retry_in_s = max(0.0, float(retry_in_s))
        super().__init__(f"sleeper circuit open ({self.retry_in_s:.0f}s left)")


def reset() -> None:
    """Close the circuit and forget strikes (tests; never called in prod)."""
    global _open_until, _strikes
    with _lock:
        _open_until, _strikes = 0.0, 0


def remaining_s() -> float:
    """Seconds until the circuit closes; 0.0 when closed."""
    with _lock:
        return max(0.0, _open_until - _monotonic())


def is_open() -> bool:
    return remaining_s() > 0.0


def check(league_id: str | None = None) -> None:
    """Raise `SleeperRateLimited` when the circuit is open. No I/O."""
    left = remaining_s()
    if left > 0.0:
        log.info("sleeper circuit open: read skipped league=%s retry_in=%.0fs",
                 league_id, left)
        raise SleeperRateLimited(left)


def parse_retry_after(value) -> float | None:
    """Retry-After as seconds from now: delta-seconds or an HTTP date.

    None when absent or unparseable (the caller then uses backoff alone).
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return float(int(text))
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    return max(0.0, when.timestamp() - _wall())


def delay_for(strikes: int, retry_after_s: float | None) -> float:
    """The open window for the `strikes`-th consecutive 429 (see module doc)."""
    n = max(1, int(strikes))
    b = min(SOFT_CAP_S, BASE_S * (2 ** (n - 1)))
    jittered = _uniform(b / 2.0, b)
    return min(CEILING_S, max(retry_after_s or 0.0, jittered))


def record_429(retry_after=None, *, league_id: str | None = None) -> float:
    """Open (or extend) the circuit after a 429.

    One throttling episode is ONE strike. A 429 that arrives while the
    circuit is already open (reads that were in flight when it opened — the
    session-init request thread and daemons, or gthread workers) adds no
    strike and draws no new jittered delay; it only pushes the window out
    when its own Retry-After ends later. Otherwise a single burst of 3–4
    throttled reads would count as 3–4 strikes and walk the window to the
    soft cap within a few episodes.

    Returns the seconds the circuit now stays open.
    """
    global _open_until, _strikes
    parsed = parse_retry_after(retry_after)
    with _lock:
        now = _monotonic()
        struck = now >= _open_until          # closed when this 429 arrived: a new episode
        if struck:
            _strikes += 1
            _open_until = now + delay_for(_strikes, parsed)
        elif parsed is not None:
            _open_until = max(_open_until, now + min(CEILING_S, parsed))
        window = _open_until - now
        strikes = _strikes
    log.warning("sleeper 429: circuit open %.0fs (%s) league=%s status=429 strikes=%d",
                window, "new strike" if struck else "already open: no strike, window extended only by Retry-After",
                league_id, strikes)
    return window


def record_success() -> None:
    global _strikes
    with _lock:
        _strikes = 0


def retry_after_of(err) -> str | None:
    """The Retry-After header of an HTTPError, if it carries one."""
    headers = getattr(err, "headers", None)
    if headers is None:
        return None
    try:
        return headers.get("Retry-After")
    except Exception:
        return None


@contextlib.contextmanager
def guard(league_id: str | None = None):
    """Wrap ONE Sleeper read: fail fast while open, record 429s and successes.

        with sleeper_http.guard(league_id):
            with opener(request, timeout=timeout) as resp: ...
    """
    check(league_id)
    try:
        yield
    except urllib.error.HTTPError as e:
        if e.code == 429:
            record_429(retry_after_of(e), league_id=league_id)
        raise
    record_success()


def classify(exc: BaseException | None) -> str:
    """Map a failed Sleeper read to `league_roster_state.last_error_code`.

    Closed set: rate_limited | blocked | http_4xx | http_5xx | timeout |
    network | invalid_payload. Anything unrecognized is `network`.
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, SleeperRateLimited):
            return "rate_limited"
        if isinstance(exc, urllib.error.HTTPError):
            code = int(getattr(exc, "code", 0) or 0)
            if code == 429:
                return "rate_limited"
            if code == 403:
                return "blocked"        # incl. Cloudflare 1010
            if 500 <= code < 600:
                return "http_5xx"
            return "http_4xx"
        if isinstance(exc, (socket.timeout, TimeoutError)):
            return "timeout"
        if isinstance(exc, urllib.error.URLError):
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                return "timeout"
            return "network"
        if isinstance(exc, ValueError):  # json.JSONDecodeError and shape checks
            return "invalid_payload"
        exc = exc.__cause__ or exc.__context__
    return "network"
