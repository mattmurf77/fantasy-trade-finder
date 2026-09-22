"""Actual quiet preparation worker: full inventory, real proofs and no exposure."""
from copy import copy, deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import time

import pytest

from backend import database as db, server, trade_service as ts
from backend.prepared_trade_payload import PreparedEvidenceCapture, restore_inventory
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, rows, ME, LEAGUE, TOKEN,
)
from backend.tests.test_owner_only_routes import exclusive, large_exclusive


def prepare(fixture, monkeypatch, *, sink_type=PreparedEvidenceCapture):
    _, _, sess, service, _ = fixture
    for name in ("_deck_exploration_enabled", "_likes_you_enabled", "_suggestion_telemetry_enabled",
                 "_deck_fatigue_enabled", "_deck_taste_enabled", "_deck_diversity_enabled", "_thompson_deck_enabled"):
        monkeypatch.setattr(server, name, lambda: False)
    # Keep first-session history enabled: preparation must not consume it.
    monkeypatch.setattr(server, "_deck_first_session_enabled", lambda: True)
    context = server._capture_trade_execution(sess, ME, LEAGUE, "1qb_ppr")
    isolated = copy(context.trade_service)
    isolated._trade_cards = {}
    isolated._significance_exemptions = {}
    isolated._past_decision_keys = set(service._past_decision_keys)
    context = replace(context, trade_service=isolated)
    job_id = "private-preparation-worker"
    job = {"job_id": job_id, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
           "started_at": time.monotonic(), "finished_at": None, "cards": [],
           "opponents_done": 0, "opponents_total": 4, "error": None,
           "fairness_threshold": .5, "outlook_value": None, "is_pinned": False,
           "owner_model": server._bakeoff.owner_arm(),
           "owner_model_version": server._bakeoff.owner_version()}
    monkeypatch.setitem(server._trade_jobs, job_id, job)
    sink = sink_type(user_id=ME, league_id=LEAGUE, job_id=job_id)
    server._run_trade_job(job_id, TOKEN, LEAGUE, .5, [], [], None,
                         prepare_sink=sink, execution_context=context)
    return job, isolated


@pytest.mark.parametrize("revision", [False, True])
def test_actual_worker_preserves_full_inventory_without_exposure(large_exclusive, monkeypatch, revision):
    client, engine, sess, service, _ = large_exclusive
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=float(revision))
    before_store = dict(service._trade_cards)
    before_last_active = sess["last_active"]
    before_history = db.load_deck_serve_history(ME, LEAGUE)
    def forbidden(*args, **kwargs):
        pytest.fail("prepared worker wrote exposure/activity")
    for name in ("record_event", "log_trade_impressions", "save_deck_impressions",
                 "save_deck_candidate_set", "save_bakeoff_run"):
        monkeypatch.setattr(server, name, forbidden)
    job, private_service = prepare(large_exclusive, monkeypatch)
    assert job["status"] == "complete", job.get("error")
    assert job["cards"] == []
    assert job["prepared_count"] >= 64
    bundle = job["prepared_bundle"]
    inventory = restore_inventory(bundle, user_id=ME, league_id=LEAGUE, now=datetime.now(timezone.utc))
    assert len(inventory.cards) == job["prepared_count"] == len(bundle["impressions"])
    assert [r["runtime"]["trade_id"] for r in bundle["cards"]] == [c.trade_id for c in inventory.cards]
    for card in inventory.cards:
        original = private_service._trade_cards[card.trade_id]
        assert card.owner_evaluation.snapshot_json == original.owner_evaluation.snapshot_json
        assert card.owner_evaluation.matches(card)
        assert not getattr(card, "owner_published", False)
    assert service._trade_cards == before_store
    assert sess["last_active"] == before_last_active
    assert db.load_deck_serve_history(ME, LEAGUE) == before_history == (False, None)
    for table in (db.deck_impressions_table, db.trade_impressions_table, db.deck_outcomes_table,
                  db.trade_decisions_table, db.deck_candidate_sets_table, db.bakeoff_runs_table,
                  db.deck_diagnostic_snapshots_table):
        assert rows(engine, table) == []
    assert service.get_pending_trades(user_id=ME, league_id=LEAGUE) == []
    # Ordinary pending projection has no back door to the private store.
    assert client.get("/api/trades", headers={"X-Session-Token": TOKEN}).json == []


def test_capture_failure_cannot_complete_or_publish_partial_inventory(large_exclusive, monkeypatch):
    _, engine, _, service, _ = large_exclusive
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.)
    class FailedCapture(PreparedEvidenceCapture):
        def impressions(self, rows):
            super().impressions(rows)
            raise RuntimeError("synthetic incomplete prepared capture")
    job, _ = prepare(large_exclusive, monkeypatch, sink_type=FailedCapture)
    assert job["status"] == "error"
    assert not job.get("prepared_bundle") and job["cards"] == []
    assert not service._trade_cards
    assert rows(engine, db.deck_impressions_table) == []
    assert rows(engine, db.trade_impressions_table) == []
