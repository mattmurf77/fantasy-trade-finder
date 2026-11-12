"""Sleeper trade universe crawler: the one HTTP client (research-plan §5.2, §8.1 phase 1).

Covers: the token bucket never exceeds its rate; the rate is capped at 10;
retry with back-off on 5xx and network errors; Retry-After honoured on 429;
a hard stop after N consecutive 429s; 404 is None; per-endpoint counters;
a generic User-Agent; only one live (real-transport) client per process.
All transports are fakes: no network.
"""
from __future__ import annotations

import urllib.error

import pytest

from backend.sleeper_universe import client as cl
from backend.tests.support.sleeper_universe_world import FakeClock


def _transport(statuses, calls):
    def t(url, headers, timeout):
        calls.append((url, headers))
        st = statuses.pop(0) if statuses else 200
        if st == "net":
            raise urllib.error.URLError("down")
        if isinstance(st, tuple):
            return st[0], st[1], b""
        return st, {}, (b'{"ok": 1}' if st == 200 else b"")
    return t


def test_throttle_never_exceeds_rate():
    clock = FakeClock()
    times = []
    c = cl.SleeperClient(lambda u, h, t: (times.append(clock()), (200, {}, b"[]"))[1],
                         rate=4, clock=clock, sleep=clock.sleep)
    for _ in range(40):
        c.get("/league/1/rosters")
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert min(gaps) >= 0.25 - 1e-9
    # any one-second window holds at most 4 requests (plus the boundary one)
    for i, t0 in enumerate(times):
        assert sum(1 for t in times[i:] if t < t0 + 1.0) <= 4


def test_rate_cap_is_ten():
    with pytest.raises(ValueError):
        cl.SleeperClient(lambda *a: (200, {}, b""), rate=10.5)
    cl.SleeperClient(lambda *a: (200, {}, b""), rate=10)


def test_stops_after_consecutive_429s():
    clock = FakeClock()
    calls = []
    c = cl.SleeperClient(_transport([429] * 20, calls), rate=4, max_consecutive_429=5,
                         clock=clock, sleep=clock.sleep)
    with pytest.raises(cl.RateLimitStop, match="5 429s in a row"):
        c.get("/league/1/rosters")
    assert len(calls) == 5


def test_429_counter_spans_requests_and_resets_on_success():
    clock = FakeClock()
    calls = []
    c = cl.SleeperClient(_transport([429, 429, 200, 429, 429, 200], calls), rate=4,
                         max_consecutive_429=3, clock=clock, sleep=clock.sleep)
    assert c.get("/a") == {"ok": 1}
    assert c.get("/b") == {"ok": 1}
    assert c.consecutive_429 == 0


def test_retry_after_is_honoured_and_5xx_retried():
    clock = FakeClock()
    calls = []
    c = cl.SleeperClient(_transport([(429, {"Retry-After": "30"}), 503, "net", 200], calls),
                         rate=4, clock=clock, sleep=clock.sleep)
    assert c.get("/league/1") == {"ok": 1}
    assert len(calls) == 4
    assert max(clock.sleeps) >= 30


def test_permanent_failure_and_404():
    clock = FakeClock()
    c = cl.SleeperClient(_transport([404, 400, 500, 500, 500, 500, 500, 500], []), rate=4,
                         max_retries=5, clock=clock, sleep=clock.sleep)
    assert c.get("/league/1") is None
    with pytest.raises(cl.RequestFailed):
        c.get("/league/2")
    with pytest.raises(cl.RequestFailed):
        c.get("/league/3")


def test_endpoint_counters_and_generic_user_agent():
    clock = FakeClock()
    calls = []
    c = cl.SleeperClient(_transport([], calls), clock=clock, sleep=clock.sleep)
    for path in ("/user/x", "/user/1/leagues/nfl/2026", "/league/1", "/league/1/transactions/3",
                 "/league/1/transactions/4", "/draft/9/picks", "/state/nfl"):
        c.get(path)
    assert c.requests == {"user": 1, "user.leagues": 1, "league": 1,
                          "league.transactions": 2, "draft.picks": 1, "other": 1}
    ua = calls[0][1]["user-agent"]
    assert ua == cl.USER_AGENT and "@" not in ua and "matt" not in ua.lower()


def test_one_live_client_per_process(monkeypatch):
    monkeypatch.setattr(cl, "_LIVE_CLIENT", None)
    cl.SleeperClient()          # real transport, never used: no request is made
    with pytest.raises(RuntimeError, match="one live Sleeper client"):
        cl.SleeperClient()
    monkeypatch.setattr(cl, "_LIVE_CLIENT", None)
