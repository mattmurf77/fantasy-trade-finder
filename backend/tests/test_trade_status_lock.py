"""T4 (E1 concurrency audit F3): /api/trades/status deep-copies OUTSIDE the job lock.

docs/plans/org-bringup/e1-concurrency-audit.md row F3: the status poll used to
`copy.deepcopy(job)` while holding the process-global `_trade_jobs_lock`, so
every other request queued behind each ~3.2 MB copy. It now takes a shallow
`dict(job)` under the lock and copies outside it, as /generate already did.
Modeled on test_trade_job_admission.py::test_input_reads_capture_and_start_are_outside_job_lock.
"""
import copy

import pytest

from backend import server
from backend.tests.test_trade_job_admission import world, kickoff, PREFS, TOKEN


@pytest.mark.parametrize("query", ["", "&cursor=0", "&cursor=1"])
def test_status_deepcopy_runs_outside_the_job_lock(world, monkeypatch, query):
    job_id = kickoff(prefs_preload=PREFS)
    cards = [{"trade_id": f"t{i}", "give": [{"id": "give"}], "receive": [{"id": f"r{i}"}],
              "preserve_server_order": True} for i in range(3)]
    server._trade_jobs[job_id]["cards"] = cards
    original, held = copy.deepcopy, []

    def recording(*args, **kwargs):
        held.append(server._trade_jobs_lock.locked())
        return original(*args, **kwargs)

    monkeypatch.setattr(server.copy, "deepcopy", recording)
    response = server.app.test_client().get(f"/api/trades/status?job_id={job_id}{query}",
                                            headers={"X-Session-Token": TOKEN})
    monkeypatch.setattr(server.copy, "deepcopy", original)
    assert response.status_code == 200, response.get_json()
    assert held and not any(held)
    expected = cards[int(query.rsplit("=", 1)[1]):] if query else cards
    assert response.get_json()["cards"] == expected
