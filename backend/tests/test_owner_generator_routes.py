"""Owner route integration: real Flask routes, generator and isolated SQLite.

Legacy route goldens live in their original files. This fixture reuses only
their synthetic league/session setup, not a mocked generation result.
"""
import copy
import json
import time

import pytest
from sqlalchemy import select

from backend import database as db, feature_flags as ff, server, trade_service as ts
from backend.tests.test_fair_packages import harness, ME, OPP, LEAGUE, TOKEN, SEED


@pytest.fixture
def owner_harness(harness, monkeypatch):
    client, engine, sess, service, league = harness
    monkeypatch.setattr(db, "ingest_engine", engine)
    ff._flags_cache.update({"trade.bakeoff": True, "trade.asset_ideas": True,
                           "deck.signal_v2": True, "analytics.ingest": True})
    ts._cfg.update(bakeoff_include_owner=1., bakeoff_serve_owner=1.)
    ranking = sess["service"]
    ranking._elo_overrides.update({**SEED, "a1": 1500., "b1": 1700.})
    monkeypatch.setattr(ranking, "placement_bands", lambda: {p: (1200, 1900) for p in SEED})
    monkeypatch.setattr(server, "load_member_rankings", lambda *a, **k: {
        OPP: {"elo_ratings": {**SEED, "a1": 1700., "b1": 1500.},
              "confidence_sources": {p: "explicit" for p in SEED},
              "username": "opp",
              "board_updated_at": "2026-09-01T00:00:00+00:00"}})
    yield harness


def post(client, route="fair-packages", **kwargs):
    body = {"league_id": LEAGUE, "give_player_ids": ["a1"],
            "receive_player_ids": ["b1"], "opponent_user_id": OPP, **kwargs}
    return client.post("/api/trades/" + route, json=body,
                       headers={"X-Session-Token": TOKEN})


def assign(monkeypatch, arm):
    original = server._owner_selected_assignment
    def assignment(*args, **kwargs):
        result = original(*args, **kwargs)
        result["model_arm"] = arm
        return result
    monkeypatch.setattr(server, "_owner_selected_assignment", assignment)


def rows(engine, table):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(table))]


def test_fair_owner_uses_actual_generator_and_frozen_private_impression(owner_harness, monkeypatch):
    client, engine, sess, service, league = owner_harness
    assign(monkeypatch, "owner_v1")
    response = post(client)
    assert response.status_code == 200
    ideas = response.json["ideas"]
    assert ideas, response.json
    idea = ideas[0]
    assert idea["give_player_ids"] == ["a1"]
    assert idea["receive_player_ids"] == ["b1"]
    assert idea["model_arm"] == "owner_v1"
    assert idea["trade_id"] in service._trade_cards
    assert idea["generator_version"] == "owner-v1"
    impression = rows(engine, db.deck_impressions_table)[0]
    assert impression["impression_id"] == idea["impression_id"]
    assert impression["model_arm"] == "owner_v1"
    valuation = json.loads(impression["valuation_json"])
    assert valuation["generator_version"] == "owner-v1"
    assert valuation["market"]["effective_floor"] == impression["fairness_threshold"]
    assert "owner_experiment" in json.loads(impression["features_json"])
    public = json.dumps(response.json)
    for private in ("user_elo", "opponent_sources", "manager_preferences", "owner_evaluation", "valuation_json"):
        assert private not in public


@pytest.mark.parametrize("direction,asset", [("give", "a1"), ("receive", "b1")])
def test_asset_ideas_both_directions_use_owner(owner_harness, monkeypatch, direction, asset):
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    response = post(client, "asset-ideas", asset_id=asset, direction=direction)
    assert response.status_code == 200
    assert set(response.json["groups"]) == {"upgrade", "lateral", "downgrade"}
    ideas = [i for group in response.json["groups"].values() for i in group]
    assert ideas, response.json
    assert all(asset in i["give_player_ids" if direction == "give" else "receive_player_ids"] for i in ideas)
    assert all(i["model_arm"] == "owner_v1" and i["impression_id"] for i in ideas)


def test_include_only_serves_and_attributes_control(owner_harness):
    client, engine, *_ = owner_harness
    ts._cfg["bakeoff_serve_owner"] = 0.
    response = post(client)
    assert response.status_code == 200 and response.json["ideas"]
    assert {i["model_arm"] for i in response.json["ideas"]} == {"legacy_fair"}
    run = rows(engine, db.bakeoff_runs_table)[0]
    assert json.loads(run["arms_json"])["owner_v1"]["cards"] > 0
    assert run["served_arm"] == "legacy_fair"


def test_include_off_is_wire_compatible_and_does_not_generate(owner_harness, monkeypatch):
    from backend import trade_gen_owner
    client, engine, *_ = owner_harness
    ts._cfg["bakeoff_include_owner"] = 0.
    monkeypatch.setattr(trade_gen_owner, "generate_owner_trades", lambda **kw: pytest.fail("disabled generator ran"))
    response = post(client)
    assert response.status_code == 200 and response.json["ideas"]
    assert "model_arm" not in response.json["ideas"][0]
    assert not rows(engine, db.deck_impressions_table)


def test_treatment_failure_does_not_relabel_legacy(owner_harness, monkeypatch):
    from backend import trade_gen_owner
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    def fail(**kwargs):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(trade_gen_owner, "generate_owner_trades", fail)
    response = post(client)
    assert response.status_code == 200
    assert response.json["ideas"] == []
    assert response.json["reason"] == "generation_unavailable"
    assert not rows(engine, db.deck_impressions_table)


def test_owner_selected_queue_joins_real_impression(owner_harness, monkeypatch):
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    idea = post(client).json["ideas"][0]
    response = post(client, "queue", impression_id=idea["impression_id"], dwell_ms=750)
    assert response.status_code == 200 and response.json["queued"]
    assert rows(engine, db.trade_decisions_table)[0]["impression_id"] == idea["impression_id"]
    assert rows(engine, db.deck_outcomes_table)[0]["action"] == "like"
    post(client, "queue", impression_id=idea["impression_id"], dwell_ms=750)
    assert len(rows(engine, db.deck_outcomes_table)) == 1


def test_queue_rejects_edited_package_impression(owner_harness, monkeypatch):
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    idea = post(client).json["ideas"][0]
    response = post(client, "queue", receive_player_ids=["b2"], impression_id=idea["impression_id"])
    assert response.status_code == 200 and response.json["queued"]
    assert not rows(engine, db.deck_outcomes_table)
    assert rows(engine, db.trade_decisions_table)[0]["impression_id"] is None


def test_final_owner_mutation_is_rejected(owner_harness, monkeypatch):
    client, engine, sess, service, league = owner_harness
    assign(monkeypatch, "owner_v1")
    idea = post(client).json["ideas"][0]
    card = service._trade_cards[idea["trade_id"]]
    altered = copy.deepcopy(card)
    altered.receive_player_ids = ["b2"]
    assert server._owner_cards_valid([altered], {}) == []
    with pytest.raises(ValueError, match="does not match"):
        server._log_deck_signal_impressions(user_id=ME, league_id=LEAGUE,
            job_id="mutated", cards=[altered], players_dict=service._players,
            capture=None, scoring_format="1qb_ppr")


def test_owner_switches_invalidate_cache_compatibility(owner_harness):
    before = server._trade_safety_signature()
    ts._cfg["bakeoff_serve_owner"] = 0.
    assert before != server._trade_safety_signature()
    ts._cfg["bakeoff_include_owner"] = 0.
    assert "owner_include" not in server._trade_safety_signature()


def context_for(harness):
    _, _, sess, svc, league = harness
    service = sess["service"]
    return server._owner_generation_context(
        sess=sess, service=service, league=league, players=svc._players,
        seed_map=SEED, user_elo={rp.player.id: rp.elo for rp in service.get_rankings().rankings},
        user_roster=sess["user_roster"], scoring_format="1qb_ppr", fairness_threshold=.5,
        pinned_give_players=["a1"], pinned_receive_players=["b1"], exact_give=True,
        opponent_user_id=OPP)


def test_assignment_stable_on_reorder_and_activation(owner_harness):
    context = context_for(owner_harness)
    context["past_decision_keys"] = {(frozenset(["b", "a"]), frozenset(["d", "c"]))}
    initial = server._owner_selected_assignment(context, "fair_packages", serve=True)
    changed = copy.deepcopy(context)
    changed["league"].members.reverse()
    changed["user_roster"].reverse()
    changed["config"]["bakeoff_serve_owner"] = 0.
    changed["config"]["bakeoff_include_owner"] = 0.
    again = server._owner_selected_assignment(changed, "fair_packages", serve=False)
    assert initial["request_hash"] == again["request_hash"]
    assert initial["assignment_probability"] == .5
    assert again["model_arm"] == "legacy_fair"
    changed["user_elo"]["b1"] += 1
    assert server._owner_selected_assignment(changed, "fair_packages", serve=True)["request_hash"] != initial["request_hash"]


def test_context_captures_declared_inputs_without_mutating_control(owner_harness, monkeypatch):
    _, _, sess, _, league = owner_harness
    original = copy.deepcopy(league.members[1].elo_ratings)
    monkeypatch.setattr(server, "load_league_preferences_bulk", lambda *a: {
        ME: {"team_outlook": "contender", "acquire_positions": ["WR"]},
        OPP: {"team_outlook": "rebuilder", "trade_away_positions": ["RB"]}})
    monkeypatch.setattr(server, "load_asset_preferences", lambda **kw: {"untouchables": ["b1"]})
    monkeypatch.setitem(server._FA_LEAGUE_META_CACHE, LEAGUE,
                        (time.time(), {"roster_positions": ["QB", "RB", "WR", "FLEX", "BN"]}))
    context = context_for(owner_harness)
    assert context["outlook"] == "contender"
    assert context["opponent_outlooks"] == {OPP: "rebuilder"}
    assert context["manager_preferences"][OPP]["untouchables"] == ["b1"]
    assert context["manager_preferences"][ME]["starter_slots"] == ["QB", "RB", "WR", "FLEX"]
    assert context["manager_preferences"][ME]["lineup_source"] == "observed"
    assert league.members[1].elo_ratings == original


def worker(owner_harness, monkeypatch, *, give=(), receive=(), opponent=None, expected_error=None):
    _, _, sess, _, _ = owner_harness
    for name in ("_deck_exploration_enabled", "_deck_first_session_enabled", "_likes_you_enabled",
                 "_suggestion_telemetry_enabled", "_deck_fatigue_enabled", "_deck_taste_enabled",
                 "_deck_diversity_enabled", "_thompson_deck_enabled"):
        monkeypatch.setattr(server, name, lambda: False)
    job_id = "owner-route-worker"
    job = {"job_id": job_id, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
           "started_at": time.monotonic(), "finished_at": None, "cards": [],
           "opponents_done": 0, "opponents_total": 2, "error": None,
           "fairness_threshold": .5, "outlook_value": None, "is_pinned": bool(give or receive)}
    monkeypatch.setitem(server._trade_jobs, job_id, job)
    server._run_trade_job(job_id, TOKEN, LEAGUE, .5, list(give), list(receive), opponent)
    assert job["status"] == ("error" if expected_error else "complete"), job
    if expected_error:
        assert job["error"] == expected_error
    assert not job.get("final_checks_pending")
    return job


@pytest.mark.parametrize("give,receive", [((), ("b1",)), (("a1",), ("b1",))])
def test_pinned_worker_reaches_owner_and_preserves_transport(owner_harness, monkeypatch, give, receive):
    assign(monkeypatch, "owner_v1")
    job = worker(owner_harness, monkeypatch, give=give, receive=receive, opponent=OPP)
    assert job["cards"], job
    assert all(c["model_arm"] == "owner_v1" and c["impression_id"] for c in job["cards"])
    assert all(set(receive) <= set(p["id"] for p in c["receive"]) for c in job["cards"])
    assert all(c["preserve_server_order"] for c in job["cards"])


def test_organic_owner_survives_legacy_personal_veto_and_context_is_captured_once(owner_harness, monkeypatch):
    _, engine, _, svc, _ = owner_harness
    ts._cfg.update(bakeoff_serve_interleaved=1., bakeoff_group_size=0.,
                   bakeoff_include_gen_v2=0., bakeoff_include_challenger=0.)
    ff._flags_cache["trade.personal_market_policy_v1"] = True
    original_context = server._owner_generation_context
    captures = []
    def capture(**kwargs):
        captures.append("capture")
        return original_context(**kwargs)
    monkeypatch.setattr(server, "_owner_generation_context", capture)
    original_generate = svc.generate_trades
    def legacy(**kwargs):
        assert captures == ["capture"]
        return original_generate(**kwargs)
    monkeypatch.setattr(svc, "generate_trades", legacy)
    def reject_legacy(cards, *args, **kwargs):
        assert all(getattr(c, "owner_evaluation", None) is None for c in cards)
        return [], {}, []
    monkeypatch.setattr(server, "_evaluate_deck_policy", reject_legacy)
    job = worker(owner_harness, monkeypatch)
    assert job["cards"], job
    assert all(c["model_arm"] == "owner_v1" for c in job["cards"])
    assert captures == ["capture"]
    assert {r["model_arm"] for r in rows(engine, db.deck_impressions_table)} == {"owner_v1"}
    run_record = json.loads(rows(engine, db.bakeoff_runs_table)[0]["config_json"])["owner_request"]
    first_impression = rows(engine, db.deck_impressions_table)[0]
    card_record = json.loads(first_impression["features_json"])["owner_request"]
    assert run_record["request_hash"] == card_record["request_hash"]
    assert run_record["captured_at"] == card_record["captured_at"]
    assert set(run_record["input"]["seed_elo"]) == set(SEED)
    assert len(card_record["input"]["seed_elo"]) < len(SEED)


def test_selected_owner_cannot_bypass_roster_legality(owner_harness, monkeypatch):
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    ff._flags_cache["trade.roster_protection"] = True
    class Blocked:
        def card(self, card):
            return {"schema_version": 1, "status": "blocked", "eligible": False,
                    "unknowns": ["synthetic_slot_violation"], "teams": {}}
    monkeypatch.setattr(server, "_build_trade_roster_context", lambda **kw: Blocked())
    response = post(client)
    assert response.status_code == 200
    assert response.json["ideas"] == []
    assert not rows(engine, db.deck_impressions_table)


def test_shadow_control_is_not_subject_to_new_treatment_filters(owner_harness, monkeypatch):
    client, _, *_ = owner_harness
    ts._cfg["bakeoff_serve_owner"] = 0.
    ff._flags_cache["trade.roster_protection"] = True
    monkeypatch.setattr(server, "_build_trade_roster_context", lambda **kw: pytest.fail("shadow changed control gate"))
    monkeypatch.setattr(server, "_project_trade_dispositions", lambda *a: pytest.fail("shadow changed control membership"))
    response = post(client)
    assert response.status_code == 200 and response.json["ideas"]
    assert all("preserve_server_order" not in i for i in response.json["ideas"])


@pytest.mark.parametrize("serve", [False, True])
def test_capture_failure_shadow_fallback_or_named_unavailable(owner_harness, monkeypatch, serve):
    client, engine, *_ = owner_harness
    ts._cfg["bakeoff_serve_owner"] = float(serve)
    def unavailable(**kw):
        raise RuntimeError("synthetic missing input")
    monkeypatch.setattr(server, "_owner_generation_context", unavailable)
    response = post(client)
    assert response.status_code == (503 if serve else 200)
    if serve:
        assert response.json == {"error": "owner_experiment_unavailable"}
    else:
        assert response.json["ideas"]
        assert "model_arm" not in response.json["ideas"][0]
    assert not rows(engine, db.deck_impressions_table)


def test_selected_partial_retains_frozen_authority_and_public_notice(owner_harness, monkeypatch):
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    response = post(client, receive_player_ids=["b1", "b2"])
    assert response.status_code == 200 and response.json["ideas"], response.json
    idea = response.json["ideas"][0]
    assert idea["give_player_ids"] == ["a1"]
    assert idea["selection_coverage"] == "partial"
    assert "part of your selection" in idea["selection_notice"]
    assert json.loads(rows(engine, db.deck_impressions_table)[0]["valuation_json"])["selection"]["coverage"] == "partial"


def test_selected_safety_and_impression_failure_cannot_expose_unattributed_cards(owner_harness, monkeypatch):
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    def failure(*args, **kwargs):
        raise RuntimeError("synthetic write unavailable")
    monkeypatch.setattr(server, "save_deck_impressions", failure)
    response = post(client)
    assert response.status_code == 503
    assert response.json == {"error": "owner_experiment_unavailable"}
    assert not rows(engine, db.deck_impressions_table)


def test_queue_drops_foreign_impression(owner_harness, monkeypatch):
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    idea = post(client).json["ideas"][0]
    with engine.begin() as conn:
        conn.execute(db.deck_impressions_table.update().values(user_id="not-the-viewer"))
    response = post(client, "queue", impression_id=idea["impression_id"])
    assert response.status_code == 200 and response.json["queued"]
    assert rows(engine, db.trade_decisions_table)[0]["impression_id"] is None
    assert not rows(engine, db.deck_outcomes_table)


def test_worker_uses_published_inferred_outlook(owner_harness, monkeypatch):
    from backend import trade_gen_owner
    assign(monkeypatch, "owner_v1")
    seen = []
    original = trade_gen_owner.generate_owner_trades
    def generate(**kwargs):
        assert kwargs["outlook"] is None
        assert kwargs["inferred_outlooks"][ME] == "contender"
        cards, report = original(**kwargs)
        seen.extend(c.owner_evaluation.as_dict()["viewer"] for c in cards)
        return cards, report
    monkeypatch.setattr(trade_gen_owner, "generate_owner_trades", generate)
    monkeypatch.setattr(server, "_infer_user_outlook", lambda *a, **kw: ("contender", None))
    job = worker(owner_harness, monkeypatch, give=["a1"], receive=["b1"], opponent=OPP)
    assert job["cards"] and seen
    assert all(c["outlook"] == "contender" for c in job["cards"])
    assert all(v["outlook"] == "contender" and v["outlook_source"] == "inferred" for v in seen)


@pytest.mark.parametrize("targeted", [False, True])
def test_worker_shadow_capture_failure_preserves_control(owner_harness, monkeypatch, targeted):
    _, engine, _, svc, _ = owner_harness
    ts._cfg.update(bakeoff_include_owner=0., bakeoff_serve_owner=0.,
                   bakeoff_include_challenger=0., bakeoff_include_gen_v2=0.)
    control = ts.TradeCard("unchanged-control", LEAGUE, ME, OPP, "opp", ["a1"], ["b1"], 0., .9, 1.)
    monkeypatch.setattr(svc, "generate_trades", lambda **kw: [copy.deepcopy(control)])
    kwargs = {"give": ["a1"], "receive": ["b1"], "opponent": OPP} if targeted else {}
    before = worker(owner_harness, monkeypatch, **kwargs)
    assert before["cards"]
    def capture_failure(**kwargs):
        raise RuntimeError("synthetic capture unavailable")
    monkeypatch.setattr(server, "_owner_generation_context", capture_failure)
    ts._cfg["bakeoff_include_owner"] = 1.
    after = worker(owner_harness, monkeypatch, **kwargs)
    def package(cards):
        return [(c["trade_id"], [p["id"] for p in c["give"]], [p["id"] for p in c["receive"]]) for c in cards]
    assert package(after["cards"]) == package(before["cards"])
    assert all(c.get("model_arm") != "owner_v1" for c in after["cards"])


def test_selected_response_view_and_pass_join_one_impression(owner_harness, monkeypatch):
    client, engine, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    idea = post(client).json["ideas"][0]
    headers = {"X-Session-Token": TOKEN, "X-Device-Id": "owner-test-device"}
    response = client.post("/api/events", headers=headers, json={"events": [{
        "event_type": "deck_card_viewed", "event_id": "owner-test-view-event",
        "session_id": "owner-test-analytics-session", "seq": 1,
        "screen": "Trades", "props": {
            "impression_id": idea["impression_id"], "trade_id": idea["trade_id"], "card_index": 0}}]})
    assert response.status_code == 200
    assert response.json["accepted"] == 1, response.json
    response = post(client, "swipe", trade_id=idea["trade_id"], decision="pass",
                    target_user_id=OPP, impression_id=idea["impression_id"], dwell_ms=800)
    assert response.status_code == 200
    outcome_rows = rows(engine, db.deck_outcomes_table)
    assert {r["action"] for r in outcome_rows} == {"viewed", "pass"}
    assert {r["impression_id"] for r in outcome_rows} == {idea["impression_id"]}


def test_trial_worker_does_not_publish_before_all_real_impressions(owner_harness, monkeypatch):
    assign(monkeypatch, "owner_v1")
    original = server._log_deck_signal_impressions
    observed = []
    def write(**kwargs):
        job = server._trade_jobs["owner-route-worker"]
        observed.append(True)
        assert job["cards"] == []
        assert job["final_checks_pending"]
        return original(**kwargs)
    monkeypatch.setattr(server, "_log_deck_signal_impressions", write)
    job = worker(owner_harness, monkeypatch, give=["a1"], receive=["b1"], opponent=OPP)
    assert observed and job["cards"]
    assert all(c["impression_id"] for c in job["cards"])


@pytest.mark.parametrize("failure", ["raise", "incomplete"])
def test_trial_worker_impression_failure_withholds_entire_deck(owner_harness, monkeypatch, failure):
    assign(monkeypatch, "owner_v1")
    def write(**kwargs):
        assert server._trade_jobs["owner-route-worker"]["cards"] == []
        if failure == "raise":
            raise RuntimeError("synthetic missing impressions")
        return {}
    monkeypatch.setattr(server, "_log_deck_signal_impressions", write)
    job = worker(owner_harness, monkeypatch, give=["a1"], receive=["b1"], opponent=OPP,
                 expected_error="owner_impression_unavailable")
    assert job["cards"] == []


@pytest.mark.parametrize("source", ["platform", "any"])
def test_selected_final_roster_picks_use_shared_authorized_source(owner_harness, monkeypatch, source):
    client, _, *_ = owner_harness
    assign(monkeypatch, "owner_v1")
    ff._flags_cache["trade.roster_protection"] = True
    monkeypatch.setattr(server, "_owned_picks_available", lambda *a: False)
    monkeypatch.setattr(server, "_pick_read_source", lambda: source)
    calls, captured = [], []
    pick_rows = [{"pick_id": "synthetic-owned-pick", "owner_user_id": ME}]
    def load(*, league_id, source):
        assert league_id == LEAGUE
        calls.append(source)
        return pick_rows
    class Safe:
        def card(self, card):
            return {"schema_version": 1, "status": "safe", "eligible": True,
                    "unknowns": [], "teams": {}}
    def build(**kwargs):
        captured.append(kwargs["picks"])
        return Safe()
    monkeypatch.setattr(server, "load_draft_picks", load)
    monkeypatch.setattr(server, "_build_trade_roster_context", build)
    response = post(client)
    assert response.status_code == 200 and response.json["ideas"]
    assert calls == [source]
    assert captured == [pick_rows]
