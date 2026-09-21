"""Offline harness checks and executable reproductions of current cache risks.

No server import, database import, provider access or application mutation.
The two cache tests document baseline behavior; they are not acceptance
criteria for the proposed replacement queue/fingerprint implementation.
"""
import ast
from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from scripts.research_trade_pipeline import (
    ObservedJob, Timeline, configure_isolation, forbid_network, instrument_worker,
)


SERVER = Path(__file__).resolve().parents[1] / "server.py"


def extracted(name, namespace):
    """Compile the real function without importing server startup side effects."""
    tree = ast.parse(SERVER.read_text())
    node = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == name)
    node.decorator_list = []
    env = dict(namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SERVER), "exec"), env)
    return env[name]


def test_all_current_worker_markers_are_unique():
    tree = ast.parse(SERVER.read_text())
    node = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "_run_trade_job")
    fn = instrument_worker(ast.unparse(node), {"_TradeExecutionContext": object}, lambda *_: None)
    assert callable(fn)


def test_instrumentation_preserves_function_result_and_rejects_drift():
    source = "def worker():\n    try:\n        value = 4\n        return value + 1\n    except Exception:\n        raise\n"
    visited = []
    worker = instrument_worker(source, {}, lambda name, _: visited.append(name),
                               stages=(("compute", "value = 4"),))
    assert worker() == 5
    assert visited == ["compute"]
    with pytest.raises(ValueError, match="matched 0"):
        instrument_worker(source, {}, lambda *_: None, stages=(("missing", "value = 3"),))


def test_timing_partition_and_durable_publication_observation():
    wall = iter([0.0, 1.0, 3.0, 4.0, 5.0])
    cpu = iter([0.0, 0.5, 1.5])
    timeline = Timeline(wall=lambda: next(wall), cpu=lambda: next(cpu))
    timeline.checkpoint("work")
    timeline.checkpoint("done")
    assert sum(row["wall_ms"] for row in timeline.stages) == 3000
    assert sum(row["cpu_ms"] for row in timeline.stages) == 1500
    job = ObservedJob(timeline, final_checks_pending=True)
    job["cards"] = [{"impression_id": "durable"}]
    assert job.first_actionable_ms is None
    job["final_checks_pending"] = False
    assert job.first_cards_ms == 4000
    assert job.first_actionable_ms == 5000


def test_isolation_refuses_preimported_database_and_existing_directory(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "backend.database", SimpleNamespace())
    with pytest.raises(RuntimeError, match="fresh Python process"):
        configure_isolation(tmp_path / "new")
    monkeypatch.delitem(sys.modules, "backend.database")
    with pytest.raises(FileExistsError):
        configure_isolation(tmp_path)
    with pytest.raises(RuntimeError, match="forbids network"):
        forbid_network("private address must never appear in the error")


def route_fixture(kickoff):
    jobs, pointers = {}, {}
    lock = threading.Lock()
    league = SimpleNamespace(league_id="test-league", members=[])
    session = {"user_id": "test-user", "league": league}
    env = {
        "time": time, "copy": copy, "request": SimpleNamespace(
            get_json=lambda **_: {}, headers={}), "jsonify": lambda result: result,
        "_require_initialized_session": lambda: session,
        "is_enabled": lambda _: False, "_deck_fatigue_enabled": lambda: False,
        "_active_format": lambda _: "test-format",
        "load_league_preference": lambda **_: {"team_outlook": "new-outlook"},
        "_capture_trade_presentation": lambda: (False, None, None),
        "_trade_job_key": lambda *args: args, "_trade_jobs_lock": lock,
        "_trade_jobs": jobs, "_trade_jobs_by_key": pointers,
        "_trade_job_is_fresh": lambda *args, **kwargs: False,
        "_trade_presentation_matches": lambda *args: True,
        "_trade_owner_model_matches": lambda *args: True,
        "_trade_significance_matches": lambda *args: True,
        "_trade_job_public_view": lambda job: job,
        "_kickoff_trade_job": lambda **kwargs: kickoff(jobs, pointers, lock, kwargs),
    }
    return extracted("generate_trades", env), jobs, pointers, lock


def test_baseline_two_simultaneous_cold_requests_both_reach_kickoff():
    """The route's lookup lock ends before registration: reproduce the race."""
    barrier = threading.Barrier(2)

    def kickoff(jobs, pointers, lock, kwargs):
        # Both callers must have left the lookup with no existing job.
        barrier.wait(timeout=3)
        with lock:
            job_id = f"job-{len(jobs)}"
            jobs[job_id] = {"job_id": job_id, "status": "running"}
            pointers[(kwargs["user_id"], kwargs["league_id"], kwargs["scoring_format"])] = job_id
        return job_id

    route, jobs, pointers, _ = route_fixture(kickoff)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: route(), range(2)))
    assert len(jobs) == 2
    assert len(pointers) == 1
    assert results[0]["job_id"] != results[1]["job_id"]


def test_baseline_invalidation_keeps_running_job_and_new_outlook_reuses_it():
    def unexpected_kickoff(*_):
        raise AssertionError("baseline unexpectedly stopped reusing the running job")

    route, jobs, pointers, lock = route_fixture(unexpected_kickoff)
    key = ("test-user", "test-league", "test-format")
    jobs["old-job"] = {"job_id": "old-job", "status": "running", "fairness_threshold": .75,
                       "outlook_value": "old-outlook", "key": key}
    pointers[key] = "old-job"
    invalidate = extracted("_invalidate_trade_jobs", {
        "_trade_jobs": jobs, "_trade_jobs_by_key": pointers, "_trade_jobs_lock": lock})
    assert invalidate(user_id="test-user", league_id="test-league") == 0
    result = route()
    assert result["job_id"] == "old-job"
    assert result["outlook_value"] == "old-outlook"


def test_baseline_rank_change_during_running_job_has_no_completed_dirty_fence():
    key = ("test-user", "test-league", "test-format")
    job = {"status": "running", "key": key, "fairness_threshold": .75,
           "outlook_value": "balanced", "safety_policy": []}
    jobs, pointers = {"old-job": job}, {key: "old-job"}
    invalidate = extracted("_invalidate_trade_jobs", {"_trade_jobs": jobs,
        "_trade_jobs_by_key": pointers, "_trade_jobs_lock": threading.Lock()})
    assert invalidate(user_id="test-user") == 0
    # The real worker finishes its captured board; no changed-board marker
    # was retained by invalidation and freshness has no board-version input.
    job.update(status="complete", finished_at=time.monotonic())
    fresh = extracted("_trade_job_is_fresh", {
        "time": time, "_PREGEN_TTL_SECONDS": 1800,
        "_trade_owner_model_matches": lambda _: True,
        "_trade_presentation_matches": lambda *_: True,
        "_capture_trade_presentation": lambda: (False, None, None),
        "_trade_safety_signature": lambda: [],
    })
    assert fresh(job, .75, "balanced")
