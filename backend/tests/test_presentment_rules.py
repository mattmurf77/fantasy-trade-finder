"""G6 — trade presentment rules (flag trade.presentment_rules).

Feedback #340 (R1 overpay ceiling), #341 (R2 per-position net cap), #339
(R3 pick-is-the-gap band), #304 (R5 window-scaled need gate, untargeted
decks only — R-5b bypass), #336 (R4 windowless awaiting/matched exclusion).
Spec: docs/feedback/items/304-positional-need-filter/ (prd.md §3.1 test
plan, lld-delta.md §3-§5 predicates/hooks/tripwire).

D-056 sabotage ledger — every behavioral test below was proven RED on its
named sabotage, then green on revert (evidence table in
docs/feedback/items/304-positional-need-filter/build-verification.md):

  U-R1-*   overpay_ok: replace max(g, r) with min(g, r).
  U-R2-*   pos_net_ok: count PICK assets as positional bodies (drop the
           is_pick_asset exclusion and admit "PICK" into the counted set).
  U-R2-5   trade_optimizer: drop presentment_ok_fn from the _try_sweeten
           call (sweetened combos skip re-validation).
  U-R3-*   pick_gap_ok: (a) evaluate the LIGHTER side's picks instead of
           the heavier side; (b) drop the band's upper bound (caught by
           U-R3-5, the B1 centerpiece-consolidation case).
  U-R5-*   call site: swap position_needs/position_surplus (caught by the
           not_sure branch tests); U-R5-10: compute the incumbent from the
           full pre-trade roster instead of roster − give_ids.
  U-R5-B*  server: derive the bypass from anything but the four job fields
           (helper truth table + source-wiring pin).
  U-R4-1   server _load_presentment_exclusions: reintroduce since_days=7
           (an 8-day-old awaiting like stops being excluded).
  U-R4-7   trade_service: accumulate the exclusion set instead of
           overwriting per call.
  U-R6-*   generators: move the presentment hook after the fairness gate
           (killed shapes reach the near-miss pool / heap).
  U-R7-1   relaxed pass: add the R1 knob to the stage overrides.
  U-R8-*   flag check removed (predicates invoked flag-off).
  U-R9-1   tripwire: drop the rule-kill term from the condition.
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
    need_gate_ok,
    overpay_ok,
    pick_gap_ok,
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


class _Player:
    def __init__(self, pid, position="WR", team="TST"):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = team
        self.age = 24
        self.ktc_value = None
        self.years_experience = 3     # player_to_dict (U-R10 serialization)


def _pick(pid):
    """Owned-pick pseudo-asset (position == 'PICK', _inject_owned_picks)."""
    return _Player(pid, position="PICK", team="PICK")


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _elo(value: float) -> float:
    """Inverse of elo_to_value at default knobs (k=0.005, ref 1500/1000)."""
    return 1500.0 + 200.0 * math.log(value / 1000.0)


def _sv(values: dict):
    """seed_value accessor over a VALUE-space dict (predicate tests)."""
    return lambda pid: values[pid]


def _find(cards, give, recv):
    g, r = tuple(sorted(give)), tuple(sorted(recv))
    for c in cards:
        if (tuple(sorted(c.give_player_ids)),
                tuple(sorted(c.receive_player_ids))) == (g, r):
            return c
    return None


# ═══════════════════════════════════════════════════════════════════════════
# R1 #340 — overpay ceiling (overpay_ok)
# ═══════════════════════════════════════════════════════════════════════════

_R1_PLAYERS = {"G": _Player("G"), "R": _Player("R")}


def test_r1_kills_both_directions():
    """U-R1-1/2 — opponent overpay AND user overpay both die."""
    sv = _sv({"G": 1000.0, "R": 1600.0})
    assert not overpay_ok(["G"], ["R"], sv)   # user wins big — still noise
    assert not overpay_ok(["R"], ["G"], sv)   # user pays big — insult


def test_r1_gap_floor_boundary():
    """U-R1-3 — gap 499 at 30% passes (absolute floor binds first)."""
    sv = _sv({"G": 1163.0, "R": 1662.0})      # gap 499, frac 0.30
    assert overpay_ok(["G"], ["R"], sv)


def test_r1_frac_boundary():
    """U-R1-4 — gap >= 500 at 24% passes; exactly 25% kills."""
    assert overpay_ok(["G"], ["R"], _sv({"G": 1900.0, "R": 2500.0}))   # 0.24
    assert not overpay_ok(["G"], ["R"], _sv({"G": 1875.0, "R": 2500.0}))  # 0.25


def test_r1_fit_premium_band_cannot_trip():
    """U-R1-6 — a 300-value raw loss (the fit_premium_max_loss ceiling)
    sits under the 500 floor, so a flagged need-fill card never trips R1."""
    sv = _sv({"G": 1000.0, "R": 700.0})       # gap 300, frac 0.30
    assert overpay_ok(["G"], ["R"], sv)


def test_r1_knob_disable():
    ts._cfg["max_overpay_frac"] = 0.0
    assert overpay_ok(["G"], ["R"], _sv({"G": 1000.0, "R": 9000.0}))


def _r1_engine_fixture():
    players = {"G": _Player("G", "WR"), "R": _Player("R", "WR")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={"G": 1700, "R": 1500}, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc


def _r1_engine_gen(svc, **kw):
    return svc.generate_trades(
        user_id="user", user_elo={"G": 1500, "R": 1700}, user_roster=["G"],
        league_id="L1", seed_elo={"G": 1500.0, "R": _elo(1600.0)},
        fairness_threshold=0.5, max_per_opponent=5, **kw)


def test_r1_engine_fairness_toggle_off_still_kills():
    """U-R1-5 — fairness_threshold 0.5 (mobile toggle OFF) passes the card
    through every pre-G6 gate (consensus ratio 0.625 >= 0.5); R1 kills it
    on the absolute raw-gap bound (gap 600 >= 500, frac 0.375 >= 0.25).
    The knob at its disable value resurrects it, pinning attribution."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    cards = _r1_engine_gen(_r1_engine_fixture())
    assert _find(cards, ["G"], ["R"]) is None, (
        "R1 must kill independent of the fairness toggle")
    assert _r1_engine_fixture; ts._cfg["max_overpay_frac"] = 0.0
    cards = _r1_engine_gen(_r1_engine_fixture())
    assert _find(cards, ["G"], ["R"]) is not None, (
        "knob-disabled control failed — fixture no longer passes the "
        "pre-G6 gates, kill attribution is unproven")


# ═══════════════════════════════════════════════════════════════════════════
# R2 #341 — per-position net cap (pos_net_ok)
# ═══════════════════════════════════════════════════════════════════════════

_R2_PLAYERS = {
    "RB1": _Player("RB1", "RB"), "RB2": _Player("RB2", "RB"),
    "RB3": _Player("RB3", "RB"),
    "WR1": _Player("WR1", "WR"), "WR2": _Player("WR2", "WR"),
    "PK1": _pick("PK1"), "PK2": _pick("PK2"),
}


def test_r2_two_rb_for_two_wr_killed():
    """U-R2-1 — 2RB→2WR wrecks positional balance (net RB −2, WR +2)."""
    assert not pos_net_ok(["RB1", "RB2"], ["WR1", "WR2"], _R2_PLAYERS)


def test_r2_signed_net_not_per_side_count():
    """U-R2-2 — one signed quantity per position: 2RB→1RB+1WR passes
    (net RB −1), and 2RB→2RB is net 0 (the N1 gross-count misread)."""
    assert pos_net_ok(["RB1", "RB2"], ["RB3", "WR1"], _R2_PLAYERS)
    assert pos_net_ok(["RB1", "RB2"], ["RB3", "RB3"], _R2_PLAYERS)


def test_r2_picks_uncounted():
    """U-R2-3 (corrected gloss, orchestrator 2026-08-16) — picks are not
    positional bodies: 2 picks + RB → 1 WR passes (net RB −1, WR +1,
    picks uncounted). Sabotage-catcher: counting PICK as a position reads
    net PICK −2 and turns this RED. The ORIGINAL prd gloss's
    'pick+RB→2WW passes' contradicted the R-2 formula — that shape KILLS
    on net WR +2 regardless of the pick, pinned below."""
    assert pos_net_ok(["PK1", "PK2", "RB1"], ["WR1"], _R2_PLAYERS)


def test_r2_pick_plus_rb_for_two_wr_kills():
    """Corrected U-R2-3 counterpart: pick+RB→2WR KILLS — the WR owner
    gives up 2 of a position without getting one back (net WR +2); the
    pick's exclusion does not rescue the player imbalance."""
    assert not pos_net_ok(["PK1", "RB1"], ["WR1", "WR2"], _R2_PLAYERS)


def test_r2_cap_zero_disables():
    """U-R2-4 — pos_net_cap 0 disables (filler_min_frac convention)."""
    ts._cfg["pos_net_cap"] = 0.0
    assert pos_net_ok(["RB1", "RB2"], ["WR1", "WR2"], _R2_PLAYERS)


def _sweetener_fixture():
    """v3 near-miss whose only rescue sweetener creates net WR +2.

    Base combo RB_G→WR_R1 (consensus 1000 vs 520, point ratio 0.52) sits
    inside the sweetener band [0.40, 0.55) and passes R1 (gap 480 < 500)
    and R2 (net −1/+1). The cheapest opponent sweetener WR_S (500) lifts
    fairness to 0.98 but makes the receive side 2 WRs (net WR +2) — the
    re-validation must reject it, and every alternative sweetener (flat
    1000-value fillers) trips R1 on the sweetened gap (>= 520, frac >=
    0.34), so NO sweetened card may surface. confidence=None keeps the
    point fairness gate (no range-overlap rescue) and no Elo shrinkage.
    """
    fill_u = {"QBu": "QB", "RBu1": "RB", "RBu2": "RB", "WRu1": "WR",
              "WRu2": "WR", "TEu": "TE"}
    fill_o = {"QBo": "QB", "RBo1": "RB", "RBo2": "RB", "WRo1": "WR",
              "WRo2": "WR", "TEo": "TE"}
    positions = {"RB_G": "RB", "WR_R1": "WR", "WR_S": "WR",
                 **fill_u, **fill_o}
    players = {pid: _Player(pid, pos) for pid, pos in positions.items()}
    flat = {pid: 1500.0 for pid in list(fill_u) + list(fill_o)}
    user_elo = {"RB_G": 1500, "WR_R1": 1700, "WR_S": 1500, **flat}
    opp_elo = {"RB_G": 1800, "WR_R1": 1400, "WR_S": 1500, **flat}
    seed = {"RB_G": 1500.0, "WR_R1": _elo(520.0), "WR_S": _elo(500.0),
            **flat}
    opp = LeagueMember(
        user_id="opp", username="opp",
        roster=["WR_R1", "WR_S"] + list(fill_o), elo_ratings=opp_elo,
        has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    user_roster = ["RB_G"] + list(fill_u)
    return svc, user_elo, user_roster, seed


def _sweetener_gen(flags_on=True):
    flags = {"trade_engine.v2": True, "trade_engine.v3": True}
    if flags_on:
        flags["trade.presentment_rules"] = True
    _set_flags(**flags)
    ts._cfg["v3_pool_size"] = 1
    svc, ue, ur, seed = _sweetener_fixture()
    return svc.generate_trades(
        user_id="user", user_elo=ue, user_roster=ur, league_id="L1",
        seed_elo=seed, confidence=None, fairness_threshold=0.75,
        max_per_opponent=5)


def test_r2_sweetener_revalidation():
    """U-R2-5 / U-R6-2 — a sweetener that creates a ±2 positional net is
    caught by the sweetened-combo re-validation; flag off, the same
    fixture emits exactly that card (pinning that re-validation, not some
    other gate, is what blocks it)."""
    cards = _sweetener_gen(flags_on=True)
    assert _find(cards, ["RB_G"], ["WR_R1", "WR_S"]) is None, (
        "sweetened net-+2 combo escaped the presentment re-validation")
    cards = _sweetener_gen(flags_on=False)
    assert _find(cards, ["RB_G"], ["WR_R1", "WR_S"]) is not None, (
        "flag-off control failed — the sweetener fixture no longer "
        "produces the ±2 card, so the re-validation assert proves nothing")


# ═══════════════════════════════════════════════════════════════════════════
# R3 #339 — pick-is-the-gap two-sided band (pick_gap_ok)
# ═══════════════════════════════════════════════════════════════════════════

_R3_PLAYERS = {
    "A": _Player("A"), "B": _Player("B"), "C": _Player("C"),
    "PK": _pick("PK"),
}


def _r3(give_vals: dict, recv_vals: dict):
    vals = dict(give_vals); vals.update(recv_vals)
    return pick_gap_ok(list(give_vals), list(recv_vals), _sv(vals),
                       _R3_PLAYERS)


def test_r3_pick_inside_band_on_heavier_side_killed():
    """U-R3-1 — gap 3,000 with a 3,000 pick on the heavier side: the pick
    IS the gap (band [2,400, 3,750]) — the #339 shape dies."""
    assert not _r3({"A": 3000.0, "PK": 3000.0}, {"B": 3000.0})


def test_r3_same_pick_on_lighter_side_passes():
    """U-R3-2 — the identical pick riding the LIGHTER side is fine."""
    assert _r3({"A": 6000.0}, {"PK": 3000.0})


def test_r3_sub_min_gap_passes():
    """U-R3-3 — gap under pick_gap_min_value (300) never evaluates."""
    assert _r3({"A": 1000.0, "PK": 200.0}, {"B": 1000.0})


def test_r3_knob_disable():
    """U-R3-4 — pick_gap_frac 0 disables."""
    ts._cfg["pick_gap_frac"] = 0.0
    assert _r3({"A": 3000.0, "PK": 3000.0}, {"B": 3000.0})


def test_r3_large_pick_small_gap_passes():
    """U-R3-5 — the B1 centerpiece-consolidation case the one-sided form
    banned: gap 300, mid-1st 3,000 (band [240, 375]) — the operator's own
    stud-scaled style. Catches the drop-the-upper-bound sabotage."""
    assert _r3({"PK": 3000.0}, {"B": 2700.0})


def test_r3_band_edges():
    """U-R3-6 — both edges are INSIDE the band (<=); one value off either
    edge is outside."""
    assert not _r3({"A": 5600.0, "PK": 2400.0}, {"B": 5000.0})  # lower edge
    assert not _r3({"A": 4250.0, "PK": 3750.0}, {"B": 5000.0})  # upper edge
    assert _r3({"A": 5602.0, "PK": 2398.0}, {"B": 5000.0})      # below band
    assert _r3({"A": 4248.0, "PK": 3752.0}, {"B": 5000.0})      # above band


def test_r3_engine_kill_through_v2_path():
    """R3 through the live v2 divergence path with an injected-pick-style
    pseudo-asset: give A (3,000) for B (2,900) + PK (600) — raw gap 500 on
    the heavier receive side with the pick inside [400, 625]: the pick IS
    the gap. R1 passes (frac 0.143 < 0.25), so the knob-off control pins
    the kill to R3. Companion to the DB-4 replay, whose local corpus
    contained zero R3-shaped candidates (fair 1-for-1 player-for-pick
    swaps only) — this proves the hook is not a silent no-op in-engine."""
    players = {"A": _Player("A", "WR"), "B": _Player("B", "WR"),
               "PK": _pick("PK")}
    user_elo = {"A": 1500, "B": 1700, "PK": 1600}
    opp_elo = {"A": 1700, "B": 1500, "PK": 1500}
    seed = {"A": _elo(3000.0), "B": _elo(2900.0), "PK": _elo(600.0)}

    def run():
        opp = LeagueMember(user_id="opp", username="opp",
                           roster=["B", "PK"], elo_ratings=dict(opp_elo),
                           has_rankings=True)
        svc = TradeService(players=players)
        svc.add_league(League(league_id="L1", name="T", platform="demo",
                              members=[opp]))
        return svc.generate_trades(
            user_id="user", user_elo=dict(user_elo), user_roster=["A"],
            league_id="L1", seed_elo=dict(seed), fairness_threshold=0.75,
            max_per_opponent=5)

    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    assert _find(run(), ["A"], ["B", "PK"]) is None, (
        "pick-is-the-gap package escaped R3 in the v2 path")
    ts._cfg["pick_gap_frac"] = 0.0
    assert _find(run(), ["A"], ["B", "PK"]) is not None, (
        "knob-off control failed — the kill was not R3's")


def test_r3_playerless_packages_ignored():
    """No pick anywhere ⇒ R3 never evaluates, whatever the gap."""
    assert pick_gap_ok(["A"], ["B"], _sv({"A": 9000.0, "B": 1000.0}),
                       _R3_PLAYERS)


def test_r1_engine_kill_through_consensus_path():
    """R-6 / CW-1 path 4 (QA 2026-08-16 F-5) — a rule kill through the live
    CONSENSUS generator (`_generate_consensus_for_pair`'s inner `_emit`
    hook), the one engine path no other G6 test exercises (every other
    engine fixture has has_rankings=True). Opponent has NO rankings, so the
    card is consensus-basis by construction: give G (1,000) for R (1,600) —
    the user comes out ahead (+600 consensus gain, so the #108 user-gain
    gate and fairness 0.625 ≥ 0.5 all pass) but R1's absolute bound kills
    it (gap 600 ≥ 500 floor, frac 0.375 ≥ 0.25). The knob-off control
    resurrects the same card and pins attribution to R1. Proven RED by
    deleting the `presentment_ok_fn` check inside `_emit`
    (trade_service.py:4412-4414) — the sabotage that leaves every other G6
    test green."""
    players = {"G": _Player("G", "WR"), "R": _Player("R", "WR")}
    seed = {"G": _elo(1000.0), "R": _elo(1600.0)}

    def run():
        opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                           elo_ratings={}, has_rankings=False)
        svc = TradeService(players=players)
        svc.add_league(League(league_id="L1", name="T", platform="demo",
                              members=[opp]))
        return svc.generate_trades(
            user_id="user", user_elo={"G": 1500, "R": 1700},
            user_roster=["G"], league_id="L1", seed_elo=dict(seed),
            fairness_threshold=0.5, max_per_opponent=5)

    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    assert _find(run(), ["G"], ["R"]) is None, (
        "overpay-shaped card escaped R1 in the consensus path")
    ts._cfg["max_overpay_frac"] = 0.0
    resurrected = _find(run(), ["G"], ["R"])
    assert resurrected is not None, (
        "knob-off control failed — the kill was not R1's")
    assert resurrected.basis == "consensus", (
        "fixture drifted off the consensus path — this test exists to "
        "cover _generate_consensus_for_pair's _emit hook specifically")


# ═══════════════════════════════════════════════════════════════════════════
# R5 #304 — window-scaled need gate (need_gate_ok)
# ═══════════════════════════════════════════════════════════════════════════

_R5_PLAYERS = {
    "TE_LOVE": _Player("TE_LOVE", "TE"), "TE_STAR": _Player("TE_STAR", "TE"),
    "WR_X": _Player("WR_X", "WR"), "PK": _pick("PK"),
}


def _r5(give, recv, vals, *, outlook, upv, surplus=(), needs=(),
        fmt="1qb_ppr"):
    return need_gate_ok(give, recv, seed_value=_sv(vals),
                        players=_R5_PLAYERS, user_pos_values=upv,
                        outlook=outlook, position_needs=list(needs),
                        position_surplus=list(surplus), scoring_format=fmt)


_LOVELAND_VALS = {"WR_X": 1000.0, "TE_LOVE": 1200.0, "TE_STAR": 3000.0,
                  "PK": 2000.0}
_LOVELAND_UPV = {"TE": [("TE_STAR", 3000.0)], "WR": [("WR_X", 1000.0)]}


def test_r5_loveland_contender_killed_rebuilder_served():
    """U-R5-1/2 — TE-primary behind the rostered starter: contender ⇒
    KILL; the identical card on a rebuilder (value accumulation) passes.
    jets and unresolved windows also pass (deliberate fail-open)."""
    kw = dict(vals=_LOVELAND_VALS, upv=_LOVELAND_UPV)
    assert not _r5(["WR_X"], ["TE_LOVE"], outlook="contender", **kw)
    assert not _r5(["WR_X"], ["TE_LOVE"], outlook="championship", **kw)
    assert _r5(["WR_X"], ["TE_LOVE"], outlook="rebuilder", **kw)
    assert _r5(["WR_X"], ["TE_LOVE"], outlook="jets", **kw)
    assert _r5(["WR_X"], ["TE_LOVE"], outlook=None, **kw)


def test_r5_not_sure_kills_only_on_surplus():
    """U-R5-3/4 — not_sure without surplus at P ⇒ served; with P in the
    surplus list ⇒ killed. (Catches the swap-needs/surplus sabotage.)"""
    kw = dict(vals=_LOVELAND_VALS, upv=_LOVELAND_UPV)
    assert _r5(["WR_X"], ["TE_LOVE"], outlook="not_sure", **kw)
    assert not _r5(["WR_X"], ["TE_LOVE"], outlook="not_sure",
                   surplus=["TE"], **kw)
    # needs alone must NOT flip the not_sure branch.
    assert _r5(["WR_X"], ["TE_LOVE"], outlook="not_sure",
               needs=["TE"], **kw)


def test_r5_hole_filling_receive_passes():
    """U-R5-5 — no TE bodies post-give ⇒ P fills a starting hole."""
    assert _r5(["WR_X"], ["TE_LOVE"], vals=_LOVELAND_VALS,
               upv={"WR": [("WR_X", 1000.0)]}, outlook="contender")


def test_r5_strict_upgrade_passes_and_margin_knob():
    """U-R5-6 — a receive above the incumbent passes; raising
    need_gate_upgrade_margin re-gates it."""
    vals = dict(_LOVELAND_VALS, TE_LOVE=3500.0)
    assert _r5(["WR_X"], ["TE_LOVE"], vals=vals, upv=_LOVELAND_UPV,
               outlook="contender")
    ts._cfg["need_gate_upgrade_margin"] = 0.5      # needs > 4500 now
    assert not _r5(["WR_X"], ["TE_LOVE"], vals=vals, upv=_LOVELAND_UPV,
                   outlook="contender")


def test_r5_sub_floor_primary_passes():
    """U-R5-7 — sub-500 primary is churn, not a need-gate case."""
    vals = dict(_LOVELAND_VALS, TE_LOVE=400.0)
    assert _r5(["WR_X"], ["TE_LOVE"], vals=vals, upv=_LOVELAND_UPV,
               outlook="contender")


def test_r5_pick_primary_exempt():
    """U-R5-7b — pick-primary cards are exempt (players only); a mixed
    receive judges the best PLAYER, not the pick."""
    assert _r5(["WR_X"], ["PK"], vals=_LOVELAND_VALS, upv=_LOVELAND_UPV,
               outlook="contender")
    # Pick (2000) outvalues TE_LOVE (1200) but the TE is still the primary.
    assert not _r5(["WR_X"], ["PK", "TE_LOVE"],
                   vals=dict(_LOVELAND_VALS, PK=2000.0),
                   upv=_LOVELAND_UPV, outlook="contender")


def test_r5_knob_disable():
    """need_gate_min_value <= 0 disables the whole gate."""
    ts._cfg["need_gate_min_value"] = 0.0
    assert _r5(["WR_X"], ["TE_LOVE"], vals=_LOVELAND_VALS,
               upv=_LOVELAND_UPV, outlook="contender")


def test_r5_post_give_incumbent():
    """U-R5-10 (round-1 B2) — the incumbent is computed on roster −
    give_ids: a contender tier-down that SENDS the starter away survives.
    Sabotage (full pre-trade roster) reads TE_STAR as the incumbent and
    kills the legitimate consolidation."""
    assert _r5(["TE_STAR"], ["TE_LOVE"], vals=_LOVELAND_VALS,
               upv=_LOVELAND_UPV, outlook="contender")


def test_r5_superflex_starter_slots():
    """QB starter slots follow the format (S=2 in superflex): a second
    startable QB is a hole-fill in sf, gated in 1qb."""
    players = dict(_R5_PLAYERS, QB_N=_Player("QB_N", "QB"),
                   QB_I=_Player("QB_I", "QB"))
    vals = {"WR_X": 1000.0, "QB_N": 1200.0, "QB_I": 3000.0}
    upv = {"QB": [("QB_I", 3000.0)]}

    def run(fmt):
        return need_gate_ok(["WR_X"], ["QB_N"], seed_value=_sv(vals),
                            players=players, user_pos_values=upv,
                            outlook="contender", position_needs=[],
                            position_surplus=[], scoring_format=fmt)
    assert not run("1qb_ppr")
    assert run("sf_tep")


# ─── R5 engine level (v2 divergence path) ─────────────────────────────────

def _r5_engine_fixture():
    players = {"WR_X": _Player("WR_X", "WR"), "TE_LOVE": _Player("TE_LOVE", "TE"),
               "TE_STAR": _Player("TE_STAR", "TE")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["TE_LOVE"],
                       elo_ratings={"WR_X": 1700, "TE_LOVE": 1500},
                       has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc


def _r5_engine_gen(svc, outlook, **kw):
    return svc.generate_trades(
        user_id="user", user_elo={"WR_X": 1500, "TE_LOVE": 1700},
        user_roster=["WR_X", "TE_STAR"], league_id="L1",
        seed_elo={"WR_X": 1500.0, "TE_LOVE": _elo(1200.0),
                  "TE_STAR": _elo(3000.0)},
        fairness_threshold=0.75, max_per_opponent=5, outlook=outlook, **kw)


def test_r5_engine_window_and_fit_premium_decoupling():
    """U-R5-1/2 through the live v2 path, and U-R5-9: trade.fit_premium is
    OFF here, so a silent coupling of R5's inputs to the fit-premium
    _user_needs plumbing would leave the gate inert — the kill proves the
    inputs are computed independently."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    assert _find(_r5_engine_gen(_r5_engine_fixture(), "contender"),
                 ["WR_X"], ["TE_LOVE"]) is None
    assert _find(_r5_engine_gen(_r5_engine_fixture(), "rebuilder"),
                 ["WR_X"], ["TE_LOVE"]) is not None
    # And with fit_premium ON the contender kill is unchanged (no
    # dependence either way — U-R5-9's flip side).
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True,
                  "trade.fit_premium": True})
    assert _find(_r5_engine_gen(_r5_engine_fixture(), "contender"),
                 ["WR_X"], ["TE_LOVE"]) is None


def test_r5_engine_not_sure_surplus_kill():
    """U-R5-3/4 through the live path: the engine threads the RESOLVED
    analyze_roster_strengths outputs — a not_sure user stacked 4-deep at
    WR (surplus) is not served another bench WR; unresolved window serves
    it. Catches the call-site needs/surplus swap sabotage (with only WRs
    rostered, needs = [QB, RB, TE], so swapped inputs stop the kill)."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    players = {p: _Player(p, "WR") for p in ("W1", "W2", "W3", "W4", "WN")}
    for p in ("W1", "W2", "W3", "W4"):
        players[p].search_rank = 20      # dynasty_value ⇒ startable ⇒ surplus

    def run(outlook):
        opp = LeagueMember(user_id="opp", username="opp", roster=["WN"],
                           elo_ratings={"W4": 1700, "WN": 1500},
                           has_rankings=True)
        svc = TradeService(players=players)
        svc.add_league(League(league_id="L1", name="T", platform="demo",
                              members=[opp]))
        return svc.generate_trades(
            user_id="user", user_elo={"W4": 1500, "WN": 1700},
            user_roster=["W1", "W2", "W3", "W4"], league_id="L1",
            seed_elo={"W1": _elo(3000.0), "W2": _elo(2900.0),
                      "W3": _elo(2800.0), "W4": 1500.0, "WN": _elo(1200.0)},
            fairness_threshold=0.75, max_per_opponent=5, outlook=outlook)

    assert _find(run("not_sure"), ["W4"], ["WN"]) is None
    assert _find(run(None), ["W4"], ["WN"]) is not None


def test_r5_engine_bypass_serves_targeted_jobs():
    """U-R5-B (engine half) — bypass_need_gate=True serves the identical
    R5-failing card; trade_away_positions alone (WITHOUT the bypass —
    B5's non-member) still kills."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    assert _find(_r5_engine_gen(_r5_engine_fixture(), "contender",
                                bypass_need_gate=True),
                 ["WR_X"], ["TE_LOVE"]) is not None
    assert _find(_r5_engine_gen(_r5_engine_fixture(), "contender",
                                trade_away_positions=["WR"]),
                 ["WR_X"], ["TE_LOVE"]) is None


def test_r5b_server_bypass_derivation():
    """U-R5-B1..B5 — the bypass derives from exactly the four job fields
    (pinned_give, pinned_receive, opponent_user_id, acquire_positions);
    an untargeted job never bypasses. NOTE: trade_away_positions is not
    even an input — the helper signature is the guarantee."""
    import backend.server as srv
    fn = srv._presentment_need_gate_bypass
    assert fn(["p1"], None, None, []) is True          # B1 pinned_give
    assert fn(None, ["p2"], None, []) is True          # B2 pinned_receive
    assert fn(None, None, "opp", []) is True           # B3 opponent scope
    assert fn(None, None, None, ["WR"]) is True        # B4 explicit acquire
    assert fn(None, None, None, []) is False           # B5 untargeted
    assert fn([], [], "", None) is False
    import inspect
    params = list(inspect.signature(fn).parameters)
    assert params == ["pinned_give", "pinned_receive", "opponent_user_id",
                      "acquire_positions"]


def test_r5b_run_trade_job_wiring():
    """Source pin (request-body-derivation sabotage): _run_trade_job must
    derive the bypass via the helper from its own job args and thread it
    into generate_trades — never read it from a request payload."""
    import inspect

    import backend.server as srv
    src = inspect.getsource(srv._run_trade_job)
    assert "_presentment_need_gate_bypass(" in src
    assert "bypass_need_gate" in src
    assert "request" not in src.split("_presentment_need_gate_bypass(")[1] \
        .split(")")[0]


# ═══════════════════════════════════════════════════════════════════════════
# R4 #336 — windowless awaiting/matched exclusion
# ═══════════════════════════════════════════════════════════════════════════

def _mem_db(monkeypatch):
    from sqlalchemy import create_engine

    import backend.database as db
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    return db, eng


def _insert_like(eng, user_id, league_id, give, recv, *, age_days=1,
                 retracted=False):
    import json as _json
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text
    created = (datetime.now(timezone.utc).replace(tzinfo=None)
               - timedelta(days=age_days)).isoformat()
    with eng.begin() as conn:
        conn.execute(text(
            "INSERT INTO trade_decisions (user_id, league_id, "
            "give_player_ids, receive_player_ids, decision, created_at, "
            "retracted_at) VALUES (:u, :l, :g, :r, 'like', :c, :ra)"),
            {"u": user_id, "l": league_id, "g": _json.dumps(give),
             "r": _json.dumps(recv), "c": created,
             "ra": created if retracted else None})


def _insert_match(eng, league_id, user_a, user_b, a_give, a_recv, status):
    import json as _json

    from sqlalchemy import text
    with eng.begin() as conn:
        conn.execute(text(
            "INSERT INTO trade_matches (league_id, user_a_id, user_b_id, "
            "user_a_give, user_a_receive, matched_at, status) "
            "VALUES (:l, :a, :b, :g, :r, '2026-08-01T00:00:00', :s)"),
            {"l": league_id, "a": user_a, "b": user_b,
             "g": _json.dumps(a_give), "r": _json.dumps(a_recv), "s": status})


def _seed_league_members(eng, league_id, rosters: dict):
    import json as _json

    from sqlalchemy import text
    with eng.begin() as conn:
        for uid, roster in rosters.items():
            conn.execute(text(
                "INSERT INTO league_members (league_id, user_id, username, "
                "roster_data, updated_at) VALUES (:l, :u, :u, :r, :t)"),
                {"l": league_id, "u": uid, "r": _json.dumps(roster),
                 "t": "2026-08-13T00:00:00"})


def test_r4_awaiting_like_excluded_windowless(monkeypatch):
    """U-R4-1 — THE root-cause regression: an 8-day-old un-retracted
    awaiting like is excluded. Today's since_days=7 generation dedup lets
    it regenerate; the sabotage (reintroducing the window into the
    exclusion query) turns this test red."""
    import backend.server as srv
    db, eng = _mem_db(monkeypatch)
    _seed_league_members(eng, "L1", {"me": ["a1", "a2"], "opp": ["x1"]})
    _insert_like(eng, "me", "L1", ["a1", "a2"], ["x1"], age_days=8)
    keys = srv._load_presentment_exclusions("me", "L1")
    assert (frozenset(["a1", "a2"]), frozenset(["x1"])) in keys


def test_r4_matches_excluded_both_orientations(monkeypatch):
    """U-R4-2/3 — pending and accepted matches exclude in BOTH the user_a
    and user_b orientation (user_b keys mirror to the user's give)."""
    import backend.server as srv
    db, eng = _mem_db(monkeypatch)
    _insert_match(eng, "L1", "me", "opp", ["g1"], ["r1"], "pending")
    _insert_match(eng, "L1", "opp2", "me", ["g2"], ["r2"], "accepted")
    keys = srv._load_presentment_exclusions("me", "L1")
    assert (frozenset(["g1"]), frozenset(["r1"])) in keys
    # user_b orientation: their give is my receive.
    assert (frozenset(["r2"]), frozenset(["g2"])) in keys
    assert len(keys) == 2


def test_r4_declined_and_retracted_regenerate(monkeypatch):
    """Q-G6-2 / #318 — declined matches and retracted likes do NOT block;
    a foreign league's rows never leak in."""
    import backend.server as srv
    db, eng = _mem_db(monkeypatch)
    _seed_league_members(eng, "L1", {"me": ["a1"], "opp": ["x1"]})
    _insert_match(eng, "L1", "me", "opp", ["g1"], ["r1"], "declined")
    _insert_like(eng, "me", "L1", ["a1"], ["x1"], age_days=10, retracted=True)
    _insert_match(eng, "L2", "me", "opp", ["g3"], ["r3"], "pending")
    assert srv._load_presentment_exclusions("me", "L1") == set()


def _r4_engine_fixture(n_recv=1):
    players = {"G": _Player("G", "WR"), "R": _Player("R", "WR")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={"G": 1700, "R": 1500}, has_rankings=True)
    svc = TradeService(players=players)
    for lid in ("L1", "L2"):
        svc.add_league(League(league_id=lid, name=lid, platform="demo",
                              members=[opp]))
    return svc


def _r4_engine_gen(svc, league_id, **kw):
    return svc.generate_trades(
        user_id="user", user_elo={"G": 1500, "R": 1700}, user_roster=["G"],
        league_id=league_id, seed_elo={"G": 1500.0, "R": _elo(1300.0)},
        fairness_threshold=0.75, max_per_opponent=5, **kw)


_R4_KEY = (frozenset(["G"]), frozenset(["R"]))


def test_r4_engine_exclusion_and_streaming_snapshot():
    """U-R4-5/6 — the exclusion set filters the organic deck AND every
    streaming snapshot published through on_opponent_done; the kill is
    accounted once under R4."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    svc = _r4_engine_fixture()
    snapshots = []
    cards = _r4_engine_gen(
        svc, "L1", exclusion_keys={_R4_KEY},
        on_opponent_done=lambda i, n, snap: snapshots.append(list(snap)))
    assert _find(cards, ["G"], ["R"]) is None
    assert snapshots, "streaming callback never fired"
    for snap in snapshots:
        assert _find(snap, ["G"], ["R"]) is None
    assert svc.presentment_kill_counts()["R4"] == 1
    # Control: without the exclusion the card exists.
    svc2 = _r4_engine_fixture()
    assert _find(_r4_engine_gen(svc2, "L1"), ["G"], ["R"]) is not None


def test_r4_engine_overwrite_per_call_two_league():
    """U-R4-7 (round-1 N3) — league A's exclusion set never filters league
    B's job on the same TradeService instance, and a None kwarg clears the
    stored set. Sabotage (accumulate instead of overwrite) turns this red."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    svc = _r4_engine_fixture()
    assert _find(_r4_engine_gen(svc, "L1", exclusion_keys={_R4_KEY}),
                 ["G"], ["R"]) is None
    # Same asset sets, league B, no exclusion passed: must serve.
    assert _find(_r4_engine_gen(svc, "L2", exclusion_keys=None),
                 ["G"], ["R"]) is not None


def test_r4_injector_dedup_and_quality_carveout(monkeypatch):
    """U-R4-4 / U-R13-1 — the likes-you injector refuses an
    already-matched mirror (R4 dedup applies, Q-G6-1) while an R1-shaped
    like ABOVE the D-055 user-gain floor still injects (Q21: quality rules
    never touch this surface — the floor is its only quality gate)."""
    import backend.server as srv
    players = {"A": _Player("A"), "B": _Player("B")}
    svc = TradeService(players=players)
    opp = LeagueMember(user_id="opp", username="opp", roster=["B"],
                       elo_ratings={}, has_rankings=False)
    league = League(league_id="L1", name="T", platform="demo", members=[opp])
    like = {"user_id": "opp", "give_player_ids": ["B"],
            "receive_player_ids": ["A"]}
    monkeypatch.setattr(srv, "load_recent_league_likes", lambda **kw: [like])
    # R1-shaped in the viewer's FAVOR: receive B (elo 1700 ≈ 2718) for A
    # (1500 ≈ 1000) — |Δ| ≈ +1718 ≥ 500 and 63% of the larger side.
    seed_map = {"A": 1500.0, "B": 1700.0}

    def run(exclusion_keys=None):
        return srv._inject_likes_you_cards(
            cards=[], trade_service=svc, user_id="user", league_id="L1",
            league=league, user_roster=["A"], seed_map=seed_map,
            exclusion_keys=exclusion_keys)

    injected = run()
    assert any(c.likes_you for c in injected), (
        "quality carve-out broken: an above-floor like was not injected")
    mirror_key = (frozenset(["A"]), frozenset(["B"]))
    assert run(exclusion_keys={mirror_key}) == []


# ═══════════════════════════════════════════════════════════════════════════
# R7 — never relaxed (#189)
# ═══════════════════════════════════════════════════════════════════════════

def test_r7_relaxed_pass_never_relaxes_r1():
    """U-R7-1 — a targeted job whose only candidate violates R1 comes back
    HONESTLY EMPTY from the relaxed pass; the knob-off control proves R1
    (not fairness/surplus) was the block."""
    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})

    def run():
        players = {"G": _Player("G"), "R": _Player("R")}
        opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                           elo_ratings={"G": 1700, "R": 1500},
                           has_rankings=True)
        svc = TradeService(players=players)
        svc.add_league(League(league_id="L1", name="T", platform="demo",
                              members=[opp]))
        return svc.generate_trades(
            user_id="user", user_elo={"G": 1500, "R": 1700},
            user_roster=["G"], league_id="L1",
            seed_elo={"G": 1500.0, "R": _elo(1800.0)},
            fairness_threshold=0.75, max_per_opponent=5,
            pinned_give_players=["G"])

    assert run() == [], "the #189 relaxed pass must not relax R1"
    ts._cfg["max_overpay_frac"] = 0.0
    assert _find(run(), ["G"], ["R"]) is not None, (
        "knob-off control failed — R1 was not what emptied the deck")


# ═══════════════════════════════════════════════════════════════════════════
# R8 — flag OFF ⇒ byte-identical; knobs are per-rule kill switches
# ═══════════════════════════════════════════════════════════════════════════

def test_r8_flag_off_predicates_never_run_and_cards_serve(monkeypatch):
    """U-R8-1 — flag OFF: the R1-violating fixture card serves exactly as
    pre-G6, and no presentment predicate is ever invoked (the strongest
    cheap proxy for byte-identity on top of the DB-1 corpus replay)."""
    calls = {"n": 0}
    real = ts.overpay_ok

    def spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)
    monkeypatch.setattr(ts, "overpay_ok", spy)
    _set_flags(**{"trade_engine.v2": True})     # presentment absent = OFF
    cards = _r1_engine_gen(_r1_engine_fixture())
    assert _find(cards, ["G"], ["R"]) is not None
    assert calls["n"] == 0


def test_r8_all_knobs_disabled_equals_flag_off_deck():
    """U-R8-2 — flag ON with every rule's knob at its disable value yields
    the same card list as flag OFF (each knob is that rule's kill switch)."""
    def keys(cards):
        return [(tuple(sorted(c.give_player_ids)),
                 tuple(sorted(c.receive_player_ids))) for c in cards]

    _set_flags(**{"trade_engine.v2": True})
    off = keys(_r1_engine_gen(_r1_engine_fixture()))

    _set_flags(**{"trade_engine.v2": True, "trade.presentment_rules": True})
    ts._cfg["max_overpay_frac"] = 0.0
    ts._cfg["pos_net_cap"] = 0.0
    ts._cfg["pick_gap_frac"] = 0.0
    ts._cfg["need_gate_min_value"] = 0.0
    on = keys(_r1_engine_gen(_r1_engine_fixture()))
    assert on == off


# ═══════════════════════════════════════════════════════════════════════════
# R9 — kill counters + tripwire
# ═══════════════════════════════════════════════════════════════════════════

def test_r9_tripwire_warning_with_attribution(caplog):
    """U-R9-1 — thin deck whose thinness the rules explain ⇒ WARNING with
    per-rule attribution; a thin deck the rules did NOT thin stays silent
    (the N2 false-alarm guard); the INFO counter line always emits."""
    import logging

    import backend.server as srv
    svc = TradeService(players={})
    svc._presentment_kills = {"R1": 20, "R2": 0, "R3": 0, "R5": 3}
    with caplog.at_level(logging.INFO, logger="trade_finder"):
        srv._log_presentment_outcome(svc, "job1", "L1", served=2)
    assert any("presentment-tripwire" in r.message for r in caplog.records)
    assert any("'R1': 20" in r.message for r in caplog.records)

    caplog.clear()
    svc._presentment_kills = {"R1": 0, "R2": 0, "R3": 0, "R5": 0}
    with caplog.at_level(logging.INFO, logger="trade_finder"):
        srv._log_presentment_outcome(svc, "job2", "L1", served=2)
    assert not any("presentment-tripwire" in r.message
                   for r in caplog.records)
    assert any("presentment kills=" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════
# R10 — no payload change (G4 contract)
# ═══════════════════════════════════════════════════════════════════════════

def test_r10_serialized_card_keys_identical_flag_on_vs_off():
    """U-R10-1 — trade_card_to_dict key-set is identical flag-ON vs
    flag-OFF: the rules only remove candidates before the serializer."""
    import backend.server as srv
    players = {"G": _Player("G"), "R": _Player("R")}

    def one_card(flag_on):
        flags = {"trade_engine.v2": True}
        if flag_on:
            flags["trade.presentment_rules"] = True
        _set_flags(**flags)
        opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                           elo_ratings={"G": 1700, "R": 1500},
                           has_rankings=True)
        svc = TradeService(players=players)
        svc.add_league(League(league_id="L1", name="T", platform="demo",
                              members=[opp]))
        cards = svc.generate_trades(
            user_id="user", user_elo={"G": 1500, "R": 1700},
            user_roster=["G"], league_id="L1",
            seed_elo={"G": 1500.0, "R": _elo(1300.0)},   # fair: no rule fires
            fairness_threshold=0.75, max_per_opponent=5)
        card = _find(cards, ["G"], ["R"])
        assert card is not None
        return srv.trade_card_to_dict(card, players)

    assert set(one_card(True).keys()) == set(one_card(False).keys())
