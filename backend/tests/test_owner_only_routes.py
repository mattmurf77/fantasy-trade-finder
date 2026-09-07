"""Owner-only rollout: real routes, captured permissions and truthful F1 rows.

The existing owner route harness supplies synthetic data and isolated SQLite.
No legacy generator may run in the exclusive mode, including selected paths.
"""
import copy
import json
import math
import time

import pytest

from backend import database as db, feature_flags as ff, server, trade_service as ts
from backend.ranking_service import Player, RankingService
from backend.tests.test_owner_generator_routes import (
    harness, owner_harness, post, rows, worker, context_for, ME, OPP, LEAGUE)


@pytest.fixture
def exclusive(owner_harness):
    ts._cfg["bakeoff_owner_only"] = 1.
    return owner_harness


@pytest.fixture
def large_exclusive(exclusive, monkeypatch):
    """Four real synthetic rosters: 64 different safe 1-for-1 returns."""
    _, _, sess, service, league = exclusive
    rosters = {f"opponent-{n}": [f"r{n}-{i}" for i in range(16)] for n in range(4)}
    ids = ["g", *(p for roster in rosters.values() for p in roster)]
    players = [Player(id=p, name=p, position="WR", team="AAA", age=26) for p in ids]
    seed = dict.fromkeys(ids, 1500.)
    low, high = 1500 + math.log(.8) / .005, 1500 + math.log(1.2) / .005
    ranking = RankingService(players=players)
    ranking._seed = seed
    ranking._elo_overrides.update({p: low if p == "g" else high for p in ids})
    monkeypatch.setattr(ranking, "placement_bands", lambda: {p: (1200, 1900) for p in ids})
    league.members = [ts.LeagueMember(user_id=ME, username="me", roster=["g"], elo_ratings={}),
        *(ts.LeagueMember(user_id=uid, username=uid, roster=roster, elo_ratings={})
          for uid, roster in rosters.items())]
    sess.update(players=players, user_roster=["g"], service=ranking, services={"1qb_ppr": ranking})
    service._players = {p.id: p for p in players}
    boards = {uid: {"elo_ratings": {p: low if p in roster else high for p in ids},
                    "confidence_sources": dict.fromkeys(ids, "explicit"), "username": uid}
              for uid, roster in rosters.items()}
    monkeypatch.setattr(server, "load_member_rankings", lambda *a, **k: boards)
    monkeypatch.setattr(server, "load_league_preferences_bulk", lambda *a: {
        uid: {"team_outlook": "not_sure"} for uid in [ME, *rosters]})
    monkeypatch.setattr(server, "_infer_user_outlook", lambda *a, **k: ("not_sure", None))
    return exclusive


def forbid_controls(monkeypatch, service):
    def forbidden(**kwargs):
        pytest.fail("legacy generator executed during owner-only discovery")
    for name in ("generate_trades", "generate_fair_packages", "generate_asset_ideas"):
        monkeypatch.setattr(service, name, forbidden)
    monkeypatch.setattr(server._bakeoff, "gen_v2_cards", lambda *a, **k: forbidden())
    monkeypatch.setattr(server._bakeoff, "gen_fit_cards", lambda *a, **k: forbidden())


@pytest.mark.parametrize("route,selection", [
    ("fair-packages", {}),
    ("asset-ideas", {"asset_id": "a1", "direction": "give"}),
    ("asset-ideas", {"asset_id": "b1", "direction": "receive"}),
])
def test_selected_exclusive_never_runs_controls_and_attributes_probability_one(exclusive, monkeypatch, route, selection):
    client, engine, _, service, _ = exclusive
    forbid_controls(monkeypatch, service)
    response = post(client, route, **selection)
    assert response.status_code == 200, response.json
    ideas = response.json.get("ideas") if route == "fair-packages" else [
        i for group in response.json["groups"].values() for i in group]
    assert ideas
    assert all(i["model_arm"] == "owner_v1" and i["impression_id"] for i in ideas)
    run = rows(engine, db.bakeoff_runs_table)[0]
    assignment = json.loads(run["config_json"])
    assert assignment["assignment_probability"] == 1.
    assert assignment["exclusive"] is True
    assert assignment["version"] == server._OWNER_EXCLUSIVE_VERSION
    assert set(json.loads(run["arms_json"])) == {"owner_v1"}
    assert json.loads(run["arm_order"]) == ["owner_v1"]
    for row in rows(engine, db.deck_impressions_table):
        assert row["policy_version"] == server._OWNER_EXCLUSIVE_VERSION
        assert json.loads(row["features_json"])["owner_experiment"]["exclusive"] is True
    assert not any(k in json.dumps(response.json) for k in (
        "user_elo", "opponent_sources", "owner_evaluation", "manager_preferences"))


@pytest.mark.parametrize("selection", [
    {}, {"give": ["a1"]}, {"receive": ["b1"]},
    {"give": ["a1"], "receive": ["b1"], "opponent": OPP},
    {"opponent": OPP},
])
def test_worker_all_entrances_exclude_controls_even_when_interleaving_off(exclusive, monkeypatch, selection):
    _, engine, _, service, _ = exclusive
    ts._cfg.update(bakeoff_serve_interleaved=0., bakeoff_group_size=1., bakeoff_deck_limit=1.)
    forbid_controls(monkeypatch, service)
    job = worker(exclusive, monkeypatch, **selection)
    assert job["cards"], job
    assert all(c["model_arm"] == "owner_v1" and c["impression_id"] for c in job["cards"])
    assert "owner_only" in job["safety_policy"]
    assert {r["model_arm"] for r in rows(engine, db.deck_impressions_table)} == {"owner_v1"}
    assert {r["policy_version"] for r in rows(engine, db.deck_impressions_table)} == {
        server._OWNER_EXCLUSIVE_VERSION}
    assert all(set(json.loads(r["arms_json"])) == {"owner_v1"}
               for r in rows(engine, db.bakeoff_runs_table))


@pytest.mark.parametrize("initial", [False, True])
def test_worker_captures_exclusive_mode_before_context_and_invalidates_hot_cache(owner_harness, monkeypatch, initial):
    ts._cfg.update(bakeoff_owner_only=float(initial), bakeoff_serve_interleaved=1.,
                   bakeoff_group_size=0., bakeoff_include_challenger=0., bakeoff_include_gen_v2=0.)
    original_context = server._owner_generation_context
    original_run = server._bakeoff.run_bakeoff
    captured = []
    def capture(**kwargs):
        ts._cfg["bakeoff_owner_only"] = float(not initial)
        return original_context(**kwargs)
    def run(**kwargs):
        captured.append(kwargs.get("owner_exclusive"))
        assert kwargs.get("owner_exclusive") is initial
        return original_run(**kwargs)
    monkeypatch.setattr(server, "_owner_generation_context", capture)
    monkeypatch.setattr(server._bakeoff, "run_bakeoff", run)
    job = worker(owner_harness, monkeypatch)
    assert captured == [initial]
    assert ("owner_only" in job["safety_policy"]) is initial
    assert not server._trade_job_is_fresh(job, .5, job.get("outlook_value"))


@pytest.mark.parametrize("route,selection", [
    ("fair-packages", {}), ("asset-ideas", {"asset_id": "a1", "direction": "give"})])
def test_selected_captures_exclusivity_before_context_reload(exclusive, monkeypatch, route, selection):
    client, _, _, service, _ = exclusive
    forbid_controls(monkeypatch, service)
    original = server._owner_generation_context
    def capture(**kwargs):
        ts._cfg["bakeoff_owner_only"] = 0.
        return original(**kwargs)
    monkeypatch.setattr(server, "_owner_generation_context", capture)
    response = post(client, route, **selection)
    assert response.status_code == 200, response.json


@pytest.mark.parametrize("include,serve,only", [(0, 1, 1), (1, 0, 1), (1, 1, 0)])
def test_exclusive_signature_requires_all_three_permissions(owner_harness, include, serve, only):
    ts._cfg.update(bakeoff_include_owner=include, bakeoff_serve_owner=serve, bakeoff_owner_only=only)
    assert "owner_only" not in server._trade_safety_signature()


def test_demo_freshness_excludes_exclusive_state(exclusive):
    job = {"status": "complete", "key": (ME, "league_demo", "1qb_ppr"),
           "finished_at": time.monotonic(), "fairness_threshold": .5,
           "safety_policy": server._trade_safety_signature((False, False, False))}
    assert server._trade_job_is_fresh(job, .5, None)
    job["key"] = (ME, LEAGUE, "1qb_ppr")
    assert not server._trade_job_is_fresh(job, .5, None)


@pytest.mark.parametrize("failure", ["capture", "generation", "impressions"])
def test_selected_exclusive_failure_never_falls_back(exclusive, monkeypatch, failure):
    from backend import trade_gen_owner
    client, engine, _, service, _ = exclusive
    forbid_controls(monkeypatch, service)
    def unavailable(**kwargs):
        raise RuntimeError("synthetic unavailable")
    if failure == "capture":
        monkeypatch.setattr(server, "_owner_generation_context", unavailable)
    elif failure == "generation":
        monkeypatch.setattr(trade_gen_owner, "generate_owner_trades", unavailable)
    else:
        monkeypatch.setattr(server, "_log_deck_signal_impressions", unavailable)
    response = post(client)
    assert response.status_code == (200 if failure == "generation" else 503)
    if failure == "generation":
        assert response.json["ideas"] == []
        assert response.json["reason"] == "generation_unavailable"
    assert not rows(engine, db.deck_impressions_table)


def test_exclusive_assignment_version_is_distinct_and_not_randomized(exclusive):
    context = context_for(exclusive)
    normal = server._owner_selected_assignment(context, "fair_packages", serve=True)
    exclusive_assignment = server._owner_selected_assignment(context, "fair_packages", serve=True, exclusive=True)
    assert exclusive_assignment["model_arm"] == "owner_v1"
    assert exclusive_assignment["assignment_probability"] == 1.
    assert exclusive_assignment["version"] != normal["version"]
    other = copy.deepcopy(context)
    other["config"]["bakeoff_owner_only"] = 0.
    assert server._owner_selected_assignment(other, "fair_packages", serve=True, exclusive=True)["request_hash"] == exclusive_assignment["request_hash"]


def test_selected_returns_all_64_distinct_packages_with_real_impressions(large_exclusive, monkeypatch):
    client, engine, _, service, _ = large_exclusive
    forbid_controls(monkeypatch, service)
    ts._cfg["fair_packages_cap"] = 1.
    response = post(client, give_player_ids=["g"], receive_player_ids=[], opponent_user_id=None)
    assert response.status_code == 200, response.json
    ideas = response.json["ideas"]
    assert len(ideas) == 64
    assert len({(i["counterparty_user_id"], tuple(i["receive_player_ids"])) for i in ideas}) == 64
    assert len({i["impression_id"] for i in ideas}) == 64
    assert len(rows(engine, db.deck_impressions_table)) == 64
    assert all(i["give_player_ids"] == ["g"] and i["fairness"] == 1. for i in ideas)


def enable_real_ghost_holdout(monkeypatch):
    original = server._ghost_holdout_active
    def ghost(*args):
        # The reusable worker helper disables unrelated layers. Restore the
        # actual telemetry predicate at its first read, not a fake ghost test.
        monkeypatch.setattr(server, "_suggestion_telemetry_enabled", lambda: True)
        return original(*args)
    monkeypatch.setattr(server, "_ghost_holdout_active", ghost)
    ts._cfg["ghost_holdout_one_in"] = 1.


def test_exclusive_returns_all_64_despite_ghost_and_presentation_quotas(large_exclusive, monkeypatch):
    _, engine, _, service, _ = large_exclusive
    forbid_controls(monkeypatch, service)
    enable_real_ghost_holdout(monkeypatch)
    ts._cfg.update(bakeoff_group_size=1., bakeoff_deck_limit=1., first_session_deck_max=1.,
                   deck_max_per_target=1.)
    original = server._bakeoff.run_bakeoff
    def run(**kwargs):
        result = original(**kwargs)
        # Reactivate these real feature branches after the generic worker
        # fixture disables them; a quota merely set in config proves nothing.
        monkeypatch.setattr(server, "_deck_first_session_enabled", lambda: True)
        monkeypatch.setattr(server, "_deck_diversity_enabled", lambda: True)
        return result
    monkeypatch.setattr(server._bakeoff, "run_bakeoff", run)
    monkeypatch.setattr(server, "_apply_first_session_shaping", lambda *a, **k: pytest.fail("first-deck quota applied"))
    monkeypatch.setattr(server, "_order_deck", lambda *a, **k: pytest.fail("per-target quota applied"))
    job = worker(large_exclusive, monkeypatch)
    assert len(job["cards"]) == 64
    assert job["first_deck"] is True
    impressions = rows(engine, db.deck_impressions_table)
    assert len(impressions) == 64
    assert all(not r["is_ghost"] and r["impression_id"] for r in impressions)


def test_comparison_ghost_behavior_is_not_disabled(owner_harness, monkeypatch):
    _, engine, *_ = owner_harness
    ts._cfg.update(bakeoff_owner_only=0., bakeoff_serve_interleaved=1., bakeoff_group_size=0.)
    enable_real_ghost_holdout(monkeypatch)
    job = worker(owner_harness, monkeypatch)
    assert job["cards"] == []
    assert rows(engine, db.deck_impressions_table)
    assert all(r["is_ghost"] for r in rows(engine, db.deck_impressions_table))


@pytest.mark.parametrize("targeted", [False, True])
def test_captured_exclusive_master_hot_off_cannot_route_to_legacy(exclusive, monkeypatch, targeted):
    _, engine, _, service, _ = exclusive
    forbid_controls(monkeypatch, service)
    original = server._bakeoff.bakeoff_active
    def active(*args, **kwargs):
        ff._flags_cache["trade.bakeoff"] = False
        return original(*args, **kwargs)
    monkeypatch.setattr(server._bakeoff, "bakeoff_active", active)
    selection = {"give": ["a1"], "receive": ["b1"], "opponent": OPP} if targeted else {}
    job = worker(exclusive, monkeypatch, **selection)
    assert job["cards"]
    assert all(c["model_arm"] == "owner_v1" for c in job["cards"])
    config = json.loads(rows(engine, db.bakeoff_runs_table)[0]["config_json"])
    record = config if targeted else config["owner_request"]
    assert record["surface"] == ("targeted_deck" if targeted else "organic")
    assert record["assignment_probability"] == 1.


def test_real_incoming_like_remains_separate_from_owner_arm(exclusive, monkeypatch):
    _, engine, _, service, _ = exclusive
    forbid_controls(monkeypatch, service)
    original = server._bakeoff.run_bakeoff
    def run(**kwargs):
        result = original(**kwargs)
        monkeypatch.setattr(server, "_likes_you_enabled", lambda: True)
        return result
    monkeypatch.setattr(server._bakeoff, "run_bakeoff", run)
    monkeypatch.setattr(server, "_standing_offers_enabled", lambda: False)
    # An actual inbound hand-queued 2x2 package. The small owner constructor
    # does not generate it, so this exercises the real injection branch.
    assert db.save_trade_decision(OPP, LEAGUE, "calcq_synthetic-inbound",
        ["b1", "b2"], ["a1", "a2"], "like", impression_id="incoming-source-impression",
        queue_target_user_id=ME)
    job = worker(exclusive, monkeypatch)
    injected = [c for c in job["cards"] if c["trade_id"].startswith("likesyou_")]
    assert len(injected) == 1, {"served": [c["trade_id"] for c in job["cards"]],
                               "registered_inbound": [key for key in service._trade_cards if key.startswith("likesyou_")]}
    assert injected[0].get("model_arm") is None
    assert injected[0]["likes_you"] is True
    impression = next(r for r in rows(engine, db.deck_impressions_table)
                      if r["impression_id"] == injected[0]["impression_id"])
    assert impression["model_arm"] is None
    assert json.loads(impression["features_json"])["likes_you"] is True
    assert not json.loads(impression["features_json"]).get("owner_request")


def old_request_projection(assignment, card):
    """Exact pre-optimization algorithm retained as a parity oracle."""
    result = copy.deepcopy(assignment)
    inputs = result["input"]
    assets = set(card.give_player_ids + card.receive_player_ids)
    for key in ("user_elo", "seed_elo", "user_sources", "players"):
        inputs[key] = {pid: value for pid, value in inputs.get(key, {}).items() if pid in assets}
    inputs["members"] = [m for m in inputs["members"] if m["id"] == card.target_user_id]
    for member in inputs["members"]:
        member["elo"] = {pid: value for pid, value in member["elo"].items() if pid in assets}
    inputs["opponent_sources"] = {card.target_user_id: {
        pid: source for pid, source in inputs.get("opponent_sources", {}).get(card.target_user_id, {}).items()
        if pid in assets}}
    inputs["manager_preferences"] = {uid: prefs for uid, prefs in inputs.get("manager_preferences", {}).items()
                                      if uid in {inputs["user_id"], card.target_user_id}}
    return result


def test_request_projection_matches_prior_json_and_is_detached(exclusive):
    context = context_for(exclusive)
    assignment = server._owner_selected_assignment(context, "fair_packages", serve=True, exclusive=True)
    card = ts.TradeCard("test", LEAGUE, ME, OPP, "opp", ["a1"], ["b1"], 0., 1., 1.)
    before = copy.deepcopy(assignment)
    actual = server._owner_request_snapshot(assignment, card)
    assert actual == old_request_projection(assignment, card)
    actual["input"]["players"]["a1"]["position"] = "CHANGED"
    actual["input"]["members"][0]["roster"].clear()
    actual["input"]["config"].clear()
    actual["input"]["manager_preferences"][ME]["targets"] = ["CHANGED"]
    assert assignment == before


def test_request_projection_never_deepcopies_unrelated_boards(exclusive):
    class Unrelated:
        def __deepcopy__(self, memo):
            raise AssertionError("unrelated league data copied for one impression")
    assignment = server._owner_selected_assignment(context_for(exclusive), "fair_packages", serve=True)
    inputs = assignment["input"]
    for key in ("user_elo", "seed_elo", "user_sources", "players"):
        inputs[key]["unrelated-player"] = Unrelated()
    inputs["members"].append({"id": "unrelated-user", "elo": {"unrelated-player": Unrelated()}})
    for member in inputs["members"]:
        if member["id"] == OPP:
            member["elo"]["unrelated-player"] = Unrelated()
    inputs["manager_preferences"]["unrelated-user"] = Unrelated()
    inputs["opponent_sources"]["unrelated-user"] = Unrelated()
    card = ts.TradeCard("test", LEAGUE, ME, OPP, "opp", ["a1"], ["b1"], 0., 1., 1.)
    with pytest.raises(AssertionError, match="unrelated league data"):
        old_request_projection(assignment, card)
    result = server._owner_request_snapshot(assignment, card)
    assert set(result["input"]["user_elo"]) == {"a1", "b1"}
