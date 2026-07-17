"""#141 — junk-filler gate (TradesHome: "suggestions add low-value players
to both sides").

Any piece beyond a side's headliner must be worth at least
``filler_min_frac`` of that headliner, where each player is priced at the
MAX of the two boards (user's and opponent's raw values) — a filler EITHER
side genuinely values is a legitimate piece; junk BOTH boards value low
never pads a suggestion. Headliners (the 1-for-1 core) are exempt: the
gate touches ADDITIONS only, and it never weakens the fairness /
user-gain / surplus gates (it only removes cards, never rescues them).

Covered paths: v2 pair (_consider), v3 optimizer (enumeration + the 3.4
sweetener pass) and consensus fallback (_emit). filler_min_frac = 0
restores pre-#141 behavior byte-identically (pinned below).

Repro fixture (raw values, marginal off): user gives [G1, JUNK] for [R].
G1 1500/1620/seed 1520, R 1620/1500/seed 1560 — a healthy divergence
2-for-1 — and JUNK 1220 on BOTH boards (value ~247 vs a 1822 max-board
headliner: 247 < 0.25 * 1822 = 456 → gated). Every pre-#141 gate passes:
surpluses ~1279/~948 >= 150, consensus ratio ~0.678, multi-asset #108
exemption.
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    filler_ok,
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
    def __init__(self, pid, position="WR"):
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
# Helper semantics
# ───────────────────────────────────────────────────────────────────────────

def test_helper_semantics():
    uval = {"H": 2000.0, "MID": 700.0, "JUNK": 100.0, "GOLD": 100.0}.get
    oval = {"H": 1500.0, "MID": 300.0, "JUNK": 120.0, "GOLD": 1200.0}.get

    # 1-for-1 core is exempt regardless of values.
    assert filler_ok(["JUNK"], ["H"], uval, oval)
    # A filler below frac * headliner on BOTH boards is junk.
    assert not filler_ok(["H", "JUNK"], ["MID"], uval, oval)
    # The max rule: one board valuing the piece highly rescues it.
    assert filler_ok(["H", "GOLD"], ["MID"], uval, oval)
    # The receive side is gated the same way as the give side.
    assert not filler_ok(["H"], ["MID", "JUNK"], uval, oval)
    # A meaningful piece (700 >= 0.25 * max-board 1200) passes both sides.
    assert filler_ok(["H"], ["MID", "GOLD"], uval, oval)
    # frac = 0 disables the gate entirely.
    ts._cfg["filler_min_frac"] = 0.0
    assert filler_ok(["H", "JUNK"], ["MID"], uval, oval)


# ───────────────────────────────────────────────────────────────────────────
# v2 pair path (_consider)
# ───────────────────────────────────────────────────────────────────────────

_V2_POS = {"G1": "WR", "JUNK": "WR", "R": "WR"}
_V2_USER = {"G1": 1500.0, "JUNK": 1220.0, "R": 1620.0}
_V2_OPP = {"G1": 1620.0, "JUNK": 1220.0, "R": 1500.0}
_V2_SEED = {"G1": 1520.0, "JUNK": 1220.0, "R": 1560.0}


def _v2_run(opp_elo=None):
    _set_flags(**{"trade_engine.v2": True})
    opp = _member("opp", ["R"], dict(opp_elo or _V2_OPP))
    svc = _svc(dict(_V2_POS), [opp])
    return _gen(svc, dict(_V2_USER), ["G1", "JUNK"], dict(_V2_SEED),
                fairness_threshold=0.6, max_per_opponent=8)


def test_v2_junk_filler_excluded_from_padded_package():
    """The junk-padded 2-for-1 is dark at the default knob; the clean
    1-for-1 core still surfaces. knob=0 resurrects the padded card,
    pinning the pre-#141 leak."""
    cards = _v2_run()
    assert _find(cards, ["G1", "JUNK"], ["R"]) is None, (
        "junk filler (low on BOTH boards) padded a v2 package")
    assert _find(cards, ["G1"], ["R"]) is not None, (
        "the 1-for-1 core must be untouched by the filler gate")

    ts._cfg["filler_min_frac"] = 0.0
    cards = _v2_run()
    assert _find(cards, ["G1", "JUNK"], ["R"]) is not None, (
        "fixture no longer reproduces the pre-#141 leak — repro invalid")


def test_v2_filler_valued_by_one_board_survives():
    """Same trade, but the OPPONENT values JUNK highly (their board 1620):
    max(user, opp) clears the bar, so the padded package surfaces —
    a piece either side genuinely wants is not junk."""
    opp_elo = dict(_V2_OPP)
    opp_elo["JUNK"] = 1620.0
    cards = _v2_run(opp_elo)
    assert _find(cards, ["G1", "JUNK"], ["R"]) is not None, (
        "the max-of-both-boards rule failed to rescue a wanted piece")


def test_v2_knob_zero_is_byte_identical_to_gate_bypass(monkeypatch):
    """filler_min_frac = 0 must reproduce the exact pre-#141 output:
    same cards, same scores as physically bypassing the gate."""
    ts._cfg["filler_min_frac"] = 0.0
    baseline = _v2_run()

    ts._cfg["filler_min_frac"] = 0.25
    monkeypatch.setattr(ts, "filler_ok", lambda *a, **k: True)
    bypassed = _v2_run()

    def key(cards):
        return sorted((frozenset(c.give_player_ids),
                       frozenset(c.receive_player_ids),
                       c.composite_score, c.fairness_score,
                       c.mismatch_score) for c in cards)
    assert key(baseline) == key(bypassed)


# ───────────────────────────────────────────────────────────────────────────
# v3 optimizer path (enumeration)
# ───────────────────────────────────────────────────────────────────────────

_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix):
    return {f"{prefix}_{pid}": pos for pid, pos in _BASE_POS.items()}


def _v3_fixture():
    """The v2 repro embedded in lineup-feasible rosters. Bodies carry
    slight negative divergence so they stay inert; pool size 2 pins the
    give pool to [G1, JUNK] (divergence order) so body-swap siblings don't
    crowd the assertions out of the top-K, and the diversity filter is
    disabled so the padded sibling is observable when the knob is off."""
    ts._cfg["v3_diversity_max_overlap"] = 1.0
    ts._cfg["v3_pool_size"] = 2
    pos = {**_bodies("u"), **_bodies("o"), **_V2_POS}
    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    for pid in _bodies("u"):
        opp_elo[pid] = 1490.0
    for pid in _bodies("o"):
        user_elo[pid] = 1490.0
    user_elo.update(_V2_USER)
    opp_elo.update(_V2_OPP)
    seed = {pid: 1500.0 for pid in pos}
    seed.update(_V2_SEED)
    opp = _member("opp", list(_bodies("o")) + ["R"], opp_elo)
    svc = _svc(pos, [opp])
    return svc, user_elo, list(_bodies("u")) + ["G1", "JUNK"], seed


def _v3_run():
    _set_flags(**{"trade_engine.v2": True, "trade_engine.v3": True})
    svc, ue, ur, seed = _v3_fixture()
    return _gen(svc, ue, ur, seed, fairness_threshold=0.6,
                max_per_opponent=8)


def test_v3_junk_filler_excluded_from_padded_package():
    cards = _v3_run()
    assert all("JUNK" not in c.give_player_ids and
               "JUNK" not in c.receive_player_ids for c in cards), (
        "junk filler (low on BOTH boards) padded a v3 package")
    assert _find(cards, ["G1"], ["R"]) is not None

    ts._cfg["filler_min_frac"] = 0.0
    cards = _v3_run()
    assert _find(cards, ["G1", "JUNK"], ["R"]) is not None, (
        "v3 fixture no longer reproduces the pre-#141 leak — repro invalid")


# ───────────────────────────────────────────────────────────────────────────
# v3 sweetener pass (3.4) — a sweetener is an ADDED piece, so it is gated
# ───────────────────────────────────────────────────────────────────────────

def _sweetener_fixture():
    """Mirror of test_trade_optimizer._sweetener_fixture(1494.0): a 1-for-1
    near-miss (ratio ~0.624, inside the [0.60, 0.75) band) that the pass
    closes by adding a give-side piece. s1 (seed 1300) is too cheap to
    close the gap; s2 (seed 1455, max-board value ~799) closes it and is
    the pre-#141 pick. Headliner max-board value ~1822 (opp's view of uA)."""
    ts._cfg["v3_pool_size"] = 1
    pos = {**_bodies("u"), **_bodies("o"),
           "uA": "WR", "oA": "WR", "s1": "WR", "s2": "WR"}
    user_roster = list(_bodies("u")) + ["uA", "s1", "s2"]
    opp_roster = list(_bodies("o")) + ["oA"]
    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    for pid in _bodies("u"):
        opp_elo[pid] = 1490.0
    for pid in _bodies("o"):
        user_elo[pid] = 1490.0
    user_elo.update({"oA": 1620.0, "s1": 1455.0, "s2": 1455.0})
    opp_elo.update({"uA": 1620.0, "s1": 1455.0, "s2": 1455.0})
    seed = {pid: 1500.0 for pid in pos}
    seed.update({"uA": 1494.0, "oA": 1536.0, "s1": 1300.0, "s2": 1455.0})
    opp = _member("opp", opp_roster, opp_elo)
    svc = _svc(pos, [opp])
    return svc, user_elo, user_roster, seed


def _sweet_run():
    _set_flags(**{"trade_engine.v2": True, "trade_engine.v3": True})
    # Pin the divergence floor above the passed threshold so 0.75 still
    # governs — the interview-2026-07-17 loosening (default 0.55) would
    # otherwise pass this fixture's near-miss ratio organically and no
    # sweetener would be needed.
    ts._cfg["fairness_floor_divergence"] = 1.0
    svc, ue, ur, seed = _sweetener_fixture()
    return _gen(svc, ue, ur, seed, fairness_threshold=0.75,
                max_per_opponent=5)


def _sweeteners(cards):
    return [getattr(c, "sweetener", None) for c in cards
            if getattr(c, "sweetener", None)]


def test_sweetener_meaningful_piece_survives_default_bar():
    """s2 (~799) clears the default bar (0.25 * ~1822 = ~456): the
    legitimate sweetener rescue is untouched."""
    sweets = _sweeteners(_sweet_run())
    assert {"player_id": "s2", "side": "give"} in sweets


def test_sweetener_below_bar_is_never_used():
    """Raise the bar above s2's max-board value (0.5 * ~1822 = ~911 > 799):
    the junk sweeteners are skipped — whatever the pass picks instead must
    not be s1/s2. knob=0 restores the pre-#141 cheapest-junk pick."""
    ts._cfg["filler_min_frac"] = 0.5
    for s in _sweeteners(_sweet_run()):
        assert s["player_id"] not in ("s1", "s2"), (
            "a sweetener below the filler bar entered a package")

    ts._cfg["filler_min_frac"] = 0.0
    sweets = _sweeteners(_sweet_run())
    assert {"player_id": "s2", "side": "give"} in sweets, (
        "sweetener fixture no longer reproduces pre-#141 behavior")


# ───────────────────────────────────────────────────────────────────────────
# Consensus fallback path (_emit) — opponent with no rankings
# ───────────────────────────────────────────────────────────────────────────

def _consensus_run():
    """QB fixture (valueless test players make every position a 'need', so
    the receive pool survives the roster-fit filter). Seeds make [G1,JUNK]
    -> [R] a fair, user-gaining 2-for-1 pre-#141; JUNK (seed 1220, ~247)
    sits far below the bar of the ~1105 headliner."""
    _set_flags(**{"trade_engine.v2": True})
    pos = {"G1": "QB", "JUNK": "QB", "R": "QB"}
    opp = _member("opp", ["R"], {}, has_rankings=False)
    svc = _svc(pos, [opp])
    return _gen(svc, dict(_V2_USER), ["G1", "JUNK"], dict(_V2_SEED),
                fairness_threshold=0.6, max_per_opponent=8)


def test_consensus_junk_filler_excluded():
    cards = _consensus_run()
    assert _find(cards, ["G1", "JUNK"], ["R"]) is None, (
        "junk filler padded a consensus-basis package")
    assert _find(cards, ["G1"], ["R"]) is not None

    ts._cfg["filler_min_frac"] = 0.0
    cards = _consensus_run()
    assert _find(cards, ["G1", "JUNK"], ["R"]) is not None, (
        "consensus fixture no longer reproduces the pre-#141 leak")
