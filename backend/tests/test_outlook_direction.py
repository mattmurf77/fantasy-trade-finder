"""Feedback #175 — directional outlook weighting (flag trade.outlook_direction).

"The users outlook should heavily weight the trade suggestions to then
acquiring a younger player or a pick for the player they are giving away.
It's rare that a rebuilder would move a younger player for an older player
(outside of maybe a 1 year gap)."

Covers:
  1. flag-off parity — composites byte-identical, nothing stamped; a
     directionless outlook (not_sure / None) with the flag ON is equally
     byte-identical
  2. rebuilder direction — an older-player return is penalized below an
     otherwise-equal younger-player return; a pick return ranks above an
     older-player return at comparable value
  3. the ~1-year tolerance — an older-by-<=1yr return gets at most the mild
     shift-term penalty, never the age-gap near-exclusion
  4. contender mirror is MILD — no age-gap rule, bounded symmetric term
  5. hard-rule unit coverage on outlook_direction_mult — pick / younger
     comparable-value rescues, sub-floor components never rescue, pick
     primaries and missing ages disable the rule
  6. composition with trade.picks_in_pool — a PICK asset in the pool is
     future capital (negative now-lean) and boosts naturally

Fixture conventions mirror test_block_boost.py (flag isolation, symmetric
divergence pairs that tie absent the feature so only the directional term can
separate them).
"""
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League, LeagueMember, TradeService, outlook_direction_mult,
)


@dataclass
class _Player:
    id: str
    name: str
    position: str = "WR"
    team: str = "TST"
    age: Optional[float] = 25
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
# Orchestrator fixture — symmetric 1-for-1 divergence pairs, distinguished
# ONLY by the age/kind of the received asset
# ---------------------------------------------------------------------------

def _direction_league():
    """The user gives 24yo WRs; the opponent's swappable assets differ only
    in age/kind: o_old (WR 30), o_young (WR 22), o_near (WR 25 — inside the
    1-year tolerance), o_pick (a PICK pseudo-asset, age None). All four carry
    IDENTICAL elo on every board (user 1570, opp 1500, seed 1530), and every
    user give asset is a 24yo WR the opponent over-values at 1570 — so all
    1-for-1 cards tie in composite absent the directional term. Ages never
    enter v2 scoring with the default flag set, which is what makes the tie
    hold; only trade.outlook_direction can separate the cards.

    The user holds a SINGLE divergence give asset (u_a) so higher-surplus
    multi-asset packages stay few enough that every probe 1-for-1 survives
    the top-K cut."""
    players, user_roster, opp_roster = {}, [], []
    for i in range(4):                       # startable ballast on both sides
        up, op = f"u_core{i}", f"o_core{i}"
        players[up] = _Player(id=up, name=up, position="WR", search_rank=40 + i)
        players[op] = _Player(id=op, name=op, position="RB", search_rank=40 + i)
        user_roster.append(up)
        opp_roster.append(op)
    players["u_a"] = _Player(id="u_a", name="u_a", position="WR", age=24,
                             search_rank=60)
    user_roster.append("u_a")
    players["o_old"] = _Player(id="o_old", name="o_old", position="WR",
                               age=30, search_rank=60)
    players["o_young"] = _Player(id="o_young", name="o_young", position="WR",
                                 age=22, search_rank=60)
    players["o_near"] = _Player(id="o_near", name="o_near", position="WR",
                                age=25, search_rank=60)
    players["o_pick"] = _Player(id="o_pick", name="2027 1st", position="PICK",
                                team="PICK", age=None, search_rank=60)
    opp_roster += ["o_old", "o_young", "o_near", "o_pick"]

    recv_assets = ("o_old", "o_young", "o_near", "o_pick")
    give_assets = ("u_a",)
    user_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    opp_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    seed_elo = {pid: 1500.0 for pid in user_roster + opp_roster}
    for pid in recv_assets:
        user_elo[pid] = 1570.0
        seed_elo[pid] = 1530.0
    for pid in give_assets:
        opp_elo[pid] = 1570.0
        seed_elo[pid] = 1530.0

    league = League(league_id="L1", name="L", platform="sleeper", members=[
        _member("user", user_roster, user_elo),
        _member("opp", opp_roster, opp_elo),
    ])
    return players, user_roster, user_elo, seed_elo, league


def _gen(players, league, user_roster, user_elo, seed_elo, outlook):
    svc = TradeService(players=players)
    return svc._generate_trades_v2(
        user_id="user",
        user_elo=user_elo,
        user_roster=user_roster,
        league=league,
        league_id="L1",
        seed_elo=seed_elo,
        max_per_opponent=200,  # wide cut: multi-asset packages outscore the
                               # probe 1-for-1s, so the final cut must keep
                               # everything for _find to work
        fairness_threshold=0.75,
        acquire_positions=None,
        trade_away_positions=None,
        pinned_give_players=None,
        pinned_receive_players=None,
        scoring_format="1qb_ppr",
        on_opponent_done=None,
        confidence=None,
        outlook=outlook,
    )


def _find(cards, give, recv):
    for i, c in enumerate(cards):
        if (set(c.give_player_ids) == set(give)
                and set(c.receive_player_ids) == set(recv)):
            return i, c
    raise AssertionError(f"card {give}->{recv} not in deck "
                         f"{[(c.give_player_ids, c.receive_player_ids) for c in cards]}")


def _score_map(cards):
    return {(frozenset(c.give_player_ids), frozenset(c.receive_player_ids)):
            c.composite_score for c in cards}


# ---------------------------------------------------------------------------
# 1. Flag off / directionless outlook — byte-identical, nothing stamped
# ---------------------------------------------------------------------------

def test_flag_off_parity():
    players, user_roster, user_elo, seed_elo, league = _direction_league()
    _set_flags()   # v2 only, outlook_direction OFF
    cards = _gen(players, league, user_roster, user_elo, seed_elo, "rebuilder")
    assert cards, "generation produced no cards"
    assert all(c.outlook_dir is None for c in cards)
    # The four receive assets are interchangeable absent the feature: every
    # 1-for-1 from the same give asset carries the same composite.
    _, old = _find(cards, ["u_a"], ["o_old"])
    _, young = _find(cards, ["u_a"], ["o_young"])
    _, pick = _find(cards, ["u_a"], ["o_pick"])
    assert old.composite_score == young.composite_score == pick.composite_score


@pytest.mark.parametrize("outlook", ["not_sure", None])
def test_directionless_outlook_zero_effect(outlook):
    players, user_roster, user_elo, seed_elo, league = _direction_league()
    _set_flags()   # baseline: feature off
    base = _score_map(_gen(players, league, user_roster, user_elo, seed_elo,
                           outlook))
    _set_flags("trade.outlook_direction")
    cards = _gen(players, league, user_roster, user_elo, seed_elo, outlook)
    assert cards
    assert all(c.outlook_dir is None for c in cards)
    assert _score_map(cards) == base


# ---------------------------------------------------------------------------
# 2. Rebuilder direction — younger/pick returns above older returns
# ---------------------------------------------------------------------------

def test_rebuilder_penalizes_older_return_below_younger():
    players, user_roster, user_elo, seed_elo, league = _direction_league()
    _set_flags()   # baseline composites for the exact-math check
    base = _score_map(_gen(players, league, user_roster, user_elo, seed_elo,
                           "rebuilder"))
    _set_flags("trade.outlook_direction")
    cards = _gen(players, league, user_roster, user_elo, seed_elo, "rebuilder")

    old_idx, old = _find(cards, ["u_a"], ["o_old"])
    young_idx, young = _find(cards, ["u_a"], ["o_young"])
    assert old.composite_score < young.composite_score
    assert old_idx > young_idx
    assert old.outlook_dir is not None and old.outlook_dir < 1.0
    assert young.outlook_dir is not None and young.outlook_dir > 1.0
    # The older return is crushed by the age-gap rule (30 > 24 + 1, no
    # rescue on a 1-for-1) — "near-excluded", far beyond the mild band.
    assert old.outlook_dir < ts._c("outlook_dir_age_gap_mult") * 1.0 + 0.05
    # Exact math: composite = base * outlook_direction_mult on consensus.
    _vs = lambda pid: ts.elo_to_value(seed_elo.get(pid, 1500.0))
    for c in (old, young):
        key = (frozenset(c.give_player_ids), frozenset(c.receive_player_ids))
        m = outlook_direction_mult(c.give_player_ids, c.receive_player_ids,
                                   players, "rebuilder", _vs)
        assert c.composite_score == round(base[key] * m, 3)
    # Gates untouched: identical divergence + consensus fairness.
    assert old.fairness_score == young.fairness_score
    assert old.mismatch_score == young.mismatch_score


def test_rebuilder_ranks_pick_return_above_older_return():
    players, user_roster, user_elo, seed_elo, league = _direction_league()
    _set_flags("trade.outlook_direction")
    cards = _gen(players, league, user_roster, user_elo, seed_elo, "rebuilder")

    pick_idx, pick = _find(cards, ["u_a"], ["o_pick"])
    old_idx, old = _find(cards, ["u_a"], ["o_old"])
    assert pick.composite_score > old.composite_score
    assert pick_idx < old_idx
    # Pick = pure future capital: boosted, and above the young player too
    # (its now-lean is more negative than a 22yo WR's).
    _, young = _find(cards, ["u_a"], ["o_young"])
    assert pick.outlook_dir > 1.0
    assert pick.outlook_dir > young.outlook_dir


# ---------------------------------------------------------------------------
# 3. The ~1-year tolerance — older-by-<=1yr is NOT hard-penalized
# ---------------------------------------------------------------------------

def test_one_year_gap_not_hard_penalized():
    players, user_roster, user_elo, seed_elo, league = _direction_league()
    _set_flags("trade.outlook_direction")
    cards = _gen(players, league, user_roster, user_elo, seed_elo, "rebuilder")

    _, near = _find(cards, ["u_a"], ["o_near"])   # 25yo for a 24yo give
    _, old = _find(cards, ["u_a"], ["o_old"])     # 30yo for a 24yo give
    # o_near gets at most the mild shift-term penalty; the near-exclusion
    # multiplier never fires inside the tolerance.
    assert near.outlook_dir is not None
    assert near.outlook_dir > 0.75          # mild (measured ~0.87)
    assert near.outlook_dir > old.outlook_dir * 3
    assert near.composite_score > old.composite_score


# ---------------------------------------------------------------------------
# 4. Contender mirror — mild scoring term only, no age-gap rule
# ---------------------------------------------------------------------------

def test_contender_mirror_is_mild():
    players, user_roster, user_elo, seed_elo, league = _direction_league()
    _set_flags("trade.outlook_direction")
    cards = _gen(players, league, user_roster, user_elo, seed_elo, "contender")

    _, old = _find(cards, ["u_a"], ["o_old"])
    _, young = _find(cards, ["u_a"], ["o_young"])
    _, pick = _find(cards, ["u_a"], ["o_pick"])
    # Positive shift (acquiring the older producer) boosted; future capital
    # mildly penalized. Everything stays inside a tight band — no crush.
    assert old.outlook_dir > 1.0
    assert pick.outlook_dir < 1.0
    assert young.outlook_dir < 1.0
    for c in (old, young, pick):
        assert 0.8 < c.outlook_dir < 1.25
    assert old.composite_score > young.composite_score > 0


def test_championship_same_side_as_contender():
    players, user_roster, user_elo, seed_elo, league = _direction_league()
    _set_flags("trade.outlook_direction")
    cards = _gen(players, league, user_roster, user_elo, seed_elo,
                 "championship")
    _, old = _find(cards, ["u_a"], ["o_old"])
    assert old.outlook_dir > 1.0


# ---------------------------------------------------------------------------
# 5. Hard-rule unit coverage on outlook_direction_mult
# ---------------------------------------------------------------------------

def _mini(players):
    values = {pid: 1000.0 for pid in players}
    return players, (lambda pid: values.get(pid, 1000.0)), values


def test_hard_rule_rescued_by_comparable_pick():
    players = {
        "give": _Player(id="give", name="g", position="WR", age=24),
        "old":  _Player(id="old", name="o", position="WR", age=30),
        "pick": _Player(id="pick", name="p", position="PICK", age=None),
    }
    players, value_of, values = _mini(players)
    values["pick"] = 600.0    # >= rescue_frac (0.5) * 1000
    crushed = outlook_direction_mult(["give"], ["old"], players,
                                     "rebuilder", value_of)
    rescued = outlook_direction_mult(["give"], ["old", "pick"], players,
                                     "rebuilder", value_of)
    # Same-shape sanity: the unrescued 1-for-1 carries the near-exclusion
    # factor; adding a comparable-value pick removes it.
    assert crushed < ts._c("outlook_dir_age_gap_mult")
    assert rescued > ts._c("outlook_dir_age_gap_mult") * 2


def test_hard_rule_rescued_by_comparable_younger_player():
    players = {
        "give":  _Player(id="give", name="g", position="WR", age=24),
        "old":   _Player(id="old", name="o", position="WR", age=30),
        "young": _Player(id="young", name="y", position="WR", age=22),
    }
    players, value_of, values = _mini(players)
    values["young"] = 700.0
    rescued = outlook_direction_mult(["give"], ["old", "young"], players,
                                     "rebuilder", value_of)
    assert rescued > ts._c("outlook_dir_age_gap_mult") * 2


def test_hard_rule_sub_floor_component_never_rescues():
    players = {
        "give": _Player(id="give", name="g", position="WR", age=24),
        "old":  _Player(id="old", name="o", position="WR", age=30),
        "pick": _Player(id="pick", name="p", position="PICK", age=None),
    }
    players, value_of, values = _mini(players)
    values["pick"] = 100.0    # < rescue_frac * 1000 — junk throw-in
    m = outlook_direction_mult(["give"], ["old", "pick"], players,
                               "rebuilder", value_of)
    assert m < ts._c("outlook_dir_age_gap_mult")


def test_hard_rule_needs_player_primaries_and_ages():
    players = {
        "gpick": _Player(id="gpick", name="gp", position="PICK", age=None),
        "old":   _Player(id="old", name="o", position="WR", age=30),
        "give":  _Player(id="give", name="g", position="WR", age=24),
        "noage": _Player(id="noage", name="n", position="WR", age=None),
    }
    players, value_of, _ = _mini(players)
    # Primary give is a PICK → rule can't judge; ONLY the shift term runs
    # (giving a pick for a vet is already heavily shift-penalized).
    # shift = (now_lean(WR30) − now_lean(PICK))/2 = (0.34 + 0.25)/2 = 0.295
    m = outlook_direction_mult(["gpick"], ["old"], players,
                               "rebuilder", value_of)
    assert m == pytest.approx(max(0.05, 1.0 - 3.0 * 0.295))
    # Missing age on the return primary → rule stays out; shift term only:
    # shift = (0 − (−0.10))/2 = 0.05 → 1 − 3·0.05 = 0.85, no ×0.15 factor.
    m = outlook_direction_mult(["give"], ["noage"], players,
                               "rebuilder", value_of)
    assert m == pytest.approx(0.85)


def test_hard_rule_exact_tolerance_boundary():
    players = {
        "give": _Player(id="give", name="g", position="WR", age=24),
        "at":   _Player(id="at", name="a", position="WR", age=25),    # +1.0
        "past": _Player(id="past", name="p", position="WR", age=26),  # +2.0
    }
    players, value_of, _ = _mini(players)
    at_tol = outlook_direction_mult(["give"], ["at"], players,
                                    "rebuilder", value_of)
    past_tol = outlook_direction_mult(["give"], ["past"], players,
                                      "rebuilder", value_of)
    assert at_tol > 0.75                                  # mild only
    assert past_tol < ts._c("outlook_dir_age_gap_mult")   # crushed


def test_contender_never_crushes():
    players = {
        "give": _Player(id="give", name="g", position="WR", age=24),
        "old":  _Player(id="old", name="o", position="WR", age=30),
    }
    players, value_of, _ = _mini(players)
    m = outlook_direction_mult(["give"], ["old"], players,
                               "contender", value_of)
    assert m > 1.0    # buying a producer is a window move for a contender


# ---------------------------------------------------------------------------
# 6. Composition with trade.picks_in_pool
# ---------------------------------------------------------------------------

def test_composes_with_picks_in_pool_flag():
    """#170 injects owned picks into the candidate pool server-side; at the
    engine level a PICK asset's now-lean is negative, so with both flags on a
    pick return is boosted and outranks the older-player return with no extra
    wiring."""
    players, user_roster, user_elo, seed_elo, league = _direction_league()
    _set_flags("trade.outlook_direction", "trade.picks_in_pool")
    cards = _gen(players, league, user_roster, user_elo, seed_elo, "rebuilder")

    pick_idx, pick = _find(cards, ["u_a"], ["o_pick"])
    old_idx, old = _find(cards, ["u_a"], ["o_old"])
    assert pick.outlook_dir > 1.0
    assert pick.composite_score > old.composite_score
    assert pick_idx < old_idx
