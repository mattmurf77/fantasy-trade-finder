"""Version selection, immutable offer proof and private provenance on real routes."""
import copy
import json
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import insert

from backend import bakeoff_runner as bo, database as db, feature_flags as ff, server, trade_service as ts
from backend import trade_gen_bilateral as bilateral, trade_gen_owner as owner
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, post, rows, worker, context_for, ME, OPP, LEAGUE, TOKEN)


@pytest.fixture
def enabled(owner_harness):
    ts._cfg.update(owner_bilateral_enabled=1., bakeoff_owner_only=1.)
    return owner_harness


def forbidden(**kwargs):
    pytest.fail("another generator ran during bilateral exclusive serving")


def test_selector_is_registered_dark_and_does_not_rewrite_existing_knobs():
    assert ts._DEFAULT_CFG["owner_bilateral_enabled"] == 0
    assert next(v for k, v, _ in db._MODEL_CONFIG_DEFAULTS if k == "owner_bilateral_enabled") == 0
    assert bo.owner_arm({}) == bo.ARM_OWNER
    assert bo.owner_generator({}) is owner.generate_owner_trades
    assert bo.owner_evaluator({}) is owner.evaluate_owner_trades
    assert bo.owner_arm({"owner_bilateral_enabled": 1.}) == bo.ARM_OWNER_BILATERAL


def test_dark_selector_preserves_v1_generation_and_request_assignment(owner_harness, monkeypatch):
    client, _, *_ = owner_harness
    ts._cfg["bakeoff_owner_only"] = 1.
    monkeypatch.setattr(bilateral, "generate_bilateral_trades", forbidden)
    assert {i["model_arm"] for i in post(client).json["ideas"]} == {bo.ARM_OWNER}
    context = context_for(owner_harness)
    before = server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"]
    context["config"].pop("owner_bilateral_enabled", None)
    assert before == server._owner_selected_assignment(context, "fair_packages", serve=True)["request_hash"]


def test_selector_uses_existing_logged_hot_reload_funnel(owner_harness):
    _, engine, *_ = owner_harness
    with engine.begin() as conn:
        conn.execute(insert(db.model_config_table).values(
            key="owner_bilateral_enabled", value=0., description="test selector"))
    db.set_config("owner_bilateral_enabled", 1., source="bilateral-route-test")
    ts.reload_config()
    assert bo.owner_arm() == bo.ARM_OWNER_BILATERAL
    change = rows(engine, db.model_config_changes_table)[0]
    assert (change["key"], change["old_value"], change["new_value"], change["source"]) == (
        "owner_bilateral_enabled", 0., 1., "bilateral-route-test")


@pytest.mark.parametrize("route,extra", [
    ("fair-packages", {}),
    ("asset-ideas", {"asset_id": "a1", "direction": "give"}),
    ("asset-ideas", {"asset_id": "b1", "direction": "receive"}),
])
def test_exclusive_selected_routes_have_actual_bilateral_provenance(enabled, monkeypatch, route, extra):
    client, engine, _, svc, _ = enabled
    monkeypatch.setattr(owner, "generate_owner_trades", forbidden)
    monkeypatch.setattr(svc, "generate_fair_packages", forbidden)
    response = post(client, route, **extra)
    assert response.status_code == 200, response.json
    ideas = (response.json["ideas"] if route == "fair-packages" else
             [i for group in response.json["groups"].values() for i in group])
    assert ideas, response.json
    assert {i["model_arm"] for i in ideas} == {bo.ARM_OWNER_BILATERAL}
    assert {i["generator_version"] for i in ideas} == {bilateral.BILATERAL_GENERATOR_VERSION}
    assert all(i["impression_id"] for i in ideas)
    impressions = rows(engine, db.deck_impressions_table)
    assert {i["model_arm"] for i in impressions} == {bo.ARM_OWNER_BILATERAL}
    assert {i["policy_variant"] for i in impressions} == {bo.ARM_OWNER_BILATERAL}
    snapshots = [json.loads(i["valuation_json"]) for i in impressions]
    assert all(s["generator_version"] == bilateral.BILATERAL_GENERATOR_VERSION for s in snapshots)
    assert all("viewer" in s and "counterparty" in s for s in snapshots)
    run = rows(engine, db.bakeoff_runs_table)[0]
    assert set(json.loads(run["arms_json"])) == {bo.ARM_OWNER_BILATERAL}
    for private in ("owner_evaluation", "valuation_json", "manager_preferences", "opponent_sources",
                    "counterparty_benefits", "counterparty_preference_evidence", "weaker_support"):
        assert private not in json.dumps(response.json)


@pytest.mark.parametrize("give,receive", [((), ()), (("a1",), ("b1",))])
def test_organic_and_targeted_exclusive_replace_v1(enabled, monkeypatch, give, receive):
    _, engine, _, svc, _ = enabled
    monkeypatch.setattr(owner, "generate_owner_trades", forbidden)
    monkeypatch.setattr(svc, "generate_trades", forbidden)
    job = worker(enabled, monkeypatch, give=give, receive=receive, opponent=OPP if give else None)
    assert job["cards"], job
    assert {c["model_arm"] for c in job["cards"]} == {bo.ARM_OWNER_BILATERAL}
    assert "counterparty_benefits" not in json.dumps(job["cards"])
    assert "counterparty_preference_evidence" not in json.dumps(job["cards"])
    assert "weaker_support" not in json.dumps(job["cards"])
    assert {r["model_arm"] for r in rows(engine, db.deck_impressions_table)} == {bo.ARM_OWNER_BILATERAL}
    assert all(set(json.loads(r["arms_json"])) == {bo.ARM_OWNER_BILATERAL}
               for r in rows(engine, db.bakeoff_runs_table))


def test_failure_returns_no_legacy_fallback(enabled, monkeypatch):
    client, engine, _, svc, _ = enabled
    monkeypatch.setattr(owner, "generate_owner_trades", forbidden)
    monkeypatch.setattr(svc, "generate_fair_packages", forbidden)
    def failure(**kwargs):
        raise RuntimeError("synthetic unavailable")
    monkeypatch.setattr(bilateral, "generate_bilateral_trades", failure)
    response = post(client)
    assert response.status_code == 200
    assert response.json["ideas"] == []
    assert response.json["reason"] == "generation_unavailable"
    assert not rows(engine, db.deck_impressions_table)


def test_selector_change_during_selected_generation_withholds_stale_response(enabled, monkeypatch):
    client, engine, *_ = enabled
    original = bilateral.generate_bilateral_trades
    def flip(**context):
        result = original(**context)
        ts._cfg["owner_bilateral_enabled"] = 0.
        return result
    monkeypatch.setattr(bilateral, "generate_bilateral_trades", flip)
    response = post(client)
    assert response.status_code == 503
    assert not rows(engine, db.deck_impressions_table)


def test_queued_generation_switch_supersedes_old_job_and_starts_new_model(owner_harness, monkeypatch):
    client, *_ = owner_harness
    monkeypatch.setattr(server.threading, "Thread", lambda *a, **k: SimpleNamespace(start=lambda: None))
    key = server._trade_job_key(ME, LEAGUE, "1qb_ppr")
    monkeypatch.delitem(server._trade_jobs_by_key, key, raising=False)
    ids = []
    try:
        first = client.post("/api/trades/generate", json={"league_id": LEAGUE},
                            headers={"X-Session-Token": TOKEN}).json
        ids.append(first["job_id"])
        assert first["status"] == "running" and first["error"] is None
        ts._cfg["owner_bilateral_enabled"] = 1.
        second = client.post("/api/trades/generate", json={"league_id": LEAGUE},
                             headers={"X-Session-Token": TOKEN}).json
        ids.append(second["job_id"])
        assert ids[0] != ids[1]
        assert server._trade_jobs[ids[0]]["superseded"]
        assert second["status"] == "running" and second["error"] is None
        assert server._trade_jobs[ids[1]]["owner_model"] == bo.ARM_OWNER_BILATERAL
    finally:
        for job_id in ids:
            server._trade_jobs.pop(job_id, None)
        server._trade_jobs_by_key.pop(key, None)


def test_replenishment_regenerates_old_model_instead_of_announcing_cached_cards(enabled, monkeypatch):
    _, _, session, _, league = enabled
    prefs = server._trade_job_preferences(ME, LEAGUE, session, league)
    outlook = (prefs["prefs"] or {}).get("team_outlook") or prefs["seeded_outlook"]
    key = server._trade_job_key(ME, LEAGUE, "1qb_ppr")
    old = {"job_id": "old", "key": key, "status": "complete", "is_pinned": False,
           "owner_model": bo.ARM_OWNER, "finished_at": time.monotonic(),
           "cards": [{"trade_id": "old-owner"}],
           "presentation_capture": server._capture_trade_presentation()}
    monkeypatch.setattr(server, "_trade_jobs", {"old": old})
    monkeypatch.setattr(server, "_trade_jobs_by_key", {key: "old"})
    monkeypatch.setattr(server, "get_league_scoring", lambda _: "1qb_ppr")
    monkeypatch.setattr(server, "load_latest_trade_impression_batch", lambda *a: [])
    monkeypatch.setattr(server, "_find_live_session_token", lambda *a: TOKEN)
    seen = []
    def kickoff(**kwargs):
        seen.append(kwargs)
        server._trade_jobs["new"] = {**old, "job_id": "new", "owner_model": bo.ARM_OWNER_BILATERAL,
            "fairness_threshold": kwargs["fairness_threshold"], "outlook_value": outlook,
            "safety_policy": server._trade_safety_signature(), "cards": []}
        return "new"
    monkeypatch.setattr(server, "_kickoff_trade_job", kickoff)
    assert server._replenish_deck_for(ME, LEAGUE) == (0, 0)
    assert len(seen) == 1 and seen[0]["source"] == "replenish"


def test_switch_rejects_old_proof_job_and_pending_inventory(owner_harness, monkeypatch):
    client, engine, _, svc, _ = owner_harness
    ts._cfg["bakeoff_owner_only"] = 1.
    context = context_for(owner_harness)
    old = post(client).json["ideas"][0]
    card = copy.deepcopy(svc._trade_cards[old["trade_id"]])
    job = worker(owner_harness, monkeypatch)
    before = server._trade_safety_signature()
    old_hash = server._owner_selected_assignment(context, "fair_packages", serve=True, exclusive=True)["request_hash"]
    ts._cfg["owner_bilateral_enabled"] = 1.
    assert before != server._trade_safety_signature()
    context["config"]["owner_bilateral_enabled"] = 1.
    assert old_hash != server._owner_selected_assignment(context, "fair_packages", serve=True, exclusive=True)["request_hash"]
    assert server._owner_cards_valid([card], context) == []
    public = server._trade_job_public_view(job)
    assert public["cards"] == [] and public["error"] == "owner_model_changed"
    response = client.get("/api/trades", headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200 and response.json == []
    assert any(json.loads(row["valuation_json"])["generator"] == bo.ARM_OWNER
               for row in rows(engine, db.deck_impressions_table) if row["valuation_json"])


def test_final_bilateral_proof_is_rechecked_with_captured_model(enabled, monkeypatch):
    context = context_for(enabled)
    cards, _ = bilateral.generate_bilateral_trades(**context)
    assert cards
    ts._cfg["owner_bilateral_enabled"] = 0.
    monkeypatch.setattr(owner, "evaluate_owner_trades", forbidden)
    kept = server._owner_cards_valid(cards, context)
    assert kept
    mutated = copy.deepcopy(kept[0])
    mutated.receive_player_ids = ["b2"]
    assert server._owner_cards_valid([mutated], context) == []


def test_pending_does_not_publish_unserved_or_mutated_bilateral_proofs(enabled):
    client, _, _, svc, _ = enabled
    context = context_for(enabled)
    cards, _ = bilateral.generate_bilateral_trades(**context)
    assert cards
    svc._trade_cards.update({card.trade_id: card for card in cards})
    get = lambda: client.get("/api/trades", headers={"X-Session-Token": TOKEN})
    assert get().json == []
    idea = post(client).json["ideas"][0]
    assert any(card["trade_id"] == idea["trade_id"] for card in get().json)
    svc._trade_cards[idea["trade_id"]].receive_player_ids = ["b2"]
    assert get().json == []


def test_shadow_uses_bilateral_only_for_unserved_generation(enabled, monkeypatch):
    client, engine, *_ = enabled
    ts._cfg["bakeoff_serve_owner"] = 0.
    monkeypatch.setattr(owner, "generate_owner_trades", forbidden)
    response = post(client)
    assert response.json["ideas"]
    assert {i["model_arm"] for i in response.json["ideas"]} == {"legacy_fair"}
    run = rows(engine, db.bakeoff_runs_table)[0]
    assert json.loads(run["arms_json"])[bo.ARM_OWNER_BILATERAL]["cards"] > 0
    assert run["served_arm"] == "legacy_fair"


def test_verified_original_pick_context_not_current_holder(enabled, monkeypatch):
    monkeypatch.setattr(server, "get_league_draft_context", lambda _: {
        "season": 2026, "status": "drafted", "confidence": "high"})
    monkeypatch.setattr(server, "load_draft_picks", lambda **_: [
        {"pick_id": "own", "season": 2027, "original_user_id": ME, "owner_user_id": OPP},
        {"pick_id": "acquired", "season": 2027, "original_user_id": OPP, "owner_user_id": ME},
        {"pick_id": "expired", "season": 2026, "original_user_id": ME, "owner_user_id": ME},
    ])
    context = context_for(enabled)
    prefs = context["manager_preferences"]
    assert prefs[ME]["own_next_draft_pick_ids"] == ["own"]
    assert prefs[OPP]["own_next_draft_pick_ids"] == ["acquired"]
    assert prefs[ME]["expired_pick_ids"] == ["expired"]


@pytest.mark.parametrize("tradeable", [False, True])
def test_pick_context_obeys_shared_source_switch_and_filtered_rows(enabled, monkeypatch, tradeable):
    _, engine, *_ = enabled
    monkeypatch.setitem(ff._flags_cache, "picks.assign_tradeable", tradeable)
    monkeypatch.setattr(server, "get_league_draft_context", lambda _: {
        "season": 2026, "status": "drafted", "confidence": "high"})
    with engine.begin() as conn:
        conn.execute(insert(db.draft_picks_table), [
            {"pick_id": pid, "league_id": LEAGUE, "season": 2027, "round": 1,
             "original_user_id": ME, "owner_user_id": ME, "source": source}
            for pid, source in (("platform", None), ("asserted", "user"),
                                ("contested", "user"), ("orphaned", "user"))])
    monkeypatch.setattr(db, "_excluded_pick_ids", lambda _: ({"contested"}, {"orphaned"}))
    calls = []
    def load(**kwargs):
        calls.append(kwargs)
        return db.load_draft_picks(**kwargs)
    monkeypatch.setattr(server, "load_draft_picks", load)
    context = context_for(enabled)
    assert calls == [{"league_id": LEAGUE, "source": "any" if tradeable else "platform"}]
    assert set(context["manager_preferences"][ME]["own_next_draft_pick_ids"]) == (
        {"platform", "asserted"} if tradeable else {"platform"})


def test_outcome_joins_original_bilateral_impression_after_switch(enabled):
    client, engine, *_ = enabled
    idea = post(client).json["ideas"][0]
    ts._cfg["owner_bilateral_enabled"] = 0.
    response = post(client, "queue", impression_id=idea["impression_id"], dwell_ms=750)
    assert response.status_code == 200 and response.json["queued"]
    assert rows(engine, db.trade_decisions_table)[0]["impression_id"] == idea["impression_id"]
    assert rows(engine, db.deck_outcomes_table)[0]["impression_id"] == idea["impression_id"]
    assert rows(engine, db.deck_impressions_table)[0]["model_arm"] == bo.ARM_OWNER_BILATERAL
