"""Version-two admission, publication and rollback on actual isolated routes."""
import copy
import json
from types import SimpleNamespace

import pytest

from backend import bakeoff_runner as bo, database as db, server, trade_service as ts
from backend import trade_gen_bilateral as incumbent, trade_gen_bilateral_candidate as candidate
from backend import trade_bilateral_presentment as presentment
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, context_for, post, rows, worker, ME, LEAGUE, TOKEN)
from backend.tests.test_owner_only_routes import exclusive, large_exclusive
from backend.tests.test_owner_batch_publication import observe_batches


@pytest.fixture
def revised(owner_harness):
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.,
                   bakeoff_owner_only=1.)
    return owner_harness


def test_selector_is_dark_and_requires_bilateral_without_enabling_it():
    assert ts._DEFAULT_CFG["owner_bilateral_revision_enabled"] == 0
    assert next(v for k, v, _ in db._MODEL_CONFIG_DEFAULTS
                if k == "owner_bilateral_revision_enabled") == 0
    assert not bo.owner_revision_enabled({"owner_bilateral_revision_enabled": 1.})
    for value in (0., .5, 2., -1., None, "1"):
        cfg = {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": value}
        assert bo.owner_generator(cfg) is incumbent.generate_bilateral_trades
        assert bo.owner_evaluator(cfg) is incumbent.evaluate_bilateral_trades
        assert bo.owner_version(cfg) == incumbent.VERSION
    cfg = {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.}
    assert bo.owner_arm(cfg) == bo.ARM_OWNER_BILATERAL
    assert bo.owner_generator(cfg) is candidate.generate_bilateral_trades
    assert bo.owner_evaluator(cfg) is candidate.evaluate_bilateral_trades
    assert bo.owner_version(cfg) == candidate.VERSION


def test_dark_revision_preserves_request_hash_and_old_safety_signature(owner_harness):
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=0.)
    context = context_for(owner_harness)
    before = server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"]
    signature = server._trade_safety_signature()
    context["config"].pop("owner_bilateral_revision_enabled")
    assert before == server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"]
    assert not any(s.startswith("owner_model_version:") for s in signature)
    ts._cfg["owner_bilateral_revision_enabled"] = 1.
    assert signature != server._trade_safety_signature()


def test_same_arm_old_proof_is_not_relabelled_as_revision(revised):
    context = context_for(revised)
    cards, _ = incumbent.generate_bilateral_trades(**context)
    assert cards
    assert server._owner_cards_valid(cards, context) == []
    cards, _ = candidate.generate_bilateral_trades(**context)
    assert cards and server._owner_cards_valid(cards, context)
    context["config"]["owner_bilateral_revision_enabled"] = 0.
    assert server._owner_cards_valid(cards, context) == []


def test_selected_route_freezes_actual_revision_without_private_public_fields(revised):
    client, engine, *_ = revised
    response = post(client)
    assert response.status_code == 200 and response.json["ideas"]
    assert {i["generator_version"] for i in response.json["ideas"]} == {candidate.VERSION}
    records = rows(engine, db.deck_impressions_table)
    assert {json.loads(r["valuation_json"])["generator_version"] for r in records} == {candidate.VERSION}
    for private in ("owner_presentment", "term_efficiency", "plan_composition", "counterparty_preference"):
        assert private not in json.dumps(response.json)


def test_revision_flip_during_selected_generation_withholds_response(revised, monkeypatch):
    client, engine, *_ = revised
    generate = candidate.generate_bilateral_trades
    def flip(**kwargs):
        result = generate(**kwargs)
        ts._cfg["owner_bilateral_revision_enabled"] = 0.
        return result
    monkeypatch.setattr(candidate, "generate_bilateral_trades", flip)
    assert post(client).status_code == 503
    assert not rows(engine, db.deck_impressions_table)


@pytest.mark.parametrize("save_name", ["save_deck_impressions", "save_bakeoff_run"])
def test_commit_time_rollback_withholds_selected_output_but_preserves_evidence(revised, monkeypatch, save_name):
    client, engine, *_ = revised
    save = getattr(server, save_name)
    def flip(*args, **kwargs):
        result = save(*args, **kwargs)
        ts._cfg["owner_bilateral_revision_enabled"] = 0.
        return result
    monkeypatch.setattr(server, save_name, flip)
    response = post(client)
    assert response.status_code == 503
    records = rows(engine, db.deck_impressions_table)
    assert records  # Already committed original terms/evidence are never erased.
    assert {json.loads(r["valuation_json"])["generator_version"] for r in records} == {candidate.VERSION}
    assert client.get("/api/trades", headers={"X-Session-Token": TOKEN}).json == []


def test_rollback_withholds_old_undecided_inventory_without_erasing_evidence(revised):
    client, engine, *_ = revised
    ideas = post(client).json["ideas"]
    assert ideas
    before = rows(engine, db.deck_impressions_table)
    ts._cfg["owner_bilateral_revision_enabled"] = 0.
    response = client.get("/api/trades", headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200 and response.json == []
    assert rows(engine, db.deck_impressions_table) == before


@pytest.mark.parametrize("boundary", ["disposition", "serialization"])
def test_pending_read_rollback_withholds_revoked_cards_and_keeps_inbound(revised, monkeypatch, boundary):
    client, engine, _, service, _ = revised
    ideas = post(client).json["ideas"]
    assert len(ideas) >= 2
    inbound = service._trade_cards[ideas[0]["trade_id"]]
    service._significance_exemptions[server._significance_card_key(inbound)] = ("inbound", (), ())
    before = rows(engine, db.deck_impressions_table)
    name = "_project_trade_dispositions" if boundary == "disposition" else "trade_card_to_dict"
    original = getattr(server, name)
    def flip(*args, **kwargs):
        result = original(*args, **kwargs)
        ts._cfg["owner_bilateral_revision_enabled"] = 0.
        return result
    monkeypatch.setattr(server, name, flip)
    response = client.get("/api/trades", headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200
    assert [card["trade_id"] for card in response.json] == [inbound.trade_id]
    assert rows(engine, db.deck_impressions_table) == before


def test_same_arm_queued_job_is_superseded_by_revision_change(revised, monkeypatch):
    client, *_ = revised
    monkeypatch.setattr(server.threading, "Thread", lambda *a, **k: SimpleNamespace(start=lambda: None))
    key = server._trade_job_key(ME, LEAGUE, "1qb_ppr")
    monkeypatch.delitem(server._trade_jobs_by_key, key, raising=False)
    ids = []
    try:
        for enabled in (0., 1., 0.):
            ts._cfg["owner_bilateral_revision_enabled"] = enabled
            response = client.post("/api/trades/generate", json={"league_id": LEAGUE},
                                   headers={"X-Session-Token": TOKEN})
            assert response.status_code == 200, response.json
            ids.append(response.json["job_id"])
            assert server._trade_owner_model_matches(server._trade_jobs[ids[-1]])
        assert len(set(ids)) == 3
        assert all(server._trade_jobs[i]["superseded"] for i in ids[:-1])
        old_revision = server._trade_job_public_view(copy.deepcopy(server._trade_jobs[ids[1]]))
        assert old_revision["cards"] == []
    finally:
        for job_id in ids:
            server._trade_jobs.pop(job_id, None)
        server._trade_jobs_by_key.pop(key, None)


def test_survivor_order_runs_once_before_durable_publication_and_is_private(revised, monkeypatch):
    client, engine, *_ = revised
    calls = []
    original = presentment.present
    def present(cards, **kwargs):
        result, diag = original(cards, **kwargs)
        calls.append((tuple(id(c) for c in cards), tuple(id(c) for c in result)))
        return result, diag
    monkeypatch.setattr(presentment, "present", present)
    job = worker(revised, monkeypatch)
    assert job["cards"] and len(calls) == 1
    assert sorted(calls[0][0]) == sorted(calls[0][1])
    records = sorted(rows(engine, db.deck_impressions_table), key=lambda r: r["card_index"])
    assert [r["impression_id"] for r in records] == [c["impression_id"] for c in job["cards"]]
    provenance = [json.loads(r["features_json"])["owner_presentment"] for r in records]
    assert [p["final_index"] for p in provenance] == list(range(len(records)))
    assert [p["original_index"] for p in provenance] == job["owner_presentment"]["occurrence_original_indices"]
    for _ in range(2):
        public = client.get("/api/trades/status?job_id=owner-route-worker",
                            headers={"X-Session-Token": TOKEN}).json
        assert public["cards"] == job["cards"]
        assert "owner_presentment" not in json.dumps(public)
    assert len(calls) == 1


def test_revision_flip_after_first_batch_never_publishes_tail(large_exclusive, monkeypatch):
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.)
    _, engine, *_ = large_exclusive
    def flip(job, batch):
        ts._cfg["owner_bilateral_revision_enabled"] = 0.
    observed = observe_batches(monkeypatch, engine, flip)
    job = worker(large_exclusive, monkeypatch, expected_error="owner_model_changed")
    assert observed["batches"] == [30]
    assert len(rows(engine, db.deck_impressions_table)) == 30
    assert job["cards"] == []
