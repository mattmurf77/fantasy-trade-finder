"""Daily-tick runner: the serial, single-flight step runner behind
POST /api/cron/daily-tick (docs/plans/daily-tick-fix/scope.md).

The route authenticates, calls `start()` and answers 202 at once. The steps
then run here on ONE daemon thread, in table order. Each step is isolated (a
raise becomes `outcome=error` and never skips the steps after it) and logs
exactly one line:

    daily-tick step=<key> ms=<int> outcome=<ok|skipped|error> detail=<short>

then one `daily-tick done ms=<int> steps=<n> errors=<k>` per run.

Deliberately does NOT import backend.server: server.py owns the step table and
the step bodies; this module only runs the table it is handed, so it is
testable alone.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, NamedTuple


class Step(NamedTuple):
    key: str
    fn: Callable    # fn(now) -> outcome | (outcome, detail); outcome is "ok" | "skipped"


class Result(NamedTuple):
    key: str
    outcome: str    # "ok" | "skipped" | "error"
    detail: Any
    ms: int


_lock = threading.Lock()              # single-flight: held for a whole run
_thread: threading.Thread | None = None
_started_at: float | None = None      # time.monotonic() of the in-flight run
_last_results: list[Result] | None = None


def run(steps, now, *, log) -> list[Result]:
    """Run every step synchronously, in order. Never raises for a step."""
    results: list[Result] = []
    run_t0 = time.monotonic()
    for step in steps:
        t0 = time.monotonic()
        try:
            ret = step.fn(now)
            outcome, detail = ret if isinstance(ret, tuple) else (ret, None)
        except Exception as e:
            log.exception("daily-tick: step %s raised", step.key)
            outcome, detail = "error", f"{type(e).__name__}: {e}"
        ms = int((time.monotonic() - t0) * 1000)
        log.log(logging.WARNING if outcome == "error" else logging.INFO,
                "daily-tick step=%s ms=%d outcome=%s detail=%s",
                step.key, ms, outcome, "-" if detail is None else detail)
        results.append(Result(step.key, outcome, detail, ms))
    log.info("daily-tick done ms=%d steps=%d errors=%d",
             int((time.monotonic() - run_t0) * 1000), len(results),
             sum(1 for r in results if r.outcome == "error"))
    return results


def start(steps, now, *, log) -> bool:
    """Start ONE run on a daemon thread. False (and nothing started) while a
    run is already in flight; the lock is released when the run ends, raise
    or not."""
    global _thread, _started_at, _last_results
    if not _lock.acquire(blocking=False):
        age = time.monotonic() - (_started_at or time.monotonic())
        log.warning("daily-tick: a run is already in flight (started %ds ago); "
                    "not starting another", int(age))
        return False
    _started_at = time.monotonic()
    _last_results = None

    def _body():
        global _last_results
        try:
            _last_results = run(steps, now, log=log)
        finally:
            _lock.release()

    try:
        _thread = threading.Thread(target=_body, name="daily-tick-runner",
                                   daemon=True)
        _thread.start()
    except Exception:
        _lock.release()   # a thread that never started must not wedge every later tick
        raise
    return True


def wait(timeout: float | None = None) -> list[Result] | None:
    """Test seam: join the most recent run and return its results, or None
    if it is still running after `timeout` (or no run was ever started)."""
    t = _thread
    if t is None:
        return None
    t.join(timeout)
    return None if t.is_alive() else _last_results
