"""#227 — "1:1 trades for draft picks should never be a suggestion."

Picks carry zero divergence by construction (every board is primed with the
same bridged Elo — see server._pick_asset_elos), so a 1-for-1 pick-for-pick
card that clears the fairness gate is ~equal-value churn with no mutual-gain
basis. In prod these surfaced through the #189 relaxed pass, whose
"fairness_band+surplus_floor" stage drops the both-sides surplus minimum to
0.0 — a zero-surplus pick swap then passes every remaining gate (fairness of
two similar picks ≈ 1.0). The fixtures below emulate that stage by pinning
min_side_surplus to 0.

The gate (trade_service.pick_swap_ok) is deliberately NARROW:
  • 1-for-1 BOTH-sides-pick → banned outright (the operator's ask);
  • pick-for-player / player-for-pick 1-for-1s → allowed;
  • pick + player packages and pure pick-for-pick 2-for-1 consolidations →
    allowed (shape change has genuine utility even at equal value).

Covered paths: v2 pair (_consider), v3 optimizer (enumeration — gated before
near-miss collection so the 3.4 sweetener pass can't rescue the shape), and
the consensus fallback (_emit, exercised via a pinned receive pick). Each
engine fixture proves its own validity by monkeypatching the gate open and
asserting the degenerate card DOES appear (pre-#227 behavior).
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    is_pick_asset,
    pick_swap_ok,
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
    def __init__(self, pid, position="WR", team="TST"):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = team
        self.age = 24
        self.ktc_value = None


class _Pick:
    """Owned-pick pseudo-player, shaped like server._owned_pick_assets'."""

    def __init__(self, pid, pick_value=60.0):
        self.id = pid
        self.name = pid
        self.position = "PICK"
        self.team = "PICK"
        self.age = 0
        self.pick_value = pick_value
        self.ktc_value = None


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _member(uid, roster, elo, has_rankings=True):
    return LeagueMember(user_id=uid, username=uid, roster=roster,
                        elo_ratings=elo, has_rankings=has_rankings)


def _svc(players, opponents):
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo",
                        members=opponents))
    return s


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

def test_is_pick_asset_detection():
    assert is_pick_asset(_Pick("L_2027_1_1"))
    # generic pool picks: REAL position, team == "PICK"
    assert is_pick_asset(_Player("generic_pick_1_early", "RB", team="PICK"))
    assert not is_pick_asset(_Player("wr1", "WR"))
    assert not is_pick_asset(None)


def test_pick_swap_ok_truth_table():
    players = {
        "PK_A": _Pick("PK_A"), "PK_B": _Pick("PK_B"), "PK_C": _Pick("PK_C"),
        "W1": _Player("W1"), "W2": _Player("W2"),
    }
    # the banned shape: 1-for-1, both sides picks
    assert not pick_swap_ok(["PK_A"], ["PK_B"], players)
    # pick for player / player for pick 1-for-1s are real trades
    assert pick_swap_ok(["PK_A"], ["W1"], players)
    assert pick_swap_ok(["W1"], ["PK_A"], players)
    # players only — untouched
    assert pick_swap_ok(["W1"], ["W2"], players)
    # pick + player packages pass (picks as sweeteners are legitimate)
    assert pick_swap_ok(["PK_A", "W1"], ["PK_B"], players)
    # pure pick-for-pick CONSOLIDATION (2-for-1) passes — documented decision
    assert pick_swap_ok(["PK_A", "PK_B"], ["PK_C"], players)
    # unknown ids never crash the gate
    assert pick_swap_ok(["nope"], ["PK_A"], players)


# ───────────────────────────────────────────────────────────────────────────
# Shared engine fixture — user and opponent each hold one pick + players.
# Pick elos are IDENTICAL on every board (as primed in prod) AND equal to
# each other — two same-round 2027 2nds from different original teams, the
# operator's exact "pointless churn" sighting. Zero surplus both sides ⇒
# the swap passes once min_side_surplus = 0 (the #189 relaxed stage), with
# fairness 1.0. Unequal picks can't leak through the divergence paths
# (identical boards make any value difference zero-sum — one side's
# surplus goes negative), so the equal-value swap IS the leak shape.
# ───────────────────────────────────────────────────────────────────────────

_PK_U, _PK_O = "L1_2027_2_1", "L1_2027_2_5"
_PICK_ELOS = {_PK_U: 1400.0, _PK_O: 1400.0}

_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix):
    return {f"{prefix}_{pid}": pos for pid, pos in _BASE_POS.items()}


def _pair_fixture():
    """Feasible rosters (full body sets both sides) + one pick each. The
    bodies carry slight NEGATIVE divergence both ways (inert — no organic
    player cards outscore the swap and crowd it out of the top-N cut), so
    the zero-surplus pick swap is the only 1-for-1 that clears the gates:
    exactly the shape the relaxed pass surfaced in prod."""
    pos = {**_bodies("u"), **_bodies("o")}
    players = {pid: _Player(pid, p) for pid, p in pos.items()}
    players[_PK_U] = _Pick(_PK_U, 33.3)
    players[_PK_O] = _Pick(_PK_O, 33.3)
    user_roster = list(_bodies("u")) + [_PK_U]
    opp_roster = list(_bodies("o")) + [_PK_O]
    user_elo = {pid: 1500.0 for pid in pos}
    opp_elo = {pid: 1500.0 for pid in pos}
    for pid in _bodies("u"):
        opp_elo[pid] = 1490.0
    for pid in _bodies("o"):
        user_elo[pid] = 1490.0
    user_elo.update(_PICK_ELOS)
    opp_elo.update(_PICK_ELOS)
    seed = {pid: 1500.0 for pid in pos}
    seed.update(_PICK_ELOS)
    opp = _member("opp", opp_roster, opp_elo)
    svc = _svc(players, [opp])
    return svc, user_elo, user_roster, seed


def _run(v3: bool):
    _set_flags(**{"trade_engine.v2": True, "trade_engine.v3": v3})
    # the #189 relaxed stage's surplus floor — zero-surplus swaps pass
    ts._cfg["min_side_surplus"] = 0.0
    ts._cfg["min_side_surplus_marginal"] = 0.0
    svc, ue, ur, seed = _pair_fixture()
    return _gen(svc, ue, ur, seed, fairness_threshold=0.6,
                max_per_opponent=12)


# ── v2 pair path (_consider) ───────────────────────────────────────────────

def test_v2_pick_for_pick_1for1_never_emitted(monkeypatch):
    cards = _run(v3=False)
    assert _find(cards, [_PK_U], [_PK_O]) is None, (
        "a 1-for-1 pick-for-pick card surfaced through the v2 pair path")
    # fixture validity: with the gate held open the degenerate card appears
    monkeypatch.setattr(ts, "pick_swap_ok", lambda *a, **k: True)
    cards = _run(v3=False)
    assert _find(cards, [_PK_U], [_PK_O]) is not None, (
        "v2 fixture no longer reproduces the pre-#227 leak — repro invalid")


# ── v3 optimizer path (enumeration) ────────────────────────────────────────

def test_v3_pick_for_pick_1for1_never_emitted(monkeypatch):
    ts._cfg["v3_diversity_max_overlap"] = 1.0
    cards = _run(v3=True)
    assert _find(cards, [_PK_U], [_PK_O]) is None, (
        "a 1-for-1 pick-for-pick card surfaced through the v3 optimizer")
    # fixture validity: gate held open ⇒ the degenerate card appears
    import backend.trade_optimizer as topt
    monkeypatch.setattr(topt, "pick_swap_ok", lambda *a, **k: True)
    ts._cfg["v3_diversity_max_overlap"] = 1.0
    cards = _run(v3=True)
    assert _find(cards, [_PK_U], [_PK_O]) is not None, (
        "v3 fixture no longer reproduces the pre-#227 leak — repro invalid")


# ── consensus fallback path (_emit) — opponent with no rankings ────────────

def _consensus_run():
    """Pinned receive pick (FB-47 pins bypass the need-position filter) so
    the recv pool is exactly the opponent's pick; the user's own pick is the
    best-value give. Equal consensus values pass user_gain_epsilon (0) with
    fairness 1.0 — the degenerate swap the gate exists for."""
    _set_flags(**{"trade_engine.v2": True})
    players = {_PK_U: _Pick(_PK_U, 33.3), _PK_O: _Pick(_PK_O, 33.3),
               "G1": _Player("G1", "QB")}
    opp = _member("opp", [_PK_O], {}, has_rankings=False)
    svc = _svc(players, [opp])
    seed = {"G1": 1200.0, **_PICK_ELOS}
    return _gen(svc, {"G1": 1200.0, **_PICK_ELOS}, ["G1", _PK_U], seed,
                fairness_threshold=0.6, max_per_opponent=8,
                pinned_receive_players=[_PK_O])


def test_consensus_pick_for_pick_1for1_never_emitted(monkeypatch):
    cards = _consensus_run()
    assert _find(cards, [_PK_U], [_PK_O]) is None, (
        "a 1-for-1 pick-for-pick card surfaced through the consensus path")
    # fixture validity: gate held open ⇒ the degenerate card appears
    monkeypatch.setattr(ts, "pick_swap_ok", lambda *a, **k: True)
    cards = _consensus_run()
    assert _find(cards, [_PK_U], [_PK_O]) is not None, (
        "consensus fixture no longer reproduces the pre-#227 leak")
