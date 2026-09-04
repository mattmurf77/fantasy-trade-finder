"""Win Now service integration: settled facts, exact optimizer contracts, privacy.

Exercises Sleeper adapters with frozen HTTP fixtures, isolated ranking reads,
paired callback integration, and public result serialization. No live API or
production database access; the positive search invokes the actual optimizer.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math
from types import SimpleNamespace

from flask import Flask
import pytest
from sqlalchemy import create_engine

from backend import database as db
from backend import season_simulator as simulator
from backend import trade_service as pricing
from backend import win_now_service as service
from backend.win_now_optimizer import evaluate_candidate


NOW = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    monkeypatch.setattr(service, "_cache", {})
    monkeypatch.setattr(service, "now_utc", lambda: NOW)
    monkeypatch.setattr(service, "is_enabled", lambda _: False)
    monkeypatch.setattr(pricing, "_cfg", dict(pricing._DEFAULT_CFG))


def source_fixture(median=False):
    meta = {"season": "2026", "status": "in_season", "scoring_settings": {"rec": 1},
            "roster_positions": ["WR", "BN"],
            "settings": {"start_week": 1, "playoff_week_start": 15, "playoff_teams": 4,
                         "league_average_match": int(median), "trade_deadline": 10}}
    rosters = [{"roster_id": rid, "owner_id": f"u{rid}", "players": [f"p{rid}", f"d{rid}"],
                "starters": [f"p{rid}"], "reserve": [], "taxi": [],
                "settings": {"wins": 2 if median else 1, "losses": 2 if median else 1, "ties": 0,
                             "fpts": 222, "fpts_decimal": 12}} for rid in range(1, 5)]
    users = [{"user_id": f"u{rid}", "display_name": f"Manager {rid}"} for rid in range(1, 5)]
    matchups = {week: [{"roster_id": rid, "matchup_id": (rid + 1) // 2, "points": 0}
                       for rid in range(1, 5)] for week in range(3, 15)}
    calls = []
    def fetch(url):
        calls.append(url)
        if "/matchups/" in url:
            return deepcopy(matchups[int(url.rsplit("/", 1)[1])])
        if url.endswith("/rosters"):
            return deepcopy(rosters)
        if url.endswith("/users"):
            return deepcopy(users)
        if url.endswith("/traded_picks"):
            return []
        return deepcopy(meta)
    actor = {"platform": "sleeper", "league_id": "league", "league_user_id": "u1", "user_id": "account1",
             "scoring_format": "1qb_ppr", "players": {}, "market_values": {}, "personal_values": {}, "confidence": {}}
    for rid in range(1, 5):
        for pid, value in ((f"p{rid}", 1050 if rid == 1 else 1000), (f"d{rid}", 600)):
            actor["players"][pid] = {"name": pid, "position": "WR"}
            actor["market_values"][pid] = actor["personal_values"][pid] = value
            actor["confidence"][pid] = 0.5
    return actor, meta, rosters, matchups, fetch, calls


@pytest.mark.parametrize("median", [False, True])
def test_settled_record_checkpoint_counts_median_decisions_once(median):
    actor, _, _, _, fetch, calls = source_fixture(median)
    league, buyer, _ = service.load_league(actor, fetch)
    assert league["completed_weeks"] == 2
    assert league["median_match"] is median
    assert min(league["schedule"]) == 3
    assert buyer == 1
    assert league["teams"][0]["points_for"] == pytest.approx(222.12)
    assert not any(url.endswith("/matchups/2") for url in calls)


@pytest.mark.parametrize("mutation", [
    lambda rosters: rosters[0]["settings"].update(wins=3),
    lambda rosters: rosters[0]["settings"].update(wins=4),
])
def test_partial_or_disagreeing_median_records_never_advance_checkpoint(mutation):
    actor, _, rosters, _, fetch, _ = source_fixture(median=True)
    mutation(rosters)
    with pytest.raises(service.Unavailable, match="standings_not_final"):
        service.load_league(actor, fetch)


@pytest.mark.parametrize("points", [{"points": 0.1}, {"points": 0, "custom_points": 0.1}])
def test_nonzero_thursday_matchup_blocks_before_official_record_settles(points):
    actor, _, _, matchups, fetch, calls = source_fixture()
    matchups[3][0].update(points)
    with pytest.raises(service.Unavailable, match="live_week_unsupported"):
        service.load_league(actor, fetch)
    assert not any(url.endswith("/matchups/4") for url in calls)


def test_duplicate_live_ownership_and_nonmember_are_rejected():
    actor, _, rosters, _, fetch, _ = source_fixture()
    rosters[1]["players"].append("p1")
    with pytest.raises(service.Unavailable, match="ambiguous_roster_ownership"):
        service.load_league(actor, fetch)
    service._cache.clear()
    rosters[1]["players"].remove("p1")
    actor["league_user_id"] = "not-a-member"
    with pytest.raises(service.Unavailable, match="league_membership_unavailable"):
        service.load_league(actor, fetch)


def test_deadline_blocks_trades_while_season_projection_remains_possible():
    actor, meta, _, _, fetch, _ = source_fixture()
    meta["settings"]["trade_deadline"] = 2
    league, _, _ = service.load_league(actor, fetch)
    assert league["trades_allowed"] is False
    assert league["completed_weeks"] == 2


def forecast_bundle_seams(monkeypatch, *, kickoff=None, captured=None):
    actor, _, _, _, fetch, _ = source_fixture()
    league, buyer, meta = service.load_league(actor, fetch)
    snapshot = {"supported": True, "season": "2026", "snapshot_id": "forecast-snapshot", "provider": "fixture",
                "captured_at": (captured or NOW).isoformat(), "forecasts": [
                    {"player_id": "p1", "week": 3, "kickoff_at": (kickoff or NOW + timedelta(days=3)).isoformat()}]}
    monkeypatch.setattr(service, "load_league", lambda *_: (deepcopy(league), buyer, deepcopy(meta)))
    monkeypatch.setattr(service, "_forecast_batch", lambda *_: deepcopy(snapshot))
    simulations = []
    def simulate(*args, **kwargs):
        simulations.append(kwargs)
        return {"meta": {"supported": True}, "teams": []}
    monkeypatch.setattr(simulator, "simulate_season", simulate)
    monkeypatch.setattr(service.store, "save_forecasts", lambda *_: None)
    monkeypatch.setattr(service.store, "save_projection", lambda *_: None)
    return actor, fetch, snapshot, simulations


def test_started_source_kickoff_refuses_snapshot_before_simulating(monkeypatch):
    actor, fetch, _, simulations = forecast_bundle_seams(monkeypatch, kickoff=NOW - timedelta(seconds=1))
    with pytest.raises(service.Unavailable, match="live_week_unsupported"):
        service.load_bundle(actor, fetch)
    assert simulations == []


def test_upcoming_kickoff_caps_snapshot_expiry(monkeypatch):
    cutoff = NOW + timedelta(seconds=30)
    actor, fetch, _, _ = forecast_bundle_seams(monkeypatch, kickoff=cutoff)
    bundle = service.load_bundle(actor, fetch)
    assert service.timestamp(bundle["meta"]["expires_at"]) == cutoff


def test_stale_forecast_never_produces_new_baseline(monkeypatch):
    actor, fetch, _, simulations = forecast_bundle_seams(monkeypatch, captured=NOW - timedelta(minutes=20))
    with pytest.raises(service.Unavailable, match="stale_forecasts"):
        service.load_bundle(actor, fetch)
    assert simulations == []


def test_fourteen_minute_old_forecast_has_only_one_minute_remaining(monkeypatch):
    actor, fetch, _, _ = forecast_bundle_seams(monkeypatch, captured=NOW - timedelta(minutes=14))
    bundle = service.load_bundle(actor, fetch)
    assert service.timestamp(bundle["meta"]["expires_at"]) == NOW + timedelta(minutes=1)


def test_unrelated_import_players_cannot_inflate_roster_coverage(monkeypatch):
    actor, fetch, snapshot, _ = forecast_bundle_seams(monkeypatch)
    snapshot["weeks"] = list(range(3, 17))
    snapshot["forecasts"] = [dict(snapshot["forecasts"][0], week=week, availability=1)
                             for week in snapshot["weeks"]]
    snapshot["forecasts"] += [{"player_id": f"unrostered-{i}", "week": 3, "availability": 1}
                               for i in range(100)]
    bundle = service.load_bundle(actor, fetch)
    assert bundle["meta"]["coverage"] == pytest.approx(1 / 8)


def test_best_ball_is_rejected_before_managed_lineup_model_runs():
    actor, meta, _, _, fetch, _ = source_fixture()
    meta["settings"]["best_ball"] = 1
    with pytest.raises(service.Unavailable, match="best_ball_unsupported"):
        service.load_league(actor, fetch)


@pytest.mark.parametrize("field,value", [
    ("earliest_game_date", "2026-09-24"),
    ("earliest_game_dates", {"3": "2026-09-24", "4": "2026-10-01"}),
    ("earliest_kickoff_at", "2026-09-24T11:59:59+00:00"),
])
def test_unrostered_thursday_game_still_blocks_whole_league_snapshot(monkeypatch, field, value):
    # Every rostered player's feed row says Sunday; a globally observed
    # Thursday game still makes this checkpoint unsupported for all teams.
    actor, fetch, snapshot, simulations = forecast_bundle_seams(monkeypatch, kickoff=NOW + timedelta(days=3))
    snapshot[field] = value
    with pytest.raises(service.Unavailable, match="live_week_unsupported"):
        service.load_bundle(actor, fetch)
    assert simulations == []


@pytest.fixture
def context_inputs(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.member_rankings_table.create(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "load_draft_picks", lambda *_, **__: [])
    monkeypatch.setattr(db, "load_league_preferences_bulk", lambda *_: {"u2": {"team_outlook": "rebuilder"}})
    monkeypatch.setattr(db, "load_asset_preferences_bulk", lambda *_: {})
    monkeypatch.setattr(db, "load_member_rankings", lambda *_: {})
    actor, meta, rosters, _, fetch, _ = source_fixture()
    league, buyer, _ = service.load_league(actor, fetch)
    bundle = {"league": league, "buyer_roster_id": buyer, "baseline": {"teams": []},
              "meta": {"championship_available": False, "snapshot_id": "projection-snapshot"}, "league_meta": meta}
    params = service.validate_params({"max_dynasty_spend_pct": 10})
    yield actor, bundle, params, fetch, rosters
    engine.dispose()


def test_context_keeps_cardinal_confidence_and_protected_ownership(context_inputs):
    actor, bundle, params, fetch, _ = context_inputs
    actor["personal_values"]["p1"] = 1500
    params["protected_ids"] = ["p1"]
    frozen = deepcopy(bundle)
    context = service.build_context(actor, bundle, params, fetch)
    assert context["buyer_evidence"]["assets"]["p1"]["confidence"] == 0.5
    row = evaluate_candidate(context, 2, ["p1"], ["p2"], lambda *_: pytest.fail("protected trade simulated"))
    assert "protected_asset" in row["rejection_reasons"]
    assert bundle == frozen
    params["protected_ids"] = ["p2"]
    with pytest.raises(ValueError, match="invalid_protected_asset"):
        service.build_context(actor, bundle, params, fetch)


def test_live_pick_overlay_cannot_assign_stale_database_ownership(context_inputs, monkeypatch):
    actor, bundle, params, fetch, _ = context_inputs
    monkeypatch.setattr(db, "load_draft_picks", lambda *_, **__: [{"season": "2027", "round": 1,
                         "original_roster_id": "1", "owner_user_id": "u1", "pick_id": "owned:first"}])
    def updated_fetch(url):
        return [{"season": "2027", "round": 1, "roster_id": 1, "owner_id": 2}] if url.endswith("/traded_picks") else fetch(url)
    context = service.build_context(actor, bundle, params, updated_fetch)
    assert "owned:first" not in context["assets"]


def test_inactive_reserve_cannot_cover_slot_after_trade(context_inputs):
    actor, bundle, params, fetch, _ = context_inputs
    buyer = bundle["league"]["teams"][0]
    buyer["inactive_ids"] = ["d1"]
    buyer["player_ids"] = ["p1"]
    actor["players"]["p2"]["position"] = "RB"
    context = service.build_context(actor, bundle, params, fetch)
    row = evaluate_candidate(context, 2, ["p1"], ["p2"], lambda *_: pytest.fail("inactive reserve filled WR slot"))
    assert "illegal_post_trade_lineup" in row["rejection_reasons"]


def test_context_reserved_body_does_not_create_extra_active_space(context_inputs):
    actor, bundle, params, fetch, _ = context_inputs
    buyer = bundle["league"]["teams"][0]
    buyer["all_player_ids"].append("reserve")
    buyer["inactive_ids"] = ["reserve"]
    actor["players"]["reserve"] = {"name": "Reserve", "position": "WR"}
    actor["market_values"]["reserve"] = actor["personal_values"]["reserve"] = 500
    context = service.build_context(actor, bundle, params, fetch)
    row = evaluate_candidate(context, 2, ["p1"], ["p2", "d2"], lambda *_: pytest.fail("mandatory drop ignored"))
    assert "mandatory_drop_unhandled" in row["rejection_reasons"]


def test_review_delay_disables_trades_without_disabling_league_facts(context_inputs):
    actor, bundle, params, fetch, _ = context_inputs
    bundle["league"]["trade_review_days"] = 2
    assert bundle["league"]["completed_weeks"] == 2
    with pytest.raises(service.Unavailable, match="review"):
        service.build_context(actor, bundle, params, fetch)


def test_platform_disabled_pick_trading_is_a_hard_optimizer_constraint(context_inputs, monkeypatch):
    from backend import pick_values
    actor, bundle, params, fetch, _ = context_inputs
    bundle["league"]["pick_trading"] = False
    monkeypatch.setattr(db, "load_draft_picks", lambda *_, **__: [{"season": "2027", "round": 1,
                         "original_roster_id": "1", "owner_user_id": "u1", "pick_id": "owned:first"}])
    monkeypatch.setattr(pick_values, "priced_pool_value", lambda *_, **__: 1050)
    context = service.build_context(actor, bundle, params, fetch)
    row = evaluate_candidate(context, 2, ["owned:first"], ["p2"], lambda *_: pytest.fail("disabled pick trade simulated"))
    assert "locked_asset" in row["rejection_reasons"]
    assert next(a for a in service.public_assets(context) if a["id"] == "owned:first")["tradable"] is False


def test_published_consensus_seed_drift_does_not_become_personal_evidence(context_inputs, monkeypatch):
    actor, bundle, params, fetch, _ = context_inputs
    db.swipe_decisions_table.create(db.engine)
    monkeypatch.setattr(db, "load_tier_overrides", lambda *_: {})
    monkeypatch.setattr(db, "load_tier_override_stamps", lambda *_: {})
    monkeypatch.setattr(db, "load_member_rankings", lambda *_: {"u2": {"elo_ratings": {"p1": 1800, "p2": 1700}}})
    with db.engine.begin() as connection:
        connection.execute(db.member_rankings_table.insert(), [{"user_id": "u2", "league_id": "league",
            "player_id": pid, "elo": elo, "scoring_format": "1qb_ppr", "updated_at": NOW.isoformat()}
            for pid, elo in (("p1", 1800), ("p2", 1700))])
        # Trade preferences are explicitly NOT dynasty comparison evidence.
        connection.execute(db.swipe_decisions_table.insert(), {"user_id": "u2", "winner_player_id": "p1",
            "loser_player_id": "p2", "decision_type": "trade", "scoring_format": "1qb_ppr",
            "created_at": (NOW - timedelta(minutes=1)).isoformat()})
    context = service.build_context(actor, bundle, params, fetch)
    assert context["partner_evidence"][2]["basis"] == "market"
    assert context["partner_evidence"][2]["confidence"] == 0
    assert 2 not in context["partner_values"]


def trade_context():
    assets = {"first": {"id": "first", "name": "2027 First", "owner_roster_id": 1, "is_pick": True,
                         "position": "PICK", "market_value": 1050, "tradeable": True},
              "bench": {"id": "bench", "name": "Buyer WR", "owner_roster_id": 1, "is_pick": False,
                         "position": "WR", "market_value": 600, "tradeable": True},
              "veteran": {"id": "veteran", "name": "Seller WR", "owner_roster_id": 2, "is_pick": False,
                           "position": "WR", "market_value": 1000, "lineup_gain": 5, "tradeable": True},
              "depth": {"id": "depth", "name": "Seller depth", "owner_roster_id": 2, "is_pick": False,
                         "position": "WR", "market_value": 600, "tradeable": True}}
    return {"buyer_roster_id": 1, "assets": assets,
            "buyer_values": {p: a["market_value"] for p, a in assets.items()},
            "partner_values": {2: {"first": 1500, "veteran": 900}},
            "partner_evidence": {2: {"basis": "personal", "confidence": 1, "coverage": 1,
                                        "intent": "rebuilder", "declared": True}},
            "league": {"league_id": "league", "trades_allowed": True, "roster_capacity": 2,
                       "lineup_slots": [["WR"]], "teams": [{"roster_id": 1, "username": "Buyer"}, {"roster_id": 2, "username": "Seller"}]},
            "objective": "wins", "max_dynasty_spend_pct": 10, "min_fairness": .9,
            "max_simulated": 1, "max_results": 1, "protected_ids": [],
            "pricing_config": dict(pricing._cfg), "valuation_revision": "fixture-valuation"}


def simulated_trade(seed=42):
    result = {"supported": True, "paired": True}
    for side, sign in (("buyer", 1), ("partner", -1)):
        before = {"expected_remaining_wins": 5, "next_three_week_expected_wins": 1.5,
                  "playoff_probability": .5, "championship_probability": .1}
        delta = {"expected_remaining_wins": .2 * sign, "next_three_week_expected_wins": (.2 if seed == 42 else .18) * sign,
                 "playoff_probability": .02 * sign, "championship_probability": .01 * sign}
        result[side] = {"before": before, "after": {k: before[k] + d for k, d in delta.items()}, "delta": delta,
                        "lineup_gain": 5 * sign,
                        "uncertainty": {k: {"standard_error": .001, "lower_bound": d - .002,
                                            "upper_bound": d + .002, "paired": True} for k, d in delta.items()}}
    return result


def callback_seams(monkeypatch):
    calls = []
    def evaluate(league, forecasts, buyer, partner, give, receive, **kwargs):
        calls.append((buyer, partner, give, receive, kwargs))
        return simulated_trade(kwargs["seed"])
    monkeypatch.setattr(simulator, "evaluate_trade", evaluate)
    monkeypatch.setattr(simulator, "projected_lineup_points", lambda *_: {"supported": True, "teams": []})
    bundle = {"league": {}, "forecasts": {}, "baseline": {"teams": []}, "n_sims": 512, "buyer_roster_id": 1,
              "meta": {"snapshot_id": "projection", "championship_available": False,
                       "expires_at": (NOW + timedelta(minutes=10)).isoformat()}}
    return bundle, calls


def test_paired_callback_matches_real_optimizer_and_strips_only_pick_points(monkeypatch):
    bundle, calls = callback_seams(monkeypatch)
    context = trade_context()
    callback, _ = service.evaluate_callback(bundle, context)
    row = evaluate_candidate(context, 2, ["first"], ["veteran"], callback)
    assert row["eligible"], row["rejection_reasons"]
    assert [c[4]["seed"] for c in calls] == [42, 99173]
    assert all(c[2] == [] and c[3] == ["veteran"] for c in calls)
    assert row["buyer_dynasty_cost"] == 50
    assert row["conservative_season_gain"] == pytest.approx(.18)


def test_public_payload_scrubs_title_at_every_depth_without_mutating_snapshot():
    payload = {"meta": {"championship_available": False}, "trades": [{"buyer": simulated_trade()["buyer"]}],
               "baseline": {"teams": [{"championship_probability": .25, "playoff_probability": .5}]}}
    frozen = deepcopy(payload)
    public = service.public_payload(payload, championship=False)
    assert public["meta"]["championship_available"] is False
    assert public["trades"][0]["buyer"]["uncertainty"]["championship_probability"] is None
    assert public["trades"][0]["buyer"]["before"]["championship_probability"] is None
    assert public["baseline"]["teams"][0]["playoff_probability"] == .5
    assert service.public_payload(payload, championship=True) == payload == frozen


def test_scenario_adapter_supplies_complete_reviewable_client_metrics():
    context = trade_context()
    result = simulated_trade()
    for side in ("buyer", "partner"):
        for key, delta in result[side]["delta"].items():
            result[side]["uncertainty"][key]["confirmation_delta"] = delta
    row = evaluate_candidate(context, 2, ["first"], ["veteran"], lambda *_: result)
    public = service.scenario_payload(row, context)
    assert public["buyer"]["before"]["next_three_week_expected_wins"] == 1.5
    assert public["partner"]["after"]["expected_remaining_wins"] == 4.8
    assert public["valuation"]["buyer_budget"] == row["dynasty_budget"]
    assert public["valuation"]["partner_basis"] == "personal"
    assert public["valuation"]["partner_gain_fraction"] > 0
    assert public["valuation"]["partner_confidence"] == 1
    assert public["valuation"]["partner_coverage"] == 1


def test_positive_search_returns_real_optimizer_result_without_private_rankings(monkeypatch):
    bundle, _ = callback_seams(monkeypatch)
    context = trade_context()
    monkeypatch.setattr(service, "load_bundle", lambda *_: deepcopy(bundle))
    monkeypatch.setattr(service, "build_context", lambda *_: deepcopy(context))
    monkeypatch.setattr(service, "_prepare_marginals", lambda *_: None)
    saved = []
    def save(user, league, objective, row, meta):
        saved.append(deepcopy(row))
        return dict(row, scenario_id="scenario", meta=meta)
    monkeypatch.setattr(service.store, "save_scenario", save)
    result = service.run_search({"user_id": "actor", "league_id": "league"}, {"objective": "wins"}, lambda _: pytest.fail("unexpected live fetch"))
    assert len(result["trades"]) == len(saved) == 1
    assert result["trades"][0]["buyer"]["after"]["next_three_week_expected_wins"] > 1.5
    assert result["trades"][0]["buyer"]["after"]["championship_probability"] is None
    serialized = json.dumps(result)
    for private_key in ("partner_values", "buyer_values", "personal_values", "elo_ratings", "source_assets"):
        assert private_key not in serialized
    assert all("market_value" not in asset for asset in result["assets"])


def test_public_asset_picker_disables_locked_assets():
    context = trade_context()
    context["assets"]["veteran"]["locked"] = True
    by_id = {a["id"]: a for a in service.public_assets(context)}
    assert by_id["veteran"]["tradable"] is False
    assert by_id["bench"]["tradable"] is True


def test_authenticated_api_normalizes_confidence_without_returning_private_board(monkeypatch):
    from backend import win_now_api as api
    players = [SimpleNamespace(id=pid, name=pid, position="WR") for pid in ("p1", "p2")]
    ranking = SimpleNamespace(
        get_rankings=lambda **_: SimpleNamespace(rankings=[SimpleNamespace(player=p, elo=1600) for p in players]),
        comparison_counts=lambda: {"p1": 8, "p2": 8},
        placement_bands=lambda: {"p1": (1550, 1650)})
    sess = {"league": SimpleNamespace(league_id="league", platform="sleeper"), "user_id": "account",
            "service": ranking, "players": players}
    seen = []
    def context(who, *_):
        seen.append(who)
        return trade_context()
    monkeypatch.setattr(api, "is_enabled", lambda _: True)
    monkeypatch.setattr(db, "get_league_draft_context", lambda _: {"platform": "sleeper"})
    monkeypatch.setattr(service, "load_bundle", lambda *_: {"meta": {"championship_available": False},
                        "baseline": {"teams": []}, "buyer_roster_id": 1})
    monkeypatch.setattr(service, "build_context", context)
    app = Flask(__name__)
    api.install(app, require_session=lambda: sess, read_denial=lambda _: None, write_denial=lambda _: None,
                active_format=lambda _: "1qb_ppr", league_user_id=lambda _: "u1",
                pool_provider=lambda _: (players, {"p1": 1500, "p2": 1500}),
                fetch_json=lambda _: pytest.fail("unexpected network"))
    response = app.test_client().get("/api/league/season-projections?league_id=league")
    assert response.status_code == 200
    assert seen[0]["confidence"]["p1"] == 1
    assert seen[0]["confidence"]["p2"] == pytest.approx(2 / 3)
    payload = response.get_json()
    assert payload["status"] == "available"
    assert "personal_values" not in json.dumps(payload)
    assert "elo_ratings" not in json.dumps(payload)
    denied = app.test_client().get("/api/league/season-projections?league_id=someone-elses-league")
    assert denied.status_code == 403


@pytest.mark.parametrize("bad", [math.nan, math.inf, True, "0.9"])
def test_api_policy_inputs_do_not_coerce_invalid_values(bad):
    with pytest.raises(ValueError):
        service.validate_params({"min_fairness": bad})
