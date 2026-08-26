"""Knockout refine — R5 two-sided, R1 in the card's currency, R2 quality-aware.

Spec: docs/plans/knockout-refine/plan.md §2-§3 (verdict + evidence:
docs/reviews/2026-08-22-knockout-rules-judged.html §03). Three knobs, all
LIT by default, each with a 0 that restores the predicate byte-identically:

    need_gate_dual_rescue    C1 — R5 any-asset + dual-need rescue
    overpay_adjusted         C2 — R1 gap priced in package_value_v2
    pos_net_starter_relief   C3 — R2 starter-depth relief

plus the closure threading that makes C1(b) and C3 possible at all: the
per-league-mate `opp_ctx`, bound onto the job-level predicate inside the
member loop (plan §2). `opp_ctx=None` ⇒ every new branch is skipped.

D-056 sabotage ledger — every test below was proven RED on its named
sabotage and green again on restore from a byte copy (`cp` snapshot, NOT
`git checkout --`: this branch is uncommitted). One sabotage per test, the
exact edited line quoted:

  S1  test_knob_zero_is_byte_identical_*
      trade_service.overpay_ok:      `if _c("overpay_adjusted") >= 1.0:`
                                  -> `if _c("overpay_adjusted") >= 0.0:`
      trade_service.pos_net_ok:      `if opp_ctx is None or _c("pos_net_starter_relief") < 1.0:`
                                  -> `if opp_ctx is None:`
      trade_service.need_gate_ok:    `if _c("need_gate_dual_rescue") >= 1.0:`
                                  -> `if _c("need_gate_dual_rescue") >= 0.0:`
      (each knob's 0 stops being its documented disable value)

  S2  test_dual_need_rescue_and_loveland_still_dies
      trade_service.need_gate_ok:
          `and opp_startable.get(pos, 0) < _starters_at(`
       -> `and opp_startable.get(pos, 0) >= 0 and 0 < _starters_at(`
      (the rescue stops asking whether the PARTNER is actually short)

  S3  test_any_asset_second_piece_fills_the_hole
      trade_service.need_gate_ok:  `for pid in recv_ids:`  (any-asset loop)
                                -> `for pid in recv_ids[:1]:`
      (any-asset collapses back to "the highest-value piece only")

  S4  test_overpay_adjusted_flips_both_directions
      trade_service.overpay_ok:  `v_max = max(both)`  ->  `v_max = max(gvals)`
      (the trade-wide benchmark becomes the give side's own max)

  S5  test_pos_net_starter_relief_counts_startable_bodies
      trade_service.pos_net_ok._moved:
          `and startable_ok(pid, p):`  ->  `and True:`
      (relief counts BODIES again instead of startable bodies)

  S6  test_per_member_binding_gives_different_verdicts
      trade_service._generate_trades_v2_impl, the v2 generator call site:
          `presentment_ok_fn    = _member_presentment,`
       -> `presentment_ok_fn    = _presentment_ok,`
      (the per-member ctx stops reaching one of the three generators)

  S7  test_startable_matches_analyze_roster
      trade_service._startable_ok_fn:
          `return bin_ in ("elite", "starter")`
       -> `return bin_ in ("elite", "starter", "bench")`
      (the shared startable definition drifts off analyze_roster_strengths')

  S8  test_arm_a_never_reads_the_three_companion_knobs
      bakeoff_profiles.MODEL_A_PROFILE: `"max_overpay_frac": 0.0,` -> `0.25,`
      (the sibling kill value the EXCLUSION disposition rests on is removed)
"""

import math

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.bakeoff_profiles import MODEL_A_PROFILE
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    analyze_roster_strengths,
    elo_to_value,
    need_gate_ok,
    overpay_ok,
    pos_net_ok,
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


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _elo(value: float) -> float:
    """Inverse of elo_to_value at default knobs (k=0.005, ref 1500/1000)."""
    return 1500.0 + 200.0 * math.log(value / 1000.0)


# Ranks chosen against `dynasty_value` at default ktc_* knobs, so the tier
# bin each lands in is unambiguous: 20 -> 7871 (elite), 100 -> 2872
# (starter), 200 -> ~815 (bench). "Startable" is elite|starter, which is
# exactly analyze_roster_strengths' starter_count.
_RANK_ELITE, _RANK_STARTER, _RANK_BENCH = 20, 100, 200


class _Player:
    def __init__(self, pid, position="WR", rank=_RANK_STARTER):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = "TST"
        self.age = 24
        self.ktc_value = None
        self.pick_value = None
        self.search_rank = rank
        self.years_experience = 3


def _pick(pid):
    p = _Player(pid, position="PICK")
    p.pick_value = 60.0
    return p


def _sv(values: dict):
    return lambda pid: values[pid]


# ═══════════════════════════════════════════════════════════════════════════
# Vendored copy of TODAY's predicate logic (origin/main @ c321958), verbatim.
#
# Plan §5 item 1 asks for byte-identity proven against a copy of the logic,
# not against the author's confidence. These three are the pre-C1/C2/C3
# bodies, transcribed unchanged except for module-qualifying the helpers
# they close over — so they track `_c`, `is_pick_asset` and `_starters_at`
# if those ever move, while the PREDICATE shape stays frozen at c321958.
# ═══════════════════════════════════════════════════════════════════════════


def _legacy_overpay_ok(give_ids, recv_ids, seed_value) -> bool:
    frac = ts._c("max_overpay_frac")
    if frac <= 0:
        return True
    g = sum(seed_value(p) for p in give_ids)
    r = sum(seed_value(p) for p in recv_ids)
    big = max(g, r)
    if big <= 0:
        return True
    gap = abs(g - r)
    return not (gap >= ts._c("max_overpay_min_value") and gap / big >= frac)


def _legacy_pos_net_ok(give_ids, recv_ids, players) -> bool:
    cap = ts._c("pos_net_cap")
    if cap <= 0:
        return True
    net: dict = {}
    for ids, sign in ((recv_ids, 1), (give_ids, -1)):
        for pid in ids:
            p = players.get(pid)
            if p is None or ts.is_pick_asset(p):
                continue
            pos = getattr(p, "position", None)
            if pos in ts._PRESENTMENT_POSITIONS:
                net[pos] = net.get(pos, 0) + sign
    return all(abs(n) <= cap for n in net.values())


def _legacy_need_gate_ok(give_ids, recv_ids, *, seed_value, players,
                         user_pos_values, outlook, position_needs,
                         position_surplus, scoring_format) -> bool:
    floor = ts._c("need_gate_min_value")
    if floor <= 0:
        return True
    if outlook in ("rebuilder", "jets") or not outlook:
        return True
    primary_pos, primary_val = None, -1.0
    for pid in recv_ids:
        p = players.get(pid)
        if p is None or ts.is_pick_asset(p):
            continue
        v = seed_value(pid)
        if v > primary_val:
            primary_val = v
            primary_pos = getattr(p, "position", None)
    if primary_pos not in ts._PRESENTMENT_POSITIONS:
        return True
    if primary_val < floor:
        return True
    _ = position_needs
    give_set = set(give_ids)
    vals = sorted((v for pid, v in user_pos_values.get(primary_pos, ())
                   if pid not in give_set), reverse=True)
    starters = ts._starters_at(primary_pos, scoring_format)
    if len(vals) < starters:
        return True
    incumbent = vals[starters - 1]
    if primary_val > incumbent * (1.0 + ts._c("need_gate_upgrade_margin")):
        return True
    if outlook in ("championship", "contender"):
        return False
    if outlook == "not_sure":
        return primary_pos not in (position_surplus or ())
    return True


# ── the sweep fixture ──────────────────────────────────────────────────────
# Deliberately wide: four positions, elite/starter/bench bodies, two picks,
# and value spreads either side of max_overpay_min_value (500) and
# need_gate_min_value (500).

_SWEEP_PLAYERS = {
    "uQ":  _Player("uQ", "QB", _RANK_STARTER),
    "uR1": _Player("uR1", "RB", _RANK_ELITE),
    "uR2": _Player("uR2", "RB", _RANK_STARTER),
    "uR3": _Player("uR3", "RB", _RANK_BENCH),
    "uW1": _Player("uW1", "WR", _RANK_ELITE),
    "uW2": _Player("uW2", "WR", _RANK_STARTER),
    "uT":  _Player("uT", "TE", _RANK_STARTER),
    "uPK": _pick("uPK"),
    "oQ":  _Player("oQ", "QB", _RANK_STARTER),
    "oR1": _Player("oR1", "RB", _RANK_ELITE),
    "oR2": _Player("oR2", "RB", _RANK_BENCH),
    "oW1": _Player("oW1", "WR", _RANK_STARTER),
    "oW2": _Player("oW2", "WR", _RANK_BENCH),
    "oT":  _Player("oT", "TE", _RANK_ELITE),
    "oPK": _pick("oPK"),
}

_SWEEP_VALUES = {
    "uQ": 2100.0, "uR1": 3400.0, "uR2": 1600.0, "uR3": 420.0,
    "uW1": 3900.0, "uW2": 1450.0, "uT": 900.0, "uPK": 1100.0,
    "oQ": 1950.0, "oR1": 3600.0, "oR2": 380.0, "oW1": 1700.0,
    "oW2": 460.0, "oT": 2900.0, "oPK": 1250.0,
}

_SWEEP_GIVE = [
    ["uR1"], ["uR2"], ["uW1"], ["uT"], ["uPK"], ["uR3"],
    ["uR1", "uR2"], ["uW1", "uW2"], ["uR2", "uR3"], ["uR1", "uPK"],
    ["uQ", "uT"], ["uR1", "uR2", "uR3"], ["uW1", "uW2", "uT"],
    ["uR1", "uW1"], ["uPK", "uR3"],
]
_SWEEP_RECV = [
    ["oR1"], ["oW1"], ["oT"], ["oPK"], ["oR2"], ["oQ"],
    ["oR1", "oR2"], ["oW1", "oW2"], ["oT", "oPK"], ["oR1", "oW1"],
    ["oQ", "oR2"], ["oR1", "oR2", "oW2"], ["oW1", "oW2", "oT"],
    ["oPK", "oW2"],
]

_SWEEP_USER_POS_VALUES = {
    "QB": [("uQ", 2100.0)],
    "RB": [("uR1", 3400.0), ("uR2", 1600.0), ("uR3", 420.0)],
    "WR": [("uW1", 3900.0), ("uW2", 1450.0)],
    "TE": [("uT", 900.0)],
}


def _sweep_pairs():
    for g in _SWEEP_GIVE:
        for r in _SWEEP_RECV:
            yield g, r


# ── 1. knob 0 / ctx None ⇒ byte-identical ──────────────────────────────────


def test_knob_zero_is_byte_identical_r1():
    """C2 off ⇒ overpay_ok's verdicts are the vendored raw-sum body's, over
    the whole sweep and across the knob settings R1 itself has."""
    sv = _sv(_SWEEP_VALUES)
    ts._cfg["overpay_adjusted"] = 0.0
    checked = 0
    for frac, floor in ((0.25, 500.0), (0.0, 500.0), (0.15, 0.0),
                        (0.5, 1200.0)):
        ts._cfg["max_overpay_frac"] = frac
        ts._cfg["max_overpay_min_value"] = floor
        for g, r in _sweep_pairs():
            assert overpay_ok(g, r, sv) == _legacy_overpay_ok(g, r, sv), \
                (g, r, frac, floor)
            checked += 1
    assert checked == 4 * len(_SWEEP_GIVE) * len(_SWEEP_RECV)


def test_knob_zero_is_byte_identical_r2():
    """C3 off, and separately ctx=None with C3 ON ⇒ pos_net_ok's verdicts are
    the vendored count body's. Both disables are load-bearing: the fit
    K-chain and every unit caller pass no ctx."""
    ctx = ts._presentment_ctx(
        {"tier_depth": {"RB": {"elite": 3, "starter": 1, "bench": 0}}},
        {"RB": 4}, ts._startable_ok_fn(_SWEEP_PLAYERS, "1qb_ppr"), "1qb_ppr")
    for cap in (1.0, 0.0, 2.0):
        ts._cfg["pos_net_cap"] = cap
        for g, r in _sweep_pairs():
            legacy = _legacy_pos_net_ok(g, r, _SWEEP_PLAYERS)
            ts._cfg["pos_net_starter_relief"] = 0.0
            assert pos_net_ok(g, r, _SWEEP_PLAYERS, opp_ctx=ctx) == legacy, \
                ("knob 0", g, r, cap)
            ts._cfg["pos_net_starter_relief"] = 1.0
            assert pos_net_ok(g, r, _SWEEP_PLAYERS) == legacy, \
                ("ctx None", g, r, cap)


def test_knob_zero_is_byte_identical_r5():
    """C1 off, and separately ctx=None with C1 ON but the rescue's own
    inputs absent ⇒ need_gate_ok's verdicts are the vendored primary-only
    body's, over every window."""
    sv = _sv(_SWEEP_VALUES)
    kw = dict(seed_value=sv, players=_SWEEP_PLAYERS,
              user_pos_values=_SWEEP_USER_POS_VALUES,
              position_needs=["TE"], position_surplus=["RB"],
              scoring_format="1qb_ppr")
    ts._cfg["need_gate_dual_rescue"] = 0.0
    ctx = ts._presentment_ctx(
        {"tier_depth": {"RB": {"elite": 0, "starter": 0, "bench": 0}}},
        {"RB": 3}, ts._startable_ok_fn(_SWEEP_PLAYERS, "1qb_ppr"), "1qb_ppr")
    for outlook in ("contender", "championship", "not_sure", "rebuilder",
                    "jets", None):
        for g, r in _sweep_pairs():
            assert need_gate_ok(g, r, outlook=outlook, opp_ctx=ctx, **kw) == \
                _legacy_need_gate_ok(g, r, outlook=outlook, **kw), \
                (g, r, outlook)


# ── 2. dual-need rescue, and the #304 shape that must still die ────────────

# The originating complaint: a contender is offered a TE who neither fills a
# hole nor upgrades the incumbent — and the piece going out is NOT surplus
# the partner is short at, so there is no dual-need fact to rescue it.
_LOVELAND_PLAYERS = {
    "TE_STAR":  _Player("TE_STAR", "TE"),      # the user's incumbent TE
    "TE_LOVE":  _Player("TE_LOVE", "TE"),      # the offered TE
    "WR_X":     _Player("WR_X", "WR"),         # what the user ships
    "RB_SPARE": _Player("RB_SPARE", "RB", _RANK_STARTER),
}
_LOVELAND_VALUES = {"TE_STAR": 3000.0, "TE_LOVE": 1200.0,
                    "WR_X": 1500.0, "RB_SPARE": 2000.0}
_LOVELAND_UPV = {"TE": [("TE_STAR", 3000.0)], "WR": [("WR_X", 1500.0)],
                 "RB": [("RB_SPARE", 2000.0)]}


def _loveland_kw(**over):
    kw = dict(seed_value=_sv(_LOVELAND_VALUES), players=_LOVELAND_PLAYERS,
              user_pos_values=_LOVELAND_UPV, outlook="contender",
              position_needs=[], position_surplus=["RB"],
              scoring_format="1qb_ppr")
    kw.update(over)
    return kw


def _ctx_for(opp_startable: dict, user_startable=None, players=None):
    """A presentment ctx with the opponent's startable counts stated."""
    return ts._presentment_ctx(
        {"tier_depth": {pos: {"elite": 0, "starter": n, "bench": 0}
                        for pos, n in opp_startable.items()}},
        user_startable or {},
        ts._startable_ok_fn(players or _LOVELAND_PLAYERS, "1qb_ppr"),
        "1qb_ppr")


def test_dual_need_rescue_and_loveland_still_dies():
    """C1(b): shedding an RB the user is surplus at, into a partner with no
    startable RB, rescues the card — and the #304 Loveland shape, which has
    no such fact on the give side, still dies for a contender."""
    # The complaint shape: WR out, a non-upgrading TE back. The partner is
    # RB-barren, but the user is shipping no RB, so nothing rescues it.
    assert need_gate_ok(["WR_X"], ["TE_LOVE"],
                        opp_ctx=_ctx_for({"RB": 0, "WR": 2, "TE": 1}),
                        **_loveland_kw()) is False
    # Same card, same partner, but now the user ships the surplus RB too:
    # dual need, rescued.
    assert need_gate_ok(["WR_X", "RB_SPARE"], ["TE_LOVE"],
                        opp_ctx=_ctx_for({"RB": 0, "WR": 2, "TE": 1}),
                        **_loveland_kw()) is True
    # …and the rescue is TWO-sided: with the partner already at RB starter
    # depth there is no need on their side, so the same card dies again.
    assert need_gate_ok(["WR_X", "RB_SPARE"], ["TE_LOVE"],
                        opp_ctx=_ctx_for({"RB": 2, "WR": 2, "TE": 1}),
                        **_loveland_kw()) is False
    # …and it reads the USER's surplus, not just any position: with RB out
    # of the surplus list the same shed is unremarkable.
    assert need_gate_ok(["WR_X", "RB_SPARE"], ["TE_LOVE"],
                        opp_ctx=_ctx_for({"RB": 0, "WR": 2, "TE": 1}),
                        **_loveland_kw(position_surplus=["WR"])) is False
    # Knob 0 ⇒ the rescue cannot fire at all.
    ts._cfg["need_gate_dual_rescue"] = 0.0
    assert need_gate_ok(["WR_X", "RB_SPARE"], ["TE_LOVE"],
                        opp_ctx=_ctx_for({"RB": 0, "WR": 2, "TE": 1}),
                        **_loveland_kw()) is False


def test_dual_need_rescue_ignores_picks_on_the_give_side():
    """A pick is not a positional body — shedding one cannot be the
    positional fact that rescues a card (the R2/R5 pick convention)."""
    players = dict(_LOVELAND_PLAYERS, PK=_pick("PK"))
    vals = dict(_LOVELAND_VALUES, PK=2000.0)
    assert need_gate_ok(
        ["WR_X", "PK"], ["TE_LOVE"],
        opp_ctx=_ctx_for({"RB": 0, "WR": 2, "TE": 1}, players=players),
        **_loveland_kw(players=players, seed_value=_sv(vals))) is False


# ── 3. any-asset: the SECOND received piece is the point of the trade ──────


def test_any_asset_second_piece_fills_the_hole():
    """C1(a): a 1-for-2 whose headliner is a lateral at a full position but
    whose second piece fills an empty starting slot. Today R5 judged the
    headliner alone and killed it."""
    players = {
        "uW1": _Player("uW1", "WR"), "uW2": _Player("uW2", "WR"),
        "uGIVE": _Player("uGIVE", "WR"),
        "oW": _Player("oW", "WR"),          # headliner — WR, no upgrade
        "oT": _Player("oT", "TE"),          # second piece — the user has NO TE
    }
    vals = {"uW1": 3000.0, "uW2": 2800.0, "uGIVE": 2600.0,
            "oW": 2000.0, "oT": 1400.0}
    upv = {"WR": [("uW1", 3000.0), ("uW2", 2800.0), ("uGIVE", 2600.0)]}
    kw = dict(seed_value=_sv(vals), players=players, user_pos_values=upv,
              outlook="contender", position_needs=["TE"],
              position_surplus=["WR"], scoring_format="1qb_ppr")
    # Headliner alone: WR at a full position, below the incumbent — dead.
    assert need_gate_ok(["uGIVE"], ["oW"], **kw) is False
    # With the TE riding along, the hole check clears on the SECOND piece.
    assert need_gate_ok(["uGIVE"], ["oW", "oT"], **kw) is True
    # Knob 0 ⇒ primary-only, so the same package dies.
    ts._cfg["need_gate_dual_rescue"] = 0.0
    assert need_gate_ok(["uGIVE"], ["oW", "oT"], **kw) is False
    # …and it is the ANY-ASSET branch doing the work, not the rescue: no
    # ctx is passed anywhere above.


# ── 4. C2 — the gap in the currency the card shows ─────────────────────────


def test_overpay_adjusted_flips_both_directions():
    """C2 moves verdicts in BOTH directions, which is the proof it is a
    currency change and not a loosening or a tightening.

    Both cases are the same 3-for-1 shape; only which side is heavier
    changes. `package_value_v2` depth-discounts the three-body side, so
    when that side is the LIGHTER one the gap widens, and when it is the
    HEAVIER one the gap closes.

    * raw-even / adjusted-lopsided — 4,350 out vs 4,700 back is a 7.4% raw
      gap, comfortably fine. In package value it is 3,191 vs 4,700: a 32%
      gap, which is what the card's own fairness bar already shows.
    * raw-lopsided / adjusted-even — 3,150 out vs 2,200 back is a 30% raw
      gap over the 500 floor, dead on the raw rule. In package value it is
      2,569 vs 2,200: 14%, and under the floor besides.
    """
    sv = _sv({"g1": 1550.0, "g2": 1450.0, "g3": 1350.0, "R": 4700.0,
              "s1": 1150.0, "s2": 1050.0, "s3": 950.0, "S": 2200.0})
    # 1 — raw-even, adjusted-lopsided.
    g, r = ["g1", "g2", "g3"], ["R"]
    assert abs(4350.0 - 4700.0) / 4700.0 == pytest.approx(0.0745, abs=1e-3)
    ts._cfg["overpay_adjusted"] = 0.0
    assert overpay_ok(g, r, sv) is True            # raw: 7.4%, gap 350
    ts._cfg["overpay_adjusted"] = 1.0
    assert overpay_ok(g, r, sv) is False           # adjusted: 32%, gap 1509
    # 2 — raw-lopsided, adjusted-even.
    g2, r2 = ["s1", "s2", "s3"], ["S"]
    assert abs(3150.0 - 2200.0) / 3150.0 == pytest.approx(0.3016, abs=1e-3)
    ts._cfg["overpay_adjusted"] = 0.0
    assert overpay_ok(g2, r2, sv) is False         # raw: 30%, gap 950
    ts._cfg["overpay_adjusted"] = 1.0
    assert overpay_ok(g2, r2, sv) is True          # adjusted: 14%, gap 369


def test_overpay_adjusted_is_identity_on_one_for_ones():
    """The 0.25 was calibrated on a 78%-one-for-one corpus. A single-asset
    side is identity under package_value_v2, so C2 cannot move a 1-for-1 —
    the reason the knob could ship LIT without a recalibration."""
    sv = _sv({"G": 1875.0, "R": 2500.0, "G2": 1900.0})
    for adjusted in (0.0, 1.0):
        ts._cfg["overpay_adjusted"] = adjusted
        assert overpay_ok(["G"], ["R"], sv) is False   # exactly 0.25
        assert overpay_ok(["G2"], ["R"], sv) is True   # 0.24
        assert overpay_ok(["R"], ["G"], sv) is False   # still two-sided


def test_overpay_adjusted_keeps_both_existing_knobs():
    """`max_overpay_frac` <= 0 still disables R1 outright (and short-circuits
    before the knob is ever read), and `max_overpay_min_value` still floors
    it — both in adjusted space."""
    sv = _sv({"g1": 1550.0, "g2": 1450.0, "g3": 1350.0, "R": 4700.0})
    g, r = ["g1", "g2", "g3"], ["R"]
    assert overpay_ok(g, r, sv) is False           # killed at the defaults
    ts._cfg["max_overpay_frac"] = 0.0
    assert overpay_ok(g, r, sv) is True            # frac <= 0 still disables
    ts._cfg["max_overpay_frac"] = 0.25
    ts._cfg["max_overpay_min_value"] = 100000.0
    assert overpay_ok(g, r, sv) is True            # floor still applies


# ── 5. C3 — starter-depth relief, both rosters ─────────────────────────────

_C3_PLAYERS = {
    "uRB1": _Player("uRB1", "RB", _RANK_ELITE),
    "uRB2": _Player("uRB2", "RB", _RANK_STARTER),
    "uRB3": _Player("uRB3", "RB", _RANK_STARTER),
    "uRB4": _Player("uRB4", "RB", _RANK_BENCH),
    "uRB5": _Player("uRB5", "RB", _RANK_BENCH),
    "oWR":  _Player("oWR", "WR", _RANK_STARTER),
    "oPK":  _pick("oPK"),
}


def _c3_ctx(user_rb: int, opp_rb: int):
    return ts._presentment_ctx(
        {"tier_depth": {"RB": {"elite": 0, "starter": opp_rb, "bench": 0},
                        "WR": {"elite": 0, "starter": 2, "bench": 0}}},
        {"RB": user_rb, "WR": 2},
        ts._startable_ok_fn(_C3_PLAYERS, "1qb_ppr"), "1qb_ppr")


def test_pos_net_starter_relief_counts_startable_bodies():
    """C3, the operator's #341 intent stated in depth rather than in counts:
    RB4 + RB5 out of an RB-rich roster passes; RB1 + RB2 out of the same
    roster, which would strip it below startable depth, dies."""
    g_bench, g_starters = ["uRB4", "uRB5"], ["uRB1", "uRB2"]
    r = ["oWR"]                       # net RB = -2, over the cap of 1
    ctx = _c3_ctx(user_rb=3, opp_rb=3)
    # Both shapes are over-cap and both die on the count rule alone.
    assert pos_net_ok(g_bench, r, _C3_PLAYERS) is False
    assert pos_net_ok(g_starters, r, _C3_PLAYERS) is False
    # With the relief: two BENCH RBs leave startable depth untouched on
    # both sides (user 3 -> 3 >= 2, partner 3 -> 3 >= 2), so it passes.
    assert pos_net_ok(g_bench, r, _C3_PLAYERS, opp_ctx=ctx) is True
    # Two STARTABLE RBs strip the user 3 -> 1, below the need of 2. Dead.
    assert pos_net_ok(g_starters, r, _C3_PLAYERS, opp_ctx=ctx) is False
    # Knob 0 ⇒ the flat count kill returns for both.
    ts._cfg["pos_net_starter_relief"] = 0.0
    assert pos_net_ok(g_bench, r, _C3_PLAYERS, opp_ctx=ctx) is False


def test_pos_net_starter_relief_checks_the_receiving_roster_too():
    """"Both rosters stay at/above starter need" is not decoration: the same
    bench-RB shed dies when it is the PARTNER who is left short."""
    g, r = ["uRB4", "uRB5"], ["oWR"]
    # Partner already at exactly RB starter need — receiving two bench RBs
    # does not lift him, but he is not the shedder either, so he is only
    # required to stay at/above 2. He does.
    assert pos_net_ok(g, r, _C3_PLAYERS,
                      opp_ctx=_c3_ctx(user_rb=3, opp_rb=2)) is True
    # Partner BELOW starter need at RB: the after-check fails on his side.
    assert pos_net_ok(g, r, _C3_PLAYERS,
                      opp_ctx=_c3_ctx(user_rb=3, opp_rb=1)) is False
    # And the shedder must have been STRICTLY above need before: a user at
    # exactly 2 startable RBs may not ship depth over the cap.
    assert pos_net_ok(g, r, _C3_PLAYERS,
                      opp_ctx=_c3_ctx(user_rb=2, opp_rb=3)) is False


def test_pos_net_starter_relief_excludes_picks():
    """Picks are not positional bodies, before or after C3 — so a pick can
    neither create the over-cap position nor pay for it."""
    ctx = _c3_ctx(user_rb=3, opp_rb=3)
    # Two bench RBs + a pick out, one WR back: still net RB -2, and the
    # relief verdict is unchanged by the pick riding along.
    assert pos_net_ok(["uRB4", "uRB5", "oPK"], ["oWR"], _C3_PLAYERS,
                      opp_ctx=ctx) is True
    assert pos_net_ok(["uRB1", "uRB2", "oPK"], ["oWR"], _C3_PLAYERS,
                      opp_ctx=ctx) is False


def test_pos_net_starter_relief_superflex_qb2():
    """Starter need is `_starters_at`, so superflex asks for two QBs."""
    players = {
        "uQ1": _Player("uQ1", "QB", _RANK_ELITE),
        "uQ2": _Player("uQ2", "QB", _RANK_STARTER),
        "uQ3": _Player("uQ3", "QB", _RANK_STARTER),
        "oWR": _Player("oWR", "WR", _RANK_STARTER),
    }

    def ctx(fmt):
        return ts._presentment_ctx(
            {"tier_depth": {"QB": {"elite": 0, "starter": 3, "bench": 0}}},
            {"QB": 3}, ts._startable_ok_fn(players, fmt), fmt)

    g, r = ["uQ1", "uQ2"], ["oWR"]           # net QB -2, over the cap
    # 1QB: need 1, user 3 -> 1 >= 1 and partner 3 -> 5. Passes.
    assert pos_net_ok(g, r, players, opp_ctx=ctx("1qb_ppr")) is True
    # Superflex: need 2, user 3 -> 1 < 2. Dies.
    assert pos_net_ok(g, r, players, opp_ctx=ctx("sf_ppr")) is False


# ── 6. the per-member binding ──────────────────────────────────────────────


def _engine_players():
    p = {pid: _Player(pid, "WR", _RANK_STARTER)
         for pid in ("W1", "W2", "W3", "W4")}
    p["WNA"] = _Player("WNA", "WR", _RANK_BENCH)   # A's only WR — bench
    p["WNB"] = _Player("WNB", "WR", _RANK_BENCH)   # B's spare WR — bench
    p["B1"] = _Player("B1", "WR", _RANK_STARTER)   # …but B is WR-deep
    p["B2"] = _Player("B2", "WR", _RANK_STARTER)
    return p


def _engine_deck(players, opponents, outlook="not_sure"):
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=opponents))
    return svc.generate_trades(
        user_id="user",
        user_elo={"W4": 1500, "WNA": 1700, "WNB": 1700},
        user_roster=["W1", "W2", "W3", "W4"], league_id="L1",
        seed_elo={"W1": _elo(3000.0), "W2": _elo(2900.0),
                  "W3": _elo(2800.0), "W4": 1500.0,
                  "WNA": _elo(1200.0), "WNB": _elo(1200.0),
                  "B1": _elo(2700.0), "B2": _elo(2600.0)},
        fairness_threshold=0.75, max_per_opponent=5, outlook=outlook)


def _find(cards, give, recv):
    g, r = tuple(sorted(give)), tuple(sorted(recv))
    for c in cards:
        if (tuple(sorted(c.give_player_ids)),
                tuple(sorted(c.receive_player_ids))) == (g, r):
            return c
    return None


def test_per_member_binding_gives_different_verdicts():
    """Plan §2 — the ctx is bound PER LEAGUE-MATE, so the identical
    candidate (ship the surplus WR4, take back their bench WR) lives against
    a WR-barren partner and dies against a WR-deep one. A job-level closure
    cannot express this, which is the whole point of the threading."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    players = _engine_players()
    thin = LeagueMember(user_id="oppA", username="A", roster=["WNA"],
                        elo_ratings={"W4": 1700, "WNA": 1500},
                        has_rankings=True)
    deep = LeagueMember(user_id="oppB", username="B",
                        roster=["WNB", "B1", "B2"],
                        elo_ratings={"W4": 1700, "WNB": 1500,
                                     "B1": 1500, "B2": 1500},
                        has_rankings=True)
    # Same shape, one deck, two partners.
    cards = _engine_deck(players, [thin, deep])
    assert _find(cards, ["W4"], ["WNA"]) is not None, \
        "WR-barren partner: the dual-need rescue should serve this"
    assert _find(cards, ["W4"], ["WNB"]) is None, \
        "WR-deep partner: no dual need, R5 still kills"


def test_dual_need_rescue_engine_per_member():
    """The engine-level twin of test_presentment_rules'
    test_r5_engine_not_sure_surplus_kill, which is now pinned to the
    one-sided body. At the shipped default that fixture's card is SERVED:
    a not_sure user 4-deep at WR sheds his WR4 into a partner holding no
    startable WR. Knob 0 restores the kill."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    players = _engine_players()
    thin = LeagueMember(user_id="oppA", username="A", roster=["WNA"],
                        elo_ratings={"W4": 1700, "WNA": 1500},
                        has_rankings=True)
    assert _find(_engine_deck(players, [thin]), ["W4"], ["WNA"]) is not None
    ts._cfg["need_gate_dual_rescue"] = 0.0
    assert _find(_engine_deck(players, [thin]), ["W4"], ["WNA"]) is None


# ── the shared startable definition ────────────────────────────────────────


@pytest.mark.parametrize("tiers_on", (False, True))
def test_startable_matches_analyze_roster(tiers_on):
    """`_startable_ok_fn` must be analyze_roster_strengths' OWN startable
    definition, under BOTH banding modes — no invented threshold. Counted
    over a roster, it has to equal that profile's elite + starter."""
    _set_flags(**{"trade.position_tiers": tiers_on})
    roster = list(_SWEEP_PLAYERS)
    for fmt in ("1qb_ppr", "sf_ppr"):
        prof = analyze_roster_strengths(roster, _SWEEP_PLAYERS, fmt)
        ok = ts._startable_ok_fn(_SWEEP_PLAYERS, fmt)
        for pos, bins in prof["tier_depth"].items():
            mine = sum(1 for pid in roster
                       if getattr(_SWEEP_PLAYERS[pid], "position", None) == pos
                       and ok(pid, _SWEEP_PLAYERS[pid]))
            assert mine == bins["elite"] + bins["starter"], (pos, fmt,
                                                             tiers_on)


def test_presentment_ctx_reads_the_profile_not_a_second_pass():
    """The opponent's startable counts come off the profile the member loop
    already built — a second roster walk here is how two surfaces that are
    supposed to agree start disagreeing."""
    prof = analyze_roster_strengths(list(_C3_PLAYERS), _C3_PLAYERS, "1qb_ppr")
    ctx = ts._presentment_ctx(prof, {"RB": 1},
                              ts._startable_ok_fn(_C3_PLAYERS, "1qb_ppr"),
                              "1qb_ppr")
    for pos, bins in prof["tier_depth"].items():
        assert ctx["startable"][pos] == bins["elite"] + bins["starter"]
    assert ctx["user_startable"] == {"RB": 1}
    assert ctx["scoring_format"] == "1qb_ppr"


# ── arm A: why all three are EXCLUDED from MODEL_A_PROFILE ────────────────


def test_arm_a_never_reads_the_three_companion_knobs():
    """The disposition recorded in test_bakeoff_arm_a_golden.py's
    `_PINNED_KNOBS` is that C1/C2/C3's knobs are EXCLUDED from
    MODEL_A_PROFILE because each sits behind a sibling that arm A already
    pins at its kill value — the `max_overpay_min_value` precedent. That is
    a claim about control flow, so pin it: with the profile's kill values
    applied, setting each new knob to a value that WOULD change the verdict
    changes nothing, because the predicate never reaches the read."""
    sv = _sv({"g1": 1400.0, "g2": 1300.0, "g3": 1200.0, "R": 3300.0})
    with ts._cfg_override(MODEL_A_PROFILE):
        for adjusted in (0.0, 1.0):
            ts._cfg["overpay_adjusted"] = adjusted
            assert overpay_ok(["g1", "g2", "g3"], ["R"], sv) is True
        ctx = _c3_ctx(user_rb=3, opp_rb=3)
        for relief in (0.0, 1.0):
            ts._cfg["pos_net_starter_relief"] = relief
            assert pos_net_ok(["uRB1", "uRB2"], ["oWR"], _C3_PLAYERS,
                              opp_ctx=ctx) is True
        for rescue in (0.0, 1.0):
            ts._cfg["need_gate_dual_rescue"] = rescue
            assert need_gate_ok(["WR_X"], ["TE_LOVE"],
                                opp_ctx=_ctx_for({"RB": 0}),
                                **_loveland_kw()) is True
    # The three siblings arm A pins are what makes that true.
    assert MODEL_A_PROFILE["max_overpay_frac"] == 0.0
    assert MODEL_A_PROFILE["pos_net_cap"] == 0.0
    assert MODEL_A_PROFILE["need_gate_min_value"] == 0.0
