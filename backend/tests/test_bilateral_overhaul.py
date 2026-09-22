"""Model transitions invalidate overhaul inventory without rewriting history.

The existing route harness provides in-memory SQLite and synthetic generation.
The selector and output identity change together, as in the server wrapper.
"""

import json

import pytest
from sqlalchemy import select

from backend import database as db, overhaul_api, overhaul_service as service, overhaul_store as store
from backend.tests.test_overhaul_api import api, world, _h, _settings, _setup


LEGACY = {"model_arm": "owner_v1", "generator_version": "owner-v1"}
BILATERAL = {"model_arm": "owner_v2_bilateral", "generator_version": "owner-v2-bilateral"}


@pytest.fixture
def model_hooks(world, monkeypatch):
    world.identity = dict(LEGACY)
    original = overhaul_api.install

    def install(app, **kwargs):
        serializer = kwargs["card_to_dict"]
        context = kwargs["owner_generation_context"]
        def capture(**values):
            result = context(**values)
            if getattr(world, "flip_identity_on_context", None):
                world.identity = dict(world.flip_identity_on_context)
            return result
        kwargs["owner_generation_context"] = capture
        kwargs["generation_identity"] = lambda: dict(world.identity)
        kwargs["card_to_dict"] = lambda card, players: dict(
            serializer(card, players), **world.identity)
        return original(app, **kwargs)

    monkeypatch.setattr(overhaul_api, "install", install)


@pytest.fixture
def switched_api(model_hooks, api):
    return api


def raw_offers(oid):
    with db.engine.connect() as conn:
        return {r._mapping["offer_id"]: dict(r._mapping) for r in conn.execute(
            select(store.T_OFFERS).where(store.T_OFFERS.c.overhaul_id == oid))}


def generate(client, view):
    response = client.post(f"/api/overhauls/{view['overhaul_id']}/generate",
                           json={"revision": view["revision"]}, headers=_h())
    assert response.status_code == 200, response.json
    return response.json


@pytest.mark.parametrize("before_version,after_version", [("1", "2"), ("2", "1")])
def test_same_arm_revision_and_rollback_preserve_liked_history(
        switched_api, world, before_version, after_version):
    world.identity = {"model_arm": "owner_v2_bilateral",
                      "generator_version": "owner-v2-bilateral-" + before_version}
    view, old = _setup(switched_api)
    oid, liked = view["overhaul_id"], old["offers"][0]
    response = switched_api.post(f"/api/overhauls/{oid}/decisions", headers=_h(), json={
        "revision": view["revision"], "decisions": [
            {"offer_id": liked["offer_id"], "decision": "like", "client_key": "revision-like"}]})
    assert response.status_code == 200
    prior = raw_offers(oid)
    world.identity["generator_version"] = "owner-v2-bilateral-" + after_version
    pending = switched_api.get(f"/api/overhauls/{oid}/offers", headers=_h()).json
    assert pending["offers"] == []
    assert raw_offers(oid) == prior
    new = generate(switched_api, view)
    assert new["offers"]
    assert new["generation"]["generation_identity"] == world.identity
    after = raw_offers(oid)
    assert after[liked["offer_id"]] == prior[liked["offer_id"]]
    for offer_id in prior:
        assert after[offer_id]["evidence_json"] == prior[offer_id]["evidence_json"]


def test_switch_hides_only_undecided_old_inventory_without_mutating_get_history(switched_api, world):
    view, old = _setup(switched_api)
    oid = view["overhaul_id"]
    liked = old["offers"][0]
    response = switched_api.post(f"/api/overhauls/{oid}/decisions", headers=_h(), json={
        "revision": view["revision"], "decisions": [
            {"offer_id": liked["offer_id"], "decision": "like", "client_key": "prior-like"}]})
    assert response.status_code == 200
    before = raw_offers(oid)
    world.identity = dict(BILATERAL)
    fresh = switched_api.get(f"/api/overhauls/{oid}/offers", headers=_h()).json
    assert fresh["offers"] == []
    assert fresh["progress"] == {"decided": 1, "total": 1, "liked": 1}
    all_rows = switched_api.get(f"/api/overhauls/{oid}/offers?decision=all", headers=_h()).json["offers"]
    assert len(all_rows) == 5
    assert all(o["availability"] == ("fresh" if o["offer_id"] == liked["offer_id"] else "stale")
               for o in all_rows)
    current = switched_api.get(f"/api/overhauls/{oid}", headers=_h()).json
    assert current["generation"]["state"] == "idle"
    assert raw_offers(oid) == before


def test_switch_restarts_search_and_new_proof_preserves_likes_passes_and_old_rows(switched_api, world):
    view, old = _setup(switched_api)
    oid = view["overhaul_id"]
    decisions = [{"offer_id": o["offer_id"], "decision": decision, "client_key": decision}
                 for o, decision in zip(old["offers"], ("like", "pass"))]
    response = switched_api.post(f"/api/overhauls/{oid}/decisions", headers=_h(), json={
        "revision": view["revision"], "decisions": decisions})
    assert response.status_code == 200
    before = raw_offers(oid)
    called_before = len(world.generate_calls)
    world.identity = dict(BILATERAL)
    new = generate(switched_api, view)
    assert new["generation"]["new_offers"] == 3
    assert len(new["offers"]) == 3
    assert len(world.generate_calls) > called_before
    assert new["generation"]["generation_identity"] == BILATERAL
    assert not {o["offer_id"] for o in old["offers"]} & {o["offer_id"] for o in new["offers"]}
    after = raw_offers(oid)
    assert len(after) == 8
    for offer_id, prior in before.items():
        expected = dict(prior, availability="stale") if prior["decision"] == "undecided" else prior
        assert after[offer_id] == expected
    for offer in new["offers"]:
        saved = after[offer["offer_id"]]
        evidence = json.loads(saved["evidence_json"])
        canonical = service.package_hash(platform="sleeper", league_id="L1", seller_user_id="u1",
                                         counterparty_user_id=offer["counterparty_user_id"],
                                         give_ids=offer["give_ids"], receive_ids=offer["receive_ids"])
        assert evidence["canonical_package_hash"] == canonical
        assert evidence["generation_identity"] == BILATERAL
        assert saved["package_hash"] != canonical
        assert offer["card"]["model_arm"] == BILATERAL["model_arm"]
        assert "PRIVATE_BOARD" not in json.dumps(offer)
    # Exhausted subsets remain effective within this same generation epoch.
    again = generate(switched_api, view)
    assert again["generation"]["new_offers"] == 0
    assert len(raw_offers(oid)) == 8


def test_rollback_and_reactivation_create_new_occurrences_not_relabelled_old_evidence(switched_api, world):
    view, old = _setup(switched_api)
    oid = view["overhaul_id"]
    world.identity = dict(BILATERAL)
    first = generate(switched_api, view)
    frozen = raw_offers(oid)
    world.identity = dict(LEGACY)
    rollback = generate(switched_api, view)
    assert len(rollback["offers"]) == 5
    assert all(o["card"]["model_arm"] == "owner_v1" for o in rollback["offers"])
    world.identity = dict(BILATERAL)
    second = generate(switched_api, view)
    assert len(second["offers"]) == 5
    assert {o["offer_id"] for o in first["offers"]}.isdisjoint(
        {o["offer_id"] for o in second["offers"]})
    assert first["generation"]["generation_cache_epoch"] != second["generation"]["generation_cache_epoch"]
    after = raw_offers(oid)
    for offer_id, prior in frozen.items():
        assert after[offer_id]["evidence_json"] == prior["evidence_json"]
        assert after[offer_id]["card_json"] == prior["card_json"]


def test_wrong_model_results_cannot_enter_current_overhaul_inventory(switched_api, world, monkeypatch):
    # The identity can reload while a generator request is in flight. A
    # mismatched result cannot be saved or attributed as the captured model.
    view, _ = _setup(switched_api)
    world.identity = dict(BILATERAL)
    original = service.filter_cards

    def reload_during_generation(*args, **kwargs):
        world.identity = dict(LEGACY)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "filter_cards", reload_during_generation)
    response = switched_api.post(f"/api/overhauls/{view['overhaul_id']}/generate",
                                 json={"revision": view["revision"]}, headers=_h())
    assert response.status_code == 409
    assert response.json["error"] == "generation_changed"


def test_switch_during_context_capture_fails_before_any_generator_call(switched_api, world):
    view, _ = _setup(switched_api)
    world.identity = dict(BILATERAL)
    world.flip_identity_on_context = dict(LEGACY)
    calls = len(world.generate_calls)
    response = switched_api.post(f"/api/overhauls/{view['overhaul_id']}/generate",
                                 json={"revision": view["revision"]}, headers=_h())
    assert response.status_code == 409
    assert response.json["error"] == "generation_changed"
    assert len(world.generate_calls) == calls


def test_old_undecided_offer_cannot_be_newly_liked_via_its_id_after_switch(switched_api, world):
    view, old = _setup(switched_api)
    oid = view["overhaul_id"]
    world.identity = dict(BILATERAL)
    response = switched_api.post(f"/api/overhauls/{oid}/decisions", headers=_h(), json={
        "revision": view["revision"], "decisions": [
            {"offer_id": old["offers"][0]["offer_id"], "decision": "like", "client_key": "stale-like"}]})
    assert response.status_code == 409
    assert response.json["error"] == "stale_offer"
    assembled = switched_api.post(f"/api/overhauls/{oid}/assemble", headers=_h(),
                                  json={"revision": view["revision"]})
    assert assembled.status_code == 200
    assert assembled.json["roadmaps"] == []
    assert all(o["decision"] == "undecided" for o in store.list_offers(oid))


def test_changed_bilateral_settings_keep_original_proof_and_get_new_occurrences(switched_api, world):
    world.identity = dict(BILATERAL)
    view, first = _setup(switched_api)
    oid = view["overhaul_id"]
    original = raw_offers(oid)
    view = _settings(switched_api, oid, view["revision"], eligible_asset_ids=["A", "B", "C", "D"])
    second = generate(switched_api, view)
    assert len(second["offers"]) == 5
    assert {o["offer_id"] for o in first["offers"]}.isdisjoint(
        {o["offer_id"] for o in second["offers"]})
    assert first["generation"]["generation_cache_epoch"] != second["generation"]["generation_cache_epoch"]
    saved = raw_offers(oid)
    for offer_id, row in original.items():
        assert saved[offer_id]["card_json"] == row["card_json"]
        assert saved[offer_id]["evidence_json"] == row["evidence_json"]
