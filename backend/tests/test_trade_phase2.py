"""Interview phase 2 (docs/plans/trade-logic-interview-2026-07-17.md):
two-lane labels, fit-premium flagged cards, aggression A/B buckets, and
the outlook label/value decoupling.

Flags/_cfg snapshot-restored per test (same fixture pattern as the other
trade-engine test modules).
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League, LeagueMember, TradeService, aggression_variant, classify_lane,
    elo_to_value, fit_premium_1for1,
)


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _set(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


class _Player:
    def __init__(self, pid, position="RB", age=25):
        self.id = pid
        self.name = pid
        self.position = position
        self.age = age
        self.team = "TST"
        self.search_rank = 50
        self.pick_value = 67.5 if position == "PICK" else None


# ───────────────────────── classify_lane ─────────────────────────


def test_lane_none_without_window():
    players = {"A": _Player("A", "RB", 29), "B": _Player("B", "WR", 22)}
    v = lambda pid: 1000.0
    assert classify_lane(["B"], ["A"], players, None, v) is None
    assert classify_lane(["B"], ["A"], players, "not_sure", v) is None


def test_lane_contender_buying_vets_is_window():
    # Contender receives an aging RB (now-lean strongly +) for a 22yo WR
    # (now-lean −): clearly a window move for a contender...
    players = {"OLD": _Player("OLD", "RB", 29), "YNG": _Player("YNG", "WR", 22)}
    v = lambda pid: 1000.0
    assert classify_lane(["YNG"], ["OLD"], players, "contender", v) == "window"
    # ...and the same trade for a rebuilder points AGAINST their window.
    assert classify_lane(["YNG"], ["OLD"], players, "rebuilder", v) == "value"
    # Mirrored direction: rebuilder selling the vet for youth = window move.
    assert classify_lane(["OLD"], ["YNG"], players, "rebuilder", v) == "window"


def test_lane_picks_count_as_future_capital():
    # Rebuilder trading a 27yo WR for a pick: pure future acquisition.
    players = {"VET": _Player("VET", "WR", 27), "PK": _Player("PK", "PICK", 0)}
    v = lambda pid: 1500.0
    assert classify_lane(["VET"], ["PK"], players, "rebuilder", v) == "window"
    assert classify_lane(["VET"], ["PK"], players, "contender", v) == "value"


def test_lane_age_neutral_trade_is_value():
    # Two 25-year-old same-position players: no composition shift.
    players = {"A": _Player("A", "WR", 25), "B": _Player("B", "WR", 25)}
    v = lambda pid: 1000.0
    assert classify_lane(["A"], ["B"], players, "contender", v) == "value"


# ───────────────────────── fit_premium_1for1 ─────────────────────────

# Raw board: give G (Elo 1600) > receive R (Elo 1580) — #108 would block.
_RAW = {"G": 1600.0, "R": 1580.0}


def _fit_players(recv_pos="WR", give_pos="RB"):
    return {"G": _Player("G", give_pos), "R": _Player("R", recv_pos)}


def test_fit_premium_flag_off_keeps_108_block():
    ok, paid = fit_premium_1for1(["G"], ["R"], _RAW, _fit_players(), {"WR"})
    assert (ok, paid) == (False, None)


def test_fit_premium_allows_small_loss_into_need():
    _set(**{"trade.fit_premium": True})
    ok, paid = fit_premium_1for1(["G"], ["R"], _RAW, _fit_players(), {"WR"})
    assert ok
    expected = elo_to_value(1600.0) - elo_to_value(1580.0)
    assert paid == pytest.approx(expected, abs=0.1)


def test_fit_premium_rejects_off_need_and_need_for_need():
    _set(**{"trade.fit_premium": True})
    # Receive position is not a need → still blocked.
    ok, _ = fit_premium_1for1(["G"], ["R"], _RAW, _fit_players(), {"TE"})
    assert not ok
    # Give position is itself a need → never pay to rob one need for another.
    ok, _ = fit_premium_1for1(["G"], ["R"], _RAW,
                              _fit_players(give_pos="WR"), {"WR"})
    assert not ok


def test_fit_premium_caps_the_loss():
    _set(**{"trade.fit_premium": True})
    big_gap = {"G": 1700.0, "R": 1500.0}   # ~1418 value gap >> 300 cap
    ok, _ = fit_premium_1for1(["G"], ["R"], big_gap, _fit_players(), {"WR"})
    assert not ok


def test_fit_premium_no_premium_when_gate_passes():
    _set(**{"trade.fit_premium": True})
    raw = {"G": 1500.0, "R": 1600.0}       # plain gain — no flag
    ok, paid = fit_premium_1for1(["G"], ["R"], raw, _fit_players(), {"WR"})
    assert (ok, paid) == (True, None)


# ───────────────────────── aggression buckets ─────────────────────────


def test_aggression_variant_stable_and_covers_buckets():
    assert aggression_variant("user_x") == aggression_variant("user_x")
    seen = {aggression_variant(f"u{i}") for i in range(50)}
    assert seen == {"light", "fair", "generous"}


def _run_pair(flags):
    """1-for-1 divergence fixture; returns the single surfaced card."""
    _set(**flags)
    players = {"G": _Player("G", "RB", 25), "R": _Player("R", "WR", 25)}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={"G": 1700, "R": 1500}, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    cards = svc.generate_trades(
        user_id="user", user_elo={"G": 1500, "R": 1700}, user_roster=["G"],
        league_id="L1", seed_elo={"G": 1540, "R": 1500},
        fairness_threshold=0.05)
    return cards


def test_aggression_stamps_variant_on_cards():
    cards = _run_pair({"trade_engine.v2": True, "trade.aggression_ab": True})
    assert cards, "fixture should surface a card"
    expected = aggression_variant("user")
    assert all(c.aggression_variant == expected for c in cards)


def test_aggression_off_leaves_cards_unstamped():
    cards = _run_pair({"trade_engine.v2": True})
    assert cards and all(c.aggression_variant is None for c in cards)


# ───────────────────────── outlook label decoupling ─────────────────────────


def test_opponent_outlook_label_without_value_blend():
    """With trade.outlook_infer ON and trade.outlook_blend OFF (the phase-2
    posture), match_context still carries the opponent's window label."""
    cards = _run_pair({"trade_engine.v2": True, "trade.outlook_infer": True})
    assert cards
    assert "opponent_outlook" in (cards[0].match_context or {}), (
        "outlook label should be stamped even when the value blend is off")


# ───────────────────────── #156 Specific Team scope ─────────────────────────


def _two_opponent_league():
    players = {
        "G": _Player("G", "RB", 25),
        "R1": _Player("R1", "WR", 25),
        "R2": _Player("R2", "WR", 25),
    }
    opp1 = LeagueMember(user_id="opp1", username="opp1", roster=["R1"],
                        elo_ratings={"G": 1700, "R1": 1500}, has_rankings=True)
    opp2 = LeagueMember(user_id="opp2", username="opp2", roster=["R2"],
                        elo_ratings={"G": 1700, "R2": 1500}, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp1, opp2]))
    return svc


def _gen(svc, **extra):
    return svc.generate_trades(
        user_id="user",
        user_elo={"G": 1500, "R1": 1700, "R2": 1700},
        user_roster=["G"], league_id="L1",
        seed_elo={"G": 1540, "R1": 1500, "R2": 1500},
        fairness_threshold=0.05, **extra)


def test_opponent_scope_limits_generation_to_one_leaguemate():
    """#156 Specific Team — opponent_user_id restricts the sweep to that one
    league-mate; unset keeps the full league-wide sweep."""
    _set(**{"trade_engine.v2": True})
    all_cards = _gen(_two_opponent_league())
    assert {c.target_user_id for c in all_cards} == {"opp1", "opp2"}, (
        "unscoped generation should reach every eligible opponent")

    scoped = _gen(_two_opponent_league(), opponent_user_id="opp1")
    assert scoped, "scoped generation should still surface a card"
    assert {c.target_user_id for c in scoped} == {"opp1"}, (
        "scoping to opp1 must exclude opp2's cards")


def test_lane_stamped_via_orchestrator():
    _set(**{"trade_engine.v2": True, "trade.lanes": True})
    players = {"OLD": _Player("OLD", "RB", 29), "YNG": _Player("YNG", "WR", 22)}
    opp = LeagueMember(user_id="opp", username="opp", roster=["OLD"],
                       elo_ratings={"YNG": 1700, "OLD": 1500},
                       has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    cards = svc.generate_trades(
        user_id="user", user_elo={"YNG": 1500, "OLD": 1700},
        user_roster=["YNG"], league_id="L1",
        seed_elo={"YNG": 1540, "OLD": 1500},
        fairness_threshold=0.05, outlook="contender")
    assert cards
    assert all(c.lane in ("window", "value") for c in cards)
    # User sends the young WR for the aging RB — a contender window move.
    assert cards[0].lane == "window"
