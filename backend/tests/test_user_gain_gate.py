"""#108 — user-board gain gate (TradesHome: "why would I trade Maye for Dart?").

A card must never ask the user to send a player they rank ABOVE the player
they receive on their OWN board, unless the package compensates:

  * Divergence paths (v2 _consider + v3 optimizer) gate surpluses on the
    SHRUNK board — confidence shrinkage can pull a lightly-sampled player
    toward a consensus that inverts the user's raw ordering (amplified by,
    but not dependent on, the #113 consensus-format corruption). The #108
    gate re-checks 1-for-1 swaps against the user's raw board.
  * Consensus-basis cards were gated by fairness ONLY (TC-CFG-001): the
    user could be the side paying up to (1 − threshold) more consensus
    value, and the user's own board was never consulted. Now the user-side
    consensus delta must be ≥ user_gain_epsilon AND a 1-for-1 must respect
    the user's raw board.

Repro fixture: user board MAYE 1700 (their QB2) > DART 1560 (their QB5);
corrupt consensus has DART above MAYE. Each repro asserts the card is dark
by default and pins the pre-fix leak by disabling the gate
(user_gain_epsilon = -1e9) and watching the same card surface.

Multi-asset packages stay exempt from the raw-board rule — the aggregate
surplus gate is the compensation test (pinned below).
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    elo_to_value,
    user_gain_ok_1for1,
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


class _Player:
    def __init__(self, pid, position="QB"):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = "TST"
        self.age = 24
        self.ktc_value = None


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _svc(positions, opponents):
    players = {pid: _Player(pid, pos) for pid, pos in positions.items()}
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo",
                        members=opponents))
    return s


def _member(uid, roster, elo, has_rankings=True):
    return LeagueMember(user_id=uid, username=uid, roster=roster,
                        elo_ratings=elo, has_rankings=has_rankings)


def _gen(svc, user_elo, user_roster, seed_elo, **kw):
    return svc.generate_trades(user_id="user", user_elo=user_elo,
                               user_roster=user_roster, league_id="L1",
                               seed_elo=seed_elo, **kw)


def _find(cards, give, recv):
    g, r = tuple(sorted(give)), tuple(sorted(recv))
    for c in cards:
        if (tuple(sorted(c.give_player_ids)),
                tuple(sorted(c.receive_player_ids))) == (g, r):
            return c
    return None


# ───────────────────────────────────────────────────────────────────────────
# Repro fixture: Maye-for-Dart on the divergence path
# ───────────────────────────────────────────────────────────────────────────
# User's raw board: MAYE 1700 >> DART 1560 ("Maye is my QB2, Dart my QB5").
# Corrupt consensus (#113-style) prices DART just above MAYE (1700 vs
# 1680). Neither player has trio comparisons (confidence 0), so shrinkage
# w = n/(n+4) = 0 collapses the shrunk board onto the corrupt consensus:
# phantom user surplus ≈ 548 ≥ 150, opp surplus huge (they prefer MAYE),
# consensus fairness 0.798 ≥ 0.75 — every pre-#108 gate passes.

_RAW_USER = {"MAYE": 1700, "DART": 1560}
_OPP = {"MAYE": 1750, "DART": 1500}
_CORRUPT_SEED = {"MAYE": 1680, "DART": 1700}
_CONF = {"MAYE": 0, "DART": 0}


def _divergence_fixture():
    opp = _member("opp", ["DART"], dict(_OPP))
    svc = _svc({"MAYE": "QB", "DART": "QB"}, [opp])
    return svc


def test_v2_divergence_maye_for_dart_repro():
    """v2 1-for-1: user's raw board says MAYE > DART → card must be dark.
    Disabling the gate resurrects it, pinning the pre-fix leak."""
    _set_flags(**{"trade_engine.v2": True})
    cards = _gen(_divergence_fixture(), dict(_RAW_USER), ["MAYE"],
                 dict(_CORRUPT_SEED), confidence=dict(_CONF),
                 fairness_threshold=0.75, max_per_opponent=5)
    assert _find(cards, ["MAYE"], ["DART"]) is None, (
        "1-for-1 offering the user's higher-ranked player leaked through")

    ts._cfg["user_gain_epsilon"] = -1e9          # gate off → old behavior
    cards = _gen(_divergence_fixture(), dict(_RAW_USER), ["MAYE"],
                 dict(_CORRUPT_SEED), confidence=dict(_CONF),
                 fairness_threshold=0.75, max_per_opponent=5)
    assert _find(cards, ["MAYE"], ["DART"]) is not None, (
        "fixture no longer reproduces the original leak — repro invalid")


def _v3_fixture():
    """Same repro with full legal lineups so v3 feasibility can't veto.
    Fillers are zero-divergence (user == opp == seed == 1500)."""
    fill_u = {"RBu1": "RB", "RBu2": "RB", "WRu1": "WR", "WRu2": "WR",
              "TEu": "TE"}
    fill_o = {"RBo1": "RB", "RBo2": "RB", "WRo1": "WR", "WRo2": "WR",
              "TEo": "TE"}
    positions = {"MAYE": "QB", "DART": "QB", **fill_u, **fill_o}
    flat = {pid: 1500 for pid in list(fill_u) + list(fill_o)}
    user_elo = {**_RAW_USER, **flat}
    opp_elo = {**_OPP, **flat}
    seed = {**_CORRUPT_SEED, **flat}
    opp = _member("opp", ["DART"] + list(fill_o), opp_elo)
    svc = _svc(positions, [opp])
    return svc, user_elo, ["MAYE"] + list(fill_u), seed


def test_v3_divergence_maye_for_dart_repro():
    """The v3 optimizer (live path in prod) enforces the same raw-board
    rule for 1-for-1 swaps. v3_pool_size=1 pins the candidate pools to the
    divergent pair so filler-padded sibling packages can't crowd the
    1-for-1 out of the diverse top-K and muddy the assertion."""
    _set_flags(**{"trade_engine.v2": True, "trade_engine.v3": True})
    ts._cfg["v3_pool_size"] = 1
    svc, ue, ur, seed = _v3_fixture()
    cards = _gen(svc, ue, ur, seed, confidence=dict(_CONF),
                 fairness_threshold=0.75, max_per_opponent=8)
    assert _find(cards, ["MAYE"], ["DART"]) is None

    ts._cfg["user_gain_epsilon"] = -1e9
    svc, ue, ur, seed = _v3_fixture()
    cards = _gen(svc, ue, ur, seed, confidence=dict(_CONF),
                 fairness_threshold=0.75, max_per_opponent=8)
    assert _find(cards, ["MAYE"], ["DART"]) is not None, (
        "v3 fixture no longer reproduces the original leak — repro invalid")


# ───────────────────────────────────────────────────────────────────────────
# Consensus-basis path (opponent without rankings) — TC-CFG-001 bypass
# ───────────────────────────────────────────────────────────────────────────

def _consensus_run(seed, user_roster_pid, opp_roster_pid, user_elo=None):
    _set_flags(**{"trade_engine.v2": True})
    opp = _member("opp", [opp_roster_pid], {}, has_rankings=False)
    svc = _svc({"MAYE": "QB", "DART": "QB"}, [opp])
    return _gen(svc, dict(user_elo or _RAW_USER), [user_roster_pid],
                dict(seed), fairness_threshold=0.75, max_per_opponent=5)


def test_consensus_user_must_gain_by_consensus():
    """CORRECT consensus (MAYE > DART, inside fairness): a consensus card
    must not ask the user to pay the higher-consensus player. Independent
    of the #113 value fix. Disabling the gate restores the old bypass."""
    seed = {"MAYE": 1600, "DART": 1580}          # fairness 0.799 ≥ 0.75
    cards = _consensus_run(seed, "MAYE", "DART")
    assert _find(cards, ["MAYE"], ["DART"]) is None, (
        "consensus card asked the user to send more consensus value")

    ts._cfg["user_gain_epsilon"] = -1e9
    cards = _consensus_run(seed, "MAYE", "DART")
    assert _find(cards, ["MAYE"], ["DART"]) is not None, (
        "fixture no longer reproduces the TC-CFG-001 bypass — repro invalid")


def test_consensus_gaining_direction_still_surfaces():
    """Positive control: the same swap oriented so the USER gains by
    consensus (and by their own board) surfaces normally."""
    seed = {"MAYE": 1600, "DART": 1580}
    cards = _consensus_run(seed, "DART", "MAYE")
    assert _find(cards, ["DART"], ["MAYE"]) is not None


def test_consensus_respects_raw_board_even_when_seed_flips():
    """CORRUPT consensus (#113-style, DART above MAYE): the consensus delta
    now favors the user, but their own raw board (MAYE > DART) still vetoes
    the 1-for-1 — the fix stands even while consensus values are wrong."""
    seed = {"MAYE": 1580, "DART": 1600}          # rv-gv > 0, fairness 0.799
    cards = _consensus_run(seed, "MAYE", "DART")
    assert _find(cards, ["MAYE"], ["DART"]) is None, (
        "consensus card contradicted the user's own board ordering")

    ts._cfg["user_gain_epsilon"] = -1e9
    cards = _consensus_run(seed, "MAYE", "DART")
    assert _find(cards, ["MAYE"], ["DART"]) is not None


# ───────────────────────────────────────────────────────────────────────────
# Multi-asset packages: compensation still allowed; epsilon knob; helper
# ───────────────────────────────────────────────────────────────────────────

def test_multi_asset_package_can_compensate():
    """1-for-2 where EACH received player sits below the give on the user's
    raw board, but the aggregate clears the surplus gate → still surfaces
    (the raw-board rule is strictly a 1-for-1 rule)."""
    _set_flags(**{"trade_engine.v2": True})
    user_elo = {"MAYE": 1700, "R1": 1690, "R2": 1600}
    opp_elo = {"MAYE": 1780, "R1": 1500, "R2": 1450}
    seed = {"MAYE": 1650, "R1": 1640, "R2": 1600}
    opp = _member("opp", ["R1", "R2"], opp_elo)
    svc = _svc({"MAYE": "QB", "R1": "QB", "R2": "QB"}, [opp])
    cards = _gen(svc, user_elo, ["MAYE"], seed, confidence=None,
                 fairness_threshold=0.5, max_per_opponent=5)
    card = _find(cards, ["MAYE"], ["R1", "R2"])
    assert card is not None, "compensated 1-for-2 package was wrongly gated"
    # Document the premise: each received player is individually below the
    # give on the user's own board.
    assert user_elo["R1"] < user_elo["MAYE"]
    assert user_elo["R2"] < user_elo["MAYE"]


def test_user_gain_epsilon_is_tunable():
    """A mild-gain 1-for-1 (raw-board delta ~350 value) surfaces at the
    default epsilon 0 and is vetoed when epsilon exceeds the delta."""
    _set_flags(**{"trade_engine.v2": True})
    user_elo = {"G": 1500, "R": 1560}
    opp_elo = {"G": 1700, "R": 1500}
    seed = {"G": 1500, "R": 1520}

    def run():
        opp = _member("opp", ["R"], dict(opp_elo))
        svc = _svc({"G": "QB", "R": "QB"}, [opp])
        return _gen(svc, dict(user_elo), ["G"], dict(seed),
                    fairness_threshold=0.75, max_per_opponent=5)

    assert _find(run(), ["G"], ["R"]) is not None, "default epsilon 0 gated a gaining swap"
    delta = elo_to_value(1560) - elo_to_value(1500)
    ts._cfg["user_gain_epsilon"] = delta + 1.0
    assert _find(run(), ["G"], ["R"]) is None, "epsilon above the delta did not gate"


def test_helper_semantics():
    """user_gain_ok_1for1: multi-asset and unknown-board cases pass; a
    give ranked above the receive on the raw board fails."""
    board = {"A": 1700, "B": 1560}
    assert not user_gain_ok_1for1(["A"], ["B"], board)
    assert user_gain_ok_1for1(["B"], ["A"], board)
    assert user_gain_ok_1for1(["A"], ["B", "X"], board)      # multi-asset exempt
    assert user_gain_ok_1for1(["A"], ["UNKNOWN"], board)     # no board signal
    assert user_gain_ok_1for1(["A"], ["B"], None)            # no board at all
    assert user_gain_ok_1for1(["A"], ["A2"], {"A": 1500, "A2": 1500})  # tie passes at ε=0
