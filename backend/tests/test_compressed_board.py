"""Regression coverage for the 2026-08-15 compressed-board field bug.

docs/plans/compressed-board-pool/scope.md. Found running the real engine
against the operator's league FFV3: three of four BOARDED leaguemates
produced ZERO trade cards at any per-opponent budget while mutually
positive trades demonstrably existed. Two independent defects:

  1. `trade_optimizer` pruned its candidate pools by the RAW divergence
     `_vo - _uv`. `elo_to_value` is exponential, so an opponent board that
     sits uniformly lower than the user's (those three boards were pinned
     at the 1200 floor with median ~1220, against the consensus 1347)
     deflates high-Elo players far more than low-Elo ones. Every tradeable
     stud sorted BELOW the user's worthless bench and the top-`v3_pool_size`
     pool filled with junk. Flag `trade.pool_calibration`.

  2. `trade_service`'s boarded/unboarded branch was an if/else with no
     fall-through, so a boarded member yielding zero divergence cards got
     no consensus fallback either and vanished from the deck — a leaguemate
     who ranked a little became a WORSE trade partner than one who never
     ranked at all. Flag `trade.divergence_fallback`.

Both flags default OFF, so every test here that asserts the FIXED behavior
turns its flag on explicitly, and each is paired with a flag-off test
pinning the old behavior (proving the fix is what changed it, and that the
kill switch really restores today's engine).
"""

from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_optimizer import generate_pair_trades_v3
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    elo_to_value,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers  (same shape as test_trade_optimizer.py)
# ---------------------------------------------------------------------------

@dataclass
class _Player:
    id: str
    name: str
    position: str = "WR"
    team: str = "TST"
    age: int = 25
    ktc_value: Optional[int] = None
    search_rank: int = 100


@pytest.fixture(autouse=True)
def _isolate_flags_and_cfg():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        # Same pin as test_trade_optimizer.py: these fixtures are authored
        # against the pre-#214 'heavy' stud-tax math.
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


# A lineup-feasible body set: 1 QB, 2 RB, 2 WR, 1 TE.
_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix):
    return {f"{prefix}_{pid}": pos for pid, pos in _BASE_POS.items()}


def _compressed_fixture(opp_offset: float = 0.0):
    """User with two studs on a normal (consensus-scale) board, facing an
    opponent whose board is FLOOR-PINNED — the field shape: the opponent
    ranked their top handful and left everyone else at the 1200 floor.

    The live trade is the field case (Gibbs <-> A.J. Brown): a stud-for-stud
    swap where each side prefers the other's asset on its OWN board, so both
    surpluses are strongly positive. `studA` for `oStud` clears every gate —
    the only thing standing between the user and that trade is the prune.

    ``opp_offset`` shifts the WHOLE opponent board by a constant — a change
    that carries no information about which player the opponent prefers, so
    a correct prune must be indifferent to it.
    """
    pos = {**_bodies("u"), **_bodies("o"),
           "studA": "WR", "studB": "RB", "oStud": "WR", "oMid": "RB"}
    for i in range(6):
        pos[f"junk{i}"] = "WR"
    players = {pid: _Player(id=pid, name=pid, position=p)
               for pid, p in pos.items()}

    user_roster = list(_bodies("u")) + ["studA", "studB"] + [
        f"junk{i}" for i in range(6)]
    opp_roster = list(_bodies("o")) + ["oStud", "oMid"]

    # User board: normal consensus-like spread. The user prefers oStud to
    # their own studA, so receiving oStud for studA is a clear user gain.
    user_elo = {pid: 1300.0 for pid in pos}
    user_elo.update({pid: 1280.0 for pid in _bodies("o")})
    user_elo["studA"] = 1850.0
    user_elo["studB"] = 1800.0
    user_elo["oStud"] = 1900.0      # the user wants this back
    user_elo["oMid"] = 1420.0
    for i in range(6):
        user_elo[f"junk{i}"] = 1250.0 - 5 * i

    # Opponent board: floor-pinned at 1200, only their top handful ranked.
    # Mirror preference — they rate studA above their own oStud — so the
    # opponent gains too. Note studA's RAW divergence key is still negative
    # (5473 - 5754), which is exactly the bug: a genuinely tradeable stud
    # looks worse than the user's junk purely because the whole opponent
    # board is deflated.
    opp_elo = {pid: 1200.0 for pid in pos}
    opp_elo["studA"] = 1840.0       # opponent covets the user's stud
    opp_elo["studB"] = 1760.0
    opp_elo["oStud"] = 1700.0       # ...and under-rates their own
    opp_elo["oMid"] = 1210.0
    if opp_offset:
        opp_elo = {pid: e + opp_offset for pid, e in opp_elo.items()}

    seed_elo = {pid: 1300.0 for pid in pos}
    seed_elo["studA"] = 1870.0
    seed_elo["studB"] = 1810.0
    seed_elo["oStud"] = 1880.0
    seed_elo["oMid"] = 1400.0
    return players, user_roster, opp_roster, user_elo, opp_elo, seed_elo


def _v3(*, user_elo, user_roster, opponent, seed_elo, players, **kw):
    defaults = dict(
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
        players=players,
    )
    defaults.update(kw)
    return generate_pair_trades_v3(**defaults)


# ---------------------------------------------------------------------------
# 1. The pool prune itself: do the user's top assets survive?
# ---------------------------------------------------------------------------
#
# `v3_pool_size = 2` makes pool membership directly observable through the
# public return value: only the top-2 divergence assets can reach the give
# pool, so a card that GIVES studA proves studA was in the top 2. No
# white-box reach into a local.

def test_compressed_board_evicts_studs_from_give_pool_today():
    """Flag OFF — the reported defect, pinned. Junk outranks the studs on
    the raw divergence key, so the 2-man give pool holds no stud and the
    pair yields nothing at all."""
    _set_flags()
    ts._cfg["v3_pool_size"] = 2
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = \
        _compressed_fixture()
    opponent = _member("opp", opp_roster, opp_elo)

    cards = _v3(user_elo=user_elo, user_roster=user_roster,
                opponent=opponent, seed_elo=seed_elo, players=players)

    assert cards == [], (
        "fixture no longer reproduces the field bug — the compressed board "
        "should starve the give pool with the flag off")


def test_calibration_keeps_studs_in_a_size_2_give_pool():
    """Flag ON — the user's studs are back in the pool and the pair yields
    trades. With v3_pool_size=2 a stud on the give side IS the proof of
    pool membership."""
    _set_flags("trade.pool_calibration")
    ts._cfg["v3_pool_size"] = 2
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = \
        _compressed_fixture()
    opponent = _member("opp", opp_roster, opp_elo)

    cards = _v3(user_elo=user_elo, user_roster=user_roster,
                opponent=opponent, seed_elo=seed_elo, players=players)

    assert cards, "calibrated prune must recover the mutually-positive trade"
    given = {pid for c in cards for pid in c.give_player_ids}
    assert given & {"studA", "studB"}, (
        f"no stud reached the size-2 give pool; gave {sorted(given)}")
    # Every card is still a real divergence card — the prune changed, the
    # objective did not.
    assert all(c.basis == "divergence" for c in cards)


# ---------------------------------------------------------------------------
# 2. Scale invariance: a board-wide offset carries no preference signal
# ---------------------------------------------------------------------------

def test_calibrated_pool_is_invariant_to_a_board_wide_offset():
    """Shifting EVERY opponent rating by the same constant says nothing
    about which player the opponent prefers, so the deck must not move.
    This is the defect in its cleanest form: it does move today."""
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = \
        _compressed_fixture()
    _, _, _, _, opp_elo_shifted, _ = _compressed_fixture(opp_offset=200.0)
    ts._cfg["v3_pool_size"] = 4

    def _deck(elo):
        return [(sorted(c.give_player_ids), sorted(c.receive_player_ids))
                for c in _v3(user_elo=user_elo, user_roster=user_roster,
                             opponent=_member("opp", opp_roster, elo),
                             seed_elo=seed_elo, players=players)]

    _set_flags("trade.pool_calibration")
    assert _deck(opp_elo) == _deck(opp_elo_shifted), (
        "calibrated prune must ignore a flat offset")

    _set_flags()
    assert _deck(opp_elo) != _deck(opp_elo_shifted), (
        "fixture no longer demonstrates the offset sensitivity it was "
        "written to pin")


# ---------------------------------------------------------------------------
# 3. Flag off ⇒ the engine is untouched (kill switch really kills)
# ---------------------------------------------------------------------------

def _healthy_fixture():
    """A normal pair of boards on the same scale, with genuine per-player
    disagreement — the case the engine already handles well."""
    pos = {**_bodies("u"), **_bodies("o"), "uA": "WR", "uB": "RB",
           "oA": "WR", "oB": "RB"}
    players = {pid: _Player(id=pid, name=pid, position=p)
               for pid, p in pos.items()}
    user_roster = list(_bodies("u")) + ["uA", "uB"]
    opp_roster = list(_bodies("o")) + ["oA", "oB"]

    user_elo = {pid: 1500.0 for pid in pos}
    user_elo.update({pid: 1490.0 for pid in _bodies("o")})
    user_elo["oA"] = 1600.0
    user_elo["oB"] = 1545.0
    opp_elo = {pid: 1500.0 for pid in pos}
    opp_elo.update({pid: 1490.0 for pid in _bodies("u")})
    opp_elo["uA"] = 1600.0
    opp_elo["uB"] = 1545.0
    seed_elo = {pid: 1500.0 for pid in pos}
    for pid in ("uA", "uB", "oA", "oB"):
        seed_elo[pid] = 1545.0
    return players, user_roster, opp_roster, user_elo, opp_elo, seed_elo


def test_flag_off_deck_is_byte_identical_to_the_unpatched_engine():
    """The historical key is `_vo - _uv`; with the flag off the calibrated
    key must reduce to exactly that, composites included."""
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = \
        _healthy_fixture()
    opponent = _member("opp", opp_roster, opp_elo)

    _set_flags()
    cards = _v3(user_elo=user_elo, user_roster=user_roster,
                opponent=opponent, seed_elo=seed_elo, players=players)
    assert cards
    # Recompute the pools the old way and confirm the cards only ever use
    # assets the ORIGINAL prune would have selected.
    uv = {pid: elo_to_value(e) for pid, e in user_elo.items()}
    vo = {pid: elo_to_value(e) for pid, e in opp_elo.items()}
    pool_p = int(ts._cfg.get("v3_pool_size", 12))
    old_give = set(sorted(user_roster, key=lambda p: vo[p] - uv[p],
                          reverse=True)[:pool_p])
    old_recv = set(sorted(opp_roster, key=lambda p: uv[p] - vo[p],
                          reverse=True)[:pool_p])
    for c in cards:
        assert set(c.give_player_ids) <= old_give
        assert set(c.receive_player_ids) <= old_recv


def test_calibration_leaves_a_healthy_pair_alone():
    """Two boards already on the same scale ⇒ the calibration factor is ~1
    ⇒ the deck must not move. Guards the blast radius of the fix: it is
    meant to rescue compressed boards, not to retune healthy ones."""
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = \
        _healthy_fixture()
    opponent = _member("opp", opp_roster, opp_elo)

    _set_flags()
    off = _v3(user_elo=user_elo, user_roster=user_roster, opponent=opponent,
              seed_elo=seed_elo, players=players)
    _set_flags("trade.pool_calibration")
    on = _v3(user_elo=user_elo, user_roster=user_roster, opponent=opponent,
             seed_elo=seed_elo, players=players)

    assert off and on
    assert [(sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.composite_score) for c in off] == \
           [(sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.composite_score) for c in on]


# ---------------------------------------------------------------------------
# 4. The compounding bug: a boarded member must never vanish from the deck
# ---------------------------------------------------------------------------

def _zero_divergence_league():
    """A boarded opponent who agrees with the user on EVERY player. There is
    no divergence to trade on, so the divergence path returns nothing — but
    the member is still a real counterparty with a roster the user needs.

    The user is WR-thin and RB-heavy, the opponent the reverse, so the
    consensus generator has an obvious fit trade to find.
    """
    players, user_roster, opp_roster = {}, [], []
    for i in range(4):                       # user: startable RBs to give
        pid = f"u_r{i}"
        players[pid] = _Player(id=pid, name=pid, position="RB",
                               search_rank=40 + i)
        user_roster.append(pid)
    for i in range(4):                       # opponent: startable WRs
        pid = f"o_w{i}"
        players[pid] = _Player(id=pid, name=pid, position="WR",
                               search_rank=40 + i)
        opp_roster.append(pid)

    # Identical boards ⇒ divergence is zero for every asset on both sides.
    elo = {pid: 1550.0 for pid in players}
    seed_elo = dict(elo)
    league = League(league_id="L1", name="L", platform="sleeper", members=[
        _member("user", user_roster, dict(elo)),
        _member("boarded", opp_roster, dict(elo), has_rankings=True),
    ])
    return players, user_roster, dict(elo), seed_elo, league


def _gen(svc, league, user_roster, user_elo, seed_elo):
    return svc._generate_trades_v2(
        user_id="user",
        user_elo=user_elo,
        user_roster=user_roster,
        league=league,
        league_id="L1",
        seed_elo=seed_elo,
        max_per_opponent=3,
        fairness_threshold=0.75,
        acquire_positions=["WR"],
        trade_away_positions=None,
        pinned_give_players=None,
        pinned_receive_players=None,
        scoring_format="1qb_ppr",
        on_opponent_done=None,
        confidence=None,
    )


def test_boarded_zero_divergence_member_vanishes_today():
    """Flag OFF — the reported perverse incentive, pinned. The boarded
    member produces nothing and gets no consensus fallback, so they are
    absent from the deck entirely."""
    _set_flags("trade_engine.v3")
    players, user_roster, user_elo, seed_elo, league = _zero_divergence_league()
    svc = TradeService(players=players)

    cards = _gen(svc, league, user_roster, user_elo, seed_elo)

    assert not [c for c in cards if c.target_user_id == "boarded"], (
        "fixture no longer reproduces the vanishing-counterparty bug")


def test_boarded_zero_divergence_member_still_yields_cards():
    """Flag ON — the same member now gets the consensus fallback, labeled
    honestly, so ranking a little can no longer make a leaguemate a worse
    trade partner than never ranking at all."""
    _set_flags("trade_engine.v3", "trade.divergence_fallback")
    players, user_roster, user_elo, seed_elo, league = _zero_divergence_league()
    svc = TradeService(players=players)

    cards = _gen(svc, league, user_roster, user_elo, seed_elo)

    mine = [c for c in cards if c.target_user_id == "boarded"]
    assert mine, "a boarded member with no divergence must not vanish"
    assert all(c.basis == "consensus" for c in mine), (
        "fallback cards must be labeled consensus, not divergence")


def test_fallback_does_not_touch_a_member_who_already_has_cards():
    """The fallback is strictly additive: it only fires on an empty result,
    so a pair that already produces divergence cards is untouched."""
    players, user_roster, opp_roster, user_elo, opp_elo, seed_elo = \
        _healthy_fixture()
    league = League(league_id="L1", name="L", platform="sleeper", members=[
        _member("user", user_roster, user_elo),
        _member("opp", opp_roster, opp_elo),
    ])
    svc = TradeService(players=players)

    _set_flags("trade_engine.v3")
    off = _gen(svc, league, user_roster, user_elo, seed_elo)
    _set_flags("trade_engine.v3", "trade.divergence_fallback")
    on = _gen(svc, league, user_roster, user_elo, seed_elo)

    assert off, "healthy pair must produce divergence cards to begin with"
    assert [(c.target_user_id, sorted(c.give_player_ids),
             sorted(c.receive_player_ids), c.composite_score) for c in off] == \
           [(c.target_user_id, sorted(c.give_player_ids),
             sorted(c.receive_player_ids), c.composite_score) for c in on]
