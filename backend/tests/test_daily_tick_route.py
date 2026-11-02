"""POST /api/cron/daily-tick — the 202 + single-flight runner contract.

docs/plans/daily-tick-fix/scope.md §3 (route tests) and the code-walk at
docs/plans/daily-tick-fix/code-walk.md. Pins:

  • the POST answers 202 `{ok: true, started: true}` before any step has
    finished, then all nine steps run in table order on the runner thread;
  • a second POST while a run is in flight answers `started: false`;
  • a missing/wrong X-Cron-Secret is rejected before any thread starts;
  • a raising step never stops the steps after it;
  • replenishment is DEFERRED (operator, 2026-10-23): flag off OR on, even
    past `replenish_weekday`, `_run_weekly_replenishment` is never called, the
    flag is never read, and the step logs `outcome=skipped detail=deferred: C2`;
  • the inline (sync) entries of steps 1, 2, 3 and 5 keep their async
    wrapper's gates and locks and call the same body.

Harness: test_deck_replenishment.py's isolated in-memory SQLite + patched
flag helpers. Every POST joins the run (`daily_tick.wait`) INSIDE its patches,
so no runner thread ever outlives them.
"""
import logging
import re
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.api_observability as api_obs
import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.receipts_service as rs
import backend.server as server
from backend import daily_tick
from backend.database import metadata

URL = "/api/cron/daily-tick"
HDR = {"X-Cron-Secret": "x"}
STEP_KEYS = ["roster_snapshot", "usage_trends", "receipts_grade",
             "rookie_monitor", "players_guard", "reengagement",
             "replenishment", "eval_nightly", "value_model_refit"]
NOW = datetime(2026, 10, 22, 13, 30, tzinfo=timezone.utc)   # a Thursday


@pytest.fixture()
def client():
    # StaticPool: the steps run on the runner thread, and SQLite's default
    # per-thread pool would hand that thread a FRESH, empty :memory: database.
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    flags_on: set = set()
    flag_fn = lambda k: k in flags_on   # noqa: E731
    daily_tick.wait(60)                  # never inherit another test's run
    assert not daily_tick._lock.locked()
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", flag_fn), \
         patch.object(feature_flags, "is_enabled", flag_fn), \
         patch.object(api_obs, "is_enabled", flag_fn), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "load_all_signed_up_users",
                      MagicMock(return_value=[])):
        yield c, flags_on
    assert not daily_tick._lock.locked(), "a test left a daily-tick run in flight"


def _stub_steps(fns: dict) -> ExitStack:
    """Replace `server._daily_tick_<key>` for each key in `fns`."""
    stack = ExitStack()
    for key, fn in fns.items():
        stack.enter_context(patch.object(server, f"_daily_tick_{key}", fn))
    return stack


def _ok(now):
    return "ok"


def _post_and_join(c) -> dict:
    r = c.post(URL, headers=HDR)
    assert r.status_code == 202
    assert r.get_json() == {"ok": True, "started": True}
    results = daily_tick.wait(30)
    assert results is not None, "daily-tick run did not finish"
    return {res.key: res for res in results}


def _clock_at(fixed):
    class _FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz else fixed.replace(tzinfo=None)
    return _FixedClock


# ---------------------------------------------------------------------------
# The route: 202 at once, nine steps in order, single-flight, auth first
# ---------------------------------------------------------------------------

def test_post_returns_202_at_once_then_runs_all_nine_steps_in_order(client):
    """Every step blocks until the test opens a gate AFTER the response is in
    hand, so the 202 provably does not wait on any step (stronger than a
    sleep, and costs no wall-clock time)."""
    c, _ = client
    gate = threading.Event()
    ran = []

    def slow(key):
        def fn(now):
            assert gate.wait(60), "gate never opened"
            ran.append((key, threading.current_thread().name, now))
            return "ok"
        return fn

    with _stub_steps({k: slow(k) for k in STEP_KEYS}), \
         patch.object(server, "datetime", _clock_at(NOW)):
        t0 = time.monotonic()
        r = c.post(URL, headers=HDR)
        elapsed = time.monotonic() - t0
        assert r.status_code == 202
        assert r.get_json() == {"ok": True, "started": True}
        # Loose on purpose (loaded CI runners): an inline handler would block
        # for the gate's full 60 s at step 1, so 10 s still discriminates.
        assert elapsed < 10.0
        assert ran == []                     # nothing finished before the 202
        gate.set()
        results = daily_tick.wait(30)

    assert [res.key for res in results] == STEP_KEYS
    assert [res.outcome for res in results] == ["ok"] * 9
    assert [k for k, _, _ in ran] == STEP_KEYS
    assert {name for _, name, _ in ran} == {"daily-tick-runner"}
    assert {now for _, _, now in ran} == {NOW}   # the handler's clock, to every step


def test_second_post_while_a_run_is_in_flight_answers_started_false(client):
    c, _ = client
    gate = threading.Event()

    def blocking(now):
        assert gate.wait(60)
        return "ok"

    with _stub_steps({k: (blocking if k == "roster_snapshot" else _ok)
                      for k in STEP_KEYS}):
        assert c.post(URL, headers=HDR).get_json() == {"ok": True, "started": True}
        try:
            r = c.post(URL, headers=HDR)
            assert r.status_code == 202
            assert r.get_json() == {"ok": True, "started": False}
        finally:
            gate.set()
        assert len(daily_tick.wait(30)) == 9


def test_missing_or_wrong_secret_is_rejected_and_starts_no_thread(client):
    c, _ = client
    with _stub_steps({k: _ok for k in STEP_KEYS}), \
         patch.object(server, "_CRON_SECRET", "s3cret"), \
         patch.object(daily_tick, "start", wraps=daily_tick.start) as start:
        assert c.post(URL).status_code == 401
        assert c.post(URL, headers={"X-Cron-Secret": "wrong"}).status_code == 401
        start.assert_not_called()
        assert not [t for t in threading.enumerate()
                    if t.name == "daily-tick-runner"]

        r = c.post(URL, headers={"X-Cron-Secret": "s3cret"})
        assert r.status_code == 202
        start.assert_called_once()
        assert len(daily_tick.wait(30)) == 9


def test_a_raising_step_never_stops_the_steps_after_it(client, caplog):
    caplog.set_level(logging.INFO, logger="trade_finder")
    c, _ = client
    ran = []

    def record(key):
        def fn(now):
            ran.append(key)
            if key == "receipts_grade":
                raise RuntimeError("grader fell over")
            return "ok"
        return fn

    with _stub_steps({k: record(k) for k in STEP_KEYS}):
        steps = _post_and_join(c)

    assert ran == STEP_KEYS
    assert steps["receipts_grade"].outcome == "error"
    assert steps["receipts_grade"].detail == "RuntimeError: grader fell over"
    assert all(steps[k].outcome == "ok" for k in STEP_KEYS if k != "receipts_grade")
    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("daily-tick step=")]
    assert [re.match(r"daily-tick step=(\S+) ms=\d+ outcome=", m).group(1)
            for m in lines] == STEP_KEYS


# ---------------------------------------------------------------------------
# Replenishment: deferred — unreachable from the tick, flag off or on
# ---------------------------------------------------------------------------

def test_replenishment_flag_off_never_calls_the_pass_and_logs_skipped(client, caplog):
    caplog.set_level(logging.INFO, logger="trade_finder")
    c, _ = client
    with _stub_steps({k: _ok for k in STEP_KEYS if k != "replenishment"}), \
         patch.object(server, "_deck_replenishment_enabled", lambda: False), \
         patch.object(server, "_run_weekly_replenishment", MagicMock()) as repl:
        steps = _post_and_join(c)

    repl.assert_not_called()
    assert (steps["replenishment"].outcome, steps["replenishment"].detail) == \
        ("skipped", "deferred: C2")
    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("daily-tick step=replenishment ")]
    assert len(lines) == 1
    assert re.fullmatch(
        r"daily-tick step=replenishment ms=\d+ outcome=skipped detail=deferred: C2",
        lines[0])


def test_replenishment_flag_on_past_the_weekday_is_still_deferred(client):
    """The operator's 2026-10-23 call: with `deck.replenishment` ON and the
    clock past `replenish_weekday`, the tick still runs, but step 7 never
    reads the flag and never calls the pass."""
    c, _ = client
    assert NOW.weekday() == 3                       # Thursday ≥ Wednesday (2)
    real_cfg = server._deck_cfg
    flag = MagicMock(return_value=True)
    with _stub_steps({k: _ok for k in STEP_KEYS if k != "replenishment"}), \
         patch.object(server, "_deck_replenishment_enabled", flag), \
         patch.object(server, "_deck_cfg",
                      lambda key, default: 2 if key == "replenish_weekday"
                      else real_cfg(key, default)), \
         patch.object(server, "datetime", _clock_at(NOW)), \
         patch.object(server, "_run_weekly_replenishment", MagicMock()) as repl:
        steps = _post_and_join(c)

    assert list(steps) == STEP_KEYS                 # the tick ran every step
    repl.assert_not_called()
    flag.assert_not_called()
    assert (steps["replenishment"].outcome, steps["replenishment"].detail) == \
        ("skipped", "deferred: C2")


# ---------------------------------------------------------------------------
# Steps 1, 2, 3, 5: the inline entries keep their async wrapper's guards
# ---------------------------------------------------------------------------

def test_roster_step_keeps_the_flag_and_weekday_gates_then_sweeps_inline(client):
    _, flags_on = client
    mon = datetime(2026, 10, 19, 13, 30, tzinfo=timezone.utc)
    tue = mon + timedelta(days=1)
    with patch.object(server, "_run_roster_snapshot_sweep",
                      MagicMock(return_value={"swept": 3})) as sweep, \
         patch.object(server, "_roster_snapshot_weekday_gate", lambda: 1):
        assert server._daily_tick_roster_snapshot(tue) == ("skipped", "flag off")
        flags_on.add("market.roster_history")
        assert server._daily_tick_roster_snapshot(mon) == ("skipped", "weekday_gate=1")
        sweep.assert_not_called()
        assert server._daily_tick_roster_snapshot(tue) == ("ok", {"swept": 3})
    sweep.assert_called_once_with(tue, server._ROSTER_SNAPSHOT_SWEEP_BUDGET,
                                  server.ACTIVE_LEAGUE_WINDOW_DAYS)


def test_usage_step_keeps_the_flag_gate_and_single_flight_lock(client):
    _, flags_on = client
    held = []

    def body(source, **kw):
        held.append((source, kw, server._usage_refresh_lock.locked()))
        return {"stored": [7]}

    with patch.object(server, "_run_usage_refresh", body):
        assert server._daily_tick_usage_trends(NOW) == ("skipped", "flag off")
        flags_on.add("usage_trends.enabled")
        assert server._usage_refresh_lock.acquire(blocking=False)
        try:
            assert server._daily_tick_usage_trends(NOW) == ("skipped", "busy")
        finally:
            server._usage_refresh_lock.release()
        assert held == []
        assert server._daily_tick_usage_trends(NOW) == ("ok", {"stored": [7]})
    assert held == [("daily_tick", {"now": NOW}, True)]   # the lock was held
    assert not server._usage_refresh_lock.locked()        # and released


def test_usage_async_wrapper_still_runs_the_same_body(client):
    seen = []
    with patch.object(server, "_run_usage_refresh",
                      lambda source, **kw: seen.append((source, kw)) or {}):
        assert server._start_usage_refresh("cron_route", weeks=[3]) is True
        for t in [t for t in threading.enumerate()
                  if t.name == "usage-trends-refresh"]:
            t.join(30)
    assert seen == [("cron_route", {"weeks": [3]})]
    assert not server._usage_refresh_lock.locked()


def test_receipts_step_keeps_both_guards_then_grades_inline(monkeypatch):
    calls = []
    monkeypatch.setattr(rs, "run_grading",
                        lambda **kw: calls.append(kw) or {"ok": True, "graded": 0})
    monkeypatch.setattr(rs, "grading_enabled", lambda: False)
    assert server._daily_tick_receipts_grade(NOW) == ("skipped", "flag off")
    monkeypatch.setattr(rs, "grading_enabled", lambda: True)
    monkeypatch.setattr(rs, "is_running", lambda: True)
    assert server._daily_tick_receipts_grade(NOW) == ("skipped", "in_flight")
    assert calls == []
    monkeypatch.setattr(rs, "is_running", lambda: False)
    assert server._daily_tick_receipts_grade(NOW) == ("ok", {"ok": True, "graded": 0})
    assert calls == [{"trigger": "daily_tick"}]


def test_players_step_keeps_every_guard_then_runs_the_worker_inline(monkeypatch):
    ran = []

    def worker():
        # The step claimed the in-flight flag before calling the body; the
        # real worker clears it in its `finally`, so the stub does too.
        ran.append((threading.current_thread().name, server._players_refresh_active))
        server._last_refresh_status = {"ok": True, "players": 5}
        with server._players_refresh_lock:
            server._players_refresh_active = False

    stale = server._PLAYERS_CACHE_TTL_SECONDS + 1
    monkeypatch.setattr(server, "_players_refresh_worker", worker)
    monkeypatch.setattr(server, "_last_refresh_status", {})
    monkeypatch.setattr(server, "_players_refresh_active", False)
    monkeypatch.setattr(server, "_players_cache_age_seconds", lambda: stale)

    monkeypatch.setattr(server, "_IS_PROD_ENV", False)          # local: never
    assert server._daily_tick_players_guard(NOW)[0] == "skipped"
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    monkeypatch.setattr(server, "_players_cache_age_seconds", lambda: 60.0)
    assert server._daily_tick_players_guard(NOW)[0] == "skipped"   # fresh cache
    monkeypatch.setattr(server, "_players_cache_age_seconds", lambda: stale)
    monkeypatch.setattr(server, "_PLAYERS_REFRESH_ENABLED", False)
    assert server._daily_tick_players_guard(NOW) == ("skipped", "FTF_PLAYERS_REFRESH=0")
    monkeypatch.setattr(server, "_PLAYERS_REFRESH_ENABLED", True)
    monkeypatch.setattr(server, "_players_refresh_active", True)
    assert server._daily_tick_players_guard(NOW) == ("skipped", "in_flight")
    assert ran == []

    monkeypatch.setattr(server, "_players_refresh_active", False)
    assert server._daily_tick_players_guard(NOW) == ("ok", {"ok": True, "players": 5})
    assert ran == [(threading.current_thread().name, True)]    # inline, flag held
    assert server._players_refresh_active is False
