"""Win Now proposal §8–9: authenticated API, durable jobs and real season calculator integration.

A minimal Flask host installs production routes. Only external league/market
reads are injected; positive calculator tests retain the real optimizer,
projection simulator, paired confirmation callback, serializer and storage.
No live network or production database is reachable from this harness.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest
from flask import Flask, jsonify
from sqlalchemy import create_engine, delete, event, insert, select, update

from backend import database as db
from backend import trade_service as pricing
from backend import win_now_api as api
from backend import win_now_service as service
from backend import win_now_store as store
from backend.season_simulator import simulate_season
from backend.tests.test_season_simulator import fixture as season_fixture

TABLES = [db.users_table, db.season_forecast_snapshots_table, db.season_projection_snapshots_table,
          db.win_now_jobs_table, db.win_now_scenarios_table, db.win_now_decisions_table]


@pytest.fixture
def harness(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine, tables=TABLES)
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id="alice", username="alice"))
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "get_league_draft_context", lambda _: {"platform": "sleeper"})
    monkeypatch.setattr(pricing, "_cfg", dict(pricing._DEFAULT_CFG))
    flags = {"outlook.season_projections": True, "trades.win_now": True,
             "outlook.championship_probabilities": False}
    monkeypatch.setattr(api, "is_enabled", lambda key: flags.get(key, False))
    monkeypatch.setattr(service, "is_enabled", lambda key: flags.get(key, False))
    events, wakeups = [], []
    monkeypatch.setattr(db, "record_event", lambda *args, **kwargs: events.append((args, kwargs)))
    monkeypatch.setattr(service, "wake_worker", lambda fetch: wakeups.append(fetch))
    state = {"session": {"user_id": "alice", "league": SimpleNamespace(league_id="league", platform="sleeper")},
             "write_allowed": True}
    app = Flask(__name__)
    app.config["TESTING"] = True
    def no_network(_):
        raise AssertionError("unexpected live/source fetch")
    api.install(app, require_session=lambda: state["session"],
                read_denial=lambda sess: (jsonify({"error": "unauthorized"}), 401) if sess is None else None,
                write_denial=lambda sess: None if state["write_allowed"] else (jsonify({"error": "read_only"}), 403),
                active_format=lambda sess: "1qb", league_user_id=lambda sess: "sleeper_alice",
                pool_provider=lambda fmt: ([], {}), fetch_json=no_network)
    yield SimpleNamespace(client=app.test_client(), engine=engine, flags=flags, state=state,
                          events=events, wakeups=wakeups, fetch=no_network)
    engine.dispose()


def build_world(monkeypatch):
    league, forecasts = season_fixture(sigma=0)
    league.update(league_id="league", roster_capacity=2, lineup_slots=[["WR"]], trades_allowed=True)
    baseline = simulate_season(league, forecasts, n_sims=20)
    now = datetime.now(timezone.utc)
    meta = {"snapshot_id": "synthetic", "forecast_snapshot_id": forecasts["snapshot_id"],
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "league_revision": store.identity(league), "championship_available": False}
    bundle = {"league": league, "forecasts": forecasts, "baseline": baseline,
              "n_sims": 20, "buyer_roster_id": 1, "meta": meta}
    assets = {pid: {"id": pid, "name": pid, "owner_roster_id": t["roster_id"],
                    "position": "WR", "is_pick": False, "market_value": 1000, "tradeable": True}
              for t in league["teams"] for pid in t["player_ids"]}
    assets["p1"]["market_value"] = 1200
    assets["b1"]["market_value"] = 3000  # Budget is % of full baseline dynasty holdings.
    context = {"buyer_roster_id": 1, "assets": assets, "league": league,
               "buyer_values": {pid: a["market_value"] for pid, a in assets.items()},
               "partner_values": {6: {"p1": 1500, "p6": 900}},
               "partner_evidence": {6: {"basis": "personal", "confidence": 1, "coverage": 1,
                                          "intent": "rebuilder", "declared": True}},
               "pricing_config": dict(pricing._DEFAULT_CFG), "championship_supported": False}
    def current_context(actor, bundle, params, fetch):
        inputs = {k: v for k, v in context.items() if k != "valuation_revision"}
        return {**deepcopy(context), **params, "valuation_revision": store.identity(inputs)}
    context["valuation_revision"] = current_context({}, bundle, {}, None)["valuation_revision"]
    bundle["meta"].update(valuation_revision=context["valuation_revision"], params=service.validate_params(evaluate_body()))
    monkeypatch.setattr(service, "load_bundle", lambda actor, fetch: deepcopy(bundle))
    monkeypatch.setattr(service, "build_context", current_context)
    monkeypatch.setattr(service, "load_league", lambda actor, fetch: (deepcopy(league), 1, {}))
    return bundle, context


def assert_title_hidden(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "championship_probability":
                assert item is None
            else:
                assert_title_hidden(item)
    elif isinstance(value, list):
        for item in value:
            assert_title_hidden(item)


def evaluate_body(**updates):
    return {"league_id": "league", "partner_roster_id": 6, "give_ids": ["p1"], "receive_ids": ["p6"],
            "objective": "wins", "max_dynasty_spend_pct": 10, "min_fairness": .75, **updates}


def test_projection_route_requires_session_and_current_league(harness, monkeypatch):
    harness.state["session"] = None
    assert harness.client.get("/api/league/season-projections").status_code == 401
    harness.state["session"] = {"user_id": "alice", "league": SimpleNamespace(league_id="league")}
    response = harness.client.get("/api/league/season-projections?league_id=other")
    assert response.status_code == 403
    harness.flags["outlook.season_projections"] = False
    assert harness.client.get("/api/league/season-projections").status_code == 404


def test_write_denial_blocks_search_before_persisting_work(harness):
    harness.state["write_allowed"] = False
    response = harness.client.post("/api/win-now/search", json=evaluate_body())
    assert response.status_code == 403
    assert store.pending_jobs() == [] and harness.events == []


def test_source_unavailable_returns_explicit_reason_not_plausible_odds(harness, monkeypatch):
    def missing(*_):
        raise service.Unavailable("missing_forecast_week:17")
    monkeypatch.setattr(service, "load_bundle", missing)
    response = harness.client.get("/api/league/season-projections")
    assert response.status_code == 200
    assert response.json["status"] == "unavailable"
    assert response.json["reason"] == "missing_forecast_week:17"
    assert "teams" not in response.json


def test_season_page_scrubs_title_metrics_through_nested_payload(harness, monkeypatch):
    build_world(monkeypatch)
    response = harness.client.get("/api/league/season-projections")
    assert response.status_code == 200 and response.json["status"] == "available"
    assert len(response.json["teams"]) == 6
    assert_title_hidden(response.json)
    assert response.json["teams"][0]["expected_wins"] >= 1
    assert "market_value" not in json.dumps(response.json["assets"])


@pytest.mark.parametrize("patch,reason", [({"partner_roster_id": True}, "invalid_partner_roster_id"),
    ({"give_ids": "p1"}, "invalid_give_ids"), ({"give_ids": [1]}, "invalid_give_ids"),
    ({"receive_ids": [""]}, "invalid_receive_ids"), ({"max_dynasty_spend_pct": float("inf")}, "invalid_max_dynasty_spend_pct"),
    ({"objective": "made-up"}, "invalid_objective")])
def test_invalid_inputs_rejected_before_forecast_or_trade_work(harness, patch, reason):
    response = harness.client.post("/api/win-now/evaluate", json=evaluate_body(**patch))
    assert response.status_code == 400 and response.json["error"] == reason


def test_championship_kill_switch_and_trade_kill_switch_fail_closed(harness):
    response = harness.client.post("/api/win-now/evaluate", json=evaluate_body(objective="championship"))
    assert response.json["reason"] == "championship_not_validated"
    harness.flags["trades.win_now"] = False
    response = harness.client.post("/api/win-now/evaluate", json=evaluate_body())
    assert response.json["reason"] == "feature_disabled"


def test_real_calculator_optimizer_simulator_confirmation_and_storage(harness, monkeypatch):
    build_world(monkeypatch)
    response = harness.client.post("/api/win-now/evaluate", json=evaluate_body())
    assert response.status_code == 200
    assert response.json["eligible"], response.json
    scenario = response.json["scenario"]
    assert scenario["give"][0]["id"] == "p1" and scenario["receive"][0]["id"] == "p6"
    assert scenario["season"]["buyer"]["delta"]["next_three_week_expected_wins"] == 3
    assert scenario["season"]["partner"]["delta"]["expected_remaining_wins"] == -3
    assert_title_hidden(response.json)
    assert store.get_scenario(scenario["scenario_id"], "alice") is not None
    assert store.get_scenario(scenario["scenario_id"], "bob") is None


def test_unknown_asset_rejected_with_reason_and_no_scenario(harness, monkeypatch):
    build_world(monkeypatch)
    response = harness.client.post("/api/win-now/evaluate", json=evaluate_body(give_ids=["not-owned"]))
    assert response.status_code == 200 and not response.json["eligible"]
    assert "invalid_asset_or_partner" in response.json["rejection_reasons"]
    assert response.json["scenario"] is None


def scenario(harness, *, user="alice", league="league", expired=False, eligible=True, meta=None):
    expires = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 10)
    return store.save_scenario(user, league, "wins", {"buyer_roster_id": 1, "partner_roster_id": 2,
                 "give": [{"id": "p1"}], "receive": [{"id": "p2"}], "eligible": eligible},
                 {**(meta or {}), "snapshot_id": "s", "expires_at": expires.isoformat()})


def test_decision_is_viewer_scoped_and_never_trains_dynasty(harness, monkeypatch):
    bundle, _ = build_world(monkeypatch)
    row = scenario(harness, meta=bundle["meta"])
    foreign = scenario(harness, user="bob", meta=bundle["meta"])
    writes = []
    def inspect(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)
    event.listen(harness.engine, "before_cursor_execute", inspect)
    assert harness.client.post(f"/api/win-now/scenarios/{foreign['scenario_id']}/decision", json={"decision": "like"}).status_code == 404
    for decision in ["like", "pass"]:
        response = harness.client.post(f"/api/win-now/scenarios/{row['scenario_id']}/decision", json={"decision": decision})
        assert response.json == {"ok": True}
    assert writes and all("win_now_decisions" in statement for statement in writes)
    assert harness.events == []
    with harness.engine.connect() as conn:
        decisions = conn.execute(select(db.win_now_decisions_table)).mappings().all()
    assert len(decisions) == 1 and decisions[0]["decision"] == "pass"


@pytest.mark.parametrize("kwargs,code,reason", [({"expired": True}, 200, "stale_forecast"),
    ({"eligible": False}, 400, "ineligible_scenario"), ({"league": "other"}, 404, "not_found")])
def test_old_ineligible_or_other_league_decision_is_blocked(harness, kwargs, code, reason):
    row = scenario(harness, **kwargs)
    response = harness.client.post(f"/api/win-now/scenarios/{row['scenario_id']}/decision", json={"decision": "like"})
    assert response.status_code == code
    assert response.json.get("reason", response.json.get("error")) == reason


def test_search_persists_viewer_objective_and_bounds_pending_work(harness):
    response = harness.client.post("/api/win-now/search", json=evaluate_body(objective="playoffs"))
    assert response.status_code == 202
    job_id = response.json["job_id"]
    inputs = json.loads(store.get_job(job_id, "alice")["input_json"])
    assert inputs["actor"]["league_user_id"] == "sleeper_alice"
    assert inputs["params"]["objective"] == "playoffs"
    assert harness.events[0][1]["props"]["platform"] == "web"
    assert harness.wakeups
    assert harness.client.post("/api/win-now/search", json=evaluate_body()).status_code == 202
    assert harness.client.post("/api/win-now/search", json=evaluate_body()).status_code == 429
    foreign = store.create_job("bob", "league", {})
    assert harness.client.get(f"/api/win-now/jobs/{foreign['job_id']}").status_code == 404
    other = store.create_job("alice", "other", {})
    assert harness.client.get(f"/api/win-now/jobs/{other['job_id']}").status_code == 404


def test_durable_worker_resumes_queued_input_and_sanitizes_failures(harness, monkeypatch):
    job = store.create_job("alice", "league", {"actor": {"user_id": "alice"}, "params": {"objective": "wins"}})
    assert store.claim_job(job["job_id"])
    assert store.recover_interrupted_jobs() == 1
    seen = []
    def run(actor, params, fetch, *, job_id=None):
        seen.append((actor, params))
        return {"meta": {"expires_at": job["expires_at"]}, "trades": []}
    monkeypatch.setattr(service, "run_search", run)
    service.process_pending(harness.fetch)
    assert seen == [({"user_id": "alice"}, {"objective": "wins"})]
    assert store.get_job(job["job_id"], "alice")["status"] == "complete"
    failed = store.create_job("alice", "league", {"actor": {}, "params": {}})
    def crash(*_, **_kwargs):
        raise RuntimeError("private-token-like-detail")
    monkeypatch.setattr(service, "run_search", crash)
    service.process_pending(harness.fetch)
    response = harness.client.get(f"/api/win-now/jobs/{failed['job_id']}")
    assert response.json["status"] == "failed"
    assert response.json["reason"] == "generation_failed"
    assert "private-token" not in response.get_data(as_text=True)


def test_completed_job_revalidates_actor_and_current_roster_before_serving(harness, monkeypatch):
    bundle, _ = build_world(monkeypatch)
    response = harness.client.post("/api/win-now/search", json=evaluate_body())
    job_id = response.json["job_id"]
    result = {"meta": bundle["meta"], "trades": [], "baseline": bundle["baseline"], "buyer_roster_id": 1}
    store.finish_job(job_id, result=result)
    response = harness.client.get(f"/api/win-now/jobs/{job_id}")
    assert response.status_code == 200 and response.json["status"] == "complete"
    assert_title_hidden(response.json)
    league = deepcopy(bundle["league"])
    league["teams"][0]["points_for"] += 1
    monkeypatch.setattr(service, "load_league", lambda *_: (league, 1, {}))
    response = harness.client.get(f"/api/win-now/jobs/{job_id}")
    assert response.json["reason"] == "league_inputs_changed"
    harness.state["session"]["players"] = [SimpleNamespace(id="new", name="New", position="WR")]
    response = harness.client.get(f"/api/win-now/jobs/{job_id}")
    assert response.json["reason"] == "ranking_inputs_changed"


def league_transport():
    """Raw Sleeper-style facts; intentionally no production transport fallback."""
    league, _ = season_fixture(sigma=0)
    base = "https://api.sleeper.app/v1/league/league"
    raw = {base: {"season": "2026", "status": "in_season", "scoring_settings": {"rec": 1},
                  "roster_positions": ["WR", "BN"], "settings": {"playoff_week_start": 7, "playoff_teams": 4}},
           base + "/users": [{"user_id": t["user_id"], "display_name": t["username"]} for t in league["teams"]],
           base + "/rosters": [{"roster_id": t["roster_id"], "owner_id": t["user_id"],
                       "players": t["player_ids"], "starters": t["starters"],
                       "settings": {"wins": t["wins"], "losses": t["losses"], "ties": 0, "fpts": 30}}
                      for t in league["teams"]]}
    for week, pairs in league["schedule"].items():
        raw[base + f"/matchups/{week}"] = [{"roster_id": rid, "matchup_id": index, "points": 0}
                                           for index, pair in enumerate(pairs, 1) for rid in pair]
    actor = {"league_id": "league", "platform": "sleeper", "league_user_id": "user1", "user_id": "alice"}
    return actor, raw, lambda url: deepcopy(raw[url])


def test_real_league_normalizer_uses_official_records_not_nonzero_points(harness, monkeypatch):
    monkeypatch.setattr(service, "_cache", {})
    actor, raw, fetch = league_transport()
    league, buyer, _ = service.load_league(actor, fetch)
    assert league["completed_weeks"] == 3 and buyer == 1
    assert set(league["schedule"]) == {4, 5, 6}
    assert league["teams"][0]["points_for"] == 30
    monkeypatch.setattr(service, "_cache", {})
    raw["https://api.sleeper.app/v1/league/league/matchups/4"][0]["points"] = 0.1
    with pytest.raises(service.Unavailable, match="live"):
        service.load_league(actor, fetch)
    monkeypatch.setattr(service, "_cache", {})
    raw["https://api.sleeper.app/v1/league/league/rosters"][0]["settings"]["wins"] = 2
    with pytest.raises(service.Unavailable, match="standings"):
        service.load_league(actor, fetch)


def test_source_import_fresh_bundle_persists_frozen_evidence(harness, monkeypatch, tmp_path):
    league, forecasts = season_fixture(sigma=0)
    league["league_id"] = "league"
    forecasts["earliest_game_date"] = "2026-09-06"
    path = tmp_path / "provider.json"
    path.write_text(json.dumps(forecasts))
    monkeypatch.setenv("FTF_SEASON_FORECAST_FILE", str(path))
    monkeypatch.setenv("FTF_SEASON_SIM_COUNT", "256")
    monkeypatch.setattr(service, "now_utc", lambda: datetime(2026, 9, 4, 18, tzinfo=timezone.utc))
    monkeypatch.setattr(service, "load_league", lambda *_: (league, 1, {}))
    bundle = service.load_bundle({"user_id": "alice", "league_id": "league"}, harness.fetch)
    assert bundle["baseline"]["meta"]["supported"]
    assert bundle["forecasts"]["captured_at"] == forecasts["captured_at"]
    with harness.engine.connect() as conn:
        frozen = conn.execute(select(db.season_forecast_snapshots_table)).mappings().all()
        projections = conn.execute(select(db.season_projection_snapshots_table)).mappings().all()
    assert len(frozen) == len(projections) == 1
    assert json.loads(frozen[0]["payload_json"])["captured_at"] == forecasts["captured_at"]
    # Loading an old normalized file cannot freshen its capture timestamp.
    monkeypatch.setattr(service, "now_utc", lambda: datetime(2026, 9, 4, 19, tzinfo=timezone.utc))
    with pytest.raises(service.Unavailable, match="stale"):
        service.load_bundle({"user_id": "alice", "league_id": "league"}, harness.fetch)


def test_global_feed_week_start_blocks_even_when_rostered_players_start_later(harness, monkeypatch):
    league, forecasts = season_fixture(sigma=0)
    forecasts["earliest_game_date"] = "2026-09-03"
    for row in forecasts["forecasts"]:
        row["game_date"] = "2026-09-06"
    monkeypatch.setattr(service, "now_utc", lambda: datetime(2026, 9, 4, 18, tzinfo=timezone.utc))
    monkeypatch.setattr(service, "load_league", lambda *_: (league, 1, {}))
    monkeypatch.setattr(service, "_forecast_batch", lambda *_: forecasts)
    with pytest.raises(service.Unavailable, match="live"):
        service.load_bundle({"user_id": "alice", "league_id": "league"}, harness.fetch)


def test_expired_job_cannot_resume_or_expose_cached_cards(harness, monkeypatch):
    job = store.create_job("alice", "league", {"actor": {}, "params": {}})
    with harness.engine.begin() as conn:
        conn.execute(update(db.win_now_jobs_table).where(db.win_now_jobs_table.c.job_id == job["job_id"])
                     .values(expires_at="2020-01-01T00:00:00Z"))
    def forbidden(*_):
        raise AssertionError("expired work must never simulate")
    monkeypatch.setattr(service, "run_search", forbidden)
    service.process_pending(harness.fetch)
    assert store.get_job(job["job_id"], "alice")["reason"] == "job_expired"
    response = harness.client.get(f"/api/win-now/jobs/{job['job_id']}")
    assert response.json["reason"] == "stale_forecast"
    assert "result" not in response.json


def test_real_search_queue_worker_optimizer_and_viewer_poll(harness, monkeypatch):
    build_world(monkeypatch)
    submitted = harness.client.post("/api/win-now/search", json=evaluate_body())
    assert submitted.status_code == 202
    job_id = submitted.json["job_id"]
    service.process_pending(harness.fetch)
    response = harness.client.get(f"/api/win-now/jobs/{job_id}")
    assert response.status_code == 200 and response.json["status"] == "complete", response.json
    result = response.json["result"]
    assert any(row["give_ids"] == ["p1"] and row["receive_ids"] == ["p6"] for row in result["trades"]), result
    assert all(row["eligible"] for row in result["trades"])
    assert_title_hidden(result)
    assert result["meta"]["objective"] == "wins"
    assert result["baseline"]["teams"][0]["expected_wins"] >= 1


@pytest.mark.parametrize("route", ["poll", "decision"])
@pytest.mark.parametrize("changed_input", ["buyer_values", "partner_values", "pick_owner", "protected_preference"])
def test_stale_valuation_or_pick_revision_blocks_poll_and_decision(harness, monkeypatch, route, changed_input):
    bundle, context = build_world(monkeypatch)
    context["assets"]["future_pick"] = {"id": "future_pick", "name": "2027 first", "is_pick": True,
                                        "position": "PICK", "owner_roster_id": 1, "market_value": 800}
    context["buyer_values"]["future_pick"] = 800
    current = service.build_context({}, bundle, service.validate_params(evaluate_body()), harness.fetch)
    bundle["meta"]["valuation_revision"] = current["valuation_revision"]
    if route == "poll":
        job_id = harness.client.post("/api/win-now/search", json=evaluate_body()).json["job_id"]
        store.finish_job(job_id, result={"meta": bundle["meta"], "trades": [],
                         "baseline": bundle["baseline"], "buyer_roster_id": 1})
        request_current = lambda: harness.client.get(f"/api/win-now/jobs/{job_id}")
        assert request_current().json["status"] == "complete"
    else:
        row = scenario(harness, meta=bundle["meta"])
        request_current = lambda: harness.client.post(f"/api/win-now/scenarios/{row['scenario_id']}/decision", json={"decision": "like"})
        assert request_current().json == {"ok": True}
    if changed_input == "buyer_values":
        context["buyer_values"]["p1"] += 1
    elif changed_input == "partner_values":
        context["partner_values"][6]["p1"] += 1
    elif changed_input == "pick_owner":
        context["assets"]["future_pick"]["owner_roster_id"] = 6
    else:
        context["assets"]["p6"]["locked"] = True
    response = request_current()
    assert response.status_code == 200
    assert response.json["reason"] == "valuation_inputs_changed"
    assert "result" not in response.json and "ok" not in response.json


def test_decision_rechecks_current_league_revision_before_writing(harness, monkeypatch):
    bundle, _ = build_world(monkeypatch)
    row = scenario(harness, meta=bundle["meta"])
    changed = deepcopy(bundle["league"])
    changed["teams"][0]["player_ids"].remove("p1")
    monkeypatch.setattr(service, "load_league", lambda *_: (changed, 1, {}))
    response = harness.client.post(f"/api/win-now/scenarios/{row['scenario_id']}/decision", json={"decision": "like"})
    assert response.json["reason"] == "league_inputs_changed"
    with harness.engine.connect() as conn:
        assert conn.execute(select(db.win_now_decisions_table)).first() is None


def test_scenarios_persist_hashes_and_package_evidence_without_raw_partner_boards(harness, monkeypatch):
    build_world(monkeypatch)
    response = harness.client.post("/api/win-now/evaluate", json=evaluate_body())
    assert response.json["eligible"]
    scenario_id = response.json["scenario"]["scenario_id"]
    frozen = json.loads(store.get_scenario(scenario_id, "alice")["payload_json"])
    assert len(frozen["meta"]["valuation_revision"]) == 64
    assert frozen["meta"]["params"]["objective"] == "wins"
    forbidden = {"partner_values", "partner_boards", "elo_ratings", "rank_revisions", "raw_rankings", "personal_values", "context"}
    def inspect(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for item in value.values():
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
    inspect(frozen)
    assert frozen["valuation"]["partner_gain_fraction"] > 0


def test_real_context_revision_changes_when_authoritative_pick_ownership_changes(harness, monkeypatch):
    from backend import pick_values
    real_builder = service.build_context
    bundle, _ = build_world(monkeypatch)
    for team in bundle["league"]["teams"]:
        team["all_player_ids"] = list(team["player_ids"])
        team["inactive_ids"] = []
    db.metadata.create_all(harness.engine, tables=[db.member_rankings_table])
    monkeypatch.setattr(db, "load_draft_picks", lambda _, **__: [{"pick_id": "pick:2027:1:1", "season": 2027,
        "round": 1, "original_roster_id": "1", "owner_user_id": "user1", "original_username": "Team 1"}])
    monkeypatch.setattr(db, "load_league_preferences_bulk", lambda *_: {})
    monkeypatch.setattr(db, "load_asset_preferences_bulk", lambda *_: {})
    monkeypatch.setattr(db, "load_member_rankings", lambda *_: {})
    monkeypatch.setattr(pick_values, "priced_pool_value", lambda *args, **kwargs: 1000)
    monkeypatch.setattr(service, "_cache", {})
    ids = [pid for team in bundle["league"]["teams"] for pid in team["player_ids"]]
    actor = {"user_id": "alice", "league_id": "league", "scoring_format": "1qb",
             "players": {pid: {"name": pid, "position": "WR"} for pid in ids},
             "market_values": dict.fromkeys(ids, 1000), "personal_values": {}, "confidence": {}}
    transfers = []
    def fetch(url):
        assert url.endswith("/traded_picks")
        return deepcopy(transfers)
    params = service.validate_params(evaluate_body())
    before = real_builder(actor, bundle, params, fetch)
    assert before["assets"]["pick:2027:1:1"]["owner_roster_id"] == 1
    transfers.append({"season": "2027", "round": 1, "roster_id": 1, "owner_id": 6})
    monkeypatch.setattr(service, "_cache", {})
    after = real_builder(actor, bundle, params, fetch)
    assert "pick:2027:1:1" not in after["assets"]  # Stale local ownership is ineligible.
    assert before["valuation_revision"] != after["valuation_revision"]


def test_offline_import_without_game_start_evidence_cannot_be_served(harness, monkeypatch, tmp_path):
    league, forecasts = season_fixture(sigma=0)
    assert not forecasts.get("earliest_game_date") and not forecasts.get("earliest_kickoff_at")
    path = tmp_path / "offline-only.json"
    path.write_text(json.dumps(forecasts))
    monkeypatch.setenv("FTF_SEASON_FORECAST_FILE", str(path))
    monkeypatch.setattr(service, "now_utc", lambda: datetime(2026, 9, 4, 18, tzinfo=timezone.utc))
    monkeypatch.setattr(service, "load_league", lambda *_: (league, 1, {}))
    with pytest.raises(service.Unavailable, match="game_start_cutoff_unavailable"):
        service.load_bundle({"user_id": "alice", "league_id": "league"}, harness.fetch)
    with harness.engine.connect() as conn:
        assert conn.execute(select(db.season_projection_snapshots_table)).first() is None


def test_calculator_crossing_cutoff_during_simulation_does_not_persist_or_serve(harness, monkeypatch):
    bundle, _ = build_world(monkeypatch)
    real_callback = service.evaluate_callback
    def crossing_callback(*args):
        callback, baseline = real_callback(*args)
        def evaluate(*params):
            result = callback(*params)
            expired = service.timestamp(bundle["meta"]["expires_at"]) + timedelta(seconds=1)
            monkeypatch.setattr(service, "now_utc", lambda: expired)
            return result
        return evaluate, baseline
    monkeypatch.setattr(service, "evaluate_callback", crossing_callback)
    response = harness.client.post("/api/win-now/evaluate", json=evaluate_body())
    assert response.json["reason"] == "stale_forecasts"
    assert "scenario" not in response.json
    with harness.engine.connect() as conn:
        assert conn.execute(select(db.win_now_scenarios_table)).first() is None


@pytest.mark.parametrize("operation", ["search", "evaluate", "decision"])
def test_stale_session_cannot_recreate_deleted_account_evidence(harness, monkeypatch, operation):
    bundle, _ = build_world(monkeypatch)
    row = scenario(harness, meta=bundle["meta"])
    with harness.engine.begin() as conn:
        conn.execute(delete(db.users_table).where(db.users_table.c.sleeper_user_id == "alice"))
    if operation == "decision":
        response = harness.client.post(f"/api/win-now/scenarios/{row['scenario_id']}/decision", json={"decision": "like"})
    else:
        response = harness.client.post(f"/api/win-now/{operation}", json=evaluate_body())
    assert response.status_code == 400
    assert response.json["error"] == "account_no_longer_available"
    with harness.engine.connect() as conn:
        assert conn.execute(select(db.win_now_jobs_table)).first() is None
        assert conn.execute(select(db.win_now_decisions_table)).first() is None
        assert len(conn.execute(select(db.win_now_scenarios_table)).all()) == 1
