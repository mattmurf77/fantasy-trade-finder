"""Owner challenger scope: genuinely new small candidates and frozen evidence.

Covers raw entry authority/fallback, two-sided utility (including a dynasty
loss rescued by outlook), market/stud bounds, exact selection, personal tier
direction, soft preferences, causal roster improvements, and bounded search.
All fixtures are synthetic and use no provider or database reads/writes.
"""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import time

import pytest

from backend import feature_flags, trade_gen_owner as owner, trade_service as ts
from backend.ranking_service import Player
from backend.trade_gen_owner import evaluate_owner_trade, generate_owner_trades


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(feature_flags, "_flags_cache", dict(feature_flags.DEFAULT_FLAGS))


def world(spec=None, give=None, receive=None, viewer=None, opponent=None, **extra):
    spec = spec or {"g": ("WR", 26, 1000), "r": ("WR", 26, 1000)}
    players = {pid: Player(pid, pid, pos, "PICK" if pos == "PICK" else "TST", age)
               for pid, (pos, age, value) in spec.items()}
    seed = {pid: ts.value_to_elo(value) for pid, (_, _, value) in spec.items()}
    other = ts.LeagueMember("opp", "Other", receive or ["r"],
        {pid: ts.value_to_elo(value) for pid, value in (opponent or {}).items()}, bool(opponent))
    kwargs = dict(players=players, league=ts.League("L", "Test", "sleeper", [other]),
        user_id="me", user_roster=give or ["g"], seed_elo=seed,
        user_elo={pid: ts.value_to_elo(value) for pid, value in (viewer or {}).items()},
        outlook="not_sure", opponent_outlooks={"opp": "not_sure"}, fairness_threshold=.75)
    kwargs.update(extra)
    return kwargs


def keys(cards):
    return {(tuple(c.give_player_ids), tuple(c.receive_player_ids)) for c in cards}


def favorable(**extra):
    return world(viewer={"g": 800, "r": 1200}, opponent={"g": 1200, "r": 800}, **extra)


def test_raw_preferences_construct_new_candidates_not_a_sort():
    neutral, _ = generate_owner_trades(**world())
    personal, report = generate_owner_trades(**favorable())
    assert neutral == []
    assert keys(personal) == {(("g",), ("r",))}
    assert report.as_dict()["emitted"] == 1
    assert personal[0].give_value == personal[0].receive_value


@pytest.mark.parametrize("source", ["explicit", "votes", "cross_format", "legacy"])
def test_all_deliberate_methods_have_equal_raw_authority(source):
    kwargs = favorable(user_sources={"g": source, "r": source},
        opponent_sources={"opp": {"g": source, "r": source}})
    cards, _ = generate_owner_trades(**kwargs)
    assert len(cards) == 1
    snapshot = cards[0].owner_evaluation.as_dict()
    assert snapshot["viewer"]["incoming_personal"] == pytest.approx(1200)
    assert snapshot["viewer"]["outgoing_personal"] == pytest.approx(800)


def test_seed_entries_and_individually_missing_entries_fallback():
    kwargs = favorable(user_sources={"g": "seed", "r": "explicit"})
    kwargs["user_elo"]["g"] = ts.value_to_elo(2)
    cards, _ = generate_owner_trades(**kwargs)
    assert cards
    give = next(a for a in cards[0].owner_evaluation.as_dict()["assets"] if a["id"] == "g")
    assert give["viewer_personal"] == give["market"]
    assert give["viewer_source"] == "consensus_fallback"
    assert give["counterparty_personal"] == pytest.approx(1200)


def test_per_entry_source_evidence_not_member_flag_controls_authority():
    kwargs = favorable(opponent_sources={"opp": {"g": "explicit", "r": "votes"}})
    kwargs["league"].members[0].has_rankings = False
    assert len(generate_owner_trades(**kwargs)[0]) == 1
    kwargs["opponent_sources"] = {"opp": {"g": "seed", "r": "seed"}}
    assert generate_owner_trades(**kwargs)[0] == []


def test_incomplete_opponent_board_does_not_exclude_pair():
    kwargs = favorable()
    del kwargs["league"].members[0].elo_ratings["g"]
    cards, _ = generate_owner_trades(**kwargs)
    assert cards
    snapshot = cards[0].owner_evaluation.as_dict()
    assert snapshot["counterparty"]["incoming_personal"] == pytest.approx(1000)


def test_outlook_can_rescue_negative_personal_dynasty_gain():
    kwargs = world({"pick": ("PICK", 0, 1100), "vet": ("RB", 27, 1000)},
        ["pick"], ["vet"], outlook="championship", opponent_outlooks={"opp": "jets"})
    cards, _ = generate_owner_trades(**kwargs)
    assert keys(cards) == {(("pick",), ("vet",))}
    evidence = cards[0].owner_evaluation.as_dict()
    assert evidence["viewer"]["personal_gain_fraction"] < 0
    assert evidence["viewer"]["personal_loss_rescued"]
    assert evidence["counterparty"]["outlook_utility"] > 0
    kwargs["outlook"] = "jets"
    assert generate_owner_trades(**kwargs)[0] == []


def test_declared_outlook_beats_inference(monkeypatch):
    monkeypatch.setattr(ts, "infer_team_outlook", lambda *a, **k: (_ for _ in ()).throw(AssertionError("inferred")))
    assert generate_owner_trades(**favorable())[0]


def test_captured_inferred_outlook_is_used_and_labelled_honestly(monkeypatch):
    kwargs = favorable(outlook=None, inferred_outlooks={"me": "rebuilder"})
    monkeypatch.setattr(ts, "infer_team_outlook", lambda *a, **k: (_ for _ in ()).throw(AssertionError("reinferred")))
    card = generate_owner_trades(**kwargs)[0][0]
    viewer = card.owner_evaluation.as_dict()["viewer"]
    assert viewer["outlook"] == "rebuilder" and viewer["outlook_source"] == "inferred"
    kwargs["outlook"] = "championship"
    viewer = generate_owner_trades(**kwargs)[0][0].owner_evaluation.as_dict()["viewer"]
    assert viewer["outlook"] == "championship" and viewer["outlook_source"] == "declared"


def test_no_free_need_credit_for_equal_player_churn():
    kwargs = world()
    card = ts.TradeCard("x", "L", "me", "opp", "Other", ["g"], ["r"], 0, 0, 0)
    result = evaluate_owner_trade(card, **kwargs).as_dict()
    assert not result["eligible"]
    assert result["viewer"]["need_utility"] == 0
    assert result["counterparty"]["need_utility"] == 0


def test_position_surplus_to_actual_hole_has_two_sided_need_benefit():
    spec = {"g": ("WR", 26, 1000), "r": ("RB", 26, 1000),
            "w1": ("WR", 26, 1400), "w2": ("WR", 26, 1300),
            "w3": ("WR", 26, 1200), "b1": ("RB", 26, 1400),
            "b2": ("RB", 26, 1300)}
    kwargs = world(spec, ["g", "w1", "w2", "w3"], ["r", "b1", "b2"],
                   pinned_give_players=["g"], pinned_receive_players=["r"])
    cards, _ = generate_owner_trades(**kwargs)
    card = next(c for c in cards if c.give_player_ids == ["g"] and c.receive_player_ids == ["r"])
    evidence = card.owner_evaluation.as_dict()
    assert evidence["viewer"]["need_utility"] > 0
    assert evidence["counterparty"]["need_utility"] > 0


def test_market_price_does_not_follow_extreme_personal_willingness():
    kwargs = favorable()
    kwargs["user_elo"]["r"] = ts.value_to_elo(100000)
    card = generate_owner_trades(**kwargs)[0][0]
    with ts.stud_tax_override("market"):
        expected = ts.price_consensus_package(["g"], ["r"], value_of=ts.make_consensus_value_fn(kwargs["seed_elo"], kwargs["players"]))
    assert (card.fairness_score, card.give_value, card.receive_value) == expected


@pytest.mark.parametrize("ratio,floor", [(.6, .5), (.8, .95)])
def test_market_floor_is_never_relaxed_for_personal_conviction(ratio, floor):
    kwargs = world({"g": ("WR", 26, 4000), "r": ("WR", 26, 4000 * ratio)},
        viewer={"g": 100, "r": 10000}, opponent={"g": 10000, "r": 100}, fairness_threshold=floor)
    cards, report = generate_owner_trades(**kwargs)
    assert cards == []
    assert report.as_dict()["rejections"]["market_floor"]


def test_established_overpay_ceiling_still_blocks_both_directions():
    for reverse in (False, True):
        spec = {"g": ("WR", 26, 4000), "r": ("WR", 26, 2800)}
        if reverse:
            spec["g"], spec["r"] = spec["r"], spec["g"]
        kwargs = world(spec, viewer={"g": 100, "r": 10000},
            opponent={"g": 10000, "r": 100}, fairness_threshold=.65)
        cards, report = generate_owner_trades(**kwargs)
        assert cards == []
        assert report.as_dict()["rejections"]["market_overpay"]


def test_stud_mode_cannot_be_disabled_by_calling_context():
    with ts.stud_tax_override("off"):
        cards, _ = generate_owner_trades(**favorable())
    assert cards[0].owner_evaluation.as_dict()["market"]["stud_mode"] == "market"


def test_exact_give_order_and_all_receive_pins():
    spec = {"g1": ("WR", 26, 600), "g2": ("WR", 26, 600), "r": ("WR", 26, 1000)}
    kwargs = world(spec, ["g1", "g2"], ["r"],
        {"g1": 300, "g2": 300, "r": 1300}, {"g1": 1000, "g2": 1000, "r": 600},
        exact_give=True, pinned_give_players=["g2", "g1"], pinned_receive_players=["r"])
    cards, _ = generate_owner_trades(**kwargs)
    assert cards
    assert all(c.give_player_ids == ["g2", "g1"] and c.receive_player_ids == ["r"] for c in cards)
    assert all(c.owner_evaluation.as_dict()["selection"]["coverage"] == "full" for c in cards)


def test_wrong_owner_target_is_never_silently_substituted():
    kwargs = favorable(pinned_receive_players=["missing"], opponent_user_id="opp")
    assert generate_owner_trades(**kwargs)[0] == []
    kwargs = favorable(opponent_user_id="unknown")
    assert generate_owner_trades(**kwargs)[0] == []


def test_partial_pins_are_explicit_and_only_after_full_failure():
    kwargs = favorable(pinned_give_players=["g", "missing"], pinned_receive_players=["r"])
    cards, report = generate_owner_trades(**kwargs)
    assert cards and report.as_dict()["partial_search"]
    selection = cards[0].owner_evaluation.as_dict()["selection"]
    assert selection["coverage"] == "partial"
    assert selection["give"]["omitted"] == ["missing"]
    assert selection["receive"]["included"] == ["r"]
    assert cards[0].reasons


def test_personal_tiers_and_within_tier_direction_not_market_direction():
    kwargs = favorable(trade_intent="tier_up")
    cards, _ = generate_owner_trades(**kwargs)
    assert cards and cards[0].owner_group == "upgrade"
    kwargs["trade_intent"] = "tier_down"
    assert generate_owner_trades(**kwargs)[0] == []


def test_chasing_is_soft_but_explicit_avoid_and_swap_are_hard():
    kwargs = favorable(acquire_positions=["RB"])
    assert generate_owner_trades(**kwargs)[0]
    kwargs["avoid_positions"] = ["WR"]
    assert generate_owner_trades(**kwargs)[0] == []
    kwargs = favorable(swap_positions=["RB"])
    assert generate_owner_trades(**kwargs)[0] == []


def test_untouchable_requires_above_market_and_replacement_unless_selected():
    kwargs = favorable(manager_preferences={"me": {"untouchables": ["g"]}})
    assert generate_owner_trades(**kwargs)[0] == []
    kwargs["pinned_give_players"] = ["g"]
    cards, _ = generate_owner_trades(**kwargs)
    assert cards
    assert kwargs["manager_preferences"]["me"]["untouchables"] == ["g"]


def test_context_is_immutable_detached_and_exact_package_bound():
    card = generate_owner_trades(**favorable())[0][0]
    context = card.owner_evaluation
    assert context.matches(card)
    with pytest.raises(FrozenInstanceError):
        context.eligible = False
    detached = context.as_dict()
    detached["market"]["give"] = -1
    assert context.as_dict()["market"]["give"] > 0
    card.receive_player_ids.append("extra")
    assert not context.matches(card)


def test_budgets_round_robin_opponents_and_small_shapes_only():
    kwargs = favorable(config={"owner_total_budget": 3, "owner_pair_budget": 2})
    kwargs["league"].members = [ts.LeagueMember(f"o{i}", f"o{i}", ["r"],
        {"g": ts.value_to_elo(1200), "r": ts.value_to_elo(800)}, True) for i in range(3)]
    kwargs["opponent_outlooks"] = {f"o{i}": "not_sure" for i in range(3)}
    cards, report = generate_owner_trades(**kwargs)
    assert report.as_dict()["evaluated"] == 3
    assert all(p["evaluated"] == 1 for p in report.as_dict()["per_opponent"].values())
    assert all((len(c.give_player_ids), len(c.receive_player_ids)) in ((1, 1), (1, 2), (2, 1)) for c in cards)


def test_previous_disposition_cannot_be_regenerated():
    kwargs = favorable(past_decision_keys={(frozenset(["g"]), frozenset(["r"]))})
    assert generate_owner_trades(**kwargs)[0] == []


@pytest.mark.parametrize("floor", [True, "0.75", float("nan"), -1, 2])
def test_invalid_fairness_fails_closed(floor):
    assert generate_owner_trades(**favorable(fairness_threshold=floor))[0] == []


def test_joint_outlook_need_target_pool_changes_before_market_checks():
    spec = {"g": ("WR", 26, 1000), **{f"w{i}": ("WR", 26, 1000) for i in range(3)},
            **{f"r{i}": ("RB", 22 if i == 8 else 27, 1000) for i in range(9)}}
    kwargs = world(spec, ["g", "w0", "w1", "w2"], [f"r{i}" for i in range(9)],
        pinned_give_players=["g"], config={"owner_pool_size": 4,
            "age_pref_mult_u23": 1.0, "age_pref_mult_30plus": 1.0})
    kwargs["outlook"] = "championship"
    now, now_report = generate_owner_trades(**kwargs)
    kwargs["outlook"] = "jets"
    future, future_report = generate_owner_trades(**kwargs)
    assert now_report.as_dict()["pools"]["opp"]["receive"] != future_report.as_dict()["pools"]["opp"]["receive"]
    assert keys(now) != keys(future)
    assert any(c.receive_player_ids == ["r8"] for c in future)
    assert all(c.give_value == pytest.approx(1000) and c.receive_value == pytest.approx(1000)
               for c in now + future if len(c.receive_player_ids) == 1)


def test_requested_get_cannot_override_other_owners_untouchable():
    kwargs = favorable(pinned_receive_players=["r"],
        manager_preferences={"opp": {"untouchables": ["r"]}})
    cards, report = generate_owner_trades(**kwargs)
    assert cards == []
    assert report.as_dict()["rejections"]["untouchable_return"]


def test_same_personal_tier_can_qualify_upgrade_and_lateral():
    kwargs = favorable()
    # Find two real within-tier values; thresholds themselves are not fixture assumptions.
    from backend.ranking_service import RankingService
    for elo in range(1300, 1800):
        if RankingService.tier_for_elo(elo, "WR", "1qb_ppr") == RankingService.tier_for_elo(elo + 20, "WR", "1qb_ppr"):
            kwargs["user_elo"] = {"g": float(elo), "r": float(elo + 20)}
            break
    kwargs.update(trade_intent="tier_up", lateral_scope="tier")
    up, _ = generate_owner_trades(**kwargs)
    kwargs["trade_intent"] = "same_value"
    same, _ = generate_owner_trades(**kwargs)
    assert keys(up) == keys(same) == {(("g",), ("r",))}
    assert up[0].owner_groups == ("upgrade", "lateral")


def test_outlook_never_changes_frozen_market_currency():
    kwargs = favorable()
    cards = []
    for outlook in ("championship", "contender", "rebuilder", "jets"):
        kwargs["outlook"] = outlook
        cards.append(generate_owner_trades(**kwargs)[0][0])
    assert len({(c.give_value, c.receive_value, c.fairness_score) for c in cards}) == 1


def test_partial_survives_exact_context_revalidation_not_new_selection():
    kwargs = favorable(pinned_give_players=["g", "missing"], pinned_receive_players=["r"])
    card = generate_owner_trades(**kwargs)[0][0]
    result = evaluate_owner_trade(card, **kwargs)
    assert result.eligible and result.as_dict()["selection"]["coverage"] == "partial"
    kwargs["pinned_give_players"] = ["g", "different"]
    assert not evaluate_owner_trade(card, **kwargs).eligible


def test_actual_superflex_slot_does_not_double_count_a_qb():
    spec = {"g": ("WR", 26, 1000), "r": ("QB", 26, 1000), "q": ("QB", 26, 1000)}
    kwargs = world(spec, ["g", "q"], ["r"],
        viewer={"g": 800, "r": 1200}, opponent={"g": 1200, "r": 800},
        manager_preferences={"me": {"starter_slots": ["QB", "SUPER_FLEX"], "lineup_source": "observed"},
                             "opp": {"starter_slots": ["WR"], "lineup_source": "observed"}},
        pinned_give_players=["g"], pinned_receive_players=["r"])
    card = next(c for c in generate_owner_trades(**kwargs)[0] if c.give_player_ids == ["g"] and c.receive_player_ids == ["r"])
    viewer = card.owner_evaluation.as_dict()["viewer"]
    # Replacing the WR in superflex with the new QB: existing QB starts once.
    assert viewer["usable_depth_delta"]["QB"] == pytest.approx(1000)
    assert viewer["usable_depth_delta"]["WR"] == pytest.approx(-1000)
    assert viewer["need_utility"] == 0
    assert viewer["lineup_source"] == "observed"


@pytest.mark.parametrize("elo", [float("nan"), float("inf"), -1e9])
def test_invalid_personal_entry_fallback_has_honest_provenance(elo):
    kwargs = favorable(user_sources={"g": "explicit", "r": "explicit"})
    kwargs["user_elo"]["g"] = elo
    card = generate_owner_trades(**kwargs)[0][0]
    entry = next(a for a in card.owner_evaluation.as_dict()["assets"] if a["id"] == "g")
    assert entry["viewer_personal"] == entry["market"]
    assert entry["viewer_source"] == "consensus_fallback"


def test_full_sixteen_asset_pair_remains_bounded_and_diverse():
    spec = {f"g{i}": (_pos, 26, 1000 + i * 40) for i, _pos in enumerate(_POSITIONS * 4)}
    spec.update({f"r{i}": (_pos, 26, 1000 + i * 40) for i, _pos in enumerate(_POSITIONS * 4)})
    give = [f"g{i}" for i in range(16)]
    recv = [f"r{i}" for i in range(16)]
    kwargs = world(spec, give, recv,
        {**{p: 500 for p in give}, **{p: 3000 for p in recv}},
        {**{p: 3000 for p in give}, **{p: 500 for p in recv}})
    cards, report = generate_owner_trades(**kwargs)
    assert report.as_dict()["evaluated"] == 4096
    assert len(cards) > 10
    assert len({c.give_player_ids[0] for c in cards[:12]}) > 1
    assert all((len(c.give_player_ids), len(c.receive_player_ids)) in ((1, 1), (1, 2), (2, 1)) for c in cards)
    assert keys(cards) == keys(generate_owner_trades(**kwargs)[0])


_POSITIONS = ("QB", "RB", "WR", "TE")


@pytest.mark.parametrize("partial", [False, True])
def test_batch_revalidation_matches_single_and_builds_context_once(monkeypatch, partial):
    kwargs = favorable(**({"pinned_give_players": ["g", "missing"],
                          "pinned_receive_players": ["r"]} if partial else {}))
    valid = generate_owner_trades(**kwargs)[0][0]
    mutated = deepcopy(valid)
    mutated.receive_player_ids = ["unknown"]
    cards = [valid, mutated, valid]  # Repeated occurrence retains its own result.
    expected = [evaluate_owner_trade(card, **kwargs) for card in cards]
    real_search = owner._Search
    constructions = []
    def counted_search(**inputs):
        constructions.append(inputs)
        return real_search(**inputs)
    monkeypatch.setattr(owner, "_Search", counted_search)
    results = owner.evaluate_owner_trades(cards, **kwargs)
    assert len(constructions) == 1
    assert [result.as_dict() for result in results] == [result.as_dict() for result in expected]
    assert [result.eligible for result in results] == [True, False, True]
    assert results[0].matches(valid) and not results[1].matches(mutated)
    assert results[0].as_dict()["selection"]["coverage"] == ("partial" if partial else "full")


def test_batch_does_not_reauthorize_partial_against_different_request():
    kwargs = favorable(pinned_give_players=["g", "missing"], pinned_receive_players=["r"])
    card = generate_owner_trades(**kwargs)[0][0]
    kwargs["pinned_give_players"] = ["g", "different"]
    result = owner.evaluate_owner_trades([card], **kwargs)[0]
    assert not result.eligible and result.reason == "selection_mismatch"


def test_distinct_same_headliner_companions_are_not_collapsed():
    kwargs = world({"g": ("WR", 26, 1000), "r": ("WR", 26, 700),
                    "s1": ("WR", 26, 300), "s2": ("WR", 26, 300)},
        ["g"], ["r", "s1", "s2"], viewer={"g": 600, "r": 1000, "s1": 500, "s2": 500},
        opponent={"g": 1600, "r": 400, "s1": 100, "s2": 100})
    cards, report = generate_owner_trades(**kwargs)
    assert {(tuple(c.give_player_ids), frozenset(c.receive_player_ids)) for c in cards} == {
        (("g",), frozenset(("r", "s1"))), (("g",), frozenset(("r", "s2")))}
    assert report.as_dict()["emitted"] == 2


def test_more_than_sixty_distinct_eligible_offers_return_without_output_limit():
    give, receive = [f"g{i}" for i in range(8)], [f"r{i}" for i in range(8)]
    kwargs = world({pid: ("WR", 26, 1000) for pid in give + receive}, give, receive,
        viewer={pid: 800 if pid in give else 1200 for pid in give + receive},
        opponent={pid: 1200 if pid in give else 800 for pid in give + receive})
    cards, report = generate_owner_trades(**kwargs)
    assert len(cards) == len(keys(cards)) == 64
    assert report.as_dict()["limits"] == {"pool": 16, "per_pair": 4096, "total": 60000}


def test_exact_package_duplicates_are_still_suppressed(monkeypatch):
    original = owner._Search.candidates
    def repeated(self, member, *, partial=False):
        for card in original(self, member, partial=partial):
            yield card
            yield deepcopy(card)
    monkeypatch.setattr(owner._Search, "candidates", repeated)
    assert len(generate_owner_trades(**favorable())[0]) == 1


def test_twelve_team_dense_search_reports_output_cost_without_capping(capsys):
    # Plausible league/roster sizes with intentionally dense reciprocal
    # preferences: a stress bound, not a forecast of production demand.
    values = [300, 500, 800, 1000, 1500, 2200]
    positions = ["QB", "RB", "WR", "WR", "TE", "RB"]
    spec, rosters = {}, {}
    for team in range(12):
        uid = f"team{team}"
        rosters[uid] = []
        for index in range(24):
            pid = f"{uid}_asset{index}"
            rosters[uid].append(pid)
            spec[pid] = (positions[index % 6], [23, 25, 28, 31][index % 4], values[index % 6])
    viewer = "team0"
    kwargs = world(spec, rosters[viewer], rosters["team1"], user_id=viewer,
        viewer={p: value * (.85 if p in rosters[viewer] else 1.15)
                for p, (_, _, value) in spec.items()})
    kwargs["league"].members = [ts.LeagueMember(uid, uid, ids,
        {p: ts.value_to_elo(spec[p][2] * (1.15 if p in rosters[viewer] else .85))
         for p in rosters[viewer] + ids}, True) for uid, ids in rosters.items() if uid != viewer]
    kwargs["opponent_outlooks"] = {m.user_id: "not_sure" for m in kwargs["league"].members}
    start = time.perf_counter()
    cards, report = generate_owner_trades(**kwargs)
    elapsed = time.perf_counter() - start
    data = report.as_dict()
    assert data["evaluated"] == 11 * 4096
    assert data["budget_exhausted"]
    assert len(cards) > 60
    assert len(cards) == len({(c.target_user_id, frozenset(c.give_player_ids),
                              frozenset(c.receive_player_ids)) for c in cards})
    with capsys.disabled():
        print(json.dumps({"synthetic_teams": 12, "assets_per_team": 24,
            "elapsed_seconds": round(elapsed, 3), "evaluated": data["evaluated"],
            "emitted": len(cards), "budget_exhausted": data["budget_exhausted"],
            "limits": data["limits"], "private_decision_context_bytes_total":
            sum(len(c.owner_evaluation.snapshot_json.encode()) for c in cards),
            "report_json_bytes": len(json.dumps(data).encode())}))
