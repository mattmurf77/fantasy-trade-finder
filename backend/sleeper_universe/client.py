"""The one HTTP client the crawler uses to read Sleeper.

Every request goes through ``SleeperClient.get``: a token-bucket throttle
(default 4 requests a second, hard maximum 10), timeouts, retry with back-off
on 429 / 5xx / network errors, a hard stop after N consecutive 429s, and a
request counter per endpoint class. The transport is injectable; tests pass a
fake and make no network call. Only one client with the real transport may
exist per process, so nothing can open a second, unthrottled path.
"""
from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

BASE_URL = "https://api.sleeper.app/v1"
DEFAULT_RATE = 4.0
MAX_RATE = 10.0
# Generic, no personal detail. Sleeper's REST v1 reads accept a plain UA (the
# existing research capture uses one); the Cloudflare 1010 trap documented in
# docs/integrations/sleeper.md §4 concerns the GraphQL/write paths.
USER_AGENT = "FTF-Research-Crawler/1.0"


class SleeperError(Exception):
    """Base class for client failures."""


class RateLimitStop(SleeperError):
    """Raised after too many consecutive 429s. The run must stop."""


class RequestFailed(SleeperError):
    """A request that failed permanently (non-retryable status or retries spent)."""

    def __init__(self, endpoint: str, status):
        super().__init__(f"{endpoint} failed: {status}")
        self.endpoint = endpoint
        self.status = status


class TokenBucket:
    """Token bucket; capacity 1 by default, i.e. no bursts: two requests are
    never closer than 1/rate seconds. Clock and sleep are injectable."""

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
                self.tokens = min(self.capacity,
                                  self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                self.sleep((1.0 - self.tokens) / self.rate)


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


class SleeperClient:
    def __init__(self, transport=None, *, rate: float = DEFAULT_RATE,
                 timeout: float = 20.0, max_retries: int = 5,
                 max_consecutive_429: int = 5, backoff_base: float = 2.0,
                 backoff_cap: float = 120.0, clock=time.monotonic,
                 sleep=time.sleep, user_agent: str = USER_AGENT,
                 base_url: str = BASE_URL, rng=None):
        global _LIVE_CLIENT
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
        self.max_consecutive_429 = max_consecutive_429
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

    @property
    def total_requests(self) -> int:
        return sum(self.requests.values())

    def _backoff(self, attempt: int) -> float:
        base = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        return base * (0.5 + self.rng.random() / 2)

    def get(self, path: str):
        """GET a v1 path. Returns parsed JSON, or None for 404 / an empty body.
        Raises RequestFailed or RateLimitStop."""
        cls = endpoint_class(path)
        url = self.base_url + "/" + path.lstrip("/")
        attempt = 0
        while True:
            self.bucket.acquire()
            self.requests[cls] += 1
            retry_after = None
            try:
                status, headers, body = self.transport(url, dict(self.headers),
                                                       self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError,
                    OSError):
                status, headers, body = None, {}, b""
            self.statuses[str(status)] += 1
            if status == 200:
                self.consecutive_429 = 0
                text = (body or b"").strip()
                if not text:
                    return None
                return json.loads(text)
            if status == 404:
                self.consecutive_429 = 0
                return None
            if status == 429:
                self.consecutive_429 += 1
                if self.consecutive_429 >= self.max_consecutive_429:
                    raise RateLimitStop(
                        f"Stopped: {self.consecutive_429} consecutive HTTP 429 "
                        f"responses from Sleeper (last endpoint {cls}). Work so "
                        "far is checkpointed. Wait, lower --rate, and re-run the "
                        "same command to resume.")
                ra = (headers or {}).get("Retry-After") or (headers or {}).get("retry-after")
                try:
                    retry_after = min(600.0, max(0.0, float(ra)))
                except (TypeError, ValueError):
                    retry_after = None
            elif status is not None and status < 500:
                raise RequestFailed(cls, status)
            attempt += 1
            if attempt > self.max_retries:
                raise RequestFailed(cls, status if status is not None else "network")
            wait = self._backoff(attempt - 1)
            if retry_after is not None:
                wait = max(wait, retry_after)
            self.sleep(wait)
