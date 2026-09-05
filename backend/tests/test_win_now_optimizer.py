"""Win Now proposal §6: season objective, fixed budget, honest partner gates.

Covers shared adjusted pricing, buyer dynasty sacrifices, conservative paired
improvement, exact calculator legality, fallback evidence, and frontier order.
All assets and simulation outputs are frozen synthetic inputs; no live reads.
"""

from copy import deepcopy
import math

import pytest

from backend import trade_service as pricing
from backend.win_now_optimizer import METRICS, POLICY, evaluate_candidate, generate_candidates


@pytest.fixture(autouse=True)
def isolate_pricing(monkeypatch):
    monkeypatch.setattr(pricing, "_cfg", dict(pricing._DEFAULT_CFG))


def context():
    assets = {
        "first": {"id": "first", "owner_roster_id": "buyer", "is_pick": True, "position": "PICK", "market_value": 1200},
        "bench": {"id": "bench", "owner_roster_id": "buyer", "is_pick": False, "position": "WR", "market_value": 600},
        "veteran": {"id": "veteran", "owner_roster_id": "seller", "is_pick": False, "position": "WR", "market_value": 1000, "lineup_gain": 5},
        "depth": {"id": "depth", "owner_roster_id": "seller", "is_pick": False, "position": "WR", "market_value": 600},
    }
    return {"buyer_roster_id": "buyer", "assets": assets,
            "buyer_values": {pid: asset["market_value"] for pid, asset in assets.items()},
            "partner_values": {"seller": {"first": 1500, "veteran": 900}},
            "partner_evidence": {"seller": {"basis": "personal", "confidence": 1, "coverage": 1,
                                              "intent": "rebuilder", "declared": True}},
            "league": {"trades_allowed": True, "roster_capacity": 3, "lineup_slots": [["WR"]]},
            "objective": "wins", "max_dynasty_spend_pct": 20, "min_fairness": 0.75}


def outcome(*, wins=0.2, playoffs=0.02, title=0.01, partner_wins=-0.2,
            partner_playoffs=-0.02, partner_title=-0.01, lower=None, confirmation=None,
            lineup_gain=5):
    result = {"paired": True}
    for team, w, p, t in (("buyer", wins, playoffs, title), ("partner", partner_wins, partner_playoffs, partner_title)):
        before = {"next_three_week_expected_wins": 1.5, "expected_remaining_wins": 5,
                  "playoff_probability": 0.5, "championship_probability": 0.1}
        delta = {"next_three_week_expected_wins": w, "expected_remaining_wins": w,
                 "playoff_probability": p, "championship_probability": t}
        result[team] = {"before": before, "after": {k: before[k] + d for k, d in delta.items()},
                        "delta": delta, "lineup_gain": lineup_gain,
                        "uncertainty": {key: {"lower_bound": d * 0.8 if lower is None else lower,
                                              "confirmation_delta": d * 0.9 if confirmation is None else confirmation,
                                              "standard_error": abs(d) * 0.1, "paired": True}
                                        for key, d in delta.items()}}
    return result


def evaluate(ctx=None, result=None, give=None, receive=None):
    return evaluate_candidate(ctx or context(), "seller", give or ["first"], receive or ["veteran"],
                              lambda *_: deepcopy(result or outcome()))


def test_buyer_dynasty_loss_survives_season_search_without_mutation():
    ctx = context()
    frozen = deepcopy(ctx)
    rows = generate_candidates(ctx, lambda *_: outcome())
    row = next(r for r in rows if r["give_ids"] == ["first"] and r["receive_ids"] == ["veteran"])
    assert row["buyer_dynasty_delta"] == -200
    assert row["buyer_dynasty_cost"] == 200
    assert row["eligible"] and row["conservative_season_gain"] > 0
    assert ctx == frozen


def test_budget_is_fixed_baseline_and_filler_cannot_dilute_it():
    ctx = context()
    ctx["max_dynasty_spend_pct"] = 5
    base = evaluate(ctx)
    padded = evaluate(ctx, give=["first", "bench"], receive=["veteran", "depth"])
    assert base["dynasty_budget"] == padded["dynasty_budget"] == 90
    assert base["buyer_dynasty_cost"] >= 200 and padded["buyer_dynasty_cost"] >= 200
    assert "dynasty_budget_exceeded" in base["rejection_reasons"]
    assert "dynasty_budget_exceeded" in padded["rejection_reasons"]


def test_package_matches_shared_market_calculator_pricing():
    ctx = context()
    row = evaluate(ctx, give=["first", "bench"], receive=["veteran", "depth"])
    with pricing.stud_tax_override("market"):
        ratio, give, receive = pricing.price_consensus_package(
            ["first", "bench"], ["veteran", "depth"], value_of=lambda pid: ctx["assets"][pid]["market_value"])
    assert (row["market_ratio"], row["market_give_value"], row["market_receive_value"]) == (ratio, give, receive)


def test_junk_filler_fails_shared_gate():
    ctx = context()
    ctx["assets"]["junk"] = {"id": "junk", "owner_roster_id": "buyer", "is_pick": True,
                              "position": "PICK", "market_value": 1}
    row = evaluate(ctx, give=["first", "junk"])
    assert "junk_filler" in row["rejection_reasons"]


def test_negative_partner_personal_utility_cannot_be_rescued_by_fairness():
    ctx = context()
    ctx["partner_values"]["seller"].update(first=800, veteran=1400)
    row = evaluate(ctx)
    assert row["market_ratio"] > 0.8
    assert "partner_dynasty_loss_or_negligible_gain" in row["rejection_reasons"]


@pytest.mark.parametrize("intent,declared,reason", [
    ("contender", True, "partner_competitive_misfit"),
    ("championship", True, "partner_competitive_misfit"),
    ("rebuilder", False, "unknown_partner_season_loss"),
    ("not_sure", True, "unknown_partner_season_loss"),
    ("jets", True, "unknown_partner_season_loss"),
])
def test_partner_intent_is_honest(intent, declared, reason):
    ctx = context()
    ctx["partner_evidence"]["seller"].update(intent=intent, declared=declared)
    assert reason in evaluate(ctx)["rejection_reasons"]


def test_unknown_partner_with_no_season_loss_is_eligible():
    ctx = context()
    ctx["partner_evidence"]["seller"].update(intent="not_sure", declared=False)
    assert evaluate(ctx, outcome(partner_wins=0, partner_playoffs=0, partner_title=0))["eligible"]


def test_contender_with_own_competitive_benefit_is_eligible():
    ctx = context()
    ctx["partner_evidence"]["seller"].update(intent="contender")
    assert evaluate(ctx, outcome(partner_wins=0.1))["eligible"]


def test_missing_board_is_market_fallback_with_stricter_gate():
    ctx = context()
    ctx["partner_values"] = {}
    row = evaluate(ctx)
    assert row["partner_evidence"]["basis"] == "market"
    assert row["market_floor"] == 0.9
    assert "market_fairness" in row["rejection_reasons"]
    ctx["assets"]["first"]["market_value"] = 1050
    ctx["buyer_values"]["first"] = 1050
    row = evaluate(ctx)
    assert row["eligible"]
    assert row["partner_evidence"]["confidence"] == 0


def test_sparse_rankings_shrink_to_market_and_consensus_seed_is_not_personal_evidence():
    ctx = context()
    ctx["partner_values"]["seller"].update(first=100, veteran=2000)
    ctx["partner_evidence"]["seller"].update(confidence=0)
    row = evaluate(ctx)
    assert row["partner_dynasty_surplus"] == 200
    assert row["partner_evidence"]["basis"] == "market"
    ctx["partner_evidence"]["seller"].update(confidence=1, assets={
        "first": {"source": "consensus_seed"}, "veteran": {"source": "consensus_seed"}})
    row = evaluate(ctx)
    assert row["partner_dynasty_surplus"] == 200
    assert row["partner_evidence"]["basis"] == "market"


@pytest.mark.parametrize("floor", [0, 0.5, 0.95])
def test_user_floor_never_relaxes_policy(floor):
    ctx = context()
    ctx["min_fairness"] = floor
    row = evaluate(ctx)
    assert row["market_floor"] == max(0.75, floor)
    if floor == 0.95:
        assert "market_fairness" in row["rejection_reasons"]


@pytest.mark.parametrize("mutation,reason", [
    (lambda c: c.update(protected_ids=["first"]), "protected_asset"),
    (lambda c: c.update(partner_protected_ids={"seller": ["veteran"]}), "partner_protected_asset"),
    (lambda c: c.update(pinned_give=["bench"]), "pin_not_satisfied"),
    (lambda c: c.update(pinned_receive=["depth"]), "pin_not_satisfied"),
    (lambda c: c["assets"]["first"].update(owner_roster_id="seller"), "asset_ownership"),
    (lambda c: c["assets"]["veteran"].update(locked=True), "locked_asset"),
    (lambda c: c["assets"]["first"].update(tradeable=False), "locked_asset"),
    (lambda c: c["league"].update(deadline_passed=True), "trade_deadline_or_unavailable"),
    (lambda c: c["league"].pop("trades_allowed"), "trade_deadline_or_unavailable"),
    (lambda c: c["league"].update(stale=True), "stale_or_unsupported_snapshot"),
    (lambda c: c["league"].update(live_week_unsupported=True), "stale_or_unsupported_snapshot"),
    (lambda c: c["league"].update(roster_capacity={"buyer": 1, "seller": 3}), "mandatory_drop_unhandled"),
    (lambda c: c["assets"].pop("depth"), "illegal_post_trade_lineup"),
])
def test_all_side_legality_precedes_simulation(mutation, reason):
    ctx = context()
    mutation(ctx)
    def forbidden(*_):
        raise AssertionError("ineligible packages must not simulate")
    row = evaluate_candidate(ctx, "seller", ["first"], ["veteran"], forbidden)
    assert reason in row["rejection_reasons"]


def test_flex_slot_matching_cannot_reuse_a_player():
    ctx = context()
    ctx["league"]["lineup_slots"] = [["WR"], ["RB", "WR", "TE"]]
    assert "illegal_post_trade_lineup" in evaluate(ctx)["rejection_reasons"]


@pytest.mark.parametrize("give,receive,reason", [
    (["first", "first"], ["veteran"], "duplicate_asset"),
    (["first"], ["first"], "duplicate_asset"),
    (["missing"], ["veteran"], "invalid_asset_or_partner"),
    ([], ["veteran"], "empty_side"),
    (["first", "bench", "a"], ["veteran", "depth"], "package_too_large"),
])
def test_invalid_exact_calculator_packages(give, receive, reason):
    row = evaluate_candidate(context(), "seller", give, receive, lambda *_: outcome())
    assert reason in row["rejection_reasons"]


@pytest.mark.parametrize("kwargs,reason", [
    ({"wins": 0}, "season_gain_not_reliable"),
    ({"lower": -0.01}, "season_gain_not_reliable"),
    ({"confirmation": -0.01}, "season_gain_not_reliable"),
    ({"wins": 0.001}, "season_gain_not_reliable"),
    ({"lineup_gain": 0}, "no_meaningful_lineup_gain"),
])
def test_only_stable_meaningful_paired_improvement_survives(kwargs, reason):
    assert reason in evaluate(result=outcome(**kwargs))["rejection_reasons"]


def test_missing_confirmation_and_unpaired_worlds_fail_closed():
    result = outcome()
    result["buyer"]["uncertainty"][METRICS["wins"]].pop("confirmation_delta")
    assert "missing_season_evidence" in evaluate(result=result)["rejection_reasons"]
    result = outcome()
    result["paired"] = False
    assert "unpaired_season_evaluation" in evaluate(result=result)["rejection_reasons"]


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "1200"])
def test_invalid_cardinal_values_fail_closed(bad):
    ctx = context()
    ctx["assets"]["first"]["market_value"] = bad
    assert not evaluate(ctx)["eligible"]
    assert generate_candidates(ctx, lambda *_: outcome()) == []


def test_invalid_simulation_delta_fails_closed():
    result = outcome()
    result["buyer"]["after"][METRICS["wins"]] = math.nan
    assert not evaluate(result=result)["eligible"]
    result = outcome()
    result["buyer"]["after"][METRICS["wins"]] += 0.1
    assert "inconsistent_season_delta" in evaluate(result=result)["rejection_reasons"]


def test_championship_capability_required_without_silent_fallback():
    ctx = context()
    ctx["objective"] = "championship"
    assert "championship_unavailable" in evaluate(ctx)["rejection_reasons"]
    assert generate_candidates(ctx, lambda *_: outcome()) == []
    ctx["championship_supported"] = True
    assert evaluate(ctx)["eligible"]


def test_future_picks_never_gain_direct_points_even_with_bad_metadata():
    ctx = context()
    ctx["assets"]["veteran"].update(is_pick=True, position="PICK", lineup_gain=100)
    assert generate_candidates(ctx, lambda *_: outcome()) == []
    assert "no_projected_lineup_contribution" in evaluate(ctx)["rejection_reasons"]


def test_partner_mandatory_drop_is_checked_too():
    ctx = context()
    ctx["league"]["roster_capacity"] = {"buyer": 3, "seller": 2}
    ctx["assets"]["first"].update(is_pick=False, position="WR")
    assert "mandatory_drop_unhandled" in evaluate(ctx, give=["first", "bench"])["rejection_reasons"]


def test_unknown_partner_cannot_hide_remaining_season_loss_behind_three_good_weeks():
    ctx = context()
    ctx["partner_evidence"]["seller"].update(intent="not_sure", declared=False)
    result = outcome(partner_wins=0, partner_playoffs=0, partner_title=0)
    result["partner"]["delta"]["expected_remaining_wins"] = -0.5
    result["partner"]["after"]["expected_remaining_wins"] -= 0.5
    assert "unknown_partner_season_loss" in evaluate(ctx, result)["rejection_reasons"]


def test_objective_specific_lineup_gain_allows_playoff_upgrade():
    ctx = context()
    ctx.update(objective="championship", championship_supported=True)
    result = outcome(lineup_gain=-1)
    result["buyer"]["playoff_lineup_gain"] = 5
    assert evaluate(ctx, result)["eligible"]


def test_unknown_objective_and_invalid_uncertainty_are_not_coerced():
    ctx = context()
    ctx["objective"] = "made_up"
    assert "unsupported_objective" in evaluate(ctx)["rejection_reasons"]
    result = outcome()
    result["buyer"]["uncertainty"][METRICS["wins"]]["standard_error"] = math.nan
    assert not evaluate(result=result)["eligible"]


def test_search_uses_projected_marginal_callback_not_dynasty_rank():
    ctx = context()
    ctx["assets"]["veteran"]["lineup_gain"] = 0
    ctx["marginal_lineup_gain"] = lambda buyer, give, receive: 5 if "veteran" in receive else 0
    assert generate_candidates(ctx, lambda *_: outcome())


def test_protect_remaining_wins_is_separate_from_playoff_objective():
    ctx = context()
    ctx.update(objective="playoffs", protect_remaining_wins=True)
    assert "remaining_wins_protection" in evaluate(ctx, outcome(wins=-0.1))["rejection_reasons"]


def test_frontier_ranks_selected_objective_before_cost_and_cheaper_equivalents():
    from backend.win_now_optimizer import _rank_frontier
    rows = [{"give_ids": [str(i)], "receive_ids": ["v"], "conservative_season_gain": gain,
             "buyer_dynasty_cost": cost, "partner_dynasty_surplus": 100, "market_ratio": 0.9}
            for i, (gain, cost) in enumerate([(0.40, 100), (0.20, 50), (0.395, 90), (0.1, 110)])]
    ranked = _rank_frontier(rows, "wins")
    assert [r["give_ids"] for r in ranked] == [["2"], ["0"], ["1"]]
    assert [r["rank"] for r in ranked] == [1, 2, 3]


def test_search_order_changes_with_explicit_season_objective():
    ctx = context()
    ctx["pinned_give"] = ["first"]
    ctx["assets"]["second_vet"] = {"id": "second_vet", "owner_roster_id": "seller",
                                     "is_pick": False, "position": "WR", "market_value": 1100,
                                     "lineup_gain": 6}
    ctx["buyer_values"]["second_vet"] = 1100
    ctx["partner_values"]["seller"]["second_vet"] = 1000

    def callback(buyer, partner, give, receive):
        if receive == ["veteran"]:
            return outcome(wins=0.5, playoffs=0.01)
        if receive == ["second_vet"]:
            return outcome(wins=0.2, playoffs=0.05)
        return outcome(wins=0, playoffs=0, lineup_gain=0)

    wins = generate_candidates(ctx, callback)
    ctx["objective"] = "playoffs"
    playoffs = generate_candidates(ctx, callback)
    assert wins[0]["receive_ids"] == ["veteran"]
    assert playoffs[0]["receive_ids"] == ["second_vet"]


def test_rejection_diagnostics_and_work_bounds():
    ctx = context()
    ctx["max_dynasty_spend_pct"] = 0
    diagnostics = {}
    assert generate_candidates(ctx, lambda *_: outcome(), diagnostics=diagnostics) == []
    assert diagnostics["rejections"]["dynasty_budget_exceeded"] > 0
    assert diagnostics["simulated"] <= POLICY["max_simulated"]
    assert diagnostics["screened"] <= POLICY["max_screened"]


@pytest.mark.parametrize("key", ["max_simulated", "max_results"])
@pytest.mark.parametrize("bad", [0, -1, 0.5, 100, True, "2", math.nan, math.inf])
def test_invalid_request_work_limits_fail_closed(key, bad):
    ctx = context()
    ctx[key] = bad
    assert generate_candidates(ctx, lambda *_: outcome()) == []
    assert "invalid_policy_input" in evaluate(ctx)["rejection_reasons"]


def test_request_work_limits_do_not_mutate_shared_policy():
    ctx = context()
    ctx.update(max_simulated=1, max_results=1)
    policy = deepcopy(POLICY)
    calls = []
    diagnostics = {}
    def callback(*args):
        calls.append(args)
        return outcome()
    rows = generate_candidates(ctx, callback, diagnostics=diagnostics)
    assert len(calls) == diagnostics["simulated"] == 1
    assert len(rows) == 1
    assert POLICY == policy


def test_twelve_team_search_reaches_affordable_third_target_with_real_work_bound():
    ctx = context()
    ctx["assets"] = {"bench": ctx["assets"]["bench"], "veteran": ctx["assets"]["veteran"],
                     "depth": ctx["assets"]["depth"]}
    for i in range(18):
        pid = f"pick-{i:02}"
        ctx["assets"][pid] = {"id": pid, "position": "PICK", "is_pick": True,
                               "owner_roster_id": "buyer", "market_value": 1050}
    for i, value in enumerate((10000, 9000)):
        pid = f"unaffordable-{i}"
        ctx["assets"][pid] = {"id": pid, "position": "WR", "is_pick": False,
                               "owner_roster_id": "seller", "market_value": value, "lineup_gain": 30 - i}
    for i in range(10):
        pid = f"other-player-{i}"
        ctx["assets"][pid] = {"id": pid, "position": "WR", "is_pick": False,
                               "owner_roster_id": f"other-{i}", "market_value": 600}
    ctx["buyer_values"] = {pid: a["market_value"] for pid, a in ctx["assets"].items()}
    ctx["partner_values"] = {}
    ctx["league"]["roster_capacity"] = 30
    diagnostics = {}
    rows = generate_candidates(ctx, lambda *_: outcome(), diagnostics=diagnostics)
    assert any(r["receive_ids"] == ["veteran"] for r in rows)
    assert diagnostics["screened"] <= POLICY["max_screened"]
    assert diagnostics["simulated"] <= POLICY["max_simulated"]


@pytest.mark.parametrize("side,exclusion", [
    ("buyer", "protected"), ("buyer", "locked"), ("buyer", "tradeable"),
    ("seller", "protected"), ("seller", "locked"), ("seller", "tradeable"),
])
def test_excluded_high_value_assets_cannot_displace_eligible_pool(side, exclusion):
    ctx = context()
    excluded = []
    for i in range(POLICY["pool_size"]):
        pid = f"excluded-{i}"
        asset = {"id": pid, "position": "WR", "is_pick": False,
                 "owner_roster_id": side, "market_value": 10000, "lineup_gain": 100}
        if exclusion == "locked":
            asset["locked"] = True
        elif exclusion == "tradeable":
            asset["tradeable"] = False
        ctx["assets"][pid] = asset
        excluded.append(pid)
    if exclusion == "protected":
        if side == "buyer":
            ctx["protected_ids"] = excluded
        else:
            ctx["partner_protected_ids"] = {"seller": excluded}
    ctx["league"]["roster_capacity"] = 30
    rows = generate_candidates(ctx, lambda *_: outcome())
    assert any("first" in r["give_ids"] and "veteran" in r["receive_ids"] for r in rows)
    assert all(not set(excluded) & set(r["give_ids"] + r["receive_ids"]) for r in rows)
