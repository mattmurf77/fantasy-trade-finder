"""Gap-sweetener relative band + best-effort fallback — `sweetener_gap_frac`
and `sweetener_best_effort` (docs/plans/sweetener-relative-band/scope.md;
feedback #414, mattmurf77 2026-08-31).

The served card: give Drake London, receive CeeDee Lamb, 1x1, `basis =
consensus`, give_value 5,932.8 / receive_value 7,328.9 (prod
`deck_impressions`, 2026-08-27..29), fairness 0.81 against a 0.75 bar,
`gap_sweetener: None`. The gap (1,396 = 19% of the richer side) passes R1
(`max_overpay_frac` 0.25) and sits UNDER the flat `sweetener_gap_threshold`
1,539, so `close_value_gap` never ran — the value bar told the user he was
winning by "over a first" while the sweetener's own unit said the gap was too
small to bother with. Second defect (QA 2026-09-01): the closer is
all-or-nothing, so lowering the threshold alone REGRESSES — a card partially
closable to 1,535 at 1,539 ships unsweetened at 1,825 once the line is 750.

Fixture note — the prod numbers are PACKAGED values. Under the live trade-wide
benchmark (`package_bench_trade_wide` 1.0) a 1x1's richer single asset earns
the crown credit, so CeeDee's SEED is inverted from the served 7,328.9 to
6,965.6 (`_CEEDEE`), which reproduces the card exactly: 5,932.8 / 7,328.8,
gap 1,396.0, ratio 0.81. The same math is why the brief's "a 900 equalizer
closes it to ≤ 879" does not hold: adding ANY second piece re-benchmarks
London himself against CeeDee at `package_floor_cross` 0.4 (−275), so 900
nets only −107 of packaged gap and 1,200 nets −337. With the 450/600/900/
1,200 bench the card is a best-effort PARTIAL (1,200 → 1,058.9); it closes
fully only when the bench holds a ≥ 1,500 piece (→ 772.1 ≤ 879.5).

Claims, and where each is proven:

  1. **Knob 0 is byte-identical to origin/main** (`e16bb487`). `_GOLDEN_*`
     are `close_value_gap` results on nine fixtures and full
     `generate_pair_trades_v3` decks on the engine-quality fixture and the
     gap-sweetener v3 fixture, captured on that tree — code that had never
     heard of either knob. Non-vacuity: the same rows differ at the live
     triple.
  2. **The #414 card.** Untouched at today's knobs; a best-effort partial
     (1,200, `partial: True`, gap 1,396 → 1,058.9, filler-clean at
     `filler_min_frac` 0.15, fairness ≥ 0.75) at (750 / 0.12 / 1); a full
     close (1,500 → 772.1 ≤ 879.5) when the bench has one; the relative
     band raises the trigger above the floor (frac 0.20 → 1,466 > 1,396 →
     no fire).
  3. **QA's regression.** G 5,400 / R 7,000 (gap 1,828.1), equalizers
     1,200 (→ 1,708.3) and 1,480 (→ 1,534.5): full close at 1,539;
     unsweetened at (750 / 0 / 0); best-effort partial with 1,480 at
     (750 / 0 / 1) — the tightest, not the cheapest.
  4. **Guards.** A 3,200 piece flips the richer side at |gap| 1,063.6 while
     passing R1, filler and fairness — best-effort must not pick it over
     the 900 partial. Pieces that RAISE the packaged gap are never
     attached. The two knobs are read at call time through the overlay.
  5. **Property fuzz** (200 random rosters × 4 formats × picks on/off
     through the helper with the live gate stack; 32 generated decks):
     every sweetened card passes R1, filler, fairness and lineup
     feasibility; every partial strictly narrows the gap and keeps the
     richer side; every full close sits under the effective trigger.

Capture procedure for the goldens (re-run only if a fixture changes)::

    git archive origin/main | tar -x -C <scratch>/main_tree
    cp backend/tests/test_sweetener_relative_band.py <scratch>/main_tree/backend/tests/
    (cd <scratch>/main_tree && PYTHONHASHSEED=0 python3 -m backend.tests.test_sweetener_relative_band)

Sabotage recipes (each proven red then green on 2026-09-02; clear
`backend/**/__pycache__` after restoring — G-060):
  * `thr_eff = max(gap_threshold, frac * max(gv, rv))` → `gap_threshold`
    → test_414_full_close_when_the_bench_holds_a_closer and
      test_frac_raises_the_trigger_above_the_floor red;
  * best-effort keeps the LARGEST post-add gap (`n_gap >= best[0]` →
    `n_gap <= best[0]`) → test_qa_regression_best_effort_attaches_the_tightest red;
  * drop the richer-side flip guard (`(n_rv > n_gv) != user_richer`)
    → test_best_effort_never_flips_the_richer_side red;
  * remove either pin from MODEL_A_PROFILE
    → test_bakeoff_arm_a_golden.py::test_sweetener_band_pins_are_load_bearing red;
  * hoist the reads to `_DEFAULT_CFG[...]`
    → test_knobs_are_read_at_call_time_through_the_overlay red.
"""

import json
import math
import os
import random

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_optimizer import (
    _consensus_packages,
    _feasible_after,
    _pos_counts,
    _subset_pos_delta,
    close_value_gap,
    generate_pair_trades_v3,
)
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    elo_to_value,
    filler_ok,
    overpay_ok,
    pick_swap_ok,
)
from backend.tests.test_engine_quality_golden import (
    _CONFIDENCE as _EQ_CONFIDENCE,
    _deck_fixture as _eq_fixture,
)
from backend.tests.test_gap_sweetener import (
    _Player,
    _bodies,
    _elo_for_value,
    _mini_league,
    _v3_league,
)

KNOB_THR = "sweetener_gap_threshold"
KNOB_FRAC = "sweetener_gap_frac"
KNOB_BEST = "sweetener_best_effort"
#: The proposed live triple (results.md § Recommendation).
LIVE = {KNOB_THR: 750.0, KNOB_FRAC: 0.12, KNOB_BEST: 1.0}
#: Prod `model_config` as read 2026-09-02 (D-159 bundle + D-172), so the
#: #414 arithmetic is the arithmetic users get. Every key exists on the
#: capture tree, so the goldens are captured under the same pins.
PROD_PINS = {
    "filler_min_frac":    0.15,
    "overpay_adjusted":   0.0,
    "trade_elo_gap_max":  0.0,
    "v3_shape_max_delta": 2.0,
    "consensus_fit_weight": 0.5,
}

_LONDON = 5932.8
_CEEDEE = 6965.6          # seed; packages to the served 7,328.9 (see docstring)
_FAIR = 0.75


@pytest.fixture(autouse=True)
def _isolate():
    old_flags, old_cfg = ff._flags_cache, dict(ts._cfg)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _live_flags():
    """The prod flag posture (`config/features.json` booleans over the code
    defaults). Load-bearing for the arithmetic: `trade.crown_asset` (ON in
    prod) is what gives the 1x1's richer single asset its credit, so the
    #414 numbers only reproduce under it. `trade.bakeoff` is forced off so
    `generate_trades` runs the plain engine, as every harness does."""
    cfg = json.load(open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "config",
        "features.json")))
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update({k: v for k, v in cfg.items() if isinstance(v, bool)})
    cache.update({"trade_engine.v2": True, "trade.bakeoff": False})
    return cache


def _setup(cfg=None, **flags):
    cache = _live_flags()
    cache.update(flags)
    ff._flags_cache = cache
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(PROD_PINS)
    # The two new knobs do not exist on the capture tree; only set a key
    # when it is asked for at a non-default value so the same file runs on
    # both trees (a stray key in `_cfg` is harmless but the golden must be
    # captured without one).
    for k, v in (cfg or {}).items():
        if v:
            ts._cfg[k] = float(v)


# ── the #414 card and its siblings ─────────────────────────────────────────

def _card(headline_give, headline_recv, bench, *, prefix="x"):
    """1x1 `headline_give` → `headline_recv` (both WR, age 25 so the age
    multipliers are the identity), an equalizer bench of WRs on the USER's
    roster, and the lineup-feasibility bodies at 200 on both sides — under
    the #141 floors, so they can never be the equalizer."""
    values = {"give": float(headline_give), "recv": float(headline_recv)}
    spec = {"give": "WR", "recv": "WR"}
    for i, v in enumerate(bench):
        values[f"{prefix}{i}"] = float(v)
        spec[f"{prefix}{i}"] = "WR"
    for pid, pos in {**_bodies("u"), **_bodies("o")}.items():
        spec[pid] = pos
        values[pid] = 200.0
    players = {pid: _Player(id=pid, name=pid, position=pos)
               for pid, pos in spec.items()}
    user_roster = ["give"] + [f"{prefix}{i}" for i in range(len(bench))] \
        + list(_bodies("u"))
    opp_roster = ["recv"] + list(_bodies("o"))
    return players, user_roster, opp_roster, values


def _card414(bench=(450.0, 600.0, 900.0, 1200.0)):
    return _card(_LONDON, _CEEDEE, bench)


def _card_qa(bench=(1200.0, 1480.0)):
    """QA's 2026-09-01 regression shape: packaged gap 1,828.1; 1,480 closes
    to 1,534.5 (under 1,539), 1,200 only to 1,708.3."""
    return _card(5400.0, 7000.0, bench)


def _close(cfg, fixture, *, fairness=_FAIR, gates=True, gap_threshold=None):
    """`close_value_gap` on a `_card` fixture, the way the callers call it:
    `gap_threshold` from the live row, the path's gate stack (here the
    consensus-metric #141 filler gate and R1) as `extra_ok_fn`. `cfg=None`
    leaves the process state exactly as the caller set it (the overlay
    test relies on that)."""
    if cfg is not None:
        _setup(cfg)
    players, user_roster, opp_roster, values = fixture
    sv = values.__getitem__
    extra = (lambda g, r: filler_ok(g, r, sv, sv) and overpay_ok(g, r, sv)) \
        if gates else None
    thr = ts._c(KNOB_THR) if gap_threshold is None else gap_threshold
    return close_value_gap(["give"], ["recv"], seed_value=sv,
                           gap_threshold=thr, fairness_threshold=fairness,
                           user_roster=user_roster, opp_roster=opp_roster,
                           players=players, extra_ok_fn=extra)


def _packaged(fixture, give, recv):
    values = fixture[3]
    return _consensus_packages(give, recv, values.__getitem__)


# ── consensus-path deck for the #414 card (pin test + stamp path) ──────────

def _consensus_deck(cfg, headline_give, headline_recv, bench):
    """A `_card` fixture through `generate_trades` against a partner with
    NO board (the consensus path — the path that served #414). Returns
    the cards that give the headliner and receive the other."""
    _setup(cfg)
    players, user_roster, opp_roster, values = _card(
        headline_give, headline_recv, bench)
    elos = {pid: _elo_for_value(v) for pid, v in values.items()}
    opp = LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                       elo_ratings={}, has_rankings=False)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    cards = svc.generate_trades(
        user_id="user", user_elo=dict(elos), user_roster=user_roster,
        league_id="L1", seed_elo=dict(elos), fairness_threshold=_FAIR,
        max_per_opponent=10)
    return [c for c in cards if c.receive_player_ids == ["recv"]
            and "give" in c.give_player_ids]


def _card414_consensus_deck(cfg):
    return _consensus_deck(cfg, _LONDON, _CEEDEE, (450.0, 600.0, 900.0, 1200.0))


# ── 1. goldens vs origin/main @ e16bb487 ──────────────────────────────────

def _helper_rows(cfg=None):
    """`close_value_gap` on nine fixtures; the first seven return fields
    (the capture tree's whole tuple), plus the gap the call started from."""
    rows = []

    def rec(name, fixture, give, recv, *, thr, fairness=_FAIR, gates=True,
            user_roster=None, opp_roster=None):
        _setup(cfg)
        players, ur, orr, values = fixture
        sv = values.__getitem__
        extra = (lambda g, r: filler_ok(g, r, sv, sv)
                 and overpay_ok(g, r, sv)) if gates else None
        out = close_value_gap(give, recv, seed_value=sv, gap_threshold=thr,
                              fairness_threshold=fairness,
                              user_roster=user_roster or ur,
                              opp_roster=opp_roster or orr,
                              players=players, extra_ok_fn=extra)
        rows.append([name, None if out is None else list(out[:7])])

    for thr in (1539.0, 750.0):
        rec(f"414@{thr:.0f}", _card414(), ["give"], ["recv"], thr=thr)
        rec(f"414+1500@{thr:.0f}", _card414((900.0, 1200.0, 1500.0)),
            ["give"], ["recv"], thr=thr)
        rec(f"qa@{thr:.0f}", _card_qa(), ["give"], ["recv"], thr=thr)
        rec(f"flip@{thr:.0f}", _card414((900.0, 3200.0)), ["give"],
            ["recv"], thr=thr)
    # The 2026-08-21 helper fixture, both directions (gap 1,600 > 1,539).
    players, ur, orr, sv, values = _mini_league()
    mini = (players, ur, orr, values)
    rec("mini", mini, ["G"], ["R"], thr=1539.0, gates=False)
    values["Y1"] = 1500.0
    players["Y1"] = _Player(id="Y1", name="Y1", position="WR")
    rec("mini-mirror", mini, ["R"], ["G"], thr=1539.0, gates=False,
        user_roster=orr, opp_roster=ur + ["Y1"])
    return rows


def _v3_rows(cfg=None):
    """Full `generate_pair_trades_v3` decks: the engine-quality fixture
    against its three boarded partners, then the gap-sweetener v3 fixture
    (the one whose organic winner carries a ~2,900 gap)."""
    rows = []
    _setup(cfg)
    svc, user_elo, user_roster, seed = _eq_fixture()
    for opp in svc._leagues["L1"].members:
        cards = generate_pair_trades_v3(
            user_id="user", shrunk_user_elo=dict(user_elo),
            user_value={p: elo_to_value(e) for p, e in user_elo.items()},
            user_roster=user_roster, opponent=opp, league_id="L1",
            seed_elo=dict(seed), confidence=dict(_EQ_CONFIDENCE),
            max_cards=10, fairness_threshold=0.6, players=svc._players,
            raw_user_elo=dict(user_elo))
        rows.extend(_card_rows(cards))
    _setup(cfg)
    _svc, players, user_roster, opp, seed, user_elo = _v3_league()
    cards = generate_pair_trades_v3(
        user_id="user", shrunk_user_elo=user_elo,
        user_value={p: elo_to_value(e) for p, e in user_elo.items()},
        user_roster=user_roster, opponent=opp, league_id="L1",
        seed_elo=seed, confidence=None,
        # 1, as in test_gap_sweetener._v3_cards: with headroom the organic
        # [G1, G2, X1] combo exists and the collision guard skips the gap
        # sweetening this golden exists to pin.
        max_cards=1, fairness_threshold=_FAIR,
        players=players, raw_user_elo=user_elo)
    rows.extend(_card_rows(cards))
    return rows


def _card_rows(cards):
    return [[sorted(c.give_player_ids), sorted(c.receive_player_ids),
             c.target_user_id, c.composite_score, c.fairness_score,
             c.mismatch_score, c.give_value, c.receive_value,
             c.gap_sweetener] for c in cards]


_GOLDEN_HELPER_JSON = """\
["414@1539",null],
["414+1500@1539",null],
["qa@1539",["x1","give",["give","x1"],["recv"],6006.0,7540.5,0.796]],
["flip@1539",null],
["414@750",null],
["414+1500@750",null],
["qa@750",null],
["flip@750",null],
["mini",["X1","give",["G","X1"],["R"],6022.3,7543.8,0.798]],
["mini-mirror",["X1","receive",["R"],["G","X1"],7543.8,6022.3,0.798]],
"""

_GOLDEN_V3_JSON = """\
[["hub"],["star1"],"opp1",1.195,0.67,3015.2,2718.3,1822.1,null],
[["hub","uq"],["o1q","o1w1","star1"],"opp1",1.137,0.875,3262.0,3600.2,3151.8,null],
[["hub","ur1"],["o1r1","o1w2","star1"],"opp1",1.137,0.875,3286.6,3600.2,3151.8,null],
[["hub","ur2"],["PKo1","o1r2","star1"],"opp1",1.134,0.962,3572.5,3600.2,3464.2,null],
[["hub","ur1","uw1"],["o1r2","o1w1","star1"],"opp1",1.127,0.703,3547.1,4482.2,3151.8,null],
[["hub","ur2","uw2"],["o1r1","o1w1","star1"],"opp1",1.127,0.703,3547.1,4482.2,3151.8,null],
[["hub","ut","uw1"],["o1t","o1w2","star1"],"opp1",1.127,0.703,3522.0,4482.2,3151.8,null],
[["PKu","hub","uw2"],["PKo1","o1w2","star1"],"opp1",1.121,0.717,3549.0,4830.5,3464.2,null],
[["PKu","uq","ut"],["o1q","o1t","star1"],"opp1",1.018,0.798,1257.6,2926.0,3666.6,null],
[["PKu","ur2","uw1"],["o1r1","o1w2","star1"],"opp1",1.003,0.798,1227.6,2926.0,3666.6,null],
[["hub"],["star2"],"opp2",1.278,0.67,3015.2,2718.3,1822.1,null],
[["hub","uq"],["o2q","o2w1","star2"],"opp2",1.187,0.875,3262.0,3600.2,3151.8,null],
[["hub","ur1"],["o2r1","o2w2","star2"],"opp2",1.187,0.875,3286.6,3600.2,3151.8,null],
[["hub","ur2"],["PKo2","o2r2","star2"],"opp2",1.182,0.962,3572.5,3600.2,3464.2,null],
[["hub","ur1","uw1"],["o2r2","o2w1","star2"],"opp2",1.171,0.703,3547.1,4482.2,3151.8,null],
[["hub","ur2","uw2"],["o2r1","o2w1","star2"],"opp2",1.171,0.703,3547.1,4482.2,3151.8,null],
[["hub","ut","uw1"],["o2t","o2w2","star2"],"opp2",1.171,0.703,3522.0,4482.2,3151.8,null],
[["PKu","hub","uw2"],["PKo2","o2w2","star2"],"opp2",1.162,0.717,3549.0,4830.5,3464.2,null],
[["PKu","uq","ut"],["o2q","o2t","star2"],"opp2",1.062,0.798,1257.6,2926.0,3666.6,null],
[["PKu","ur2","uw1"],["o2r1","o2w2","star2"],"opp2",1.046,0.798,1227.6,2926.0,3666.6,null],
[["hub"],["star3"],"opp3",1.297,0.67,3015.2,2718.3,1822.1,null],
[["hub","uq"],["o3q","o3w1","star3"],"opp3",1.199,0.875,3262.0,3600.2,3151.8,null],
[["hub","ur1"],["o3r1","o3w2","star3"],"opp3",1.199,0.875,3286.6,3600.2,3151.8,null],
[["hub","ur2"],["PKo3","o3r2","star3"],"opp3",1.193,0.962,3572.5,3600.2,3464.2,null],
[["hub","ur1","uw1"],["o3r2","o3w1","star3"],"opp3",1.181,0.703,3547.1,4482.2,3151.8,null],
[["hub","ur2","uw2"],["o3r1","o3w1","star3"],"opp3",1.181,0.703,3547.1,4482.2,3151.8,null],
[["hub","ut","uw1"],["o3t","o3w2","star3"],"opp3",1.181,0.703,3522.0,4482.2,3151.8,null],
[["PKu","hub","uw2"],["PKo3","o3w2","star3"],"opp3",1.172,0.717,3549.0,4830.5,3464.2,null],
[["PKu","uq","ut"],["o3q","o3t","star3"],"opp3",1.072,0.798,1257.6,2926.0,3666.6,null],
[["PKu","ur2","uw1"],["o3r1","o3w2","star3"],"opp3",1.056,0.798,1227.6,2926.0,3666.6,null],
[["G1","G2"],["R"],"opp",1.413,0.61,6822.0,5091.3,8344.6,null],
"""


def _load(blob):
    return [json.loads(line) for line in
            blob.strip().rstrip(",").split(",\n")]


GOLDEN_HELPER = _load(_GOLDEN_HELPER_JSON)
GOLDEN_V3 = _load(_GOLDEN_V3_JSON)


def test_helper_knob0_is_byte_identical_to_origin_main():
    """Both knobs at their defaults ⇒ `close_value_gap` returns exactly what
    the capture tree returned on nine fixtures, and every hit is a FULL
    close (the 8th field, absent on main, is False)."""
    assert _helper_rows() == GOLDEN_HELPER
    assert _helper_rows({KNOB_FRAC: 0.0, KNOB_BEST: 0.0}) == GOLDEN_HELPER
    out = _close({}, _card_qa(), gap_threshold=1539.0)
    assert out is not None and out[7] is False


def test_v3_deck_knob0_is_byte_identical_to_origin_main():
    """Full v3 decks — 24 engine-quality cards and the sweetened 3-for-1 —
    byte-identical at the defaults, `gap_sweetener` dicts included (no
    `partial` key rides on a full close)."""
    assert _v3_rows() == GOLDEN_V3
    assert _v3_rows({KNOB_FRAC: 0.0, KNOB_BEST: 0.0}) == GOLDEN_V3


def test_the_goldens_are_not_vacuous():
    """The same fixtures MOVE at the live triple, so the goldens pin the
    default, not a fixture that cannot change."""
    live_helper = _helper_rows(LIVE)
    assert live_helper != GOLDEN_HELPER
    # The #414 card, unreachable on main at either threshold, now closes.
    moved = {name: row for name, row in live_helper}
    assert moved["414@750"] is not None and moved["qa@750"] is not None
    assert _v3_rows(LIVE) != GOLDEN_V3


# ── 2. the #414 card ───────────────────────────────────────────────────────

def test_414_fixture_reproduces_the_served_card():
    gv, rv = _packaged(_card414(), ["give"], ["recv"])
    assert (gv, rv) == (5932.8, 7328.8)
    assert round(abs(gv - rv), 1) == 1396.0
    assert round(min(gv, rv) / max(gv, rv), 2) == 0.81
    assert round(0.12 * max(gv, rv), 1) == 879.5


def test_414_card_is_untouched_at_todays_knobs():
    """1,396 < 1,539 with the relative band off ⇒ the helper never runs,
    exactly as it did not in prod."""
    assert _close({}, _card414()) is None
    assert _close({KNOB_THR: 1539.0, KNOB_FRAC: 0.0, KNOB_BEST: 0.0},
                  _card414()) is None


def test_414_card_gets_a_best_effort_partial_at_the_live_triple():
    """(750 / 0.12 / 1): trigger 879.5; no bench piece closes under it, so
    the best-effort branch attaches the gate-passing piece that leaves the
    tightest gap — 1,200 (→ 1,058.9), not 900 (→ 1,288.8) — and stamps
    `partial`. The 450/600 pieces fail the #141 bar (max(0.15 × 5,932.8,
    450) = 889.9) AND would widen the packaged gap."""
    fixture = _card414()
    out = _close(LIVE, fixture)
    assert out is not None
    s_pid, side, new_give, new_recv, gv, rv, ratio, partial = out
    assert partial is True
    assert side == "give" and s_pid == "x3" and new_recv == ["recv"]
    assert fixture[3][s_pid] == 1200.0
    assert round(abs(gv - rv), 1) == 1058.9 < 1396.0
    assert ratio >= _FAIR
    sv = fixture[3].__getitem__
    assert filler_ok(new_give, new_recv, sv, sv)
    assert overpay_ok(new_give, new_recv, sv)
    assert fixture[3][s_pid] >= max(0.15 * _LONDON, 450.0)


def test_414_full_close_when_the_bench_holds_a_closer():
    """With a 1,500 piece on the bench the card closes FULLY under the
    879.5 trigger (→ 772.1) — and it is a full close only because the
    relative band lifted the trigger from 750 to 879.5."""
    out = _close(LIVE, _card414((900.0, 1200.0, 1500.0)))
    assert out is not None
    s_pid, _side, _g, _r, gv, rv, _ratio, partial = out
    assert s_pid == "x2" and partial is False
    assert round(abs(gv - rv), 1) == 772.1 <= 879.5


def test_frac_raises_the_trigger_above_the_floor():
    """`thr_eff = max(threshold, frac × max(gv, rv))`: at frac 0.20 the
    trigger is 1,465.8 > 1,396 and the card is left alone; at 0.12 it is
    879.5 and the closer runs."""
    assert _close({KNOB_THR: 750.0, KNOB_FRAC: 0.20, KNOB_BEST: 1.0},
                  _card414()) is None
    assert _close(LIVE, _card414()) is not None
    # And the floor still wins when frac × H is under it.
    assert _close({KNOB_THR: 1539.0, KNOB_FRAC: 0.12, KNOB_BEST: 1.0},
                  _card414()) is None


# ── 3. QA's regression case ────────────────────────────────────────────────

def test_qa_fixture_numbers():
    fx = _card_qa()
    gv, rv = _packaged(fx, ["give"], ["recv"])
    assert round(abs(gv - rv), 1) == 1828.1
    g1, r1 = _packaged(fx, ["give", "x1"], ["recv"])
    g0, r0 = _packaged(fx, ["give", "x0"], ["recv"])
    assert round(abs(g1 - r1), 1) == 1534.5 <= 1539.0
    assert round(abs(g0 - r0), 1) == 1708.3


def test_qa_regression_full_close_at_the_old_threshold():
    out = _close({KNOB_THR: 1539.0}, _card_qa())
    assert out is not None and out[0] == "x1" and out[7] is False


def test_qa_regression_threshold_cut_alone_ships_unsweetened():
    """THE regression: 750 with the all-or-nothing closer ⇒ the card that
    used to close to 1,535 ships at its ORIGINAL 1,828. This is why any
    threshold cut must ship with `sweetener_best_effort` on."""
    assert _close({KNOB_THR: 750.0, KNOB_FRAC: 0.0, KNOB_BEST: 0.0},
                  _card_qa()) is None


def test_qa_regression_best_effort_attaches_the_tightest():
    """(750 / 0 / 1): both pieces pass every gate, neither closes under 750;
    the one that leaves the SMALLER gap wins (1,480 → 1,534.5 over 1,200 →
    1,708.3), even though 1,200 is cheaper and tried first."""
    out = _close({KNOB_THR: 750.0, KNOB_FRAC: 0.0, KNOB_BEST: 1.0},
                 _card_qa())
    assert out is not None
    s_pid, side, new_give, new_recv, gv, rv, ratio, partial = out
    assert s_pid == "x1" and partial is True and side == "give"
    assert round(abs(gv - rv), 1) == 1534.5
    assert ratio >= _FAIR


# ── 4. guards ──────────────────────────────────────────────────────────────

def test_best_effort_never_flips_the_richer_side():
    """3,200 flips the card (give 8,239.7 > receive 7,176.1) and leaves
    |gap| 1,063.6 — smaller than 900's 1,288.8 — while passing R1 (raw
    2,167 / 9,133 = 0.237 < 0.25), filler and fairness. Best-effort must
    still pick 900: a flipped partial has turned the user's overpay into
    the partner's."""
    fx = _card414((900.0, 3200.0))
    sv = fx[3].__getitem__
    # Non-vacuity: the flipper passes every other gate on its own.
    g, r = _packaged(fx, ["give", "x1"], ["recv"])
    assert g > r and round(abs(g - r), 1) == 1063.6
    assert overpay_ok(["give", "x1"], ["recv"], sv)
    assert filler_ok(["give", "x1"], ["recv"], sv, sv)
    assert min(g, r) / max(g, r) >= _FAIR
    out = _close(LIVE, fx)
    assert out is not None
    assert out[0] == "x0" and out[7] is True
    assert round(abs(out[4] - out[5]), 1) == 1288.8


def test_best_effort_never_widens_the_gap():
    """Cheap pieces WIDEN the packaged gap (the trade-wide benchmark
    re-prices London against CeeDee once his side has two pieces): 450 →
    1,514.2, 600 → 1,445.0. With the #141 gate off they still must not be
    attached — strict reduction is its own rule."""
    fx = _card414((450.0, 600.0))
    for x in ("x0", "x1"):
        g, r = _packaged(fx, ["give", x], ["recv"])
        assert abs(g - r) > 1396.0
    _setup(LIVE)
    ts._cfg["filler_min_frac"] = 0.0          # gate off: only the rule stands
    assert _close(LIVE, fx, gates=False) is None or \
        _close(LIVE, fx, gates=False)[0] not in ("x0", "x1")
    assert _close(LIVE, fx, gates=False) is None


def test_knobs_are_read_at_call_time_through_the_overlay():
    """A process-global live triple overlaid with the two identity values
    is the knob-0 result (arm A's pin, the #189 relaxed pass); overlaying
    only one of them leaves the other live."""
    _setup(LIVE)
    with ts._cfg_override({KNOB_FRAC: 0.0, KNOB_BEST: 0.0}):
        assert _close(None, _card414(), gap_threshold=750.0) is None
    _setup(LIVE)
    with ts._cfg_override({KNOB_BEST: 0.0}):       # band on, closer strict
        assert _close(None, _card414((900.0, 1200.0, 1500.0)),
                      gap_threshold=750.0)[0] == "x2"
    _setup(LIVE)
    with ts._cfg_override({KNOB_FRAC: 0.0}):       # floor only, best-effort
        out = _close(None, _card414((900.0, 1200.0, 1500.0)),
                     gap_threshold=750.0)
        assert out[0] == "x2" and out[7] is True   # 772.1 > 750: partial


def test_defaults_registered_in_both_stores_and_arm_dispositions():
    from backend import database as db
    from backend.bakeoff_profiles import (MODEL_A_PROFILE,
                                          MODEL_CHALLENGER_PROFILE)
    seeded = {k: v for k, v, _ in db._MODEL_CONFIG_DEFAULTS}
    for knob in (KNOB_FRAC, KNOB_BEST):
        assert ts._DEFAULT_CFG[knob] == 0.0
        assert seeded[knob] == 0.0            # the admin PUT needs the row
        assert MODEL_A_PROFILE[knob] == 0.0   # arm A pins the identity
        assert knob not in MODEL_CHALLENGER_PROFILE   # arm D inherits prod
    assert ts._DEFAULT_CFG[KNOB_THR] == 1539.0   # the code default stays


# ── 5. the stamp path, per generator ──────────────────────────────────────

def test_consensus_path_stamps_partial_on_the_414_card():
    off = _card414_consensus_deck({})
    assert off and all(c.gap_sweetener is None for c in off)
    assert off[0].give_player_ids == ["give"]
    on = _card414_consensus_deck(LIVE)
    sweet = [c for c in on if c.gap_sweetener]
    assert sweet, "the #414 consensus card was not sweetened"
    c = sweet[0]
    assert c.gap_sweetener["partial"] is True
    assert c.gap_sweetener["player_id"] == "x3" and "x3" in c.give_player_ids
    assert c.gap_sweetener["gap_before"] == 1396.0
    assert c.gap_sweetener["gap_after"] == 1058.9
    assert round(abs(c.give_value - c.receive_value), 1) == 1058.9
    assert c.fairness_score >= _FAIR


def test_v3_path_stamps_partial_and_full_closes_distinctly():
    """The gap-sweetener v3 fixture at the PROD flag posture is QA's shape
    on the v3 path: [G1, G2] → [R] carries a 3,253 gap and X1 (2,200) cannot
    bring it under 1,539, so today the card ships UNSWEETENED at its full
    gap (the golden's last row, `gap_sweetener: null`); at the live triple
    the same card is a best-effort partial and says so. A full close (the
    helper's QA row at 1,539) carries no `partial` key."""
    off = [r for r in _v3_rows() if r[0] == ["G1", "G2"]]
    assert off and off[0][8] is None
    assert abs(off[0][6] - off[0][7]) > 1539.0
    live = [r for r in _v3_rows(LIVE) if r[8]]
    assert live and any(r[8].get("partial") for r in live), live
    for r in live:
        assert r[8]["gap_after"] < r[8]["gap_before"]
    full = _close({KNOB_THR: 1539.0}, _card_qa())
    assert full is not None and full[7] is False


def test_v2_divergence_path_stamps_partial():
    """Same fixture through the heap-based v2 pair generator (v3 off), at
    the code-default flag posture `test_gap_sweetener._v2_cards` proves
    sweetens (there X1 closes the ~2,881 gap to 1,127 ≤ 1,539); at the
    live triple the trigger is 0.12 × ~8,330 ≈ 1,000, so the same close
    is now a stamped partial. The STAMP path is what this pins."""
    _setup(LIVE)
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update({"trade_engine.v2": True})
    ff._flags_cache = cache
    svc, _players, user_roster, _opp, seed, user_elo = _v3_league()
    cards = svc.generate_trades(
        user_id="user", user_elo=dict(user_elo), user_roster=user_roster,
        league_id="L1", seed_elo=dict(seed), fairness_threshold=_FAIR,
        max_per_opponent=3)
    sweet = [c for c in cards if c.gap_sweetener and c.basis == "divergence"]
    assert sweet, "fixture no longer sweetens on the v2 divergence path"
    assert any(c.gap_sweetener.get("partial") for c in sweet)
    for c in sweet:
        assert c.gap_sweetener["gap_after"] < c.gap_sweetener["gap_before"]


# Arm C (`trade_gen_v2`) stamps through the same tuple (its own
# `close_value_gap` call, fairness 0.0 + its native band); it emits nothing
# on these unit fixtures, so its partial stamps are read off the harness
# (docs/plans/sweetener-relative-band/results.md, `C_gen_v2` rows) and the
# code-walk, not a unit test here.


# ── 6. property fuzz ───────────────────────────────────────────────────────

_FORMATS = ("1qb_ppr", "1qb_std", "sf_ppr", "sf_tep")
_POS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE")


class _FzPlayer:
    def __init__(self, pid, position, team="TST"):
        self.id = pid
        self.name = pid
        self.position = position
        self.team = team
        self.age = 25
        self.ktc_value = None
        self.pick_value = None
        self.years_experience = 3
        self.search_rank = 50


def _random_roster(rng, tag, n, picks, players, values):
    roster = []
    for i in range(n):
        pid = f"{tag}{i}"
        # log-uniform 250 .. 8,000 — the served value curve's span
        v = round(math.exp(rng.uniform(math.log(250.0), math.log(8000.0))), 1)
        players[pid] = _FzPlayer(pid, _POS[i % len(_POS)] if i < 7
                                 else rng.choice(_POS))
        values[pid] = v
        roster.append(pid)
    if picks:
        for k in range(3):
            pid = f"{tag}pk{k}"
            players[pid] = _FzPlayer(pid, "PICK", team="PICK")
            values[pid] = float(rng.choice((700.0, 1500.0, 2200.0, 2400.0)))
            roster.append(pid)
    return roster


def _random_card(rng, roster_u, roster_o, values):
    g = rng.sample(roster_u, rng.choice((1, 1, 2)))
    r = rng.sample(roster_o, rng.choice((1, 1, 2)))
    return g, r


def test_property_fuzz_helper_with_the_live_gate_stack():
    """200 random rosters × 4 formats × picks on/off through `close_value_gap`
    at the live triple with the consensus filler gate, R1 and the #227 pick
    gate as `extra_ok_fn`. Every returned close passes every gate; partials
    strictly narrow the gap and keep the richer side; full closes sit under
    the effective trigger. The run must exercise BOTH branches."""
    _setup(LIVE)
    rng = random.Random(414)
    fulls = partials = fired = 0
    for i in range(200):
        fmt = _FORMATS[i % 4]
        picks = bool((i // 4) % 2)
        players, values = {}, {}
        ru = _random_roster(rng, "u", 16, picks, players, values)
        ro = _random_roster(rng, "o", 16, picks, players, values)
        sv = values.__getitem__
        give, recv = _random_card(rng, ru, ro, values)
        gv, rv = _consensus_packages(give, recv, sv)
        thr_eff = max(750.0, 0.12 * max(gv, rv))
        gap0 = abs(gv - rv)

        def extra(g, r):
            return (filler_ok(g, r, sv, sv) and overpay_ok(g, r, sv)
                    and pick_swap_ok(g, r, players, sv))

        out = close_value_gap(give, recv, seed_value=sv, gap_threshold=750.0,
                              fairness_threshold=_FAIR, user_roster=ru,
                              opp_roster=ro, players=players,
                              scoring_format=fmt, extra_ok_fn=extra)
        if out is None:
            continue
        fired += 1
        s_pid, side, ng, nr, n_gv, n_rv, ratio, partial = out
        n_gap = abs(n_gv - n_rv)
        assert (s_pid in ru) if side == "give" else (s_pid in ro)
        assert ratio >= _FAIR and extra(ng, nr)
        uc, oc = _pos_counts(ru, players), _pos_counts(ro, players)
        gd, rd = _subset_pos_delta(ng, players), _subset_pos_delta(nr, players)
        assert _feasible_after(uc, gd, rd, fmt) and \
            _feasible_after(oc, rd, gd, fmt)
        if partial:
            partials += 1
            assert n_gap < gap0 and n_gap > thr_eff
            assert (n_rv > n_gv) == (rv > gv)      # richer side unchanged
        else:
            fulls += 1
            assert n_gap <= thr_eff
            assert gap0 > thr_eff
    assert fulls > 0 and partials > 0, (fired, fulls, partials)


def test_property_fuzz_generated_decks_at_the_live_triple():
    """32 generated decks (4 formats × picks on/off × 4 seeds; one boarded
    and one unboarded partner, presentment rules ON as in prod): no
    exceptions; every card carrying `gap_sweetener` passes R1 and the #141
    gate on the path's own boards, clears the fairness bar, keeps both
    lineups legal, and — reconstructing the pre-sweetener card — strictly
    narrowed its gap without flipping the richer side (partials) or sits
    under the effective trigger (full closes)."""
    rng = random.Random(4140)
    seen_sweet = seen_partial = 0
    for i in range(32):
        fmt = _FORMATS[i % 4]
        picks = bool((i // 4) % 2)
        _setup(LIVE, **{"trade_engine.v3": True,
                        "trade.presentment_rules": True})
        players, values = {}, {}
        ru = _random_roster(rng, "u", 14, picks, players, values)
        ro1 = _random_roster(rng, "a", 14, picks, players, values)
        ro2 = _random_roster(rng, "b", 14, picks, players, values)
        seed = {p: _elo_for_value(v) for p, v in values.items()}
        user_elo = {p: e + rng.choice((-80.0, 0.0, 0.0, 80.0))
                    for p, e in seed.items()}
        opp1_elo = {p: e + rng.choice((-80.0, 0.0, 0.0, 80.0))
                    for p, e in seed.items()}
        members = [
            LeagueMember(user_id="a", username="a", roster=ro1,
                         elo_ratings=opp1_elo, has_rankings=True),
            LeagueMember(user_id="b", username="b", roster=ro2,
                         elo_ratings={}, has_rankings=False),
        ]
        svc = TradeService(players=players)
        svc.add_league(League(league_id="L", name="L", platform="demo",
                              members=members))
        cards = svc.generate_trades(
            user_id="u", user_elo=dict(user_elo), user_roster=ru,
            league_id="L", seed_elo=dict(seed), fairness_threshold=_FAIR,
            max_per_opponent=5, scoring_format=fmt)
        sv = lambda p: elo_to_value(seed[p])                  # noqa: E731
        uv = lambda p: elo_to_value(user_elo[p])              # noqa: E731
        rosters = {"a": ro1, "b": ro2}
        boards = {"a": opp1_elo, "b": None}
        for c in cards:
            gs = c.gap_sweetener
            if not gs:
                continue
            seen_sweet += 1
            g, r = list(c.give_player_ids), list(c.receive_player_ids)
            ro = rosters[c.target_user_id]
            board = boards[c.target_user_id]
            ov = (lambda p: elo_to_value(board.get(p, seed[p]))) \
                if board else sv
            assert overpay_ok(g, r, sv), (c.give_player_ids, c.receive_player_ids)
            assert filler_ok(g, r, uv, ov)
            # The path's OWN bar: the divergence generators (v3 / v2 pair)
            # loosen the caller's threshold to `fairness_floor_divergence`
            # before any gate runs (`trade_optimizer.py:302`, "loosen it",
            # 2026-07-17) and the helper inherits it verbatim; consensus
            # cards keep the caller's 0.75.
            bar = _FAIR if c.basis == "consensus" else \
                min(_FAIR, ts._c("fairness_floor_divergence"))
            assert c.fairness_score >= bar, (c.basis, c.fairness_score)
            gv1, rv1 = _consensus_packages(g, r, sv)
            assert min(gv1, rv1) / max(gv1, rv1) >= bar - 1e-3
            uc, oc = _pos_counts(ru, players), _pos_counts(ro, players)
            gd, rd = _subset_pos_delta(g, players), _subset_pos_delta(r, players)
            assert _feasible_after(uc, gd, rd, fmt) and \
                _feasible_after(oc, rd, gd, fmt)
            pid, side = gs["player_id"], gs["side"]
            assert pid in (g if side == "give" else r)
            g0 = [p for p in g if p != pid] if side == "give" else g
            r0 = [p for p in r if p != pid] if side == "receive" else r
            gv0, rv0 = _consensus_packages(g0, r0, sv)
            gv1, rv1 = _consensus_packages(g, r, sv)
            thr_eff = max(750.0, 0.12 * max(gv0, rv0))
            assert abs(gv0 - rv0) > thr_eff
            assert round(abs(gv0 - rv0), 1) == gs["gap_before"]
            assert round(abs(gv1 - rv1), 1) == gs["gap_after"]
            if gs.get("partial"):
                seen_partial += 1
                assert abs(gv1 - rv1) < abs(gv0 - rv0)
                assert (rv1 > gv1) == (rv0 > gv0)
                assert abs(gv1 - rv1) > thr_eff
            else:
                assert abs(gv1 - rv1) <= thr_eff
    assert seen_sweet > 0 and seen_partial > 0, (seen_sweet, seen_partial)


if __name__ == "__main__":            # capture mode — see the module docstring
    print('_GOLDEN_HELPER_JSON = """\\')
    for row in _helper_rows():
        print(json.dumps(row, separators=(",", ":")) + ",")
    print('"""')
    print()
    print('_GOLDEN_V3_JSON = """\\')
    for row in _v3_rows():
        print(json.dumps(row, separators=(",", ":")) + ",")
    print('"""')
