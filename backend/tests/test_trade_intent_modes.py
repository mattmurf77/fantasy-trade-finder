"""#172 — trade intent modes (flag trades.intent_modes): "I want to
consolidate / I want to tier up / I want to tier down".

Covers:
  (a) _best_tier_idx / _filter_by_trade_intent unit semantics — candidate
      TradeCards of known shapes/tiers, asserting keep/drop per intent
  (b) generate_trades wiring (v2 AND legacy paths): flag on honors
      trade_intent, flag off is a byte-identical no-op even when the
      caller passes a value
  (c) an intent that filters every candidate out returns a clean, honest
      empty list (never an exception, never a silent relaxed-gate rescue)

Flags/_cfg snapshot-restored per test (same fixture pattern as the other
trade-engine test modules, e.g. test_trade_phase2.py).
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.ranking_service import ORDERED_TIERS
from backend.trade_service import (
    League, LeagueMember, TradeCard, TradeService,
    _best_tier_idx, _filter_by_trade_intent,
)

FMT = "1qb_ppr"


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
    def __init__(self, pid, position="RB"):
        self.id = pid
        self.name = pid
        self.position = position
        self.age = 25
        self.team = "TST"


# Concrete RB/WR 1qb_ppr tier bands (backend/tier_config.json — RB and WR
# share the same bands in this format):
#   firsts_4plus >= 1927, second 1400-1575, waivers 1150-1215, < 1150 unranked
ELITE    = 1950.0   # firsts_4plus
MID      = 1450.0   # second
LOW      = 1200.0   # waivers
UNRANKED = 1000.0   # below every band -> None


def _players(*ids):
    return {pid: _Player(pid) for pid in ids}


def _mk_card(give, recv):
    return TradeCard(
        trade_id=f"{'-'.join(give)}_for_{'-'.join(recv)}",
        league_id="L1", proposing_user_id="user", target_user_id="opp",
        target_username="opp",
        give_player_ids=list(give), receive_player_ids=list(recv),
        mismatch_score=100.0, fairness_score=0.9, composite_score=90.0,
    )


# ─────────────────────────── _best_tier_idx ───────────────────────────

def test_best_tier_idx_picks_the_best_asset_on_a_side():
    seed = {"a": LOW, "b": ELITE}
    idx = _best_tier_idx(["a", "b"], seed, _players("a", "b"), FMT)
    assert idx == ORDERED_TIERS.index("firsts_4plus")


def test_best_tier_idx_unranked_sinks_below_every_real_tier():
    seed = {"a": UNRANKED}
    assert _best_tier_idx(["a"], seed, _players("a"), FMT) == len(ORDERED_TIERS)


# ────────────────────────── _filter_by_trade_intent ──────────────────────────

def test_none_intent_is_a_no_op():
    cards = [_mk_card(["a"], ["b"])]
    assert _filter_by_trade_intent(cards, None, {}, {}, FMT) == cards


def test_unknown_intent_value_is_a_no_op():
    cards = [_mk_card(["a"], ["b"])]
    assert _filter_by_trade_intent(cards, "bogus", {}, {}, FMT) == cards


def test_consolidate_requires_more_pieces_out_and_quality_upgrade():
    players = _players("a", "b", "c")

    # 2 low pieces out for 1 elite piece in -> shape + upgrade both hold.
    seed = {"a": LOW, "b": LOW, "c": ELITE}
    keep = _mk_card(["a", "b"], ["c"])
    assert _filter_by_trade_intent([keep], "consolidate", seed, players, FMT) == [keep]

    # Same 2-for-1 shape, but flat tiers -> no quality upgrade -> dropped.
    seed_flat = {"a": MID, "b": MID, "c": MID}
    flat = _mk_card(["a", "b"], ["c"])
    assert _filter_by_trade_intent([flat], "consolidate", seed_flat, players, FMT) == []

    # Quality upgrade present, but WRONG shape (receiving more than giving)
    # -> dropped even though the tier condition alone would pass.
    reverse = _mk_card(["c"], ["a", "b"])
    assert _filter_by_trade_intent([reverse], "consolidate", seed, players, FMT) == []


def test_tier_up_ignores_piece_count():
    players = _players("a", "b", "c")

    # 1-for-1 quality upgrade.
    seed = {"a": LOW, "b": ELITE}
    one_for_one = _mk_card(["a"], ["b"])
    assert _filter_by_trade_intent([one_for_one], "tier_up", seed, players, FMT) == [one_for_one]

    # Sending MORE for a quality upgrade still counts — piece count is
    # irrelevant to tier_up per spec.
    seed2 = {"a": LOW, "c": LOW, "b": ELITE}
    two_for_one = _mk_card(["a", "c"], ["b"])
    assert _filter_by_trade_intent([two_for_one], "tier_up", seed2, players, FMT) == [two_for_one]

    # Flat tiers both sides -> no upgrade -> dropped.
    flat_seed = {"a": MID, "b": MID}
    flat = _mk_card(["a"], ["b"])
    assert _filter_by_trade_intent([flat], "tier_up", flat_seed, players, FMT) == []


def test_tier_down_requires_more_pieces_in_and_quality_downgrade():
    players = _players("a", "b", "c")

    # Send 1 elite piece, receive 2 lesser pieces -> shape + downgrade hold.
    seed = {"a": ELITE, "b": LOW, "c": LOW}
    keep = _mk_card(["a"], ["b", "c"])
    assert _filter_by_trade_intent([keep], "tier_down", seed, players, FMT) == [keep]

    # Same shape, flat tiers -> no downgrade -> dropped.
    seed_flat = {"a": MID, "b": MID, "c": MID}
    flat = _mk_card(["a"], ["b", "c"])
    assert _filter_by_trade_intent([flat], "tier_down", seed_flat, players, FMT) == []

    # Quality downgrade present, but WRONG shape (giving more than
    # receiving) -> dropped even though the tier condition alone would pass.
    reverse = _mk_card(["b", "c"], ["a"])
    assert _filter_by_trade_intent([reverse], "tier_down", seed, players, FMT) == []


# ───────────────────────── generate_trades wiring (v2) ─────────────────────────

def _v2_league():
    players = {"G": _Player("G", "RB"), "R": _Player("R", "WR")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={"G": 1700, "R": 1500}, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return svc


def _v2_gen(svc, seed_elo, **extra):
    return svc.generate_trades(
        user_id="user", user_elo={"G": 1500, "R": 1700}, user_roster=["G"],
        league_id="L1", seed_elo=seed_elo, fairness_threshold=0.05, **extra)


# Flat consensus tiers (G and R both land in RB/WR "second") — the fixture's
# one candidate is neither an upgrade nor a downgrade either direction.
_FLAT_SEED = {"G": 1540.0, "R": 1500.0}


def _card_key(c: TradeCard) -> tuple:
    """Stable identity for a card (trade_id is a fresh uuid every run)."""
    return (c.target_user_id, tuple(sorted(c.give_player_ids)),
            tuple(sorted(c.receive_player_ids)))


def test_flag_off_ignores_trade_intent_byte_identical():
    _set(**{"trade_engine.v2": True})
    without = _v2_gen(_v2_league(), _FLAT_SEED)
    with_intent = _v2_gen(_v2_league(), _FLAT_SEED, trade_intent="tier_up")
    assert without, "fixture should surface a card"
    assert {_card_key(c) for c in without} == {_card_key(c) for c in with_intent}


def test_flag_on_keeps_personal_upgrade_even_when_market_tiers_are_flat():
    _set(**{"trade_engine.v2": True, "trades.intent_modes": True})
    baseline = _v2_gen(_v2_league(), _FLAT_SEED)
    assert baseline, "fixture should surface a card before filtering"

    filtered = _v2_gen(_v2_league(), _FLAT_SEED, trade_intent="tier_up")
    assert filtered
    assert {_card_key(c) for c in filtered} == {_card_key(c) for c in baseline}


def test_flag_on_keeps_a_genuine_tier_up_trade():
    _set(**{"trade_engine.v2": True, "trades.intent_modes": True})
    # G stays "second" (RB), R nudges one tier up into "first_1" (WR) — a
    # small consensus gap (still clears the fairness gate) that is a real
    # tier-up per RankingService.tier_for_elo.
    seed = {"G": 1540.0, "R": 1585.0}
    cards = _v2_gen(_v2_league(), seed, trade_intent="tier_up")
    assert cards, "a genuine tier-up trade must survive the filter"


# ─────────────────────── generate_trades wiring (legacy) ───────────────────────

# Legacy-parity fixture (mirrors test_trade_engine_v2.py's _parity_setup):
# 7v7 with clear divergence, flat 1500 consensus seed for every asset —
# yields several 1-for-1 cards in the legacy path, all flat-tier.
_IDS_PARITY = [f"u{i}" for i in range(1, 8)] + [f"o{i}" for i in range(1, 8)]
_USER_ELO_PARITY = {
    "u1": 1720, "u2": 1680, "u3": 1560, "u4": 1490, "u5": 1430, "u6": 1380, "u7": 1300,
    "o1": 1420, "o2": 1390, "o3": 1530, "o4": 1480, "o5": 1420, "o6": 1370, "o7": 1290,
}
_OPP_ELO_PARITY = {
    "u1": 1800, "u2": 1760, "u3": 1540, "u4": 1470, "u5": 1420, "u6": 1360, "u7": 1290,
    "o1": 1710, "o2": 1690, "o3": 1540, "o4": 1480, "o5": 1430, "o6": 1370, "o7": 1300,
}
_SEED_PARITY = {pid: 1500.0 for pid in _IDS_PARITY}


def _legacy_gen(**extra):
    players = {pid: _Player(pid) for pid in _IDS_PARITY}
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=[f"o{i}" for i in range(1, 8)],
                       elo_ratings=dict(_OPP_ELO_PARITY), has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return svc.generate_trades(
        user_id="user", user_elo=dict(_USER_ELO_PARITY),
        user_roster=[f"u{i}" for i in range(1, 8)], league_id="L1",
        seed_elo=dict(_SEED_PARITY), **extra)


def test_legacy_path_also_applies_the_intent_filter():
    """trade_engine.v2 left at its default (off) exercises the legacy
    generation branch — the filter must be wired there too, not just v2."""
    _set(**{"trades.intent_modes": True})
    baseline = _legacy_gen()
    assert baseline, "legacy fixture should surface a card before filtering"
    assert all(len(c.give_player_ids) == 1 and len(c.receive_player_ids) == 1
              for c in baseline), "fixture assumption: legacy cards are 1-for-1"

    filtered = _legacy_gen(trade_intent="tier_up")
    assert filtered == [], "flat-tier legacy cards should be dropped by tier_up"
