"""One trade job = one read of each shared input.

Before this file's fix, a single POST /api/trades/generate read the user's
league preference TWICE (request thread for the cache-freshness key, worker
again), read `draft_picks` up to FOUR times (the request thread's outlook
seed, then the worker's outlook seed + opponent pick shares + owned-pick
injection) and ran one `load_league_preference` PER OPPONENT inside the
worker.

What is pinned here:

  • the per-opponent preference loop is a single `load_league_preferences_bulk`
    call, whatever the league size;
  • `draft_picks` is read at most once per job, no matter how many consumers
    the job has;
  • a caller that already resolved the preference + seeded outlook (the
    generate route, which must resolve them anyway) hands them over in
    `prefs_preload` and the worker reads NEITHER — and lands on exactly the
    outlook value the request thread keyed the cache on;
  • a caller that supplies nothing (session_init pre-gen, the replenishment
    cron) still gets the historical self-loading behavior.

Harness: `backend/tests/support/bakeoff_harness.py` — the same real
`_run_trade_job` the golden runs through, over a 2-opponent league.
"""

from unittest.mock import patch

import pytest

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend.tests.support import bakeoff_harness as H


class _Counter:
    """Wraps a real (or stub) loader and records how often it ran."""

    def __init__(self, fn):
        self._fn = fn
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        return self._fn(*a, **kw)


@pytest.fixture(autouse=True)
def _restore_flags():
    yield
    ff.reload()


@pytest.fixture()
def counted(monkeypatch):
    """Count every read the worker can issue for these three inputs.

    `trade.outlook_infer` is pinned ON so the opponent-preference path (the
    one that used to be a per-member query loop) actually runs.
    """
    flags = dict(ff.flags_dict())
    flags["trade.outlook_infer"] = True
    monkeypatch.setattr(ff, "_flags_cache", flags, raising=False)

    single = _Counter(lambda **kw: None)                     # no stored prefs
    bulk   = _Counter(db_module.load_league_preferences_bulk)
    picks  = _Counter(db_module.load_draft_picks)
    return {
        "single": single, "bulk": bulk, "picks": picks,
        "patches": [
            patch.object(server, "load_league_preference", single),
            patch.object(server, "load_league_preferences_bulk", bulk),
            patch.object(server, "load_draft_picks", picks),
        ],
    }


def test_one_job_reads_each_source_once(counted):
    """N opponents ⇒ one bulk preference read, one draft-pick read, and at
    most one singular preference read (the user's own, unsupplied here).

    SABOTAGE: restore the `for m in g_league.members: load_league_preference(...)`
    loop and `bulk.calls` drops to 0 while `single.calls` climbs with the
    league size.
    """
    _capture, job, _engine = H.run_capture(extra_patches=counted["patches"])
    assert job["status"] == "complete", job.get("error")

    assert counted["single"].calls <= 1
    assert counted["bulk"].calls == 1
    assert counted["picks"].calls == 1


def test_a_preloading_caller_makes_the_worker_read_neither(counted):
    """The generate route resolves the preference + seeded outlook to build
    the cache-freshness key; handing those to the worker removes both reads
    AND makes the two threads agree by construction — the job's
    `outlook_value` is exactly the value the cache was keyed on."""
    preload = {"prefs": {"team_outlook": "rebuilder",
                         "acquire_positions": [],
                         "trade_away_positions": [],
                         "avoid_positions": []},
               "seeded_outlook": None}
    _capture, job, _engine = H.run_capture(
        extra_patches=counted["patches"], prefs_preload=preload)
    assert job["status"] == "complete", job.get("error")

    assert counted["single"].calls == 0
    assert job["outlook_value"] == "rebuilder"
    # Declared outlook ⇒ no seed, so the only draft-pick read left is the
    # opponent-share one.
    assert counted["picks"].calls == 1


def test_a_preloaded_seed_is_used_verbatim(counted):
    """No declared outlook + a seeded one from the request thread: the worker
    adopts the request thread's seed instead of re-inferring it (which is
    what would let the two sides disagree and miss the cache)."""
    preload = {"prefs": None, "seeded_outlook": "contender"}
    _capture, job, _engine = H.run_capture(
        extra_patches=counted["patches"], prefs_preload=preload)
    assert job["status"] == "complete", job.get("error")

    assert counted["single"].calls == 0
    assert job["outlook_value"] == "contender"


def test_a_caller_that_supplies_nothing_still_loads_for_itself(counted):
    """session_init pre-gen and the replenishment cron pass no preload — the
    worker must keep loading the preference itself."""
    _capture, job, _engine = H.run_capture(extra_patches=counted["patches"])
    assert job["status"] == "complete", job.get("error")
    assert counted["single"].calls == 1
