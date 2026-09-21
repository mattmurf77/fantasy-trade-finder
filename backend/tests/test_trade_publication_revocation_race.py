"""Copied status responses cannot outlive input/model revocation during DB I/O."""
import pytest

from backend import database as db, server, trade_service as ts
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, rows, worker, ME, LEAGUE, TOKEN,
)
from backend.tests.test_owner_only_routes import exclusive, large_exclusive


@pytest.mark.parametrize("change", ["rankings", "force", "model", "significance"])
def test_revocation_during_projection_withholds_copied_status(large_exclusive, monkeypatch, change):
    client, engine, *_ = large_exclusive
    job = worker(large_exclusive, monkeypatch)
    assert len(job["cards"]) == 64
    before = rows(engine, db.deck_impressions_table)
    job["input_epochs"] = server._capture_trade_input_epochs(ME, LEAGUE)

    def projection(cards, user_id, league_id):
        if change == "rankings":
            server._invalidate_trade_jobs(user_id=ME)
        elif change == "force":
            with server._trade_jobs_lock:
                server._revoke_trade_job_locked(job, "superseded")
        elif change == "model":
            ts._cfg["owner_bilateral_enabled"] = 1.
        else:
            ts._cfg["significance_mode"] = 2.
        return cards

    monkeypatch.setattr(server, "_project_trade_dispositions", projection)
    response = client.get("/api/trades/status?job_id=owner-route-worker",
                          headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200
    assert response.json["status"] == "error"
    assert response.json["cards"] == []
    assert rows(engine, db.deck_impressions_table) == before
