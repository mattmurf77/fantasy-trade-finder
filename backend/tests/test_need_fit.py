"""FB-96 automatic positional-need fit (flag trade.need_fit).

Feedback #96 (tester jonbonjourvi): "you're weak in RB but strong in WR —
here's another team that needs the swap with you." Covers:
  1. need_fit_score math — cross-filling swap = 1.0, anti-swap = 0.0,
     neutral directions = 0.5, picks-only sides = None
  2. superflex QB weighting — 2 startable QBs is full strength in 1QB but
     not in superflex
  3. orchestrator reordering — with equal divergence/fairness, the
     WR-for-RB swap outranks the positionally-backward trade; need_fit is
     stamped; fairness/mismatch gates are untouched
  4. flag-off parity — need_fit stays None and the two cards keep equal
     composites

Fixture conventions mirror test_finder_targeting.py (flag isolation,
value fixtures with symmetric divergence pairs).
"""
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League, LeagueMember, TradeService, need_fit_score,
)


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
# 1 + 2. Fit math
# ---------------------------------------------------------------------------

def _profile(**startable) -> dict:
    """Roster profile with `startable` elite players per position."""
    td = {pos: {"elite": startable.get(pos, 0), "starter": 0, "bench": 0}
          for pos in ("QB", "RB", "WR", "TE")}
    return {"tier_depth": td, "position_needs": [], "position_surplus": []}


_PLAYERS = {
    "wr": _Player(id="wr", name="wr", position="WR"),
    "rb": _Player(id="rb", name="rb", position="RB"),
    "qb": _Player(id="qb", name="qb", position="QB"),
    "pick": _Player(id="pick", name="pick", position="PICK"),
}


def test_need_fit_score_math():
    user = _profile(WR=4, RB=0)     # deep WR, empty RB
    opp = _profile(WR=0, RB=4)      # mirror

    # The feedback #96 swap: give WR from surplus, receive RB into need.
    assert need_fit_score(user, opp, ["wr"], ["rb"], _PLAYERS) == 1.0
    # Backward trade: give from the thin position, receive at the deep one.
    assert need_fit_score(user, opp, ["rb"], ["wr"], _PLAYERS) == 0.0
    # One good direction + one bad direction average to neutral.
    assert need_fit_score(user, opp, ["wr"], ["wr"], _PLAYERS) == 0.5
    # Picks carry no positional profile → no signal, never 0.
    assert need_fit_score(user, opp, ["pick"], ["pick"], _PLAYERS) is None


def test_need_fit_superflex_qb_weighting():
    user = _profile(QB=2)           # 2 startable QBs
    opp = _profile()                # no startable QBs anywhere

    # 1QB: 2 startable QBs = at the surplus threshold → full-strength give.
    fit_1qb = need_fit_score(user, opp, ["qb"], [], _PLAYERS, "1qb_ppr")
    # Superflex: starting 2 QBs means 2 startable is NOT surplus (denom 3).
    fit_sf = need_fit_score(user, opp, ["qb"], [], _PLAYERS, "sf_tep")
    assert fit_1qb == 1.0
    assert fit_sf is not None and fit_sf < fit_1qb
    assert fit_sf == pytest.approx(0.5 * (2 / 3) + 0.5, abs=1e-3)


# ---------------------------------------------------------------------------
# 3 + 4. Orchestrator reordering
# ---------------------------------------------------------------------------

def _swap_league():
    """User deep at WR / empty at RB; opponent the mirror image. Two
    symmetric 1-for-1 divergence pairs exist with IDENTICAL surplus and
    fairness math:
      * swap:     give u_wA (WR)  → receive o_rB (RB)   need_fit 1.0
      * backward: give u_rA (RB)  → receive o_wX (WR)   need_fit 0.0
    Only the need-fit boost can separate them."""
    players, user_roster, opp_roster = {}, [], []
    for i in range(4):                     # user: 4 startable WRs
        pid = f"u_w{i}"
        players[pid] = _Player(id=pid, name=pid, position="WR",
                               search_rank=40 + i)
        user_roster.append(pid)
    players["u_wA"] = _Player(id="u_wA", name="u_wA", position="WR",
                              search_rank=60)
    players["u_rA"] = _Player(id="u_rA", name="u_rA", position="RB",
                              search_rank=400)     # deep bench — not startable
    user_roster += ["u_wA", "u_rA"]

    for i in range(4):                     # opponent: 4 startable RBs
        pid = f"o_r{i}"
        players[pid] = _Player(id=pid, name=pid, position="RB",
                               search_rank=40 + i)
        opp_roster.append(pid)
    players["o_rB"] = _Player(id="o_rB", name="o_rB", position="RB",
                              search_rank=60)
    players["o_wX"] = _Player(id="o_wX", name="o_wX", position="WR",
                              search_rank=400)
    opp_roster += ["o_rB", "o_wX"]

    # Symmetric divergences: the user over-values o_rB and o_wX equally;
    # the opponent over-values u_wA and u_rA equally. Seeds tie at 1530 for
    # all four traded assets → fairness 1.0 for both 1-for-1 candidates.
    user_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    user_elo["o_rB"] = user_elo["o_wX"] = 1570.0
    opp_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    opp_elo["u_wA"] = opp_elo["u_rA"] = 1570.0
    seed_elo = {pid: 1500.0 for pid in user_elo}
    for pid in ("u_wA", "u_rA", "o_rB", "o_wX"):
        seed_elo[pid] = 1530.0

    league = League(league_id="L1", name="L", platform="sleeper", members=[
        _member("user", user_roster, user_elo),
        _member("opp", opp_roster, opp_elo),
    ])
    return players, user_roster, user_elo, seed_elo, league


def _gen(players, league, user_roster, user_elo, seed_elo):
    svc = TradeService(players=players)
    return svc._generate_trades_v2(
        user_id="user",
        user_elo=user_elo,
        user_roster=user_roster,
        league=league,
        league_id="L1",
        seed_elo=seed_elo,
        max_per_opponent=25,   # wide cut: multi-asset packages outscore the
                               # two probe 1-for-1s on raw mutual gain; both
                               # probes must survive into the deck
        fairness_threshold=0.75,
        acquire_positions=None,
        trade_away_positions=None,
        pinned_give_players=None,
        pinned_receive_players=None,
        scoring_format="1qb_ppr",
        on_opponent_done=None,
        confidence=None,
    )


def _find(cards, give, recv):
    for i, c in enumerate(cards):
        if (set(c.give_player_ids) == set(give)
                and set(c.receive_player_ids) == set(recv)):
            return i, c
    raise AssertionError(f"card {give}->{recv} not in deck "
                         f"{[(c.give_player_ids, c.receive_player_ids) for c in cards]}")


def test_need_fit_reorders_swap_above_backward_trade():
    players, user_roster, user_elo, seed_elo, league = _swap_league()
    _set_flags("trade.need_fit")
    cards = _gen(players, league, user_roster, user_elo, seed_elo)
    assert cards, "generation produced no cards"

    swap_idx, swap = _find(cards, ["u_wA"], ["o_rB"])
    back_idx, back = _find(cards, ["u_rA"], ["o_wX"])

    assert swap.need_fit == 1.0
    assert back.need_fit == 0.0
    assert swap_idx < back_idx, "cross-filling swap must rank first"
    assert swap.composite_score > back.composite_score
    # Gates untouched: same divergence and same consensus fairness.
    assert swap.fairness_score == back.fairness_score
    assert swap.mismatch_score == back.mismatch_score


def test_need_fit_flag_off_parity():
    players, user_roster, user_elo, seed_elo, league = _swap_league()
    _set_flags()   # v2 only, need_fit OFF
    cards = _gen(players, league, user_roster, user_elo, seed_elo)
    assert cards
    assert all(c.need_fit is None for c in cards)
    _, swap = _find(cards, ["u_wA"], ["o_rB"])
    _, back = _find(cards, ["u_rA"], ["o_wX"])
    # Without the boost the symmetric construction leaves them tied.
    assert swap.composite_score == back.composite_score
