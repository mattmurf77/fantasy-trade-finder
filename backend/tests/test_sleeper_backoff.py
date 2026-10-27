"""S0 — the per-process Sleeper 429 circuit (backend/sleeper_http.py).

Pins (scope-eng-s0-fetch.md §B.7):
  • a 429 opens the circuit for max(Retry-After, equal-jitter backoff),
    soft cap 600 s, hard ceiling 3,600 s; Retry-After as seconds or HTTP date
  • ONE strike per throttling episode: 429s that land while the circuit is
    already open add no strike (a larger Retry-After only extends the window)
  • while open every guarded read fails fast — no network, no fixture read
  • a success resets the strike count (recovery)
  • `_sleeper_get` (via the shipped FTF_SLEEPER_FIXTURES_DIR seam) and the
    three urllib-direct fetchers all share the one circuit
  • the circuit never turns into a data clobber: the owned-pick replace-sync
    and the draft-status write are skipped while it is open (G-015 class)

No network: cassettes in a tmp dir, fake openers, an injected clock.
"""

import email.utils
import json
import random
import urllib.error

import pytest

import backend.server as server
import backend.sleeper_http as sh
import backend.sleeper_trades_service as trades_service
import backend.suggestion_telemetry as sugg_tel
import backend.trade_block_service as tb_service

LID = "1338231586314780672"


class _Clock:
    def __init__(self):
        self.mono = 1000.0
        self.wall = 1_700_000_000.0


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(sh, "_monotonic", lambda: c.mono)
    monkeypatch.setattr(sh, "_wall", lambda: c.wall)
    sh.reset()
    yield c
    sh.reset()


def _http_error(code, headers=None):
    return urllib.error.HTTPError("https://api.sleeper.app/v1/x", code, "test", headers, None)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def test_429_with_retry_after_seconds_opens_for_at_least_that(clock, monkeypatch):
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)   # backoff b=2 < 30
    assert sh.record_429("30", league_id=LID) == 30.0
    clock.mono += 29.9
    assert sh.is_open()
    clock.mono += 0.2
    assert not sh.is_open()


def test_429_with_http_date_retry_after(clock, monkeypatch):
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: lo)
    when = email.utils.formatdate(clock.wall + 120, usegmt=True)
    assert sh.parse_retry_after(when) == pytest.approx(120.0)
    assert sh.record_429(when) == pytest.approx(120.0)


@pytest.mark.parametrize("value", [None, "", "soon", "-5"])
def test_unusable_retry_after_falls_back_to_backoff(value, monkeypatch):
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)
    assert sh.record_429(value) == 2.0          # strike 1: b = 2


def test_429_without_retry_after_backs_off_exponentially(clock, monkeypatch):
    # Separate episodes: each 429 arrives after the previous window closed.
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)
    windows = []
    for _ in range(5):
        windows.append(sh.record_429(None))
        clock.mono += windows[-1] + 0.01
    assert windows == [2.0, 4.0, 8.0, 16.0, 32.0]


def test_concurrent_429s_while_open_are_one_strike(clock, monkeypatch):
    """QA P2 (#378): a burst of throttled reads already in flight when the
    circuit opened (request thread + daemons, gthread workers) is ONE episode."""
    import threading
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)
    n = 8
    barrier = threading.Barrier(n)
    windows = []

    def hit():
        barrier.wait()
        windows.append(sh.record_429(None))

    threads = [threading.Thread(target=hit) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert len(windows) == n
    assert sh._strikes == 1
    assert sh.remaining_s() == 2.0                      # the 1-strike window
    for _ in range(3):                                  # back-to-back, same episode
        assert sh.record_429(None) == 2.0
    assert sh._strikes == 1


def test_next_429_after_the_window_closed_is_strike_two(clock, monkeypatch):
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)
    sh.record_429(None)
    sh.record_429(None)                                 # same episode
    clock.mono += 2.01                                  # window over
    assert sh.record_429(None) == 4.0                   # strike 2: the progression still works
    assert sh._strikes == 2


def test_larger_retry_after_while_open_extends_without_a_strike(clock, monkeypatch):
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)
    sh.record_429(None)                                 # strike 1, 2 s
    assert sh.record_429("30") == 30.0                  # extended to its Retry-After
    assert sh._strikes == 1
    assert sh.record_429("5") == 30.0                   # a smaller one never shrinks it
    assert sh.record_429("99999") == sh.CEILING_S       # and the ceiling still holds
    assert sh._strikes == 1


def test_jitter_stays_inside_equal_jitter_bounds(monkeypatch):
    rng = random.Random(7)
    monkeypatch.setattr(sh, "_uniform", rng.uniform)
    for strikes in range(1, 15):
        b = min(sh.SOFT_CAP_S, sh.BASE_S * 2 ** (strikes - 1))
        for _ in range(50):
            d = sh.delay_for(strikes, None)
            assert b / 2 <= d <= b, (strikes, d)


def test_soft_cap_and_hard_ceiling(monkeypatch):
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)
    assert sh.delay_for(40, None) == sh.SOFT_CAP_S == 600.0
    # A Retry-After above the soft cap is honored, up to the ceiling only.
    assert sh.delay_for(1, 1200.0) == 1200.0
    assert sh.delay_for(1, 99_999.0) == sh.CEILING_S == 3600.0


def test_fail_fast_while_open_and_recovery(clock, monkeypatch):
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)
    sh.record_429(None)                                  # strike 1 → 2 s
    sh.record_429(None)                                  # same episode: still 2 s
    ran = []
    with pytest.raises(sh.SleeperRateLimited):
        with sh.guard(LID):
            ran.append(1)
    assert ran == []                                     # body never ran
    clock.mono += 5
    with sh.guard(LID):                                  # closed again
        ran.append(1)
    assert ran == [1]
    assert sh.record_429(None) == 2.0                    # success reset strikes


def test_rate_limited_is_a_urlerror():
    # Existing `except URLError` / `except Exception` fail-soft paths keep working.
    assert issubclass(sh.SleeperRateLimited, urllib.error.URLError)


@pytest.mark.parametrize("exc, code", [
    (sh.SleeperRateLimited(3), "rate_limited"),
    (_http_error(429), "rate_limited"),
    (_http_error(403), "blocked"),
    (_http_error(404), "http_4xx"),
    (_http_error(502), "http_5xx"),
    (TimeoutError(), "timeout"),
    (urllib.error.URLError(TimeoutError()), "timeout"),
    (urllib.error.URLError("dns"), "network"),
    (ValueError("invalid Sleeper response"), "invalid_payload"),
    (json.JSONDecodeError("x", "y", 0), "invalid_payload"),
])
def test_classify(exc, code):
    assert sh.classify(exc) == code


# ---------------------------------------------------------------------------
# `_sleeper_get` through the fixture seam
# ---------------------------------------------------------------------------

@pytest.fixture()
def cassettes(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_SLEEPER_FIXTURES_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_SLEEPER_RECORD", False)

    def put(rel, doc):
        path = tmp_path / f"{rel}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc))

    return put


def test_sleeper_get_429_cassette_opens_the_shared_circuit(cassettes, monkeypatch):
    cassettes(f"league/{LID}/rosters",
              {"__http_error__": 429, "__headers__": {"Retry-After": "30"}})
    cassettes(f"league/{LID}/users", [{"user_id": "1"}])
    with pytest.raises(urllib.error.HTTPError) as err:
        server._sleeper_get(f"https://api.sleeper.app/v1/league/{LID}/rosters")
    assert err.value.code == 429
    assert sh.remaining_s() >= 30.0

    reads = []
    real = server._sleeper_get_unguarded
    monkeypatch.setattr(server, "_sleeper_get_unguarded",
                        lambda url, timeout=15: (reads.append(url), real(url, timeout))[1])
    with pytest.raises(sh.SleeperRateLimited):
        server._sleeper_get(f"https://api.sleeper.app/v1/league/{LID}/users")
    assert reads == []                                   # not even a fixture read


def test_sleeper_get_success_resets_strikes(cassettes, clock, monkeypatch):
    monkeypatch.setattr(sh, "_uniform", lambda lo, hi: hi)
    cassettes(f"league/{LID}", {"league_id": LID})
    sh.record_429(None)
    clock.mono += 10
    assert server._sleeper_get(f"https://api.sleeper.app/v1/league/{LID}") == {"league_id": LID}
    assert sh.record_429(None) == 2.0


# ---------------------------------------------------------------------------
# The three urllib-direct fetchers share it
# ---------------------------------------------------------------------------

class _Opener:
    def __init__(self, exc=None):
        self.calls, self.exc = 0, exc

    def __call__(self, request, timeout=15):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        raise AssertionError("no fake body configured")


DIRECT_FETCHERS = [
    lambda op: tb_service._fetch_rosters(LID, _opener=op),
    lambda op: tb_service.fetch_league_players(LID, _opener=op),
    lambda op: trades_service.fetch_week_transactions(LID, 1, _opener=op),
    lambda op: sugg_tel.fetch_league_roster_map(LID, _opener=op),
]


@pytest.mark.parametrize("fetch", DIRECT_FETCHERS)
def test_direct_fetchers_fail_fast_while_open(fetch):
    sh.record_429("60")
    op = _Opener()
    with pytest.raises(sh.SleeperRateLimited):
        fetch(op)
    assert op.calls == 0


@pytest.mark.parametrize("fetch", DIRECT_FETCHERS)
def test_direct_fetchers_open_the_circuit_on_429(fetch):
    op = _Opener(exc=_http_error(429, {"Retry-After": "45"}))
    with pytest.raises(urllib.error.HTTPError):
        fetch(op)
    assert sh.remaining_s() >= 45.0


# ---------------------------------------------------------------------------
# Never a clobber amplifier
# ---------------------------------------------------------------------------

ROSTERS = [{"roster_id": 1, "owner_id": "u1", "players": ["p1"]},
           {"roster_id": 2, "owner_id": "u2", "players": ["p2"]}]
META = {"league_id": LID, "season": "2026", "total_rosters": 2,
        "settings": {"draft_rounds": 3}}


def test_owned_pick_sync_keeps_prior_snapshot_while_open(cassettes, monkeypatch):
    # traded_picks and drafts both fail soft to [] — while the circuit is
    # open that [] must not reach the REPLACE sync (it would reset traded picks).
    monkeypatch.setattr(server, "sync_draft_picks",
                        lambda **kw: pytest.fail("replace-sync ran on skipped reads"))
    monkeypatch.setattr(server, "save_draft_slot_order",
                        lambda *a, **kw: pytest.fail("slot order written on skipped reads"))
    sh.record_429("60")
    assert server._sync_sleeper_owned_picks(
        LID, {"u1": "A", "u2": "B"}, "1qb_ppr", rosters=ROSTERS, meta=META) is None


def test_owned_pick_sync_429_on_traded_picks_itself_is_not_written(cassettes, monkeypatch):
    cassettes(f"league/{LID}/traded_picks", {"__http_error__": 429})
    cassettes(f"league/{LID}/drafts", [])
    monkeypatch.setattr(server, "sync_draft_picks",
                        lambda **kw: pytest.fail("replace-sync ran on a throttled read"))
    assert server._sync_sleeper_owned_picks(
        LID, {"u1": "A", "u2": "B"}, "1qb_ppr", rosters=ROSTERS, meta=META) is None


def test_draft_status_not_written_while_open(monkeypatch):
    from backend import draft_status as ds
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": "sleeper", "season": 2026, "total_rosters": 2})
    monkeypatch.setattr(server, "_draft_status_is_fresh", lambda ctx: False)
    monkeypatch.setattr(server, "_detect_league_draft_status",
                        lambda lid, ctx: ds.DraftStatus(ds.UNKNOWN, ds.LOW, ds.SRC_NONE, {}))
    monkeypatch.setattr(server, "set_league_draft_status",
                        lambda *a, **kw: pytest.fail("verdict written from skipped reads"))
    sh.record_429("60")
    assert server._refresh_league_draft_status(LID) is None
