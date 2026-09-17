"""Shared significance serving contract: all arms, cache and explicit intent.

Uses synthetic owner-route fixtures, isolated SQLite and real final-worker
publication. Leaf math lives in test_trade_significance; these tests prove
low-impact cards cannot bypass the policy through another serving path.
"""
import ast
import copy
import inspect
import json
from types import SimpleNamespace

import pytest

from backend import database as db, server, trade_service as ts
from backend.ranking_service import Player
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, worker, rows, post, context_for, ME, OPP, LEAGUE, TOKEN)


@pytest.fixture
def low_owner(owner_harness, monkeypatch):
    """Mutually attractive real trades, all players below the second tier."""
    _, _, sess, _, _ = owner_harness
    ranking = sess["service"]
    ids = list(ranking._seed)
    ranking._seed = dict.fromkeys(ids, 1300.)
    ranking._elo_overrides = dict.fromkeys(ids, 1300.)
    ranking._elo_overrides.update(a1=1280., b1=1360.)
    monkeypatch.setattr(server, "load_member_rankings", lambda *a, **k: {
        OPP: {"elo_ratings": {**dict.fromkeys(ids, 1300.), "a1": 1360., "b1": 1280.},
              "confidence_sources": dict.fromkeys(ids, "explicit"), "username": "opp"}})
    ts._cfg.update(bakeoff_owner_only=1., significance_mode=2.)
    return owner_harness


def _card(arm, *, give="low-a", receive="low-b", **extra):
    return SimpleNamespace(model_arm=arm, league_id=LEAGUE, trade_id=f"card-{arm}-{give}-{receive}", give_player_ids=[give],
        receive_player_ids=[receive], target_user_id=OPP, **extra)


def _evaluate(cards, mode=2, **kwargs):
    players = {pid: Player(id=pid, name=pid, position="WR", team="AAA", age=25)
               for pid in ("low-a", "low-b", "high")}
    return server._evaluate_trade_significance(cards,
        capture=(mode, server._capture_trade_significance()[1], "second", True),
        players=players, user_elo={"low-a": 1250., "low-b": 1250., "high": 1500.},
        seed_elo={"low-a": 1250., "low-b": 1250., "high": 1500.},
        scoring_format="1qb_ppr", **kwargs)


@pytest.mark.parametrize("arm", ["baseline", "current", "challenger", "gen_v2", "fit", "owner_v1"])
def test_same_low_impact_rule_filters_every_arm_without_reordering(arm):
    low, high = _card(arm), _card(arm, receive="high")
    kept, evidence, _ = _evaluate([low, high])
    assert kept == [high]
    assert not evidence[id(low)]["eligible"]
    assert evidence[id(high)]["eligible"]


@pytest.mark.parametrize("mode", [0, 1])
def test_off_and_shadow_do_not_remove_or_reorder(mode):
    cards = [_card("owner_v1"), _card("current", receive="high")]
    kept, evidence, _ = _evaluate(cards, mode)
    assert kept == cards
    if mode == 0:
        assert not evidence
    else:
        assert not evidence[id(cards[0])]["eligible"]


def test_no_cap_and_no_low_quality_backfill():
    high = [_card("owner_v1", receive="high") for _ in range(101)]
    low = _card("owner_v1")
    kept, _, _ = _evaluate([low, *high])
    assert kept == high
    assert _evaluate([low])[0] == []


def test_untrusted_card_claims_do_not_exempt_low_value():
    card = _card("owner_v1", likes_you=True, standing_offer_reason="claimed",
                 significance_exempt=True, source="manual")
    assert _evaluate([card])[0] == []


def test_trusted_inbound_exemption_cannot_transfer_to_mutated_or_copied_card():
    card = _card("owner_v1")
    inbound = {server._significance_card_key(card)}
    assert _evaluate([card], inbound_keys=inbound)[0] == [card]
    assert _evaluate([_card("owner_v1")], inbound_keys=inbound)[0] == []
    card.give_player_ids.append("low-b")
    assert _evaluate([card], inbound_keys=inbound)[0] == []


@pytest.mark.parametrize("field,value", [("league_id", "another-league"), ("trade_id", "another-card")])
def test_trusted_inbound_exemption_is_league_and_trade_identity_scoped(field, value):
    card = _card("owner_v1")
    inbound = {server._significance_card_key(card)}
    setattr(card, field, value)
    assert _evaluate([card], inbound_keys=inbound)[0] == []


def test_actual_injector_supplies_trusted_inbound_evidence(monkeypatch):
    from backend.tests.test_trade_policy_wiring import run_job
    monkeypatch.setitem(ts._cfg, "significance_mode", 2.)
    job, _, impressions, _ = run_job(seed_like=True)
    assert job["status"] == "complete"
    inbound = [json.loads(row["features_json"]) for row in impressions
               if json.loads(row["features_json"]).get("likes_you")]
    assert inbound, "fixture must actually inject a persisted incoming like"
    assert all(row["significance"]["reason"] == "exempt_inbound" for row in inbound)


@pytest.mark.parametrize("mode", [1, 2])
def test_evaluation_failure_is_diagnosed_and_never_enforcement_bypass(monkeypatch, mode):
    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic missing context")
    monkeypatch.setattr(server._trade_significance, "evaluate_significance", unavailable)
    card = _card("owner_v1", receive="high")
    kept, evidence, diagnostics = _evaluate([card], mode)
    assert kept == ([card] if mode == 1 else [])
    assert evidence[id(card)]["reason"] == "evaluation_unavailable"
    assert diagnostics["would_reject"] == 1


def test_only_correct_direction_actual_anchor_is_exempt():
    card = _card("owner_v1")
    assert _evaluate([card], selected_give_ids=["low-a"])[0] == [card]
    assert _evaluate([card], selected_receive_ids=["low-b"])[0] == [card]
    assert _evaluate([card], selected_give_ids=["absent"])[0] == []
    assert _evaluate([card], selected_give_ids=["low-b"])[0] == []


def test_baseline_profile_does_not_switch_off_shared_policy(monkeypatch):
    from backend.bakeoff_profiles import model_a
    monkeypatch.setitem(ts._cfg, "significance_mode", 2.)
    before = server._capture_trade_significance()
    with model_a():
        assert server._capture_trade_significance() == before
        assert _evaluate([_card("baseline")])[0] == []


@pytest.mark.parametrize("selection", [{}, {"opponent": OPP}])
def test_owner_final_gate_rejects_before_impressions_without_fallback(low_owner, monkeypatch, selection):
    _, engine, _, service, _ = low_owner
    monkeypatch.setattr(service, "generate_trades", lambda **kw: pytest.fail("control fallback"))
    job = worker(low_owner, monkeypatch, **selection)
    assert job["cards"] == []
    assert rows(engine, db.deck_impressions_table) == []


def test_explicit_low_value_worker_selection_survives(low_owner, monkeypatch):
    job = worker(low_owner, monkeypatch, give=["a1"], receive=["b1"], opponent=OPP)
    assert job["cards"], job
    assert all("a1" in [p["id"] for p in c["give"]] for c in job["cards"])


@pytest.mark.parametrize("route,selection", [
    ("fair-packages", {}), ("asset-ideas", {"asset_id": "a1", "direction": "give"})])
def test_explicit_low_value_sync_routes_survive(low_owner, route, selection):
    client, engine, *_ = low_owner
    response = post(client, route, **selection)
    assert response.status_code == 200, response.json
    cards = (response.json["ideas"] if route == "fair-packages" else
             [c for group in response.json["groups"].values() for c in group])
    assert cards, response.json
    assert rows(engine, db.deck_impressions_table)


def test_legacy_policy_veto_and_owner_remerge_cannot_bypass_significance(low_owner, monkeypatch):
    from backend import feature_flags as ff
    ff._flags_cache["trade.personal_market_policy_v1"] = True
    monkeypatch.setattr(server, "_evaluate_deck_policy", lambda *a, **k: ([], {}, []))
    job = worker(low_owner, monkeypatch)
    assert job["cards"] == []


def test_mode_change_invalidates_completed_cache_and_status(low_owner, monkeypatch):
    client, _, _, _, _ = low_owner
    ts._cfg["significance_mode"] = 0.
    job = worker(low_owner, monkeypatch)
    assert job["cards"], "fixture must generate actual low-value recommendations"
    assert server._trade_job_is_fresh(job, .5, job.get("outlook_value"))
    ts._cfg["significance_mode"] = 2.
    assert not server._trade_job_is_fresh(job, .5, job.get("outlook_value"))
    response = client.get("/api/trades/status", query_string={"job_id": job["job_id"]},
                          headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200
    assert response.json["cards"] == []
    assert response.json["error"] == "significance_policy_changed"


def test_mode_change_blocks_old_pending_recommendations(low_owner, monkeypatch):
    client, _, _, _, _ = low_owner
    ts._cfg["significance_mode"] = 0.
    job = worker(low_owner, monkeypatch)
    assert job["cards"]
    ts._cfg["significance_mode"] = 2.
    response = client.get("/api/trades", query_string={"league_id": LEAGUE},
                          headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200
    assert response.json == []


def test_pending_route_preserves_explicit_low_value_card(low_owner):
    client, _, _, _, _ = low_owner
    response = post(client)
    assert response.status_code == 200 and response.json["ideas"]
    selected_ids = {card["trade_id"] for card in response.json["ideas"]}
    pending = client.get("/api/trades", query_string={"league_id": LEAGUE},
                         headers={"X-Session-Token": TOKEN})
    assert pending.status_code == 200
    assert selected_ids <= {card["trade_id"] for card in pending.json}


def test_pending_hydrates_meaningful_first_pick_missing_from_ranking_seed(low_owner, monkeypatch):
    client, _, sess, service, _ = low_owner
    pick_id = f"{LEAGUE}_2027_1_1"
    pick = Player(id=pick_id, name="2027 first", position="PICK", team="PICK", age=0,
                  pick_value=50.)
    pick_assets = {OPP: [pick]}
    monkeypatch.setattr(server, "_owned_pick_assets", lambda *a, **k: pick_assets)
    card = ts.TradeCard(trade_id="significant-first", league_id=LEAGUE,
        proposing_user_id=ME, target_user_id=OPP, target_username="opp",
        give_player_ids=["a1"], receive_player_ids=[pick_id],
        mismatch_score=0., fairness_score=1., composite_score=1.)
    # The worker's injected seed has the pick; the persisted ranking service
    # deliberately does not. Neither player is a qualifying centerpiece.
    ranking = sess["service"]
    assert pick_id not in ranking._seed
    kept, evidence, _ = server._evaluate_trade_significance([card],
        capture=server._capture_trade_significance(),
        players={**service._players, pick_id: pick}, user_elo=ranking._elo_overrides,
        seed_elo={**ranking._seed, **server._pick_asset_elos(pick_assets)},
        scoring_format="1qb_ppr")
    assert kept == [card] and evidence[id(card)]["reason"] == "meaningful_pick"
    service._trade_cards[card.trade_id] = card
    pending = client.get("/api/trades", query_string={"league_id": LEAGUE},
                         headers={"X-Session-Token": TOKEN})
    assert pending.status_code == 200
    assert card.trade_id in {c["trade_id"] for c in pending.json}
    assert pick_id not in ranking._seed, "read-only hydration must not change the user's board"


@pytest.mark.parametrize("surface", ["fair_packages", "asset_ideas", "organic"])
def test_significance_config_does_not_reassign_owner_experiment(owner_harness, surface):
    context = context_for(owner_harness)
    context["config"] = {k: v for k, v in context["config"].items()
                         if not k.startswith("significance_")}
    original = server._owner_selected_assignment(context, surface, serve=True)
    for config in (
            {"significance_mode": 0., "significance_player_min_tier": 2.,
             "significance_allow_first_round_pick": 1.},
            {"significance_mode": 2., "significance_player_min_tier": 1.,
             "significance_allow_first_round_pick": 0.}):
        changed = copy.deepcopy(context)
        changed["config"].update(config)
        assignment = server._owner_selected_assignment(changed, surface, serve=True)
        assert assignment["request_hash"] == original["request_hash"]
        assert assignment["model_arm"] == original["model_arm"]
        assert assignment["assignment_probability"] == original["assignment_probability"]


@pytest.mark.parametrize("withhold", [False, True])
def test_final_served_diagnostics_reflect_atomic_impression_failure(low_owner, monkeypatch, withhold):
    _, engine, *_ = low_owner
    if withhold:
        def unavailable(*args, **kwargs):
            raise RuntimeError("synthetic impression store unavailable")
        monkeypatch.setattr(server, "_log_deck_signal_impressions", unavailable)
    job = worker(low_owner, monkeypatch, give=["a1"], receive=["b1"], opponent=OPP,
                 expected_error="owner_impression_unavailable" if withhold else None)
    diagnostics = job["significance"]
    assert diagnostics["final_served"] == len(job["cards"])
    if withhold:
        assert diagnostics["withheld"] == "impression_unavailable"
        assert not rows(engine, db.deck_impressions_table)
    else:
        assert job["cards"]
        assert len(rows(engine, db.deck_impressions_table)) == diagnostics["final_served"]
    runs = rows(engine, db.bakeoff_runs_table)
    assert runs
    assert json.loads(runs[0]["config_json"])["significance"]["final_served"] == len(job["cards"])


def test_real_kickoff_snapshot_preserves_explicit_exception_for_pending_route(low_owner, monkeypatch):
    client, _, sess, _, _ = low_owner
    for name in ("_deck_exploration_enabled", "_deck_first_session_enabled", "_likes_you_enabled",
                 "_suggestion_telemetry_enabled", "_deck_fatigue_enabled", "_deck_taste_enabled",
                 "_deck_diversity_enabled", "_thompson_deck_enabled"):
        monkeypatch.setattr(server, name, lambda: False)
    job_id = server._kickoff_trade_job(
        TOKEN, ME, LEAGUE, "1qb_ppr", .5, pinned_give=["a1"],
        pinned_receive=["b1"], opponent_user_id=OPP,
        synchronous=True, session_context=sess)
    try:
        job = server._trade_jobs[job_id]
        assert job["status"] == "complete", job
        assert job["cards"], job
        selected_ids = {card["trade_id"] for card in job["cards"]}
        pending = client.get("/api/trades", query_string={"league_id": LEAGUE},
                             headers={"X-Session-Token": TOKEN})
        assert pending.status_code == 200
        assert selected_ids <= {card["trade_id"] for card in pending.json}
    finally:
        with server._trade_jobs_lock:
            server._trade_jobs.pop(job_id, None)


def test_queued_generate_response_and_running_config_change(low_owner, monkeypatch):
    client, _, _, _, _ = low_owner
    monkeypatch.setattr(server.threading, "Thread", lambda *a, **k: SimpleNamespace(start=lambda: None))
    headers = {"X-Session-Token": TOKEN}
    job_ids = []
    key = server._trade_job_key(ME, LEAGUE, "1qb_ppr")
    monkeypatch.delitem(server._trade_jobs_by_key, key, raising=False)
    try:
        first = client.post("/api/trades/generate", json={"league_id": LEAGUE}, headers=headers)
        assert first.status_code == 200, first.json
        assert first.json["status"] == "running"
        assert first.json["error"] is None and first.json["cards"] == []
        job_ids.append(first.json["job_id"])
        ts._cfg["significance_player_min_tier"] = 1.
        second = client.post("/api/trades/generate", json={"league_id": LEAGUE}, headers=headers)
        assert second.status_code == 200, second.json
        job_ids.append(second.json["job_id"])
        assert second.json["status"] == "running" and second.json["error"] is None
        assert job_ids[1] != job_ids[0]
        assert server._trade_jobs[job_ids[0]]["superseded"]
    finally:
        with server._trade_jobs_lock:
            for job_id in job_ids:
                server._trade_jobs.pop(job_id, None)
            server._trade_jobs_by_key.pop(key, None)


@pytest.mark.parametrize("knob,value", [
    ("significance_player_min_tier", 1.), ("significance_allow_first_round_pick", 0.)])
def test_threshold_changes_invalidate_cache_even_when_mode_unchanged(low_owner, monkeypatch, knob, value):
    job = worker(low_owner, monkeypatch)
    assert server._trade_job_is_fresh(job, .5, job.get("outlook_value"))
    ts._cfg[knob] = value
    assert not server._trade_job_is_fresh(job, .5, job.get("outlook_value"))
    assert server._trade_job_public_view(job)["cards"] == []


def test_significance_diagnostics_are_not_in_public_cards(low_owner, monkeypatch):
    ts._cfg["significance_mode"] = 1.
    job = worker(low_owner, monkeypatch)
    assert job["cards"]
    public = json.dumps(server._trade_job_public_view(job))
    assert "qualifying_asset" not in public
    assert "user_elo" not in public
    _, engine, *_ = low_owner
    impressions = rows(engine, db.deck_impressions_table)
    assert impressions
    assert all("significance" in row["features_json"] for row in impressions)


def test_all_pre_significance_worker_publications_wait_for_checks():
    tree = ast.parse(inspect.getsource(server._run_trade_job))
    gate = next(node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == "_evaluate_trade_significance")
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or node.lineno >= gate:
            continue
        if not any(isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant)
                   and target.slice.value == "cards" for target in node.targets):
            continue
        ancestor = parents.get(node)
        while ancestor is not None:
            if isinstance(ancestor, ast.If):
                test = ast.unparse(ancestor.test)
                if "final_checks_pending" in test or "not (market_live or roster_live or owner_serve or significance_capture[0])" in test:
                    break
            ancestor = parents.get(ancestor)
        assert ancestor is not None, f"Unchecked worker publication at line {node.lineno}"
        count += 1
    assert count >= 5
