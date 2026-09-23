"""Parent wiring controls for paged empty inventory and generation cleanup.

Provider/account/receipt setup uses isolated real headless fixtures. The empty
constructor seam is deliberate: no claim about model quality follows from it.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend import database as db, server
from backend import prepared_trade_runtime as runtime, prepared_trade_store_v2 as store
from backend.tests.test_prepared_trade_runtime_review import (
    headless, large_exclusive, exclusive, owner_harness, harness, new_claim,
)
from backend.tests.test_prepared_trade_runtime import adopt
from backend.tests.test_owner_generator_routes import rows


def test_empty_paged_inventory_completes_zero_prefix_and_reuses_original_expiry(headless, monkeypatch):
    fixture, target = headless
    client, engine, _, service, _ = fixture
    calls = []

    def empty_worker(job_id, *_args, prepare_sink, **_kwargs):
        calls.append(job_id)
        server._trade_jobs[job_id].update(status="complete", prepared_count=0,
            prepared_bundle=prepare_sink.finish([], iter(())), prepared_mutations=[])

    monkeypatch.setattr(server, "_run_trade_job", empty_worker)
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    reader = store.peek_inventory(scope)
    assert reader is not None and reader.header["card_count"] == 0
    created, expiry = reader.header["created_at"], reader.header["expires_at"]
    inventory_id = reader.header["inventory_id"]
    assert not service._trade_cards
    fresh = runtime.build_session(server, deepcopy(target))
    fixture2 = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((fixture2, None, scope, None), monkeypatch, "empty-v2-adoption")
    assert handled and job["status"] == "complete" and job["cards"] == [], job
    with engine.connect() as conn:
        stored = conn.execute(select(db.prepared_trade_manifests_v2_table).where(
            db.prepared_trade_manifests_v2_table.c.inventory_id == inventory_id)).mappings().one()
    assert stored["adoption_token"] is None and stored["adoption_lease_until"] is None
    assert stored["adoption_prefix"] == stored["adoption_ghost_prefix"] == 0
    _, _, claim2 = new_claim(target)
    runtime.prepare_target(server, claim2)
    reused = store.peek_inventory(scope).header
    assert len(calls) == 1 and reused["inventory_id"] == inventory_id
    assert (reused["created_at"], reused["expires_at"]) == (created, expiry)
    for table in (db.deck_impressions_table, db.deck_candidate_sets_table,
                  db.trade_decisions_table, db.user_events_table):
        assert rows(engine, table) == []


def test_failed_generation_discards_stage_without_publishing_or_deleting_user_rows(headless, monkeypatch):
    fixture, target = headless
    _, engine, *_ = fixture
    def failed(job_id, *_args, **_kwargs):
        server._trade_jobs[job_id].update(status="error", error="synthetic_prepare_failure")
    monkeypatch.setattr(server, "_run_trade_job", failed)
    scope, _, claim = new_claim(target)
    with pytest.raises(ValueError, match="synthetic_prepare_failure"):
        runtime.prepare_target(server, claim)
    assert store.peek_inventory(scope) is None
    assert not rows(engine, db.prepared_trade_manifests_v2_table)
    assert not rows(engine, db.prepared_trade_pages_v2_table)
    assert not rows(engine, db.prepared_trade_nodes_v2_table)
    assert rows(engine, db.users_table) and rows(engine, db.leagues_table)
    assert not rows(engine, db.deck_impressions_table)
    assert not server._trade_jobs


def test_cleanup_distinguishes_persistent_preparation_from_interactive_stalls():
    assert not server._trade_job_stalled({"status": "running", "started_at": 0.,
        "source": "prepared_inventory"}, 301.)
    assert server._trade_job_stalled({"status": "running", "started_at": 0.}, 61.)
    assert not server._trade_job_stalled({"status": "complete", "started_at": 0.}, 301.)


def test_only_durable_adoption_progress_refreshes_the_existing_stall_timer():
    job = {"status": "running", "started_at": 0., "prepared_inventory_id": "synthetic"}
    assert server._trade_job_stalled(job, 61.)
    job["prepared_progress_at"] = 60.
    assert not server._trade_job_stalled(job, 119.)
    assert server._trade_job_stalled(job, 121.)


def test_dark_cache_keeps_bounded_retention_without_starting_generation(monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "_active", False)
    monkeypatch.setattr(runtime, "_last_prune", 0.)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 4000.)
    monkeypatch.setattr(runtime, "enabled", lambda _: False)
    monkeypatch.setattr(runtime.store, "prune", lambda **_: calls.append("prune"))
    monkeypatch.setattr(runtime, "start", lambda *_, **__: pytest.fail("dark cache started work"))
    monkeypatch.setattr(runtime.store, "resumable_sweeps", lambda **_: pytest.fail("dark resume scan"))
    runtime.tick(server)
    runtime.tick(server)
    assert calls == ["prune"]


def test_active_sweep_does_not_starve_privacy_retention(monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "_active", True)
    monkeypatch.setattr(runtime, "_last_prune", 0.)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 4000.)
    monkeypatch.setattr(runtime.store, "prune", lambda **_: calls.append("prune"))
    monkeypatch.setattr(runtime, "enabled", lambda _: pytest.fail("active sweep rediscovery"))
    monkeypatch.setattr(runtime, "start", lambda *_, **__: pytest.fail("duplicate sweep"))
    runtime.tick(server)
    runtime.tick(server)
    assert calls == ["prune"]


@pytest.mark.parametrize("kind", ["awaiting", "matched"])
def test_prepared_projection_removes_current_awaiting_or_matched_package_only(monkeypatch, kind):
    cards = [{"trade_id": "affected", "give": [{"id": "a"}], "receive": [{"id": "b"}]},
             {"trade_id": "unrelated", "give": [{"id": "a"}], "receive": [{"id": "c"}]}]
    history = SimpleNamespace(discovery_keys=lambda *a, **k: (set(), set()),
                              likes=lambda **k: [])
    monkeypatch.setattr(server, "load_trade_interest_history", lambda *a, **k: history)
    monkeypatch.setattr(server, "load_trade_card_source_likes", lambda *a, **k: {})
    row = {"league_id": "league", "my_give": ["a"], "my_receive": ["b"]}
    monkeypatch.setattr(server, "load_awaiting_trades",
                        lambda *a: [row] if kind == "awaiting" else [])
    monkeypatch.setattr(server, "load_matches_for_exclusion",
                        lambda *a: [row] if kind == "matched" else [])
    original = deepcopy(cards)
    assert server._project_trade_dispositions(cards, "owner", "league") == cards
    assert server._project_trade_dispositions(cards, "owner", "league", prepared=True) == [cards[1]]
    assert cards == original


@pytest.mark.parametrize("reader", ["load_awaiting_trades", "load_matches_for_exclusion"])
def test_prepared_projection_history_failure_does_not_replay_affected_packages(monkeypatch, reader):
    cards = [{"trade_id": "affected", "give": [{"id": "a"}], "receive": [{"id": "b"}]}]
    monkeypatch.setattr(server, "load_awaiting_trades", lambda *a: [])
    monkeypatch.setattr(server, "load_matches_for_exclusion", lambda *a: [])
    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic history unavailable")
    monkeypatch.setattr(server, reader, unavailable)
    assert server._project_trade_dispositions(cards, "owner", "league", prepared=True) == []
