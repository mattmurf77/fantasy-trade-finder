"""Ruling 15: the live value-core branch refuses a run that hit the core's safety
ceiling (a partial pool) and forwards `safety_ceiling_hit` in the job's diagnostics.

`CoreDiagnostics.safety_ceiling_hit` arrives with models-eng's count-bounded core
(`eng/value-core-count-bounded` @ a2006b28), not on main yet. The server reads it
defensively (missing = not hit), so these tests stub the engine result: one sets it,
one strips it. The flag `trade.value_core` stays off; `_vc_on()` lights it per test.
"""
import dataclasses
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server
from backend.tests.support import bakeoff_harness as H
from backend.tests.test_value_core_serving import _vc_card_ids, _vc_on, vc_stubs  # noqa: F401


def _core_patch(transform):
    """Wrap the stubbed pipeline.run so its result carries a transformed core."""
    from backend.value_core import pipeline
    stubbed = pipeline.run

    def run(*args, **kwargs):
        result = stubbed(*args, **kwargs)
        return dataclasses.replace(result, core=transform(result.core))

    return patch.object(pipeline, "run", run)


def _with_ceiling(value):
    def transform(core):
        fields = {k: v for k, v in vars(core).items() if k != "safety_ceiling_hit"}
        return SimpleNamespace(**fields, safety_ceiling_hit=value)
    return transform


def _without_ceiling(core):
    return SimpleNamespace(**{k: v for k, v in vars(core).items() if k != "safety_ceiling_hit"})


def test_ceiling_hit_run_is_refused_and_fails_the_job(vc_stubs, caplog):
    events, legacy_log = MagicMock(), MagicMock()
    with caplog.at_level("ERROR"):
        capture, job, _engine = H.run_capture(extra_patches=_vc_on() + [
            _core_patch(_with_ceiling(True)),
            patch.object(server, "record_event", events),
            patch.object(server, "log_trade_impressions", legacy_log)])
    assert len(vc_stubs) == 1                      # the core ran ...
    assert capture["status"] == "error" and capture["error"] == "value_core_failed"
    assert not job["cards"] and not _vc_card_ids(job)   # ... and nothing was served
    assert not capture["impressions"]
    legacy_log.assert_not_called()                 # no impressions, and no legacy fallback
    assert not [c for c in events.call_args_list if c.args[1] == "trades_generated"]
    assert "value_core" not in job
    assert any("safety ceiling hit" in r.getMessage() and r.levelname == "ERROR"
               for r in caplog.records)


@pytest.mark.parametrize("transform", [_without_ceiling, _with_ceiling(False)],
                         ids=["key_absent", "key_false"])
def test_run_without_ceiling_hit_serves_and_forwards_the_flag(vc_stubs, transform):
    capture, job, _engine = H.run_capture(extra_patches=_vc_on() + [_core_patch(transform)])
    assert capture["status"] == "complete", capture["error"]
    assert job["cards"] and len(_vc_card_ids(job)) == len(job["cards"])
    assert len(capture["impressions"]) == len(job["cards"])
    assert job["value_core"]["safety_ceiling_hit"] is False
    assert job["value_core"]["served"] == len(job["cards"])
