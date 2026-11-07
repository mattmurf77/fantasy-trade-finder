"""Advisory scheduling cannot change a completed paired comparison."""
import copy

import pytest

from backend import outlook_calibration as calibration
from backend import server
from backend.outlook_calibration_adapter import VERSIONS
from backend.tests.test_calibration_round_adapter_execution import captured, fingerprint
from backend.tests.test_owner_generator_routes import harness, owner_harness
from backend.tests.test_owner_only_routes import exclusive, large_exclusive


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0., []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_pressure_wait_is_bounded_and_work_interval_is_guaranteed():
    clock = Clock()
    calls = []
    def pressure():
        calls.append(1)
        return True
    check = calibration._CooperativeYield(pressure, clock=clock, sleep=clock.sleep)
    check()
    assert len(clock.sleeps) == len(calls) == 10
    assert sum(clock.sleeps) == pytest.approx(1.)
    for _ in range(1000):
        check()
    assert len(calls) == 10
    clock.now += .099
    check()
    assert len(calls) == 10
    clock.now += .002
    check()
    assert len(calls) == len(clock.sleeps) == 20


def test_pressure_ends_early_and_idle_throttles_without_sleep():
    clock, values = Clock(), iter((True, True, False, False))
    check = calibration._CooperativeYield(lambda: next(values), clock=clock, sleep=clock.sleep)
    check()
    assert clock.sleeps == [.1, .1]
    clock.now += .101
    check()
    assert clock.sleeps == [.1, .1]
    check()  # Must not read the now-exhausted signal again within the interval.


def test_pressure_and_sleep_failures_remain_advisory():
    clock = Clock()
    def failed():
        raise RuntimeError("signal unavailable")
    check = calibration._CooperativeYield(failed, clock=clock, sleep=clock.sleep)
    check()
    assert len(clock.sleeps) == 10
    def no_sleep(_):
        raise RuntimeError("sleep unavailable")
    second = calibration._CooperativeYield(lambda: True, clock=clock, sleep=no_sleep)
    second()
    assert second.disabled
    second()  # Failure cannot poison a later candidate checkpoint.
    third = calibration._CooperativeYield(lambda: True, clock=failed, sleep=clock.sleep)
    third()
    assert third.disabled


@pytest.mark.parametrize("version", VERSIONS)
def test_actual_complete_arm_is_identical_with_repeated_pressure(captured, version, monkeypatch):
    before = copy.deepcopy(captured.owner_context)
    normal, normal_diag = captured.run_arm(version)
    clock = Clock()
    checker = calibration._CooperativeYield(lambda: True, clock=clock, sleep=clock.sleep)
    calls = []
    def check():
        # Advance simulated work occasionally; no wall-clock sleep in CI.
        if len(calls) % 20 == 0:
            clock.now += .101
        calls.append(1)
        checker()
    original = server._owner_cards_valid
    final_calls = []
    def final(cards, context, **control):
        assert "_check_current" not in context
        assert control["check_current"] is check
        start = len(calls)
        result = original(cards, context, **control)
        final_calls.append(len(calls) - start)
        return result
    monkeypatch.setattr(server, "_owner_cards_valid", final)
    yielded, yielded_diag = captured.run_arm(version, check_current=check)
    assert fingerprint(yielded) == fingerprint(normal)
    assert [c.owner_evaluation.snapshot_json for c in yielded] == [c.owner_evaluation.snapshot_json for c in normal]
    for diag in (normal_diag, yielded_diag):
        diag["generator"].pop("elapsed_seconds", None)
    assert yielded_diag == normal_diag
    assert captured.owner_context == before
    assert final_calls and final_calls[0] >= len(normal) + 1
    assert len(calls) > final_calls[0] + 7  # Actual generator checkpoints too.
    assert len(clock.sleeps) > 10
