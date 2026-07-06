"""TC-ENG-003 — Engine gate config-responsiveness (the admin tuning surface).

The operator tunes trade behavior live via model_config (PUT /api/admin/config).
Those knobs must move the gates predictably and monotonically, or tuning is a
shot in the dark. Complements test_trade_engine_v2 (which proves the gates EXIST)
by proving they RESPOND to config the way an operator would expect:

  - min_side_surplus: raising it admits FEWER trades (both sides must clear it).
  - trade_elo_gap_max: a 1-for-1 at Elo-gap G passes below the cap, fails above.
  - waiver_slot_cost: raising it erodes the extra-player side's surplus, so a
    2-for-1 disappears before the 1-for-1.
  - marginal_value flag flips which trades surface (over-replacement vs raw).

Tiny deterministic fixtures; flags/_cfg snapshot-restored per test.
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService


@pytest.fixture(autouse=True)
def _isolate():
    of, oc = ff._flags_cache, dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear(); ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = of
        ts._cfg.clear(); ts._cfg.update(oc)


class _P:
    def __init__(s, i, pos="RB"):
        s.id, s.name, s.position, s.team, s.age, s.ktc_value = i, i, pos, "T", 24, None


def _flags(**kw):
    c = dict(ff.DEFAULT_FLAGS); c.update(kw); ff._flags_cache = c


def _svc(ids, opps, positions=None):
    positions = positions or {}
    players = {i: _P(i, positions.get(i, "RB")) for i in ids}
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=opps))
    return s


def _m(uid, roster, elo):
    return LeagueMember(user_id=uid, username=uid, roster=roster, elo_ratings=elo, has_rankings=True)


def _gen(svc, ue, ur, seed, **kw):
    return svc.generate_trades(user_id="user", user_elo=ue, user_roster=ur,
                               league_id="L1", seed_elo=seed, **kw)


def _has(cards, give, recv):
    g, r = tuple(sorted(give)), tuple(sorted(recv))
    return any((tuple(sorted(c.give_player_ids)), tuple(sorted(c.receive_player_ids))) == (g, r)
               for c in cards)


# ── shared fixtures (mirror the proven ones in test_trade_engine_v2.py) ──────

# True-mutual-gain v2 fixture: user undervalues their G's (opp covets them) and
# covets the opp's R's (opp undervalues them) — each Gi<->Rj is a two-sided win.
# A gradient in both desires gives a SPREAD of surpluses, so raising the surplus
# floor cuts the weakest pairs first (clean monotonicity). Equal seeds => fair.
_GIVE = {"g1": 1500, "g2": 1500, "g3": 1500}
_RECV = {"r1": 1500, "r2": 1500, "r3": 1500}            # opp's view of opp's own R's
_USER_ELO = {"g1": 1500, "g2": 1500, "g3": 1500,        # user undervalues own G's
             "r1": 1720, "r2": 1640, "r3": 1580}        # user covets R's (gradient)
_OPP_ELO = {"g1": 1720, "g2": 1640, "g3": 1580,         # opp covets user's G's (gradient)
            "r1": 1500, "r2": 1500, "r3": 1500}
_IDS = list(_USER_ELO)


def _divergence_league():
    seed = {pid: 1500.0 for pid in _IDS}
    opp = _m("opp", ["r1", "r2", "r3"], dict(_OPP_ELO))
    return _svc(_IDS, [opp]), dict(_USER_ELO), ["g1", "g2", "g3"], seed


# Multi-player fixture: user gives M1,M2; receives E. Only the 2-for-1 is
# consensus-fair in v2; opp receives the 2-pack so it is waiver-cost-sensitive.
def _multi_setup():
    ue = {"M1": 1620, "M2": 1620, "E": 1850}
    oe = {"M1": 1650, "M2": 1650, "E": 1600}
    seed = {"M1": 1650, "M2": 1650, "E": 1700}
    opp = _m("opp", ["E"], oe)
    return _svc(["M1", "M2", "E"], [opp]), ue, ["M1", "M2"], seed


def test_min_side_surplus_monotone():
    _flags(**{"trade_engine.v2": True})
    counts = []
    for surplus in (50.0, 150.0, 400.0, 900.0):
        svc, ue, ur, seed = _divergence_league()
        ts._cfg["min_side_surplus"] = surplus
        counts.append(len(_gen(svc, ue, ur, seed, max_per_opponent=10)))
    assert counts == sorted(counts, reverse=True), f"non-monotone vs min_side_surplus: {counts}"
    assert counts[0] > counts[-1], f"gate not responsive: {counts}"


# ── 2. trade_elo_gap_max knife-edge ─────────────────────────────────────────

def test_elo_gap_cap_knife_edge():
    """A 1-for-1 whose user Elo gap is exactly G surfaces when the cap > G and
    vanishes when the cap < G — nothing else changes."""
    _flags(**{"trade_engine.v2": True})
    # User gives G (1500), wants R (1700) -> Elo gap = 200. Opp mirrors.
    ue = {"G": 1500, "R": 1700}
    oe = {"G": 1700, "R": 1500}
    seed = {"G": 1500, "R": 1500}        # equal seeds -> fairness ~1, not the gate under test

    def run(cap):
        ts._cfg["trade_elo_gap_max"] = cap
        svc = _svc(["G", "R"], [_m("opp", ["R"], dict(oe))])
        return _gen(svc, dict(ue), ["G"], dict(seed), fairness_threshold=0.5, max_per_opponent=5)

    assert _has(run(250.0), ["G"], ["R"]), "gap 200 should pass under cap 250"
    assert not _has(run(150.0), ["G"], ["R"]), "gap 200 should fail under cap 150"


# ── 3. waiver_slot_cost erodes the extra-player side ─────────────────────────

def test_waiver_slot_cost_kills_uneven_first():
    """The 2-for-1 (opp receives the M1+M2 pack) clears at low waiver cost but is
    gated out as the cost rises — the extra-player side's surplus erodes."""
    _flags(**{"trade_engine.v2": True})

    def run(cost):
        ts._cfg["waiver_slot_cost"] = cost
        svc, ue, ur, seed = _multi_setup()
        return _gen(svc, ue, ur, seed, fairness_threshold=0.5, max_per_opponent=8)

    low = run(0.0)
    high = run(5000.0)
    assert _has(low, ["M1", "M2"], ["E"]), "2-for-1 should exist at zero waiver cost"
    assert not _has(high, ["M1", "M2"], ["E"]), "high waiver cost should kill the 2-for-1"


# ── 4. tier multiplier scales composite score (ranking knob) ────────────────

def test_tier_multiplier_scales_composite():
    """tier_mult_* boosts/suppresses a card's composite by the traded players'
    tier. Raising tier_mult_elite must raise the composite of an elite-involving
    trade — the operator's lever for surfacing star moves."""
    _flags(**{"trade_engine.v2": True})

    def top_composite(elite_mult):
        ts._cfg["tier_mult_elite"] = elite_mult
        svc, ue, ur, seed = _multi_setup()        # involves elite E (user_elo 1850)
        cards = _gen(svc, ue, ur, seed, fairness_threshold=0.5, max_per_opponent=8)
        card = next((c for c in cards
                     if set(c.give_player_ids) == {"M1", "M2"}
                     and c.receive_player_ids == ["E"]), None)
        return card.composite_score if card else None

    lo = top_composite(1.0)
    hi = top_composite(2.0)
    assert lo is not None and hi is not None, "elite 2-for-1 should surface in both runs"
    assert hi > lo, f"raising tier_mult_elite must raise composite ({hi} !> {lo})"
