"""The daily-tick runner on its own (backend/daily_tick.py) — no server import.

docs/plans/daily-tick-fix/scope.md §3. Pins: table order; per-step isolation
(a raise is `outcome=error` and every later step still runs); exactly one
`daily-tick step=` line per step in the exact format, plus one `done` line;
single-flight (`start()` while a run is in flight returns False and starts
nothing); the lock is released after a raising run.
"""
import logging
import pathlib
import re
import subprocess
import sys
import threading

import pytest

from backend import daily_tick
from backend.daily_tick import Step

LOG = logging.getLogger("test.daily_tick")
NOW = object()   # the runner only passes `now` through to each step
STEP_LINE = re.compile(
    r"^daily-tick step=(\S+) ms=\d+ outcome=(ok|skipped|error) detail=.+$")


def _recording(key, ran, ret="ok"):
    def fn(now):
        assert now is NOW
        ran.append(key)
        return ret
    return Step(key, fn)


def _boom(key, ran):
    def fn(now):
        ran.append(key)
        raise ValueError("kaput")
    return Step(key, fn)


def _step_lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith("daily-tick step=")]


@pytest.fixture(autouse=True)
def _no_leftover_run():
    """Each test starts with the module lock free and leaves it free."""
    daily_tick.wait(30)
    assert not daily_tick._lock.locked()
    yield
    daily_tick.wait(30)
    assert not daily_tick._lock.locked()


def test_steps_run_in_table_order():
    ran = []
    keys = ["a", "b", "c", "d"]
    results = daily_tick.run([_recording(k, ran) for k in keys], NOW, log=LOG)
    assert ran == keys
    assert [r.key for r in results] == keys
    assert all(r.outcome == "ok" for r in results)


def test_raising_step_is_an_error_and_every_later_step_still_runs(caplog):
    caplog.set_level(logging.INFO, logger=LOG.name)
    ran = []
    steps = [_recording("a", ran), _boom("b", ran),
             _recording("c", ran, ("skipped", "flag off")), _recording("d", ran)]
    results = daily_tick.run(steps, NOW, log=LOG)

    assert ran == ["a", "b", "c", "d"]
    by_key = {r.key: r for r in results}
    assert by_key["b"].outcome == "error"
    assert by_key["b"].detail == "ValueError: kaput"
    assert (by_key["c"].outcome, by_key["c"].detail) == ("skipped", "flag off")
    assert by_key["d"].outcome == "ok"
    # The traceback is logged too, on its own (non-step) line.
    tracebacks = [r for r in caplog.records if r.exc_info]
    assert len(tracebacks) == 1 and "step b raised" in tracebacks[0].getMessage()


def test_exactly_one_line_per_step_in_the_exact_format(caplog):
    caplog.set_level(logging.INFO, logger=LOG.name)
    ran = []
    steps = [_recording("a", ran), _boom("b", ran),
             _recording("c", ran, ("ok", {"sent": 2}))]
    daily_tick.run(steps, NOW, log=LOG)

    lines = _step_lines(caplog)
    assert len(lines) == 3
    assert [STEP_LINE.match(line).groups() for line in lines] == [
        ("a", "ok"), ("b", "error"), ("c", "ok")]
    assert lines[0].endswith(" detail=-")                     # no detail given
    assert lines[1].endswith(" detail=ValueError: kaput")
    assert lines[2].endswith(" detail={'sent': 2}")
    done = [r.getMessage() for r in caplog.records
            if r.getMessage().startswith("daily-tick done")]
    assert len(done) == 1
    assert re.fullmatch(r"daily-tick done ms=\d+ steps=3 errors=1", done[0])


def test_start_runs_on_one_daemon_thread_and_wait_returns_the_results():
    seen = []

    def fn(now):
        t = threading.current_thread()
        seen.append((t.name, t.daemon, t is threading.main_thread()))
        return "ok"

    assert daily_tick.start([Step("a", fn)], NOW, log=LOG) is True
    results = daily_tick.wait(30)
    assert [(r.key, r.outcome) for r in results] == [("a", "ok")]
    assert seen == [("daily-tick-runner", True, False)]


def test_second_start_while_in_flight_returns_false_and_starts_nothing(caplog):
    caplog.set_level(logging.INFO, logger=LOG.name)
    release = threading.Event()
    first, second = [], []

    def blocking(now):
        first.append(1)
        assert release.wait(30)
        return "ok"

    def never(now):
        second.append(1)
        return "ok"

    assert daily_tick.start([Step("slow", blocking)], NOW, log=LOG) is True
    try:
        assert daily_tick.start([Step("other", never)], NOW, log=LOG) is False
        warnings = [r.getMessage() for r in caplog.records
                    if r.levelno == logging.WARNING]
        assert any(re.search(r"already in flight \(started \d+s ago\)", w)
                   for w in warnings)
    finally:
        release.set()
    results = daily_tick.wait(30)
    assert [r.key for r in results] == ["slow"]
    assert first == [1] and second == []           # the second run never started


def test_lock_is_released_after_a_raising_step():
    ran = []
    assert daily_tick.start([_boom("b", ran)], NOW, log=LOG) is True
    assert daily_tick.wait(30)[0].outcome == "error"
    assert not daily_tick._lock.locked()
    assert daily_tick.start([_recording("next", ran)], NOW, log=LOG) is True
    assert daily_tick.wait(30)[0].key == "next"
    assert ran == ["b", "next"]


def test_lock_is_released_even_when_a_run_escapes_step_isolation(monkeypatch):
    """Only Exception is isolated per step; a BaseException ends the run, and
    the `finally` must still free the lock so tomorrow's tick can start."""
    class _Abort(BaseException):
        pass

    def abort(now):
        raise _Abort()

    escaped = []
    monkeypatch.setattr(threading, "excepthook",
                        lambda args: escaped.append(args.exc_type))
    assert daily_tick.start([Step("abort", abort)], NOW, log=LOG) is True
    assert daily_tick.wait(30) is None                # no results: the run aborted
    assert escaped == [_Abort]
    assert not daily_tick._lock.locked()
    assert daily_tick.start([Step("ok", lambda now: "ok")], NOW, log=LOG) is True
    assert daily_tick.wait(30)[0].outcome == "ok"


def test_runner_module_does_not_import_server():
    """Importing server runs init_db() and starts background loops, so the
    runner must stay importable (and testable) without it."""
    src = open(daily_tick.__file__).read()
    assert not re.search(r"^\s*(from|import)\s+\S*server\b", src, re.M)
    child = subprocess.run(
        [sys.executable, "-c",
         "import sys, backend.daily_tick; "
         "assert 'backend.server' not in sys.modules"],
        cwd=pathlib.Path(__file__).resolve().parents[2],
        capture_output=True, text=True, timeout=60)
    assert child.returncode == 0, child.stderr
