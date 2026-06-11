"""FB-47 finder targeting (flag trade.finder_targeting).

Covers (docs/plans/trade-finder-targeting.md Phase A):
  1. partner_fit_score math — loaded roster attracts acquires, repels sells
  2. pinned_receive_players reachability through the v2 pair generator
  3. pinned_receive_players reachability through the v3 optimizer
  4. orchestrator stamps partner_fit + blends composite; flag-off ⇒ None

Fixture conventions mirror test_trade_optimizer.py (flag isolation, value
fixtures with a single dominant divergence pair).
"""
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    TradeService, League, LeagueMember, elo_to_value, partner_fit_score,
)
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


# ---------------------------------------------------------------------------
# 1. Fit math
# ---------------------------------------------------------------------------

def _profile(wr_starters: int) -> dict:
    return {"tier_depth": {"WR": {"elite": wr_starters, "starter": 0, "bench": 1}},
            "position_needs": [], "position_surplus": []}


def test_partner_fit_math():
    loaded = _profile(4)   # at WR surplus threshold (4)
    thin   = _profile(0)

    assert partner_fit_score(loaded, ["WR"], []) == 1.0   # they can spare one
    assert partner_fit_score(loaded, [], ["WR"]) == 0.0   # they don't want yours
    assert partner_fit_score(thin,   ["WR"], []) == 0.0
    assert partner_fit_score(thin,   [], ["WR"]) == 1.0
    # Mixed targets average; half-loaded sits between.
    assert partner_fit_score(_profile(2), ["WR"], []) == 0.5
    # No targets ⇒ targeting inactive, not fit 0.
    assert partner_fit_score(loaded, [], []) is None


# ---------------------------------------------------------------------------
# 2 + 3. Pinned receive reachability (v2 pair generator and v3 optimizer)
# ---------------------------------------------------------------------------

_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix):
    return {f"{prefix}_{pid}": pos for pid, pos in _BASE_POS.items()}


def _divergence_fixture():
    """User over-values BOTH oA and oB; oA more strongly, so the organic top
    card receives oA — a pin on oB must redirect every card to include oB."""
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


def test_pinned_receive_v2_pair_generator():
    _set_flags("trade.finder_targeting")
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = _divergence_fixture()
    opponent = _member("opp", opp_roster, opp_elo)
    svc = TradeService(players=players)

    def _run(pinned_recv):
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
            pinned_give_players=None,
            pinned_receive_players=pinned_recv,
            confidence=None,
            scoring_format="1qb_ppr",
        )

    organic = _run(None)
    assert organic and organic[0].receive_player_ids == ["oA"]   # oA dominates

    pinned = _run(["oB"])
    assert pinned, "pinned-receive produced no cards"
    for card in pinned:
        assert "oB" in card.receive_player_ids


def test_pinned_receive_v3_optimizer():
    _set_flags("trade.finder_targeting", "trade_engine.v3")
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = _divergence_fixture()
    opponent = _member("opp", opp_roster, opp_elo)

    cards = generate_pair_trades_v3(
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
        pinned_receive_players=["oB"],
        players=players,
    )
    assert cards, "v3 pinned-receive produced no cards"
    for card in cards:
        assert "oB" in card.receive_player_ids


# ---------------------------------------------------------------------------
# 4. Orchestrator: partner_fit stamped, composite blended, flag-off ⇒ None
# ---------------------------------------------------------------------------

def _consensus_league():
    """Two UNRANKED opponents: 'loaded' has 4 startable WRs, 'thin' has none.
    search_rank drives dynasty_value → tier binning in the profiles."""
    players = {}
    user_roster = []
    for i in range(3):                       # user: startable WRs to give
        pid = f"u_w{i}"
        players[pid] = _Player(id=pid, name=pid, position="WR", search_rank=40 + i)
        user_roster.append(pid)

    loaded_roster, thin_roster = [], []
    for i in range(4):                       # loaded: 4 startable WRs
        pid = f"L_w{i}"
        players[pid] = _Player(id=pid, name=pid, position="WR", search_rank=50 + i)
        loaded_roster.append(pid)
    for i in range(4):                       # thin: startable RBs, deep-bench WR
        pid = f"T_r{i}"
        players[pid] = _Player(id=pid, name=pid, position="RB", search_rank=50 + i)
        thin_roster.append(pid)
    pid = "T_w0"
    players[pid] = _Player(id=pid, name=pid, position="WR", search_rank=400)
    thin_roster.append(pid)

    seed_elo = {p: 1550.0 for p in players}
    user_elo = {p: 1550.0 for p in user_roster}

    league = League(league_id="L1", name="L", platform="sleeper", members=[
        _member("user", user_roster, user_elo),
        _member("loaded", loaded_roster, {}, has_rankings=False),
        _member("thin", thin_roster, {}, has_rankings=False),
    ])
    return players, user_roster, user_elo, seed_elo, league


def _gen(svc, league, user_roster, user_elo, seed_elo, acquire):
    return svc._generate_trades_v2(
        user_id="user",
        user_elo=user_elo,
        user_roster=user_roster,
        league=league,
        league_id="L1",
        seed_elo=seed_elo,
        max_per_opponent=3,
        fairness_threshold=0.75,
        acquire_positions=acquire,
        trade_away_positions=None,
        pinned_give_players=None,
        pinned_receive_players=None,
        scoring_format="1qb_ppr",
        on_opponent_done=None,
        confidence=None,
    )


def test_partner_fit_stamped_and_flag_off_none():
    players, user_roster, user_elo, seed_elo, league = _consensus_league()

    _set_flags("trade.finder_targeting")
    svc = TradeService(players=players)
    cards = _gen(svc, league, user_roster, user_elo, seed_elo, acquire=["WR"])
    assert cards, "consensus generation produced no cards"
    by_opp = {}
    for c in cards:
        assert c.partner_fit is not None
        by_opp.setdefault(c.target_user_id, c.partner_fit)
    # Acquiring WR: the WR-loaded roster is the better partner.
    assert by_opp.get("loaded", 0) > by_opp.get("thin", 1)

    # Flag off: identical call leaves partner_fit unset everywhere.
    _set_flags()
    svc2 = TradeService(players=players)
    cards_off = _gen(svc2, league, user_roster, user_elo, seed_elo, acquire=["WR"])
    assert cards_off
    assert all(c.partner_fit is None for c in cards_off)
