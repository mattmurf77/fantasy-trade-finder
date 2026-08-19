"""D-079 — per-round draft-pick year decay.

Operator symptom, prod `trade_pass_reasons` 2026-08-19T03:48:53Z (user
313560442465169408, league 1312140920132497408):

    "I think 2029 1st values are the issue. Adams is rated as a 3rd for me.
     Offering him for a 1st is nonsense so it must be how value is assigned
     for a pick so far out."

…and, 2026-08-17T23:43:06Z, the same tester: "1st round picks seem
undervalued." The card behind it is impression `c67c2fd1e97cb6bf` (served
2026-08-19T03:42:09Z): give Davante Adams (`give_value` 1138.8), receive one
2029 1st (`receive_value` 1300.1).

Root cause: `pick_values` applied ONE year discount — 0.85/yr — to every
round, so a 2029 1st priced at 61.4 % of a 2026 1st (2117.0 → 1300.1). Two
consequences, both reported:

  1. a far-out 1st fell to roughly a good-but-not-great player's value, so
     "player for a 2029 1st" cleared the presentment gates;
  2. two 1sts of different years became *different-valued copies of the same
     asset*, which is a pure year arbitrage — 99 of 2048 served cards moved a
     1st one way and a different-year 1st the other ("Still seeing pick
     swaps"; "Another example of a random 1st swap. Shouldn't happen").

Fix (operator direction 2026-08-19: "firsts should hold similar value YOY.
Other picks can degrade the longer away they are"): the rate is per round and
config-driven — `pick_year_decay_r{1..4}`, round 1 flat at 1.0, rounds 2-4 at
the shipped 0.85.

Full analysis, external calibration and the sources that DISAGREE with the
round-1 call: docs/reviews/2026-08-19-pick-year-valuation.md.
"""
import pytest

import backend.trade_service as ts
import backend.pick_values as pv
from backend.database import compute_pick_value
from backend.pick_values import (GENERIC_PICK_SEEDS, YEAR_DISCOUNT,
                                 discount_pick_value, pick_pool_value,
                                 year_decay, year_decay_key)


@pytest.fixture(autouse=True)
def _isolate_cfg():
    """Every test here reads live config; restore it so a knob override in
    one test cannot leak into the rest of the suite."""
    old = dict(ts._cfg)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ts._cfg.clear()
        ts._cfg.update(old)


# ── the rate itself ────────────────────────────────────────────────────────

def test_default_rates_are_flat_firsts_and_decaying_rest():
    assert year_decay(1) == 1.0
    assert year_decay(2) == year_decay(3) == year_decay(4) == YEAR_DISCOUNT


def test_deep_rounds_clamp_onto_round_four():
    # `pick_pool_value` already clamps a round-9 pick onto the (4,'Mid') seed;
    # the rate has to clamp the same way or a 5th would price off a rate that
    # does not exist and fall back to a default nobody set.
    assert year_decay_key(9) == "pick_year_decay_r4"
    assert year_decay(9) == year_decay(4)
    assert year_decay_key(0) == "pick_year_decay_r1"
    assert year_decay(0) == year_decay(1)


def test_rate_is_read_live_from_config():
    ts._cfg["pick_year_decay_r1"] = 0.5
    assert year_decay(1) == 0.5
    assert pick_pool_value(1, 1) == pytest.approx(
        pick_pool_value(1, 0) * 0.5, abs=0.1)


def test_rate_is_clamped_to_unit_interval():
    # >1 would make a further-out pick worth MORE, re-opening the arbitrage
    # in the other direction; <0 is meaningless.
    ts._cfg["pick_year_decay_r1"] = 1.4
    assert year_decay(1) == 1.0
    ts._cfg["pick_year_decay_r1"] = -0.2
    assert year_decay(1) == 0.0


def test_all_rates_at_the_old_constant_reproduce_the_old_behaviour():
    """The deploy-free revert lever. Setting all four back to 0.85 must
    restore the pre-D-079 ladder exactly, on BOTH value scales."""
    for r in (1, 2, 3, 4):
        ts._cfg[f"pick_year_decay_r{r}"] = YEAR_DISCOUNT
    base = pick_pool_value(1, 0)
    assert pick_pool_value(1, 3) == pytest.approx(
        base * YEAR_DISCOUNT ** 3, abs=0.1)
    assert pick_pool_value(1, 3) == pytest.approx(1300.1, abs=0.5)  # the bug
    assert compute_pick_value(1, 2027, 2026, league_size=12) == 57.38


# ── the reported defect ────────────────────────────────────────────────────

def test_a_2029_first_prices_exactly_like_a_2027_first():
    """The operator's sentence, as an assertion."""
    assert pick_pool_value(1, 3) == pick_pool_value(1, 1)
    assert pick_pool_value(1, 3) == pick_pool_value(1, 0)
    assert pick_pool_value(1, 0) == round(
        ts.elo_to_value(GENERIC_PICK_SEEDS[(1, "Mid")]), 1)


def test_later_rounds_still_decay_and_stay_ordered():
    for rnd in (2, 3, 4):
        assert pick_pool_value(rnd, 3) < pick_pool_value(rnd, 0)
    # and the round ordering survives at every horizon — a far-out 1st must
    # never fall below a near 2nd, which is what let the swaps happen.
    for years in range(0, 5):
        vals = [pick_pool_value(r, years) for r in (1, 2, 3, 4)]
        assert vals == sorted(vals, reverse=True)
        assert pick_pool_value(1, years) > pick_pool_value(2, 0)


def test_no_year_arbitrage_between_two_firsts():
    """The 'random 1st swap' complaint: swapping a 1st for a 1st of any other
    year must move exactly zero value, so the optimizer sees no edge in it."""
    vals = {y: pick_pool_value(1, y) for y in range(0, 6)}
    assert len(set(vals.values())) == 1
    for a in vals:
        for b in vals:
            assert vals[a] - vals[b] == 0


def test_adams_no_longer_clears_the_overpay_gate_against_a_2029_first():
    """Regression for impression c67c2fd1e97cb6bf (prod, 2026-08-19).

    Adams's consensus value that day was 1138.8 (`player_value_history`,
    player 2133, 1qb_ppr, 2026-08-19). The gate is `trade_service.overpay_ok`
    (R1 #340): kill when gap >= max_overpay_min_value AND gap/max(side) >=
    max_overpay_frac. This asserts the GATE's verdict flips, not just that a
    number moved — the number moving is only interesting because it changes
    what gets served.
    """
    adams = 1138.8
    seed_value = lambda pid: {"adams": adams,
                              "pick": pick_pool_value(1, 3)}[pid]

    # After D-079: 2117.0 vs 1138.8 → gap 978.2, 46 % of the big side. Killed.
    assert not ts.overpay_ok(["adams"], ["pick"], seed_value)

    # Before D-079: 1300.1 vs 1138.8 → gap 161.3, under the 500 floor. Served.
    for r in (1, 2, 3, 4):
        ts._cfg[f"pick_year_decay_r{r}"] = YEAR_DISCOUNT
    assert ts.overpay_ok(["adams"], ["pick"], seed_value)


# ── the rate reaches every pricing scale ───────────────────────────────────

def test_legacy_compute_pick_value_is_on_the_same_rate():
    # Two value scales, one clock — the reason the ladder lives in
    # pick_values and not in database.py.
    assert compute_pick_value(1, 2029, 2026) == compute_pick_value(1, 2026, 2026)
    assert compute_pick_value(2, 2029, 2026) < compute_pick_value(2, 2026, 2026)


def test_rung_relabel_discount_is_round_aware():
    # `discount_pick_value` takes the rung's round since D-079; a 1st rung is
    # an exact no-op, a 2nd rung still moves.
    pv_1 = round((GENERIC_PICK_SEEDS[(1, "Early")] - 1200) / 6, 1)
    pv_2 = round((GENERIC_PICK_SEEDS[(2, "Mid")] - 1200) / 6, 1)
    assert discount_pick_value(pv_1, 1, 1) == pv_1
    assert discount_pick_value(pv_1, 4, 1) == pv_1
    assert discount_pick_value(pv_2, 1, 2) < pv_2
    # years_out=0 stays an exact no-op for every round (the not-drafted path)
    for rnd in (1, 2, 3, 4):
        assert discount_pick_value(pv_2, 0, rnd) == pv_2


def test_year_decay_falls_back_to_defaults_without_config(monkeypatch):
    """`pick_values` is imported by `database`, which must stay usable when
    the config table is unreachable. A raising `_c` must not take pricing
    down with it."""
    def _boom(_key):
        raise RuntimeError("no db")
    monkeypatch.setattr(ts, "_c", _boom)
    assert year_decay(1) == pv.PICK_YEAR_DECAY_DEFAULTS[1]
    assert year_decay(3) == pv.PICK_YEAR_DECAY_DEFAULTS[3]
