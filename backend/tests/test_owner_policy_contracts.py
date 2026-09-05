"""September 5 owner contracts: personal direction, method parity, partial boards.

Guards raw user-tier precedence independently of seasonal utility, consensus
fallback per missing entry, identical authority for deliberate ranking methods,
and market-priced companions. No network, production data or experiment changes.
"""

from types import SimpleNamespace

import pytest

from backend import feature_flags as ff, trade_policy as tp, trade_service as ts
from backend.tests.test_trade_intent_modes import _mk_card, _players, FMT


@pytest.fixture(autouse=True)
def isolate():
    flags, cfg = ff._flags_cache, dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = flags
        ts._cfg.clear()
        ts._cfg.update(cfg)


def test_personal_tiers_override_market_direction_with_per_entry_fallback():
    card = _mk_card(["give"], ["receive"])
    market = {"give": 1950., "receive": 1450.}
    personal = {"give": 1200.}  # Missing receive retains its consensus rung.
    assert ts._filter_by_trade_intent(
        [card], "tier_up", market, _players("give", "receive"), FMT,
        user_elo=personal) == [card]
    assert market == {"give": 1950., "receive": 1450.}


@pytest.mark.parametrize("source,count", [("explicit", 0), ("cross_format", 0),
                                           ("votes", 1), ("votes", 100)])
def test_deliberate_methods_have_equal_authority(source, count):
    assert tp.confidence_weight_for(count, source) == 1.


def test_mixed_partner_provenance_is_not_replaced_by_majority_source():
    weights = tp.confidence_map(
        {"placed": 0, "voted": 1, "copied": 0, "missing": 0},
        source="votes", weights={"voted": .2, "copied": .75},
        sources={"placed": "explicit", "voted": "votes",
                 "copied": "cross_format", "missing": "seed"})
    assert weights == {"placed": 1., "voted": 1., "copied": 1., "missing": 0.}
    board = tp.shrink_board(
        {"placed": 1900., "voted": 1800., "copied": 1700., "missing": 2000.},
        {"placed": 1500., "voted": 1500., "copied": 1500., "missing": 1500.},
        weights)
    assert board == {"placed": 1900., "voted": 1800., "copied": 1700., "missing": 1500.}


def test_policy_board_preserves_deliberate_entries_without_sample_count_discount():
    personal = {"voted": 1800., "placed": 1900., "untouched": 1700.}
    seed = {"voted": 1500., "placed": 1500., "untouched": 1500.}
    weights = tp.confidence_map(
        {"voted": 1}, sources={"voted": "votes", "placed": "explicit"})
    assert tp.shrink_board(
        personal, seed, weights, placements={"placed": (1800., 2000.)}) == {
            "voted": 1800., "placed": 1900., "untouched": 1500.}


def _ideas(personal, *, direction="give", scope="tier", **kw):
    players = {p: SimpleNamespace(id=p, name=p, position=pos, age=25,
                                 team="TST", pick_value=None)
               for p, pos in [("give", "RB"), ("receive", "WR")]}
    svc = ts.TradeService(players)
    svc.add_league(ts.League(league_id="L", name="L", platform="demo",
        members=[ts.LeagueMember(user_id="partner", username="P",
                                roster=["receive"], elo_ratings={})]))
    return svc.generate_asset_ideas(
        user_id="viewer", user_roster=["give"], league_id="L",
        seed_elo={"give": 1500., "receive": 1750.},
        raw_user_elo=personal, asset_id="give" if direction == "give" else "receive",
        direction=direction, lateral_scope=scope, **kw)


@pytest.mark.parametrize("direction", ["give", "receive"])
def test_same_value_uses_personal_tiers_but_keeps_market_prices(direction):
    groups = _ideas({"give": 1750.}, direction=direction,
                   swap_positions=["WR" if direction == "give" else "RB"])
    assert len(groups["lateral"]) == 1
    idea = groups["lateral"][0]
    assert idea["give_value"] == ts.elo_to_value(1500.)
    assert idea["receive_value"] == round(ts.elo_to_value(1750.), 1)


def test_same_market_tier_does_not_override_different_personal_tiers():
    assert not _ideas({"give": 1200., "receive": 1750.})["lateral"]


def test_explicit_position_selection_remains_a_filter():
    assert not _ideas({"give": 1750.}, swap_positions=["RB"])["lateral"]


def test_pair_policy_falls_back_per_missing_entry_on_each_board(monkeypatch):
    """Exercise the real pair seam without replacing either partial board.
    Snapshot callbacks retain missing-entry source weights of zero."""
    seed = {"a": 1400., "b": 1500., "c": 1600.}
    personal = {"b": 1800.}
    member = ts.LeagueMember(
        user_id="partner", username="P", roster=["a"],
        has_rankings=True, elo_ratings={"a": 1900.},
        confidence_sources={"a": "explicit"})
    monkeypatch.setattr(tp, "evaluate_trade_policy", lambda **kw: kw)
    consensus = lambda pid: ts.elo_to_value(seed[pid])
    evaluator = tp.make_pair_evaluator(
        consensus_value=consensus, viewer_effective_value=None,
        viewer_raw_value=None, viewer_confidence_of=None,
        opponent=member, seed_elo=seed, requested_floor=.75,
        viewer_elo=personal, viewer_counts={"b": 1}, force=True)
    bound = evaluator(["b"], ["a"])
    assert bound["viewer_effective_value"]("b") == ts.elo_to_value(1800.)
    assert bound["viewer_effective_value"]("a") == consensus("a")
    assert bound["partner_effective_value"]("a") == ts.elo_to_value(1900.)
    assert bound["partner_effective_value"]("b") == consensus("b")
    assert bound["viewer_confidence_of"]("a") == 0.
    assert bound["partner_confidence_of"]("b") == 0.
    assert personal == {"b": 1800.}
    assert member.elo_ratings == {"a": 1900.}


@pytest.mark.parametrize("outlook", ["championship", "contending", "rebuilding", "jets"])
def test_seasonal_outlook_does_not_redefine_tier_up(monkeypatch, outlook):
    """The final mode filter receives the raw board, not adjusted utility."""
    ff._flags_cache.update({"trade_engine.v2": True, "trades.intent_modes": True})
    card = _mk_card(["give"], ["receive"])
    svc = ts.TradeService(_players("give", "receive"))
    svc.add_league(ts.League(league_id="L1", name="L1", platform="demo", members=[]))
    monkeypatch.setattr(svc, "_generate_trades_v2", lambda **kw: [card])
    with ts.stud_tax_override("market"):
        cards = svc.generate_trades(
            user_id="user", user_elo={"give": 1200., "receive": 1950.},
            user_roster=["give"], league_id="L1",
            seed_elo={"give": 1950., "receive": 1200.},
            trade_intent="tier_up", outlook=outlook)
    assert cards == [card]


@pytest.mark.parametrize("adapter", ["gen_v2", "gen_fit"])
def test_direct_bakeoff_adapter_uses_the_same_personal_direction(monkeypatch, adapter):
    """Adapters bypass TradeService generation but must keep its mode contract."""
    from backend import bakeoff_runner, trade_gen_v2, trade_gen_fit
    ff._flags_cache["trades.intent_modes"] = True
    card = _mk_card(["give"], ["receive"])
    svc = ts.TradeService(_players("give", "receive"))
    svc.add_league(ts.League(league_id="L1", name="L1", platform="demo", members=[]))
    module = trade_gen_v2 if adapter == "gen_v2" else trade_gen_fit
    monkeypatch.setattr(module, "generate_league_suggestions", lambda **kw: ([card], {}))
    kwargs = dict(user_id="user", league_id="L1", user_roster=["give"],
                  user_elo={"give": 1200., "receive": 1950.},
                  seed_elo={"give": 1950., "receive": 1200.}, trade_intent="tier_up")
    with ts.stud_tax_override("market"):
        cards = getattr(bakeoff_runner, adapter + "_cards")(svc, kwargs)
    assert cards == [card]
