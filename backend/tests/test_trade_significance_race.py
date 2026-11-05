"""E1 F9: job["significance"] is copy-on-write once the worker attaches it.

Job snapshots deep-copy the job: /api/trades/status under _trade_jobs_lock, and
the /api/trades/generate reuse path (and the kickoff response) from a shallow
copy taken under the lock, OUTSIDE it. The worker used to keep mutating the
attached dict in place (quality filters, final_served, the withheld block), so
a reader deep-copying it could raise "dictionary changed size during
iteration" or copy a half-built state. Under gthread that is a request crash.

The test thread (A) runs the real worker (_run_trade_job, the withheld-impression arm, so
every significance update site runs). A reader thread (B) deep-copies the job repeatedly,
the way the reuse path does. A probe value parks B in the middle of copying the
attached dict while A runs its updates (two Barriers), so the race is
deterministic, not timing-dependent.

Sabotage: restore the in-place mutations in _run_trade_job and this fails with
RuntimeError in thread B. Clear __pycache__ after restoring (G-060).
"""
import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from backend import server
from backend.tests.test_owner_generator_routes import harness, owner_harness, worker, OPP  # noqa: F401
from backend.tests.test_trade_significance_integration import low_owner  # noqa: F401

JOB_ID = "owner-route-worker"   # worker()'s fixed job id
WAIT = 20                       # seconds; a broken barrier fails the test, never hangs it


class _Probe(dict):
    """A significance value whose deep copy calls back into the test."""

    def __init__(self, on_copy):
        super().__init__()
        self.on_copy = on_copy

    def __deepcopy__(self, memo):
        self.on_copy()
        return {}


def test_significance_snapshots_never_race_the_worker(low_owner, monkeypatch):
    attached, updated = Barrier(2), Barrier(2)
    reader = {"thread": None, "parked": False}
    worker_done = threading.Event()

    def park_reader():
        # B, mid-iteration over the attached dict: let A run its updates, then resume.
        if threading.current_thread() is reader["thread"] and not reader["parked"]:
            reader["parked"] = True
            attached.wait(WAIT)
            updated.wait(WAIT)

    original_evaluate = server._evaluate_trade_significance

    def evaluate(*args, **kwargs):
        kept, results, diag = original_evaluate(*args, **kwargs)
        if diag:
            diag["probe"] = _Probe(park_reader)
        return kept, results, diag

    original_project = server._project_trade_dispositions
    hooks = {"attached": False, "updated": False}

    def project(*args, **kwargs):
        # A's first disposition read after the attach: wait until B is parked.
        with server._trade_jobs_lock:
            attached_now = "significance" in (server._trade_jobs.get(JOB_ID) or {})
        if attached_now and not hooks["attached"]:
            hooks["attached"] = True
            attached.wait(WAIT)
        return original_project(*args, **kwargs)

    def unavailable(*args, **kwargs):
        # After the quality-filter and final_served updates, before the withheld one.
        if not hooks["updated"]:
            hooks["updated"] = True
            updated.wait(WAIT)
        raise RuntimeError("synthetic impression store unavailable")

    monkeypatch.setattr(server, "_evaluate_trade_significance", evaluate)
    monkeypatch.setattr(server, "_project_trade_dispositions", project)
    monkeypatch.setattr(server, "_log_deck_signal_impressions", unavailable)
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: True)

    errors, snapshots = [], []

    def read_repeatedly():
        reader["thread"] = threading.current_thread()
        under_lock = False
        while not worker_done.is_set():
            try:
                with server._trade_jobs_lock:
                    job = server._trade_jobs.get(JOB_ID)
                    if job is None:
                        continue
                    if under_lock:   # /api/trades/status
                        snap = copy.deepcopy(job)
                    else:            # /api/trades/generate reuse: shallow under the lock
                        snap = dict(job)
                if not under_lock:
                    snap = copy.deepcopy(snap)
            except Exception as exc:   # RuntimeError: dictionary changed size during iteration
                errors.append(exc)
                continue
            if "significance" in snap:
                snapshots.append(snap["significance"])
            under_lock = reader["parked"] and not under_lock

    # The worker stays on this thread: the harness's in-memory SQLite is per-thread.
    with ThreadPoolExecutor(max_workers=1) as pool:
        reading = pool.submit(read_repeatedly)
        try:
            job = worker(low_owner, monkeypatch, give=["a1"], receive=["b1"], opponent=OPP,
                         expected_error="owner_impression_unavailable")
        finally:
            worker_done.set()
        reading.result()

    assert not errors, errors
    # Non-vacuous: B was parked inside the attached dict while A ran every update site.
    assert reader["parked"] and hooks["attached"] and hooks["updated"]
    assert not attached.broken and not updated.broken
    final = {k: v for k, v in job["significance"].items() if k != "probe"}
    assert {"quality_filters", "final_served", "final_served_per_arm", "withheld"} <= set(final)
    assert final["withheld"] == "impression_unavailable"

    # The states the worker publishes, in order. Per-arm counts exist at the
    # final_served update only on a bake-off run; the withheld update always sets them.
    bakeoff = "per_arm_final_candidates" in final
    base = set(final) - {"quality_filters", "final_served", "final_served_per_arm", "withheld"}
    served = {"final_served", "final_served_per_arm"} if bakeoff else {"final_served"}
    stages = [base, base | {"quality_filters"}, base | {"quality_filters"} | served,
              base | {"quality_filters", "final_served", "final_served_per_arm", "withheld"}]
    assert snapshots
    for snap in snapshots:
        snap = {k: v for k, v in snap.items() if k != "probe"}
        assert set(snap) in stages, sorted(snap)                    # a whole state, never a partial one
        assert {k: snap[k] for k in base} == {k: final[k] for k in base}
        if bakeoff and "final_served_per_arm" in snap:
            assert sum(snap["final_served_per_arm"].values()) == snap["final_served"]
        if "withheld" in snap:
            assert snap == final
    # The parked copy is the attach-time state, untouched by the updates that ran meanwhile.
    assert set(snapshots[0]) - {"probe"} == base
