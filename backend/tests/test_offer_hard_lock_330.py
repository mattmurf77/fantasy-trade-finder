"""#330 (G4) — single-pin HARD LOCK tripwire (BT-1).

Operator decision 1 for the #330 Offer/Target handoff: the offered player is
a hard lock — present in EVERY suggested trade, not a preference. The client
sends exactly one ``pinned_give_players`` (Offer) or
``pinned_receive_players`` (Target) element, so the whole decision rests on
the engine's single-pin semantics: with one pin, the documented
">= 1 of these IDs per card" contract degenerates to "the pin is in every
card".

``test_finder_targeting.py`` covers pin REACHABILITY (single receive pin) and
the two-pin ``pinned_give_mode='all'`` package constraint, but has no
single-GIVE-pin assert anywhere — every ``pinned_give_players`` use there is
``None`` or two-pin. This file is the executable guard for both sides,
across the v2 pair generator and the v3 optimizer.

TRIPWIRE NOTE (2026-08-16 wave): G6 is rewriting the enforcing functions in
``backend/trade_service.py`` (construction gates land exactly where the pin
is enforced). This G4-owned file must stay green through that merge — if it
goes red, G6's rewrite broke the #330 hard lock.

Fixture conventions mirror test_finder_targeting.py (flag isolation, value
fixtures with a single dominant divergence pair).
"""
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import TradeService, LeagueMember, elo_to_value
from backend.trade_optimizer import generate_pair_trades_v3


@dataclass
class _Player:
    id: str
    name: str
    position: str = "WR"
    team: str = "TST"
    age: int = 25
    search_rank: Optional[int] = None


@pytest.fixture(autouse=True)
def _isolate_flags_and_cfg():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        # Pin the pre-#214 engine math these fixtures were shaped against —
        # same rationale as test_finder_targeting.py's fixture.
        with ts.stud_tax_override("heavy"):
            yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _set_flags(*extra: str) -> None:
    cache = dict(ff.DEFAULT_FLAGS)
    cache["trade_engine.v2"] = True
    for key in extra:
        assert key in cache, f"unknown flag key {key!r}"
        cache[key] = True
    ff._flags_cache = cache


def _member(user_id, roster, elo, has_rankings=True):
    return LeagueMember(user_id=user_id, username=user_id, roster=roster,
                        elo_ratings=elo, has_rankings=has_rankings)


_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix):
    return {f"{prefix}_{pid}": pos for pid, pos in _BASE_POS.items()}


# ---------------------------------------------------------------------------
# Fixtures — one dominant organic pair, so the pin must REDIRECT the deck
# ---------------------------------------------------------------------------

def _give_fixture():
    """Opponent over-values BOTH uA and uB; uA more strongly, so the organic
    top card gives uA — a single give pin on uB must put uB in EVERY card."""
    pos = {**_bodies("u"), **_bodies("o"), "uA": "WR", "uB": "WR", "oA": "WR"}
    players = {pid: _Player(id=pid, name=pid, position=p) for pid, p in pos.items()}
    user_roster = list(_bodies("u")) + ["uA", "uB"]
    opp_roster = list(_bodies("o")) + ["oA"]

    user_elo = {pid: 1500.0 for pid in user_roster}
    user_elo.update({pid: 1490.0 for pid in _bodies("o")})
    user_elo["oA"] = 1570.0
    opp_elo = {pid: 1500.0 for pid in opp_roster}
    opp_elo.update({pid: 1490.0 for pid in _bodies("u")})
    opp_elo["uA"] = 1570.0
    opp_elo["uB"] = 1545.0
    seed_elo = {pid: 1500.0 for pid in pos}
    seed_elo["uA"] = seed_elo["uB"] = seed_elo["oA"] = 1530.0
    return players, user_roster, opp_roster, user_elo, opp_elo, seed_elo


def _receive_fixture():
    """Mirror: user over-values oA and oB, oA more strongly — the organic top
    card receives oA; a single receive pin on oB must put oB in EVERY card."""
    pos = {**_bodies("u"), **_bodies("o"), "uA": "WR", "oA": "WR", "oB": "WR"}
    players = {pid: _Player(id=pid, name=pid, position=p) for pid, p in pos.items()}
    user_roster = list(_bodies("u")) + ["uA"]
    opp_roster = list(_bodies("o")) + ["oA", "oB"]

    user_elo = {pid: 1500.0 for pid in user_roster}
    user_elo.update({pid: 1490.0 for pid in _bodies("o")})
    user_elo["oA"] = 1570.0
    user_elo["oB"] = 1545.0
    opp_elo = {pid: 1500.0 for pid in opp_roster}
    opp_elo.update({pid: 1490.0 for pid in _bodies("u")})
    opp_elo["uA"] = 1570.0
    seed_elo = {pid: 1500.0 for pid in pos}
    seed_elo["uA"] = seed_elo["oA"] = seed_elo["oB"] = 1530.0
    return players, user_roster, opp_roster, user_elo, opp_elo, seed_elo


def _run_v2(svc, fixture, *, pinned_give=None, pinned_receive=None):
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = fixture
    opponent = _member("opp", opp_roster, opp_elo)
    return svc._generate_for_pair_v2(
        user_id="user",
        shrunk_user_elo=user_elo,
        user_value={pid: elo_to_value(e) for pid, e in user_elo.items()},
        user_roster=user_roster,
        opponent=opponent,
        league_id="L1",
        seed_value=lambda p: elo_to_value(seed_elo.get(p, 1500.0)),
        max_cards=5,
        fairness_threshold=0.75,
        acquire_positions=[],
        trade_away_positions=[],
        pinned_give_players=pinned_give,
        pinned_receive_players=pinned_receive,
        confidence=None,
        scoring_format="1qb_ppr",
    )


def _run_v3(fixture, *, pinned_give=None, pinned_receive=None):
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = fixture
    opponent = _member("opp", opp_roster, opp_elo)
    return generate_pair_trades_v3(
        user_id="user",
        shrunk_user_elo=user_elo,
        user_value={pid: elo_to_value(e) for pid, e in user_elo.items()},
        user_roster=user_roster,
        opponent=opponent,
        league_id="L1",
        seed_elo=seed_elo,
        confidence=None,
        max_cards=5,
        fairness_threshold=0.75,
        scoring_format="1qb_ppr",
        pinned_give_players=pinned_give,
        pinned_receive_players=pinned_receive,
        players=players,
    )


# ---------------------------------------------------------------------------
# BT-1 — single GIVE pin: the pin is on the give side of EVERY card
# ---------------------------------------------------------------------------

def test_single_give_pin_v2_pair_generator():
    _set_flags("trade.finder_targeting")
    fixture = _give_fixture()
    svc = TradeService(players=fixture[0])

    organic = _run_v2(svc, fixture)
    assert organic, "organic generation produced no cards"
    # Sanity: unpinned, the deck's top card gives the coveted uA — so the
    # pinned run below genuinely REDIRECTS the deck, it doesn't coast.
    assert "uA" in organic[0].give_player_ids

    pinned = _run_v2(svc, fixture, pinned_give=["uB"])
    assert pinned, "single-give-pin produced no cards"
    for card in pinned:
        assert "uB" in card.give_player_ids, (
            f"hard lock broken (v2): card gives {card.give_player_ids} "
            "without the single pinned player uB"
        )


def test_single_give_pin_v3_optimizer():
    _set_flags("trade.finder_targeting", "trade_engine.v3")
    fixture = _give_fixture()

    pinned = _run_v3(fixture, pinned_give=["uB"])
    assert pinned, "v3 single-give-pin produced no cards"
    for card in pinned:
        assert "uB" in card.give_player_ids, (
            f"hard lock broken (v3): card gives {card.give_player_ids} "
            "without the single pinned player uB"
        )


# ---------------------------------------------------------------------------
# BT-1 mirror — single RECEIVE pin: the pin is on the receive side of EVERY
# card (the #330 Target verb)
# ---------------------------------------------------------------------------

def test_single_receive_pin_v2_pair_generator():
    _set_flags("trade.finder_targeting")
    fixture = _receive_fixture()
    svc = TradeService(players=fixture[0])

    organic = _run_v2(svc, fixture)
    assert organic, "organic generation produced no cards"
    assert "oA" in organic[0].receive_player_ids

    pinned = _run_v2(svc, fixture, pinned_receive=["oB"])
    assert pinned, "single-receive-pin produced no cards"
    for card in pinned:
        assert "oB" in card.receive_player_ids, (
            f"hard lock broken (v2): card receives {card.receive_player_ids} "
            "without the single pinned player oB"
        )


def test_single_receive_pin_v3_optimizer():
    _set_flags("trade.finder_targeting", "trade_engine.v3")
    fixture = _receive_fixture()

    pinned = _run_v3(fixture, pinned_receive=["oB"])
    assert pinned, "v3 single-receive-pin produced no cards"
    for card in pinned:
        assert "oB" in card.receive_player_ids, (
            f"hard lock broken (v3): card receives {card.receive_player_ids} "
            "without the single pinned player oB"
        )
