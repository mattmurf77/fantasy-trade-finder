"""The one HTTP client the crawler uses to read Sleeper.

Every request goes through ``SleeperClient.get``: a token-bucket throttle
(default 4 requests a second, hard maximum 10), timeouts, retry with back-off
on 429 / 5xx / network errors / malformed answers, and the hard stops below.
The transport is injectable; tests pass a fake and make no network call. Only
one client with the real transport may exist per process, and the CLI holds a
machine-wide lock (``cli.LOCK_PATH``) so only one crawler process runs at all.

Hard stops (``HardStop`` subclasses end the run; checkpoints stay intact so
the next run resumes):

* ``RateLimitStop`` -- ``max_consecutive_429`` 429s in a row (default 5, at
  most ``MAX_429``), or 429s on at least half of the last 40 responses once
  20 have been seen (an interleaved 429-429-429-429-200 pattern trips it).
* ``BlockedStop`` -- any 403, or any answer whose body carries a Cloudflare
  block marker (``CLOUDFLARE_MARKERS``): the crawler is being refused, and
  retrying is how a block becomes a ban.
* ``BadResponseStop`` -- a 200 whose body is not JSON (a challenge or error
  page): the API is not answering as an API.
* ``CircuitOpen`` -- ``max_consecutive_failures`` failed responses in a row
  (default 12 = two requests' full retry cycles of 6 attempts each: one
  request may fail outright and be recorded, two in a row means an outage),
  or three failed leagues in a row (raised by the pull).
"""
from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, deque

BASE_URL = "https://api.sleeper.app/v1"
DEFAULT_RATE = 4.0
MAX_RATE = 10.0
MAX_429 = 20
# Generic, no personal detail. Sleeper's REST v1 reads accept a plain UA (the
# existing research capture uses one); the Cloudflare 1010 trap documented in
# docs/integrations/sleeper.md §4 concerns the GraphQL/write paths.
USER_AGENT = "FTF-Research-Crawler/1.0"
CLOUDFLARE_MARKERS = (b"error code: 10", b"cf-error-details", b"Attention Required! | Cloudflare",
                      b"cf-browser-verification", b"challenge-platform", b"Just a moment...")
WINDOW = 40
WINDOW_MIN = 20
WINDOW_429_SHARE = 0.5


class SleeperError(Exception):
    """Base class for client failures."""


class HardStop(SleeperError):
    """The run must stop now. ``exit_code`` is the CLI's exit status."""
    exit_code = 1
    status = "stopped"


class RateLimitStop(HardStop):
    exit_code = 3
    status = "stopped_429"


class BlockedStop(HardStop):
    exit_code = 5
    status = "stopped_blocked"


class BadResponseStop(HardStop):
    exit_code = 6
    status = "stopped_bad_response"


class CircuitOpen(HardStop):
    exit_code = 7
    status = "stopped_circuit"


class RequestFailed(SleeperError):
    """A request that failed permanently (non-retryable status or retries spent)."""

    def __init__(self, endpoint: str, status):
        super().__init__(f"{endpoint} failed: {status}")
        self.endpoint = endpoint
        self.status = status


class TokenBucket:
    """Token bucket; capacity 1 by default, i.e. no bursts: two requests are
    never closer than 1/rate seconds. Clock and sleep are injectable. A clock
    that steps backwards adds no tokens and costs no extra wait."""

    def __init__(self, rate: float, capacity: float = 1.0,
                 clock=time.monotonic, sleep=time.sleep):
        if not (0 < float(rate) <= MAX_RATE):
            raise ValueError(f"rate must be in (0, {MAX_RATE}] requests/second")
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.clock = clock
        self.sleep = sleep
        self.tokens = self.capacity
        self.last = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            while True:
                now = self.clock()
                elapsed = max(0.0, now - self.last)
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last = now
                if self.tokens >= 1.0 - 1e-9:
                    self.tokens = max(0.0, self.tokens - 1.0)
                    return
                # At least 1 ms: a float-precision remainder (1e-11 s) must not
                # turn into a wait the clock cannot register.
                self.sleep(max(0.001, (1.0 - self.tokens) / self.rate))


def endpoint_class(path: str) -> str:
    """Bucket a path into a route template (never the ids)."""
    parts = [p for p in path.split("?")[0].strip("/").split("/") if p]
    if not parts:
        return "other"
    if parts[0] == "user":
        return "user.leagues" if len(parts) > 2 else "user"
    if parts[0] == "league":
        return "league" if len(parts) == 2 else f"league.{parts[2]}"
    if parts[0] == "draft":
        return "draft.picks" if len(parts) > 2 else "draft"
    return "other"


def urllib_transport(url: str, headers: dict, timeout: float):
    """The real transport: returns (status, headers, body). Network errors raise."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, dict((e.headers or {}).items()), body


_LIVE_CLIENT = None
_LIVE_LOCK = threading.Lock()


def _blocked(body: bytes) -> bool:
    return any(m in (body or b"")[:20000] for m in CLOUDFLARE_MARKERS)


class SleeperClient:
    def __init__(self, transport=None, *, rate: float = DEFAULT_RATE,
                 timeout: float = 20.0, max_retries: int = 5,
                 max_consecutive_429: int = 5, max_consecutive_failures: int = 12,
                 backoff_base: float = 2.0, backoff_cap: float = 120.0,
                 clock=time.monotonic, sleep=time.sleep, user_agent: str = USER_AGENT,
                 base_url: str = BASE_URL, rng=None):
        global _LIVE_CLIENT
        if not 1 <= int(max_consecutive_429) <= MAX_429:
            raise ValueError(f"max_consecutive_429 must be in [1, {MAX_429}]")
        if transport is None:
            with _LIVE_LOCK:
                if _LIVE_CLIENT is not None:
                    raise RuntimeError(
                        "one live Sleeper client per process; reuse it")
                _LIVE_CLIENT = self
            transport = urllib_transport
        self.transport = transport
        self.bucket = TokenBucket(rate, clock=clock, sleep=sleep)
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_consecutive_429 = int(max_consecutive_429)
        self.max_consecutive_failures = max_consecutive_failures
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.sleep = sleep
        self.clock = clock
        self.base_url = base_url.rstrip("/")
        self.headers = {"accept": "application/json", "user-agent": user_agent}
        self.rng = rng or random.Random()
        self.requests: Counter = Counter()
        self.statuses: Counter = Counter()
        self.consecutive_429 = 0
        self.consecutive_failures = 0
        self.recent: deque = deque(maxlen=WINDOW)    # True = that response was a 429
        self.nulls: Counter = Counter()               # null answers accepted as "none"

    @property
    def total_requests(self) -> int:
        return sum(self.requests.values())

    def _backoff(self, attempt: int) -> float:
        base = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        return base * (0.5 + self.rng.random() / 2)

    def _failed(self, cls, what):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures:
            raise CircuitOpen(
                f"Stopped: {self.consecutive_failures} failed responses in a row from Sleeper "
                f"(last: {cls} {what}). Sleeper looks down or unreachable. Work so far is "
                "checkpointed; re-run the same command later to resume.")

    def get(self, path: str, expect: type | None = None, null_ok: bool = False):
        """GET a v1 path. Returns parsed JSON, or None for a 404 (when no
        shape is expected). An empty body (zero bytes) is a failed attempt
        everywhere. ``expect=list``: anything but a JSON list (a dict, null)
        is a failed attempt and is retried; a 404 is a failure. With
        ``null_ok`` a JSON ``null`` is accepted as "none of that thing",
        returned as None and counted in ``self.nulls`` per endpoint class.
        Raises RequestFailed or a HardStop."""
        cls = endpoint_class(path)
        url = self.base_url + "/" + path.lstrip("/")
        attempt = 0
        while True:
            self.bucket.acquire()
            self.requests[cls] += 1
            retry_after = None
            try:
                status, headers, body = self.transport(url, dict(self.headers), self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                status, headers, body = None, {}, b""
            self.statuses[str(status)] += 1
            self.recent.append(status == 429)
            if status != 429:
                self.consecutive_429 = 0 if status is not None else self.consecutive_429
            if status == 403 or (body and _blocked(body)):
                raise BlockedStop(
                    f"Stopped: Sleeper refused the crawler ({cls}: HTTP {status}"
                    f"{', Cloudflare block page' if _blocked(body) else ''}). Do not retry "
                    "until the cause is understood (rate, User-Agent, IP). Work so far is "
                    "checkpointed.")
            if status == 200:
                text = (body or b"").strip()
                if not text:
                    self._failed(cls, "empty_body")
                    attempt += 1
                    if attempt > self.max_retries:
                        raise RequestFailed(cls, "empty_body")
                    self.sleep(self._backoff(attempt - 1))
                    continue
                try:
                    data = json.loads(text)
                except ValueError:
                    raise BadResponseStop(
                        f"Stopped: Sleeper answered {cls} with HTTP 200 and a body that is "
                        f"not JSON (starts {text[:15]!r}). Likely a challenge or error page. "
                        "Work so far is checkpointed.") from None
                if expect is None or isinstance(data, expect):
                    self.consecutive_failures = 0
                    return data
                if data is None and null_ok:
                    self.consecutive_failures = 0
                    self.nulls[cls] += 1
                    return None
                what = "not_a_list" if expect is list else "bad_shape"
                self._failed(cls, what)
            elif status == 404:
                self.consecutive_failures = 0
                if expect is list:
                    raise RequestFailed(cls, 404)
                return None
            elif status == 429:
                self.consecutive_429 += 1
                n429 = sum(self.recent)
                if self.consecutive_429 >= self.max_consecutive_429 or (
                        len(self.recent) >= WINDOW_MIN
                        and n429 >= WINDOW_429_SHARE * len(self.recent)):
                    raise RateLimitStop(
                        f"Stopped: Sleeper is rate-limiting the crawler ({self.consecutive_429} "
                        f"429s in a row; {n429} of the last {len(self.recent)} responses were "
                        f"429; last endpoint {cls}). Work so far is checkpointed. Wait, lower "
                        "--rate, and re-run the same command to resume.")
                ra = (headers or {}).get("Retry-After") or (headers or {}).get("retry-after")
                try:
                    retry_after = min(600.0, max(0.0, float(ra)))
                except (TypeError, ValueError):
                    retry_after = None
            elif status is not None and status < 500:
                self._failed(cls, status)
                raise RequestFailed(cls, status)
            else:
                self._failed(cls, status if status is not None else "network")
            attempt += 1
            if attempt > self.max_retries:
                if status == 200:
                    raise RequestFailed(cls, "not_a_list" if expect is list else "bad_shape")
                raise RequestFailed(cls, status if status is not None else "network")
            wait = self._backoff(attempt - 1)
            if retry_after is not None:
                wait = max(wait, retry_after)
            self.sleep(wait)
