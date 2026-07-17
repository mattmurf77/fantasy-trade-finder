"""TC-ENG-002 — Fairness-gate golden fixtures (the 1-for-1 fairness-gate watch item).

Targets behaviors the existing v2 suite does NOT pin, all tied to the recorded
"fairness-gate / package-discount" watch item (memory: project_ftf_trade_engine_v2):

  1. package_value_v2 discount math — exact hand-computed values; the
     diminishing-returns knob (package_adj_gamma) that stops "quantity beats
     quality" (a package of mids for one elite).
  2. 1-for-1 gate is config-driven at the knife-edge — a card with reported
     fairness F surfaces at threshold F-ε and is vetoed at threshold F+ε.
  3. The discount propagates to a card's fairness_score — raising gamma lowers
     a multi-give package's fairness in the documented direction.
  4. FR8 market-neutrality — outlook blend moves surpluses/composite but NEVER
     the fairness score (fairness uses consensus seed value only).
  5. v2 <-> v3 fairness-floor parity — a clearly-unfair 1-for-1 is rejected by
     BOTH engines, and a fair card's fairness matches (guards the hand-copied
     _fairness_v3 mirror against silent drift).
  6. Gate monotonicity — raising fairness_threshold never ADDS cards.

All fixtures tiny and deterministic. Flags/_cfg snapshot-restored per test.
"""

import math

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    elo_to_value,
    package_value_v2,
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
    def __init__(self, pid, position="RB"):
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


def _svc(player_ids, opponents, positions=None):
    positions = positions or {}
    players = {pid: _Player(pid, positions.get(pid, "RB")) for pid in player_ids}
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=opponents))
    return s


def _member(uid, roster, elo):
    return LeagueMember(user_id=uid, username=uid, roster=roster,
                        elo_ratings=elo, has_rankings=True)


def _gen(svc, user_elo, user_roster, seed_elo, **kw):
    return svc.generate_trades(user_id="user", user_elo=user_elo,
                               user_roster=user_roster, league_id="L1",
                               seed_elo=seed_elo, **kw)


def _find(cards, give, recv):
    g, r = tuple(sorted(give)), tuple(sorted(recv))
    for c in cards:
        if (tuple(sorted(c.give_player_ids)), tuple(sorted(c.receive_player_ids))) == (g, r):
            return c
    return None


# ───────────────────────────────────────────────────────────────────────────
# 1. package_value_v2 discount math — exact, hand-computed
# ───────────────────────────────────────────────────────────────────────────

def test_package_discount_math_exact():
    """contribution(v) = v·(0.15 + 0.85·(v/v_max)^gamma). Best asset = 100%;
    lesser assets discounted; gamma controls the steepness."""
    ts._cfg["package_adj_gamma"] = 1.5
    # Best asset always contributes 100% of its value regardless of gamma.
    assert package_value_v2([4000.0], 4000.0) == pytest.approx(4000.0)
    # Two equal mids well below the trade max: each discounted to 0.15+0.85·0.25^1.5.
    frac = 0.15 + 0.85 * (1000.0 / 4000.0) ** 1.5
    assert package_value_v2([1000.0, 1000.0], 4000.0) == pytest.approx(round(2000.0 * frac, 1))
    # The package is worth far less than the naive sum (anti "quantity>quality").
    assert package_value_v2([1000.0, 1000.0], 4000.0) < 0.5 * 2000.0


def test_package_discount_monotone_in_gamma():
    """Higher gamma => steeper discount => smaller package for sub-max assets;
    the single best asset is invariant to gamma."""
    vals, vmax = [1500.0, 900.0], 1500.0
    ts._cfg["package_adj_gamma"] = 0.0
    flat = package_value_v2(vals, vmax)            # gamma 0 -> every asset full value
    ts._cfg["package_adj_gamma"] = 1.5
    mid = package_value_v2(vals, vmax)
    ts._cfg["package_adj_gamma"] = 3.0
    steep = package_value_v2(vals, vmax)
    assert flat > mid > steep, (flat, mid, steep)
    assert flat == pytest.approx(sum(vals))        # no discount at gamma 0
    # Best asset alone never changes with gamma.
    for g in (0.0, 1.5, 3.0):
        ts._cfg["package_adj_gamma"] = g
        assert package_value_v2([1500.0], 1500.0) == pytest.approx(1500.0)


# ───────────────────────────────────────────────────────────────────────────
# 2. 1-for-1 gate is config-driven at the knife-edge (self-calibrating)
# ───────────────────────────────────────────────────────────────────────────

def _knife_fixture():
    """A clean 1-for-1 divergence: user gives G (they undervalue), receives R
    (they covet); opponent mirror. Seeds are close so consensus fairness lands
    in a sweepable mid-range, not 1.0 or near-0. confidence=None so the
    range-overlap gate degrades to the point gate (pure threshold test)."""
    user_elo = {"G": 1500, "R": 1700}
    opp_elo = {"G": 1700, "R": 1500}
    seed = {"G": 1540, "R": 1500}        # 40-Elo consensus gap -> mid fairness
    opp = _member("opp", ["R"], opp_elo)
    svc = _svc(["G", "R"], [opp])
    return svc, user_elo, ["G"], seed


def test_one_for_one_gate_knife_edge():
    _set_flags(**{"trade_engine.v2": True})
    # Pin the divergence floor above the sweep range so the passed
    # threshold governs — the interview-2026-07-17 loosening (0.55) would
    # otherwise floor the "above" sweep below the card's own fairness.
    ts._cfg["fairness_floor_divergence"] = 1.0
    svc, ue, ur, seed = _knife_fixture()
    # Calibrate: read the card's own fairness at a permissive threshold.
    cards = _gen(svc, ue, ur, seed, fairness_threshold=0.05, max_per_opponent=5)
    card = _find(cards, ["G"], ["R"])
    assert card is not None, "fixture broken: base 1-for-1 should surface"
    F = card.fairness_score
    assert 0.15 < F < 0.95, f"fixture fairness {F} not in a sweepable band"
    # Below F -> present; above F -> vetoed. Only the threshold changes.
    below = _gen(_knife_fixture()[0], ue, ur, seed,
                 fairness_threshold=max(0.01, F - 0.05), max_per_opponent=5)
    above = _gen(_knife_fixture()[0], ue, ur, seed,
                 fairness_threshold=min(0.99, F + 0.05), max_per_opponent=5)
    assert _find(below, ["G"], ["R"]) is not None, f"card vanished below its own fairness {F}"
    assert _find(above, ["G"], ["R"]) is None, f"card survived a threshold above its fairness {F}"


def test_gate_monotone_in_threshold():
    """Raising fairness_threshold never ADDS cards (tuning-surface safety)."""
    _set_flags(**{"trade_engine.v2": True})
    counts = []
    for thr in (0.50, 0.65, 0.75, 0.85, 0.95):
        cards = _gen(_knife_fixture()[0], {"G": 1500, "R": 1700}, ["G"],
                     {"G": 1540, "R": 1500}, fairness_threshold=thr, max_per_opponent=5)
        counts.append(len(cards))
    assert counts == sorted(counts, reverse=True), f"non-monotone card counts: {counts}"


# ───────────────────────────────────────────────────────────────────────────
# 3. Discount propagates to a card's fairness_score
# ───────────────────────────────────────────────────────────────────────────

def test_gamma_lowers_multi_give_fairness():
    """A 2-give-for-1-receive: raising package_adj_gamma discounts the give
    package harder, changing the reported fairness. Documents that the
    package-discount knob actually reaches card output (the watch item)."""
    _set_flags(**{"trade_engine.v2": True})
    # User gives two mids M1,M2 (undervalues), receives elite E (covets).
    # E user-Elo kept within trade_elo_gap_max (250) of the mids (1500) so the
    # ELO-gap gate doesn't pre-empt the fairness behavior under test.
    user_elo = {"M1": 1500, "M2": 1500, "E": 1740}
    opp_elo = {"M1": 1660, "M2": 1660, "E": 1560}
    seed = {"M1": 1600, "M2": 1600, "E": 1720}

    def run(gamma):
        ts._cfg["package_adj_gamma"] = gamma
        opp = _member("opp", ["E"], dict(opp_elo))
        svc = _svc(["M1", "M2", "E"], [opp])
        cards = _gen(svc, dict(user_elo), ["M1", "M2"], dict(seed),
                     fairness_threshold=0.01, max_per_opponent=5)
        return _find(cards, ["M1", "M2"], ["E"])

    lo = run(1.0)
    hi = run(2.5)
    assert lo is not None and hi is not None, "2-for-1 should surface at threshold 0.01"
    # give-package = M1+M2; harder discount shrinks it relative to the single
    # elite E -> the lesser side is the give pack, so fairness FALLS.
    assert hi.fairness_score < lo.fairness_score, (
        f"gamma 2.5 fairness {hi.fairness_score} !< gamma 1.0 fairness {lo.fairness_score}")


# ───────────────────────────────────────────────────────────────────────────
# 4. FR8 — fairness is market-neutral (outlook moves surpluses, not fairness)
# ───────────────────────────────────────────────────────────────────────────

def test_outlook_does_not_move_fairness():
    """Same trade under championship vs rebuilder outlook: fairness_score must
    be identical (consensus-seed gate), while composite/mismatch may differ."""
    _set_flags(**{"trade_engine.v2": True, "trade.outlook_blend": True})
    user_elo = {"G": 1500, "R": 1700}
    opp_elo = {"G": 1700, "R": 1500}
    seed = {"G": 1560, "R": 1500}

    def run(outlook):
        opp = _member("opp", ["R"], dict(opp_elo))
        svc = _svc(["G", "R"], [opp], positions={"G": "RB", "R": "WR"})
        cards = _gen(svc, dict(user_elo), ["G"], dict(seed),
                     fairness_threshold=0.05, max_per_opponent=5, outlook=outlook)
        return _find(cards, ["G"], ["R"])

    champ = run("championship")
    rebuild = run("rebuilder")
    assert champ is not None and rebuild is not None
    assert champ.fairness_score == pytest.approx(rebuild.fairness_score), (
        "outlook leaked into the fairness gate (FR8 violation): "
        f"{champ.fairness_score} vs {rebuild.fairness_score}")


# ───────────────────────────────────────────────────────────────────────────
# 5. v2 <-> v3 fairness-floor parity (guards the _fairness_v3 mirror)
# ───────────────────────────────────────────────────────────────────────────

def _feasible_fixture(seed):
    """Rosters carry a FULL legal lineup so v3 lineup-feasibility
    (_STARTER_NEED = QB1/RB2/WR2/TE1) is satisfied and the only thing that can
    veto the G<->R card is the fairness gate. G/R are the lone divergent pair
    (both RB); every filler has user==opp==seed Elo (zero divergence) and a
    distinct position so the post-trade lineup stays fieldable for both sides."""
    # Per side: the traded RB + one spare RB + QB + 2 WR + TE -> 6 players.
    fill_u = {"RBu": "RB", "QBu": "QB", "WRu1": "WR", "WRu2": "WR", "TEu": "TE"}
    fill_o = {"RBo": "RB", "QBo": "QB", "WRo1": "WR", "WRo2": "WR", "TEo": "TE"}
    positions = {"G": "RB", "R": "RB", **fill_u, **fill_o}
    ids = list(positions.keys())
    flat = {pid: 1500 for pid in list(fill_u) + list(fill_o)}
    user_elo = {"G": 1500, "R": 1700, **flat}
    opp_elo = {"G": 1700, "R": 1500, **flat}
    full_seed = {**seed, **flat}
    opp = _member("opp", ["R"] + list(fill_o), opp_elo)
    svc = _svc(ids, [opp], positions=positions)
    return svc, user_elo, ["G"] + list(fill_u), full_seed


def test_v2_v3_reject_clearly_unfair():
    """A clearly-unfair 1-for-1 (consensus fairness well below 0.75) must be
    dark in BOTH engines."""
    unfair_seed = {"G": 1760, "R": 1500}     # big consensus gap -> ~0.1 fairness
    for label, flags in (("v2", {"trade_engine.v2": True}),
                         ("v3", {"trade_engine.v2": True, "trade_engine.v3": True})):
        _set_flags(**flags)
        svc, ue, ur, seed = _feasible_fixture(unfair_seed)
        cards = _gen(svc, ue, ur, seed, fairness_threshold=0.75, max_per_opponent=8)
        assert _find(cards, ["G"], ["R"]) is None, (
            f"{label}: clearly-unfair 1-for-1 leaked through the fairness gate")


def test_v2_v3_fairness_score_parity():
    """A fair 1-for-1 surfaces in both engines with the SAME fairness score —
    catches drift between _fairness (v2) and the hand-copied _fairness_v3."""
    fair_seed = {"G": 1500, "R": 1500}       # equal consensus -> fairness 1.0
    scores = {}
    for label, flags in (("v2", {"trade_engine.v2": True}),
                         ("v3", {"trade_engine.v2": True, "trade_engine.v3": True})):
        _set_flags(**flags)
        svc, ue, ur, seed = _feasible_fixture(fair_seed)
        cards = _gen(svc, ue, ur, seed, fairness_threshold=0.75, max_per_opponent=8)
        card = _find(cards, ["G"], ["R"])
        assert card is not None, f"{label}: fair 1-for-1 should surface"
        scores[label] = card.fairness_score
    assert scores["v2"] == pytest.approx(scores["v3"]), (
        f"_fairness_v3 drifted from _fairness: {scores}")
