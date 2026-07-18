"""FB-147 engine hook — acquire-side trade-block boost (flag trade.block_boost).

The trade block (backend/trade_block_service.py) records which players each
manager flagged "on the block" in Sleeper's Trade Center. This SOFT, operator-
approved boost gives a bounded composite bump to a card whose ACQUIRE side holds
a player the counterparty flagged available. It mirrors FB-96 need_fit exactly:
applied AFTER all gates, it only reorders acceptable trades and never rescues a
gated one. Covers:
  1. _load_on_block_by_uid — groups flagged ids by the FLAGGING owner; read
     failure degrades to an empty map (boost no-ops, never breaks generation)
  2. orchestrator reordering — with equal divergence/fairness, the card that
     acquires a counterparty-blocked player outranks the plain card; the boost
     is stamped (block_boosted); fairness/mismatch gates are untouched
  3. acquire-side only — a player flagged on the GIVE side (the user's own
     block) never boosts
  4. flag-off / knob-0 byte-identity — composites unchanged, nothing stamped
  5. gate authority — an unfair (gated) trade that would acquire a blocked
     player stays dark; the boost cannot rescue it
  6. multi-blocked handling — a single card acquiring several blocked players
     gets ONE flat bump, not a compounded/graded one

Fixture conventions mirror test_need_fit.py (flag isolation, symmetric
divergence pairs that tie absent the boost so only the boost can separate them).
"""
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League, LeagueMember, TradeService, _load_on_block_by_uid,
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
# 1. _load_on_block_by_uid
# ---------------------------------------------------------------------------

def test_load_on_block_by_uid_groups_by_owner(monkeypatch):
    rows = [
        {"player_id": "p1", "user_id": "u_opp", "roster_id": 2},
        {"player_id": "p2", "user_id": "u_opp", "roster_id": 2},
        {"player_id": "p3", "user_id": "u_me", "roster_id": 1},
        # ints coerce to str; blank owner is dropped
        {"player_id": 99, "user_id": "u_opp", "roster_id": 2},
        {"player_id": "p4", "user_id": None, "roster_id": None},
    ]
    monkeypatch.setattr("backend.database.load_trade_block", lambda lid: rows)
    got = _load_on_block_by_uid("L1")
    assert got == {
        "u_opp": frozenset({"p1", "p2", "99"}),
        "u_me": frozenset({"p3"}),
    }
    assert all(isinstance(v, frozenset) for v in got.values())


def test_load_on_block_by_uid_read_failure_returns_empty(monkeypatch):
    def _boom(_lid):
        raise RuntimeError("db down")
    monkeypatch.setattr("backend.database.load_trade_block", _boom)
    assert _load_on_block_by_uid("L1") == {}


# ---------------------------------------------------------------------------
# Orchestrator fixture — two symmetric 1-for-1 divergence pairs
# ---------------------------------------------------------------------------

def _block_league():
    """User and opponent each hold a startable core plus two swappable assets.
    Two symmetric 1-for-1 divergence pairs exist with IDENTICAL surplus and
    fairness math:
      * blocked: give u_a → receive o_block
      * plain:   give u_b → receive o_plain
    The user over-values o_block and o_plain equally; the opponent over-values
    u_a and u_b equally; all four seeds tie at 1530 → fairness 1.0 for both
    1-for-1s. Absent any boost the two cards carry identical composites, so
    only the block signal can separate them."""
    players, user_roster, opp_roster = {}, [], []
    for i in range(4):                       # startable ballast on both sides
        up, op = f"u_core{i}", f"o_core{i}"
        players[up] = _Player(id=up, name=up, position="WR", search_rank=40 + i)
        players[op] = _Player(id=op, name=op, position="RB", search_rank=40 + i)
        user_roster.append(up)
        opp_roster.append(op)
    for pid in ("u_a", "u_b"):
        players[pid] = _Player(id=pid, name=pid, position="WR", search_rank=60)
        user_roster.append(pid)
    for pid in ("o_block", "o_plain"):
        players[pid] = _Player(id=pid, name=pid, position="RB", search_rank=60)
        opp_roster.append(pid)

    user_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    user_elo["o_block"] = user_elo["o_plain"] = 1570.0
    opp_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    opp_elo["u_a"] = opp_elo["u_b"] = 1570.0
    seed_elo = {pid: 1500.0 for pid in user_elo}
    for pid in ("u_a", "u_b", "o_block", "o_plain"):
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
        max_per_opponent=25,   # wide cut so both probe 1-for-1s survive
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


def _stub_block(monkeypatch, by_uid):
    monkeypatch.setattr(ts, "_load_on_block_by_uid", lambda _lid: by_uid)


# ---------------------------------------------------------------------------
# 2. Reordering + gate independence
# ---------------------------------------------------------------------------

def test_block_boost_reorders_acquire_above_plain(monkeypatch):
    players, user_roster, user_elo, seed_elo, league = _block_league()
    _stub_block(monkeypatch, {"opp": frozenset({"o_block"})})
    _set_flags("trade.block_boost")
    cards = _gen(players, league, user_roster, user_elo, seed_elo)
    assert cards, "generation produced no cards"

    blk_idx, blk = _find(cards, ["u_a"], ["o_block"])
    plain_idx, plain = _find(cards, ["u_b"], ["o_plain"])

    assert blk.block_boosted is True
    assert plain.block_boosted is False
    assert blk_idx < plain_idx, "acquiring a blocked player must rank first"
    assert blk.composite_score > plain.composite_score
    # The boost is exactly the flat bounded bump on the settled composite.
    w = ts._c("block_boost_weight")
    assert blk.composite_score == round(plain.composite_score * (1.0 + w), 3)
    # Gates untouched: identical divergence and consensus fairness.
    assert blk.fairness_score == plain.fairness_score
    assert blk.mismatch_score == plain.mismatch_score


def test_block_boost_flag_off_parity(monkeypatch):
    players, user_roster, user_elo, seed_elo, league = _block_league()
    _stub_block(monkeypatch, {"opp": frozenset({"o_block"})})
    _set_flags()   # v2 only, block_boost OFF
    cards = _gen(players, league, user_roster, user_elo, seed_elo)
    assert cards
    assert all(c.block_boosted is False for c in cards)
    _, blk = _find(cards, ["u_a"], ["o_block"])
    _, plain = _find(cards, ["u_b"], ["o_plain"])
    assert blk.composite_score == plain.composite_score


def test_block_boost_knob_zero_byte_identical(monkeypatch):
    """Flag ON but knob 0 ⇒ nothing stamped and composites byte-identical to
    the flag-off deck."""
    players, user_roster, user_elo, seed_elo, league = _block_league()
    _stub_block(monkeypatch, {"opp": frozenset({"o_block"})})

    _set_flags()   # baseline: block_boost off
    base = {(tuple(c.give_player_ids), tuple(c.receive_player_ids)):
            c.composite_score
            for c in _gen(players, league, user_roster, user_elo, seed_elo)}

    _set_flags("trade.block_boost")
    ts._cfg["block_boost_weight"] = 0.0
    cards = _gen(players, league, user_roster, user_elo, seed_elo)
    assert cards
    assert all(c.block_boosted is False for c in cards)
    for c in cards:
        key = (tuple(c.give_player_ids), tuple(c.receive_player_ids))
        assert c.composite_score == base[key]


# ---------------------------------------------------------------------------
# 3. Acquire-side only — give-side flags never boost
# ---------------------------------------------------------------------------

def test_block_boost_give_side_not_boosted(monkeypatch):
    """A player the USER flagged (u_a, which the user GIVES) is not the
    counterparty's block, so it never boosts. Only the opponent-keyed acquire
    lookup matters."""
    players, user_roster, user_elo, seed_elo, league = _block_league()
    # The user flagged their own u_a; the opponent flagged nothing.
    _stub_block(monkeypatch, {"user": frozenset({"u_a"})})

    _set_flags()   # baseline
    base = {(tuple(c.give_player_ids), tuple(c.receive_player_ids)):
            c.composite_score
            for c in _gen(players, league, user_roster, user_elo, seed_elo)}

    _set_flags("trade.block_boost")
    cards = _gen(players, league, user_roster, user_elo, seed_elo)
    assert cards
    assert all(c.block_boosted is False for c in cards), \
        "give-side / non-counterparty flags must never boost"
    for c in cards:
        key = (tuple(c.give_player_ids), tuple(c.receive_player_ids))
        assert c.composite_score == base[key]


# ---------------------------------------------------------------------------
# 4. Gate authority — the boost cannot rescue a gated trade
# ---------------------------------------------------------------------------

def _gated_league():
    """The opponent owns a high-value star (o_star) that is on the block. The
    only trade that would acquire it (give junk u_junk → receive o_star) is
    wildly unfair — the opponent gains nothing — so the surplus/fairness gates
    veto it. A fair blocked trade (u_a ↔ o_fair) also exists to prove the deck
    is non-empty and the boost is otherwise live."""
    players = {}
    user_roster, opp_roster = [], []
    for i in range(4):
        up, op = f"u_core{i}", f"o_core{i}"
        players[up] = _Player(id=up, name=up, position="WR", search_rank=40 + i)
        players[op] = _Player(id=op, name=op, position="RB", search_rank=40 + i)
        user_roster.append(up)
        opp_roster.append(op)
    players["u_junk"] = _Player(id="u_junk", name="u_junk", position="WR",
                                search_rank=600)
    players["u_a"] = _Player(id="u_a", name="u_a", position="WR", search_rank=60)
    user_roster += ["u_junk", "u_a"]
    players["o_star"] = _Player(id="o_star", name="o_star", position="RB",
                                search_rank=1)
    players["o_fair"] = _Player(id="o_fair", name="o_fair", position="RB",
                                search_rank=60)
    opp_roster += ["o_star", "o_fair"]

    user_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    user_elo["o_star"] = 1850.0     # elite; way above anything the user gives
    user_elo["o_fair"] = 1570.0
    user_elo["u_junk"] = 1300.0
    opp_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    opp_elo["o_star"] = 1850.0      # opponent values the star just as highly
    opp_elo["u_a"] = 1570.0
    opp_elo["u_junk"] = 1300.0
    seed_elo = {pid: 1500.0 for pid in user_elo}
    seed_elo["o_star"] = 1850.0
    seed_elo["o_fair"] = seed_elo["u_a"] = 1530.0
    seed_elo["u_junk"] = 1300.0

    league = League(league_id="L1", name="L", platform="sleeper", members=[
        _member("user", user_roster, user_elo),
        _member("opp", opp_roster, opp_elo),
    ])
    return players, user_roster, user_elo, seed_elo, league


def test_block_boost_does_not_override_gate(monkeypatch):
    players, user_roster, user_elo, seed_elo, league = _gated_league()
    _stub_block(monkeypatch, {"opp": frozenset({"o_star", "o_fair"})})
    _set_flags("trade.block_boost")
    cards = _gen(players, league, user_roster, user_elo, seed_elo)

    # The unfair star grab is gated out entirely — the boost never rescues it.
    assert all("o_star" not in c.receive_player_ids for c in cards), \
        "a gated (unfair) blocked-acquire trade must stay dark"
    # Sanity: the boost IS otherwise live on the fair blocked trade.
    fair = [c for c in cards if "o_fair" in c.receive_player_ids]
    assert fair and all(c.block_boosted for c in fair)


# ---------------------------------------------------------------------------
# 5. Multi-blocked handling — one flat bump, not compounded/graded
# ---------------------------------------------------------------------------

def test_block_boost_multi_blocked_is_flat(monkeypatch):
    """A card acquiring several blocked players gets a SINGLE flat bump."""
    players, user_roster, user_elo, seed_elo, league = _block_league()

    _set_flags()   # baseline composites (block off)
    base_cards = _gen(players, league, user_roster, user_elo, seed_elo)
    multi = next((c for c in base_cards if len(c.receive_player_ids) >= 2), None)
    assert multi is not None, "fixture produced no multi-asset receive card"
    give, recv = list(multi.give_player_ids), list(multi.receive_player_ids)
    base_composite = multi.composite_score

    # Flag EVERY received player as on the opponent's block.
    _stub_block(monkeypatch, {"opp": frozenset(recv)})
    _set_flags("trade.block_boost")
    cards = _gen(players, league, user_roster, user_elo, seed_elo)
    _, boosted = _find(cards, give, recv)
    w = ts._c("block_boost_weight")
    assert boosted.block_boosted is True
    # Flat: exactly one (1 + w) factor, not (1 + w) ** len(recv) or (1 + n*w).
    assert boosted.composite_score == round(base_composite * (1.0 + w), 3)
