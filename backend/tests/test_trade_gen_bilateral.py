"""Bilateral model: captured authority, bounded ordinal intent and minimal terms.

Hermetic synthetic fixtures exercise source provenance, missing context,
immutability, market snapshots, simple/full selection and computational bounds.
No application/server/database/provider imports or production fixtures.
"""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import time

import pytest

from backend import feature_flags, trade_gen_bilateral as bilateral, trade_gen_owner as owner, trade_service as ts
from backend.ranking_service import Player, RankingService


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(feature_flags, "_flags_cache", dict(feature_flags.DEFAULT_FLAGS))


def world(spec=None, give=None, receive=None, viewer=None, opponent=None, **extra):
    spec = spec or {"g": ("WR", 26, 1000), "r": ("WR", 26, 1000)}
    players = {pid: Player(pid, pid, pos, "PICK" if pos == "PICK" else "TST", age)
               for pid, (pos, age, _) in spec.items()}
    seed = {pid: ts.value_to_elo(value) for pid, (_, _, value) in spec.items()}
    other = ts.LeagueMember("opp", "Other", receive or ["r"],
        {pid: ts.value_to_elo(value) for pid, value in (opponent or {}).items()}, bool(opponent))
    kwargs = dict(players=players, league=ts.League("L", "Synthetic", "sleeper", [other]),
        user_id="me", user_roster=give or ["g"], seed_elo=seed,
        user_elo={pid: ts.value_to_elo(value) for pid, value in (viewer or {}).items()},
        outlook="not_sure", opponent_outlooks={"opp": "not_sure"}, fairness_threshold=.75)
    kwargs.update(extra)
    return kwargs


def favorable(**extra):
    return world(viewer={"g": 800, "r": 1200}, opponent={"g": 1200, "r": 800}, **extra)


def card(give=("g",), receive=("r",)):
    return ts.TradeCard("x", "L", "me", "opp", "Other", list(give), list(receive), 0, 0, 0)


def test_new_generator_does_not_call_old_generator_or_enumerator(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("old candidate generation")
    monkeypatch.setattr(owner, "generate_owner_trades", forbidden)
    monkeypatch.setattr(owner._Search, "candidates", forbidden)
    assert bilateral.generate_bilateral_trades(**favorable())[0]


@pytest.mark.parametrize("overrides", [{}, {"pinned_give_players": ["g", "missing"]},
                                      {"fairness_threshold": .99}, {"trade_intent": "tier_down"}])
def test_extracted_freeze_hook_preserves_owner_v1_context_bytes(monkeypatch, overrides):
    kwargs = favorable(**overrides)
    current, report = owner.generate_owner_trades(**kwargs)
    current_rejection = owner.evaluate_owner_trade(card(), **kwargs)
    def legacy_finish(self, c, data, reason, eligible=False):
        data.update(eligible=eligible, reason=reason)
        return owner.OwnerDecisionContext(eligible, reason, self.league.league_id, self.user_id,
            c.target_user_id, tuple(c.give_player_ids), tuple(c.receive_player_ids), owner._dump(data))
    monkeypatch.setattr(owner._Search, "_decision", legacy_finish)
    baseline, prior_report = owner.generate_owner_trades(**kwargs)
    assert [c.owner_evaluation.snapshot_json for c in current] == [c.owner_evaluation.snapshot_json for c in baseline]
    assert report.snapshot_json == prior_report.snapshot_json
    assert current_rejection.snapshot_json == owner.evaluate_owner_trade(card(), **kwargs).snapshot_json


@pytest.mark.parametrize("source", ["explicit", "votes", "cross_format", "legacy"])
def test_all_deliberate_ranking_actions_have_equal_authority(source):
    kwargs = favorable(user_sources={"g": source, "r": source})
    snapshot = bilateral.generate_bilateral_trades(**kwargs)[0][0].owner_evaluation.as_dict()
    assert snapshot["viewer"]["preference_evidence"]["state"] == "known"
    assert snapshot["viewer"]["intent"]["path"] == "personal_board"
    assert snapshot["assets"][1]["viewer_preference"]["source"] == source
    assert snapshot["viewer"]["incoming_personal"] == pytest.approx(1200)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1e9])
def test_invalid_personal_values_are_unknown_not_an_expressed_preference(bad):
    kwargs = favorable(user_sources={"g": "explicit", "r": "explicit"})
    kwargs["user_elo"]["g"] = bad
    data = bilateral.generate_bilateral_trades(**kwargs)[0][0].owner_evaluation.as_dict()
    asset = next(a for a in data["assets"] if a["id"] == "g")
    assert asset["viewer_preference"]["direction"] is None
    assert asset["viewer_source"] == "consensus_fallback"
    assert data["viewer"]["preference_evidence"]["state"] == "partial"


def test_unknown_other_board_is_not_recorded_as_zero_preference():
    kwargs = world(viewer={"g": 800, "r": 1200})
    result = bilateral.generate_bilateral_trades(**kwargs)[0][0].owner_evaluation.as_dict()
    assert result["counterparty"]["preference_evidence"]["state"] == "unknown"
    assert all(a["counterparty_preference"]["direction"] is None for a in result["assets"])
    interval = result["counterparty"]["support"]["range"]
    assert interval[1] - interval[0] >= .24 - 1e-9


def test_bulk_source_capture_has_same_authority_as_shared_owner_context():
    kwargs = favorable(opponent_sources={})
    kwargs["league"].members[0].confidence_sources = {"g": "seed", "r": "seed"}
    # An explicitly captured bulk map is authoritative over member metadata.
    # Its missing entry follows the shared historical real-board convention.
    data = bilateral.generate_bilateral_trades(**kwargs)[0][0].owner_evaluation.as_dict()
    assert data["counterparty"]["preference_evidence"]["state"] == "known"
    assert data["counterparty"]["intent"]["net_preference"] > 0
    assert all(a["counterparty_source"] == "legacy" for a in data["assets"])


def test_preference_direction_is_bounded_and_independent_of_price_denominator():
    kwargs = favorable()
    kwargs["user_elo"]["r"] = ts.value_to_elo(1e12)
    data = bilateral.generate_bilateral_trades(**kwargs)[0][0].owner_evaluation.as_dict()
    assert 0 < data["assets"][1]["viewer_preference"]["direction"] <= 1
    assert data["market"]["give"] == data["market"]["receive"] == pytest.approx(1000)
    assert data["bilateral"]["score_kind"] == "interpretable_support_not_probability"


def test_existing_full_board_intent_does_not_depend_on_other_roster_members():
    kwargs = world({"g": ("WR", 26, 1000), "r": ("WR", 26, 1000), "extra": ("WR", 24, 800)},
                   viewer={"g": 800, "r": 1200, "extra": 900}, opponent={"g": 1200, "r": 800})
    before = bilateral.evaluate_bilateral_trade(card(), **kwargs).as_dict()
    kwargs["league"].members[0].roster.append("extra")
    after = bilateral.evaluate_bilateral_trade(card(), **kwargs).as_dict()
    assert before["assets"][0]["viewer_preference"] == after["assets"][0]["viewer_preference"]
    assert before["assets"][1]["viewer_preference"] == after["assets"][1]["viewer_preference"]


def test_exact_evidence_is_frozen_and_market_context_is_versioned():
    kwargs = favorable(manager_preferences={"me": {"market_source_snapshot": {"source": "pinned_fixture", "version": "v1"}}})
    generated, report = bilateral.generate_bilateral_trades(**kwargs)
    c = generated[0]
    assert isinstance(c.owner_evaluation, owner.OwnerDecisionContext)
    assert c.owner_evaluation.matches(c)
    with pytest.raises(FrozenInstanceError):
        c.owner_evaluation.eligible = False
    copy = c.owner_evaluation.as_dict()
    copy["viewer"]["support"]["score"] = -100
    assert c.owner_evaluation.as_dict()["viewer"]["support"]["score"] > 0
    market = report.as_dict()["market_source_snapshot"]
    assert len(market["seed_sha256"]) == 64 and not market["new_blend_applied"]
    assert market["caller_provenance"]["source"] == "pinned_fixture"
    c.give_value += 1
    assert not c.owner_evaluation.matches(c)


@pytest.mark.parametrize("floor", [float("nan"), float("inf"), -1, 1.1, True])
def test_invalid_fairness_never_publishes(floor):
    cards, report = bilateral.generate_bilateral_trades(**favorable(fairness_threshold=floor))
    assert cards == []
    assert report.as_dict()["rejections"]["invalid_fairness"] == 1


def test_adaptive_companion_can_supply_missing_sufficient_consideration():
    kwargs = world({"g": ("WR", 26, 1000), "r": ("WR", 26, 700), "add": ("TE", 24, 300)},
        ["g"], ["r", "add"], {"g": 600, "r": 1200, "add": 700}, {"g": 1500, "r": 400, "add": 100})
    cards, report = bilateral.generate_bilateral_trades(**kwargs)
    assert any(c.give_player_ids == ["g"] and set(c.receive_player_ids) == {"r", "add"} for c in cards)
    assert report.as_dict()["rejections"]["market_floor"] >= 1


def test_untouchable_opponent_is_not_overridden_by_viewer_selection():
    kwargs = favorable(pinned_receive_players=["r"], manager_preferences={"opp": {"untouchables": ["r"]}})
    assert bilateral.generate_bilateral_trades(**kwargs)[0] == []
    kwargs = favorable(pinned_give_players=["g"], manager_preferences={"me": {"untouchables": ["g"]}})
    assert bilateral.generate_bilateral_trades(**kwargs)[0]


def test_full_multi_asset_request_is_not_replaced_by_smaller_partial():
    kwargs = world({"g1": ("WR", 26, 600), "g2": ("TE", 26, 600),
                    "r1": ("WR", 26, 600), "r2": ("TE", 26, 600)},
        ["g1", "g2"], ["r1", "r2"], {"g1": 400, "g2": 400, "r1": 900, "r2": 900},
        {"g1": 900, "g2": 900, "r1": 400, "r2": 400},
        pinned_give_players=["g2", "g1"], pinned_receive_players=["r1", "r2"], exact_give=True)
    cards, report = bilateral.generate_bilateral_trades(**kwargs)
    assert cards and not report.as_dict()["partial_search"]
    assert all(c.give_player_ids == ["g2", "g1"] and c.receive_player_ids == ["r1", "r2"] for c in cards)


def test_batch_revalidation_keeps_occurrences_and_authenticated_partial_authority():
    kwargs = favorable(pinned_give_players=["g", "missing"], pinned_receive_players=["r"])
    c = bilateral.generate_bilateral_trades(**kwargs)[0][0]
    mutated = deepcopy(c)
    mutated.receive_player_ids = ["unknown"]
    proofs = bilateral.evaluate_bilateral_trades([c, mutated, c], **kwargs)
    assert [p.eligible for p in proofs] == [True, False, True]
    assert proofs[0].matches(c)
    kwargs["pinned_give_players"] = ["g", "different"]
    assert not bilateral.evaluate_bilateral_trade(c, **kwargs).eligible


def test_draft_protection_does_not_guess_from_pick_year_or_holder():
    kwargs = world({"L_2027_1_1": ("PICK", 0, 1000), "r": ("WR", 23, 1000)},
        ["L_2027_1_1"], ["r"], {"L_2027_1_1": 800, "r": 1600}, {"L_2027_1_1": 1600, "r": 700},
        outlook="jets", pinned_receive_players=["r"])
    cards, _ = bilateral.generate_bilateral_trades(**kwargs)
    assert cards
    kwargs["manager_preferences"] = {"me": {"own_next_draft_pick_ids": ["L_2027_1_1"]}}
    assert bilateral.generate_bilateral_trades(**kwargs)[0] == []
    kwargs["pinned_give_players"] = ["L_2027_1_1"]
    assert bilateral.generate_bilateral_trades(**kwargs)[0]


def test_tanking_rb_exception_uses_canonical_personal_tier_not_fixed_elo():
    kwargs = world({"g": ("RB", 29, 1000), "r": ("RB", 23, 1000)},
        viewer={"g": 500, "r": 1500}, opponent={"g": 1500, "r": 500}, outlook="jets")
    # Explicitly identify the shared firsts_2 tier through its current bands.
    low, high = RankingService.tier_bands_for("RB", "1qb_ppr")["firsts_2"]
    kwargs["user_elo"]["r"] = (low + high) / 2
    c = bilateral.generate_bilateral_trades(**kwargs)[0][0]
    assert c.owner_evaluation.as_dict()["assets"][1]["viewer_preference"]["personal_tier"] == "firsts_2"


def test_budget_round_robins_partners_and_is_not_a_returned_offer_cap():
    kwargs = favorable(config={"owner_total_budget": 3, "owner_pair_budget": 2}, max_cards=0)
    kwargs["league"].members = [ts.LeagueMember(f"p{i}", str(i), ["r"],
        {"g": ts.value_to_elo(1200), "r": ts.value_to_elo(800)}, True) for i in range(3)]
    kwargs["opponent_outlooks"] = {f"p{i}": "not_sure" for i in range(3)}
    cards, report = bilateral.generate_bilateral_trades(**kwargs)
    assert len(cards) == 3
    assert set(report.as_dict()["per_opponent"]) == {f"p{i}" for i in range(3)}
    assert report.as_dict()["evaluated"] == 3


def test_dense_search_benchmark_is_bounded_and_private_evidence_is_consistent(capsys):
    spec = {f"{side}{i}": (("QB", "RB", "WR", "TE")[i % 4], 26, [500, 800, 1200, 1800][i % 4])
            for side in ("g", "r") for i in range(16)}
    give, receive = [f"g{i}" for i in range(16)], [f"r{i}" for i in range(16)]
    kwargs = world(spec, give, receive,
        {p: value * (.75 if p in give else 1.5) for p, (_, _, value) in spec.items()},
        {p: value * (1.5 if p in give else .75) for p, (_, _, value) in spec.items()})
    start = time.perf_counter()
    cards, report = bilateral.generate_bilateral_trades(**kwargs)
    elapsed = time.perf_counter() - start
    assert cards and len(cards) > 60
    assert report.as_dict()["evaluated"] <= 4096
    assert all(c.owner_evaluation.matches(c) for c in cards)
    assert all(c.owner_evaluation.as_dict()["bilateral"]["weaker_support"] >= .35 for c in cards)
    with capsys.disabled():
        print(json.dumps({"bilateral_dense_pair_seconds": round(elapsed, 3),
            "evaluated": report.as_dict()["evaluated"], "emitted": len(cards)}))
