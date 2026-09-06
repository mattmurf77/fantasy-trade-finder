"""Independent owner-answer acceptance cases for actual package construction.

These are black-box tests of the public generator, not assertions about its
sorting helper. All players, rankings and leagues are synthetic; there is no
database, provider, session, or production access in this module.
"""

from copy import deepcopy

import pytest

from backend import feature_flags as ff, trade_service as ts
from backend.ranking_service import Player
from backend.trade_gen_owner import generate_owner_trades


@pytest.fixture(autouse=True)
def isolated_model_state():
    original_flags, original_cfg = ff._flags_cache, dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    # Age re-pricing is not the subject of these rank/price comparisons.
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)
    try:
        yield
    finally:
        ff._flags_cache = original_flags
        ts._cfg.clear()
        ts._cfg.update(original_cfg)


def _fixture(*, own=("give",), other=("alpha", "beta"), seed=None,
             viewer=None, partner=None, positions=None, ages=None):
    ids = sorted(set(own) | set(other))
    market = seed or {pid: 1600.0 for pid in ids}
    players = {
        pid: Player(id=pid, name=pid, position=(positions or {}).get(pid, "WR"),
                    team="TST", age=(ages or {}).get(pid, 25))
        for pid in ids
    }
    viewer = dict(viewer if viewer is not None else market)
    partner = dict(partner if partner is not None else market)
    member = ts.LeagueMember(
        user_id="partner", username="Partner", roster=list(other),
        elo_ratings=partner, has_rankings=bool(partner),
        confidence_sources={pid: "explicit" for pid in partner})
    league = ts.League(
        league_id="synthetic_owner_acceptance", name="Synthetic acceptance",
        platform="sleeper", members=[member])
    return dict(
        players=players, league=league, user_id="viewer", user_roster=list(own),
        user_elo=viewer, seed_elo=dict(market), fairness_threshold=0.75,
        user_sources={pid: "explicit" for pid in viewer},
        scoring_format="1qb_ppr", outlook="not_sure", max_cards=100)


def _packages(cards):
    return {(c.target_user_id, frozenset(c.give_player_ids),
             frozenset(c.receive_player_ids)) for c in cards}


def _swap(give, receive, partner="partner"):
    return partner, frozenset(give), frozenset(receive)


def test_changing_who_i_want_changes_the_candidate_universe_not_just_order():
    args = _fixture(viewer={"give": 1600., "alpha": 1850., "beta": 1350.},
                    partner={"give": 1850., "alpha": 1500., "beta": 1500.})
    first, _ = generate_owner_trades(**args)
    second, _ = generate_owner_trades(**{
        **args, "user_elo": {"give": 1600., "alpha": 1350., "beta": 1850.}})

    first_set, second_set = _packages(first), _packages(second)
    assert _swap(["give"], ["alpha"]) in first_set
    assert _swap(["give"], ["beta"]) not in first_set
    assert _swap(["give"], ["beta"]) in second_set
    assert _swap(["give"], ["alpha"]) not in second_set
    assert first_set != second_set


def test_stronger_personal_conviction_does_not_reprice_the_same_package():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1600., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    first, _ = generate_owner_trades(**args)
    second, _ = generate_owner_trades(**{
        **args, "user_elo": {"give": 1600., "alpha": 2200.}})
    assert _packages(first) == _packages(second) == {_swap(["give"], ["alpha"])}
    assert first[0].give_value == second[0].give_value
    assert first[0].receive_value == second[0].receive_value
    assert first[0].fairness_score == second[0].fairness_score


@pytest.mark.parametrize("source", ["votes", "explicit", "cross_format"])
def test_deliberate_ranking_methods_generate_the_same_packages(source):
    args = _fixture(other=("alpha",),
                    viewer={"give": 1500., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    expected, _ = generate_owner_trades(**args)
    actual, _ = generate_owner_trades(**{
        **args, "user_sources": {pid: source for pid in args["user_elo"]}})
    assert _packages(actual) == _packages(expected) == {_swap(["give"], ["alpha"])}


def test_partial_personal_boards_do_not_require_a_shared_player_intersection():
    # Each manager has expressed only an acquisition preference. The assets
    # each gives away are absent from their own board and use consensus.
    args = _fixture(other=("alpha",), viewer={"alpha": 1800.},
                    partner={"give": 1800.})
    cards, _ = generate_owner_trades(**args)
    assert _swap(["give"], ["alpha"]) in _packages(cards)


def test_seed_only_rows_cannot_masquerade_as_strong_personal_preference():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1600., "alpha": 2500.},
                    partner={"give": 1800., "alpha": 1500.})
    explicit, _ = generate_owner_trades(**args)
    seeded, _ = generate_owner_trades(**{
        **args, "user_sources": {"give": "explicit", "alpha": "seed"}})
    missing, _ = generate_owner_trades(**{
        **args, "user_elo": {"give": 1600.},
        "user_sources": {"give": "explicit"}})
    assert explicit
    assert _packages(seeded) == _packages(missing)


def test_personal_conviction_never_bypasses_market_safety():
    args = _fixture(other=("alpha",), seed={"give": 2000., "alpha": 1400.},
                    viewer={"give": 1400., "alpha": 2400.},
                    partner={"give": 2400., "alpha": 1400.})
    cards, _ = generate_owner_trades(**args)
    assert cards == []


def test_stricter_account_fairness_cannot_add_an_unfair_package():
    args = _fixture(other=("alpha",), seed={"give": 1600., "alpha": 1575.},
                    viewer={"give": 1400., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1400.})
    broad, _ = generate_owner_trades(**args)
    strict, _ = generate_owner_trades(**{**args, "fairness_threshold": 0.99})
    assert broad
    assert _packages(strict) <= _packages(broad)
    assert strict == []


def test_every_unselected_offer_is_one_for_one_or_two_for_one_in_assets():
    args = _fixture(
        own=("g1", "g2", "g3", "g4"), other=("r1", "r2", "r3", "r4"),
        viewer={**{f"g{i}": 1500. for i in range(1, 5)},
                **{f"r{i}": 1800. for i in range(1, 5)}},
        partner={**{f"g{i}": 1800. for i in range(1, 5)},
                 **{f"r{i}": 1500. for i in range(1, 5)}})
    cards, _ = generate_owner_trades(**args)
    assert cards
    assert all((len(c.give_player_ids), len(c.receive_player_ids))
               in {(1, 1), (1, 2), (2, 1)} for c in cards)


def test_exact_send_canvas_and_feasible_get_selection_are_both_preserved():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1500., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    cards, _ = generate_owner_trades(**{
        **args, "pinned_give_players": ["give"], "pinned_receive_players": ["alpha"],
        "exact_give": True})
    assert _packages(cards) == {_swap(["give"], ["alpha"])}


def test_specific_partner_cannot_silently_expand_to_a_different_owner():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1500., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    cards, _ = generate_owner_trades(**{**args, "opponent_user_id": "someone_else"})
    assert cards == []


def test_all_in_manager_can_trade_dynasty_value_for_usable_production():
    # Both real boards use the market values here. This is a dynasty loss
    # for the viewer, not a fabricated personal arbitrage, but exchanging a
    # future pick for a starting-age RB fits the declared opposing outlooks.
    args = _fixture(
        own=("future_first",), other=("starting_rb",),
        seed={"future_first": 1600., "starting_rb": 1580.},
        positions={"future_first": "PICK", "starting_rb": "RB"},
        ages={"future_first": 0, "starting_rb": 26})
    cards, _ = generate_owner_trades(**{
        **args, "outlook": "championship",
        "opponent_outlooks": {"partner": "rebuilder"}})
    assert _swap(["future_first"], ["starting_rb"]) in _packages(cards)
    card = next(c for c in cards if c.receive_player_ids == ["starting_rb"])
    assert card.give_value > card.receive_value


def test_chasing_is_not_a_universal_receive_position_veto():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1500., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    cards, _ = generate_owner_trades(**{**args, "acquire_positions": ["RB"]})
    # A clear beneficial WR-for-WR remains available while chasing RB.
    assert _swap(["give"], ["alpha"]) in _packages(cards)


def test_a_deliberately_selected_untouchable_does_not_refuse_the_search():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1500., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    prefs = {"viewer": {"untouchables": ["give"]}}
    before = deepcopy(prefs)
    cards, _ = generate_owner_trades(**{
        **args, "manager_preferences": prefs,
        "pinned_give_players": ["give"], "exact_give": True})
    assert _swap(["give"], ["alpha"]) in _packages(cards)
    assert prefs == before


def test_meaningful_personal_upgrade_within_one_broad_tier_is_constructed():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1450., "alpha": 1500.},
                    partner={"give": 1800., "alpha": 1400.})
    cards, _ = generate_owner_trades(**{**args, "trade_intent": "tier_up"})
    assert _swap(["give"], ["alpha"]) in _packages(cards)
    context = cards[0].owner_evaluation.as_dict()
    assert context["personal_tiers"]["give"] == context["personal_tiers"]["receive"]
    assert context["direction"] == "upgrade"


def test_exhausted_full_package_returns_only_explicitly_marked_partial_alternatives():
    args = _fixture(own=("g1", "g2"), other=("alpha",),
                    viewer={"g1": 1400., "g2": 1400., "alpha": 2000.},
                    partner={"g1": 1800., "g2": 1800., "alpha": 1400.})
    cards, _ = generate_owner_trades(**{
        **args, "pinned_give_players": ["g1", "g2"], "pinned_receive_players": ["alpha"]})
    assert cards
    for card in cards:
        selection = card.owner_evaluation.as_dict()["selection"]
        assert selection["coverage"] == "partial"
        assert set(selection["give"]["requested"]) == {"g1", "g2"}
        assert len(selection["give"]["included"]) == 1
        assert len(selection["give"]["omitted"]) == 1
        assert selection["receive"]["included"] == ["alpha"]
        assert selection["receive"]["omitted"] == []


def test_frozen_evaluation_cannot_be_reused_after_package_or_price_changes():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1500., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    cards, _ = generate_owner_trades(**args)
    card = cards[0]
    decision = card.owner_evaluation
    assert decision.matches(card)
    detached = decision.as_dict()
    detached["viewer"]["utility"] = -999
    assert decision.as_dict()["viewer"]["utility"] > 0
    card.give_value += 1
    assert not decision.matches(card)
    card.give_value -= 1
    card.receive_player_ids.append("not_in_original_package")
    assert not decision.matches(card)


def test_unknown_or_wrong_owner_send_selection_never_creates_a_trade():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1500., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    for bad_give in ("unknown", "alpha"):
        cards, _ = generate_owner_trades(**{
            **args, "pinned_give_players": [bad_give], "exact_give": True})
        assert cards == []


def test_search_is_pure_and_does_not_rewrite_rankings_rosters_or_preferences():
    args = _fixture(other=("alpha",),
                    viewer={"give": 1500., "alpha": 1800.},
                    partner={"give": 1800., "alpha": 1500.})
    before = deepcopy(args)
    first, _ = generate_owner_trades(**args)
    second, _ = generate_owner_trades(**args)
    assert _packages(first) == _packages(second)
    assert args["user_elo"] == before["user_elo"]
    assert args["seed_elo"] == before["seed_elo"]
    assert args["user_roster"] == before["user_roster"]
    assert args["user_sources"] == before["user_sources"]
    assert args["league"].members == before["league"].members
