"""Shared significance: individual tiers, pick identity, trusted intent and no caps.

Pure frozen inputs only: no DB, providers, live flags, ranking writes or imports
of the route module. Thresholds are sourced from the actual tier configuration.
"""

from types import SimpleNamespace

import pytest

from backend.ranking_service import RankingService
from backend.trade_significance import VERSION, evaluate_significance


def owned_pick_parser(pid, league_id):
    if not pid.startswith(league_id + "_"):
        return None
    parts = pid[len(league_id) + 1:].split("_")
    if len(parts) < 3:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def is_pick(player):
    return player.position == "PICK" or player.team == "PICK"


def player(pos="RB", team="BUF"):
    return SimpleNamespace(position=pos, team=team)


def card(give=("a",), receive=("b",), **kwargs):
    return SimpleNamespace(league_id="league_with_underlines", give_player_ids=list(give),
                           receive_player_ids=list(receive), **kwargs)


def evaluate(trade=None, **kwargs):
    args = dict(players={"a": player(), "b": player()}, user_elo={},
                seed_elo={"a": floor() - 1, "b": floor() - 1},
                owned_pick_parser=owned_pick_parser, is_pick_asset=is_pick)
    args.update(kwargs)
    return evaluate_significance(trade or card(), **args)


def floor(position="RB", fmt="1qb_ppr", tier="second"):
    return RankingService.tier_bands_for(position, fmt)[tier][0]


@pytest.mark.parametrize("fmt", ["1qb_ppr", "sf_tep"])
@pytest.mark.parametrize("position", ["QB", "RB", "WR", "TE"])
@pytest.mark.parametrize("basis", ["personal", "consensus"])
def test_exact_player_tier_boundary(fmt, position, basis):
    key = "user_elo" if basis == "personal" else "seed_elo"
    lo = floor(position, fmt)
    kwargs = {key: {"a": lo}, "players": {"a": player(position), "b": player()},
              "scoring_format": fmt}
    result = evaluate(**kwargs)
    assert result.eligible
    assert result.as_dict()["centerpiece"]["source"] == basis
    assert result.as_dict()["centerpiece"]["threshold_elo"] == lo
    kwargs[key]["a"] = lo - .001
    assert not evaluate(**kwargs).eligible


@pytest.mark.parametrize("source", ["explicit", "votes", "cross_format", "legacy"])
def test_valid_personal_provenance_can_qualify_below_market(source):
    result = evaluate(user_elo={"b": floor()}, user_sources={"b": source})
    assert result.eligible
    assert result.as_dict()["centerpiece"]["side"] == "receive"


@pytest.mark.parametrize("source", ["seed", "consensus_fallback", "unknown", None])
def test_seed_or_unknown_provenance_cannot_masquerade_as_personal(source):
    assert not evaluate(user_elo={"a": floor() + 100}, user_sources={"a": source}).eligible


def test_partial_board_uses_consensus_without_mutating_inputs():
    board, seeds = {"a": floor() - 100}, {"a": floor() - 100, "b": floor()}
    trade = card()
    before = dict(vars(trade))
    result = evaluate(trade, user_elo=board, seed_elo=seeds, user_sources={"a": "explicit"})
    assert result.as_dict()["centerpiece"]["source"] == "consensus"
    assert board == {"a": floor() - 100}
    assert vars(trade) == before


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -float("inf"), True, "2000"])
def test_invalid_board_values_never_qualify(bad):
    result = evaluate(user_elo={"a": bad}, seed_elo={"a": bad, "b": bad})
    assert not result.eligible
    assert result.reason == "no_meaningful_centerpiece"


def test_unknown_player_or_position_does_not_get_a_default_tier():
    for players in ({"b": player()}, {"a": player(None), "b": player()}):
        assert not evaluate(players=players, seed_elo={"a": 2000}).eligible


@pytest.mark.parametrize("pid,eligible", [
    ("generic_pick_1_early", True), ("generic_pick_1_late", True),
    ("generic_pick_2_early", False), ("generic_pick_1_unknown", False),
    ("league_with_underlines_2029_1_3", True),
    ("league_with_underlines_2029_2_3", False),
    ("league_with_underlines_2029_1_", False),
    ("other_league_2029_1_3", False),
    ("league_with_underlines_29_1_3", False),
    ("league_with_underlines_2029_0_3", False),
])
def test_pick_identity_not_display_position_or_large_valuation(pid, eligible):
    # Generic picks intentionally have a fake football position in the pool.
    players = {pid: player("RB", "PICK"), "b": player()}
    result = evaluate(card(give=(pid,)), players=players, seed_elo={pid: 2000})
    assert result.eligible is eligible
    if eligible:
        assert result.as_dict()["centerpiece"]["kind"] == "pick"


@pytest.mark.parametrize("bad", [None, 0, -1, True, float("nan"), float("inf")])
def test_unvalued_first_round_pick_cannot_qualify(bad):
    pid = "generic_pick_1_late"
    assert not evaluate(card(give=(pid,)), players={pid: player("PICK"), "b": player()},
                        seed_elo={pid: bad}).eligible


def test_first_pick_can_be_disabled_without_repricing():
    pid = "generic_pick_1_mid"
    assert not evaluate(card(give=(pid,)), players={pid: player("PICK"), "b": player()},
                        seed_elo={pid: 2000}, allow_first_round_pick=False).eligible


def test_pick_identity_conflicting_with_player_metadata_never_qualifies():
    pid = "league_with_underlines_2029_1_3"
    assert not evaluate(card(give=(pid,)), players={pid: player(), "b": player()},
                        seed_elo={pid: 2000}, user_elo={pid: 2000}).eligible


def test_no_sum_of_junk_and_no_package_or_offer_count_cap():
    ids = [str(i) for i in range(120)]
    players = {pid: player() for pid in ids}
    seeds = {pid: floor() - .1 for pid in ids}
    trade = card(give=ids[:60], receive=ids[60:])
    assert not evaluate(trade, players=players, seed_elo=seeds).eligible
    seeds["119"] = floor()
    assert evaluate(trade, players=players, seed_elo=seeds).eligible
    assert all(evaluate(trade, players=players, seed_elo=seeds).eligible for _ in range(120))


@pytest.mark.parametrize("context", ["manual", "inbound"])
def test_trusted_non_recommendation_context_is_exempt(context):
    assert evaluate(context=context).reason == "exempt_" + context


def test_card_markers_cannot_claim_exemption():
    trade = card(likes_you=True, context="inbound", significance_exempt=True)
    assert not evaluate(trade).eligible


@pytest.mark.parametrize("side", ["give", "receive"])
def test_explicit_asset_exception_requires_correct_side_overlap(side):
    kwargs = {"selected_" + side + "_ids": ["a" if side == "give" else "b"]}
    assert evaluate(context="explicit_search", **kwargs).reason == "exempt_selected_asset"
    assert not evaluate(context="discovery", **kwargs).eligible
    kwargs["selected_" + side + "_ids"] = ["b" if side == "give" else "a"]
    assert not evaluate(context="explicit_search", **kwargs).eligible
    assert not evaluate(context="explicit_search").eligible


def test_whole_selection_not_required_but_no_arbitrary_substitute_exemption():
    assert evaluate(context="explicit_search", selected_give_ids=["a", "omitted"]).eligible
    assert not evaluate(context="explicit_search", selected_give_ids=["substitute"]).eligible


def test_invalid_package_and_unknown_context_fail_closed():
    assert evaluate(card(give=())).reason == "invalid_package"
    assert evaluate(card(give=(None,))).reason == "invalid_package"
    assert evaluate(context="unknown").reason == "invalid_context"
    assert evaluate(player_min_tier="not_a_tier").reason == "invalid_threshold"


@pytest.mark.parametrize("setting", [None, float("nan"), float("inf"), True, [], {}])
def test_invalid_threshold_values_are_serializable_fail_closed(setting):
    assert evaluate(player_min_tier=setting).reason == "invalid_threshold"
    if type(setting) is not bool:
        assert evaluate(allow_first_round_pick=setting).reason == "invalid_threshold"


def test_threshold_setting_uses_tier_config_and_diagnostics_are_detached():
    result = evaluate(seed_elo={"a": floor()}, player_min_tier="first_1")
    assert not result.eligible
    record = result.as_dict()
    assert record["version"] == VERSION
    record["thresholds"]["player_min_tier"] = "waivers"
    assert result.as_dict()["thresholds"]["player_min_tier"] == "first_1"


def test_player_centerpiece_preferred_for_explanation_over_pick():
    pid = "generic_pick_1_mid"
    result = evaluate(card(give=(pid,)), players={pid: player("PICK"), "b": player()},
                      seed_elo={pid: 2000, "b": floor()})
    assert result.as_dict()["centerpiece"]["asset_id"] == "b"
