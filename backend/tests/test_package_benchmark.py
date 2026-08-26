"""2026-08-21 cross-package benchmark fix — the Nacua regression + shape pins.

Evidence base: docs/reviews/2026-08-21-market-curve-comparison.md §3b. The
served defect: `_package_value_market` benchmarked every piece of a package
against the package's OWN best asset (floor 0.70 / γ 0.5, discount capped at
35%), so four similar mid-tier players took a ~5% haircut while buying a
stud. The operator's served card — Rashee Rice + Travis Etienne + D'Andre
Swift + Blake Corum → Puka Nacua — scored fairness 0.939 (inside the ±15%
serve band) while FantasyCalc priced the same package at 1.362× Nacua and
KTC at 2.260× (both: wild overpay, never build it).

The fix (`package_bench_trade_wide`, default ON): a multi-asset side that
does NOT hold the trade's best asset is benchmarked against the TRADE's best
asset, at `package_floor_cross`. Arm A pins the knob at 0.0 — the pre-fix
own-max math must remain byte-identical at the kill value (that is what lets
the arm-A golden stand un-recaptured).

Golden hygiene: every input below is a LITERAL. The five player values are
pinned to reproduce the served card's shape (naive ratio 1.057, legacy
served ratio ≈ 0.94) rather than read from any board pipeline, so this file
is immune to board drift by construction.
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import package_value_v2

# ── the pinned card (value space, literals) ───────────────────────────────
# Four mids for the stud. Values chosen to reproduce the served card's
# measured shape: naive give sum 8178 vs Nacua 7737 → naive ratio 1.057,
# exactly the memo's served number.
NACUA = 7737.0
RICE, ETIENNE, SWIFT, CORUM = 2807.0, 2318.0, 1874.0, 1179.0
GIVE = [RICE, ETIENNE, SWIFT, CORUM]

#: The serve band: mobile default fairness_threshold (±15%).
SERVE_THRESHOLD = 0.85


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.crown_asset": True}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _ratio(give_vals, recv_vals):
    """The consensus fairness ratio exactly as every generator prices it:
    package_value_v2 per side with the trade-wide best asset."""
    v_max = max(give_vals + recv_vals)
    gv = package_value_v2(give_vals, v_max, n_other=len(recv_vals),
                          other_values=recv_vals)
    rv = package_value_v2(recv_vals, v_max, n_other=len(give_vals),
                          other_values=give_vals)
    return min(gv, rv) / max(gv, rv)


# ── the regression ────────────────────────────────────────────────────────

def test_nacua_4for1_no_longer_serves():
    """THE card. Under the fix the package-adjusted fairness must fall OUT
    of the serve band — the whole point of the change."""
    ratio = _ratio(GIVE, [NACUA])
    assert ratio < SERVE_THRESHOLD, (
        f"4-mids-for-stud prices at {ratio:.3f} — back inside the serve "
        f"band. The cross-package benchmark fix has regressed.")
    # And it lands in the market's neighbourhood: FantasyCalc says 0.734,
    # the pre-#214 heavy shape said 0.692. Anywhere near there is market-
    # correct; drifting back above 0.80 means the discount is eroding.
    assert ratio < 0.80


def test_nacua_4for1_served_under_legacy_benchmark():
    """Non-vacuity: at the arm-A kill value the SAME literals reproduce the
    defect — the card prices inside the serve band, exactly as prod served
    it on 2026-08-21. If this fails the fixture no longer models the
    defect and the regression above proves nothing."""
    ts._cfg["package_bench_trade_wide"] = 0.0
    ratio = _ratio(GIVE, [NACUA])
    assert ratio >= SERVE_THRESHOLD
    assert ratio == pytest.approx(0.95, abs=0.02)   # memo: served 0.939


# ── kill-value byte-identity (what arm A's pin relies on) ─────────────────

def test_kill_value_is_byte_identical_to_pre_fix_math():
    """At package_bench_trade_wide ≤ 0 the function must reproduce the
    pre-fix own-max math bit for bit, for every shape — including ones
    where the fix would have changed the answer."""
    cases = [
        (GIVE, [NACUA]),
        ([4000.0, 2000.0], [9000.0]),
        ([1000.0, 900.0, 900.0, 900.0], [9000.0]),
        ([6500.0, 3000.0], [9000.0]),
    ]
    for vals, other in cases:
        v_max = max(vals + other)
        ts._cfg["package_bench_trade_wide"] = 0.0
        legacy = package_value_v2(vals, v_max, n_other=len(other),
                                  other_values=other)
        # Hand-derived own-max shape (floor .70, γ .5, cap, crown):
        own = max(vals)
        floor, gamma = 0.70, 0.5
        contrib = sum(v * (floor + (1 - floor) * (v / own) ** gamma)
                      for v in vals)
        expected = max(contrib, sum(vals) * 0.65)
        naive, o_naive = sum(vals), sum(other)
        skew = abs(naive - o_naive) / min(naive, o_naive)
        phase = max(0.0, 1.0 - skew / 0.5)
        if phase > 0:
            expected += sum(v for v in vals if v >= 6000.0) * 0.08 * phase
        assert legacy == pytest.approx(round(expected, 1), abs=0.05)


# ── surgical scope: what the fix must NOT touch ───────────────────────────

def test_single_asset_side_still_never_discounted():
    """A lone asset below the trade's best keeps full face value — 1-for-1
    fairness is untouched by the fix (the exemption is len > 1)."""
    ts._cfg["crown_rate_market"] = 0.0
    v = package_value_v2([3000.0], 9000.0, n_other=1, other_values=[9000.0])
    assert v == pytest.approx(3000.0, rel=1e-6)


def test_side_holding_trade_best_keeps_own_max_math():
    """The consolidating side (stud + filler) already benchmarks against
    its own headliner == the trade max; the fix changes nothing there."""
    ts._cfg["crown_rate_market"] = 0.0
    vals = [9000.0, 2000.0]
    fixed = package_value_v2(vals, 9000.0, n_other=1, other_values=[7000.0])
    ts._cfg["package_bench_trade_wide"] = 0.0
    legacy = package_value_v2(vals, 9000.0, n_other=1, other_values=[7000.0])
    assert fixed == legacy


def test_cross_bench_side_is_discounted_harder_than_own_max():
    """Directionality: the stud-buying package is worth strictly less under
    the trade-wide benchmark than under its own-max benchmark."""
    ts._cfg["crown_rate_market"] = 0.0
    v_max = max(GIVE + [NACUA])
    fixed = package_value_v2(GIVE, v_max, n_other=1, other_values=[NACUA])
    ts._cfg["package_bench_trade_wide"] = 0.0
    legacy = package_value_v2(GIVE, v_max, n_other=1, other_values=[NACUA])
    assert fixed < legacy


def test_discount_cap_still_floors_the_side():
    """package_discount_cap still bounds the total discount under the
    cross benchmark — junk-stuffing protection is unchanged."""
    ts._cfg["crown_rate_market"] = 0.0
    vals = [500.0, 450.0, 450.0, 450.0]
    naive = sum(vals)
    v = package_value_v2(vals, 9000.0, n_other=1, other_values=[9000.0])
    assert v == pytest.approx(round(naive * 0.65, 1), abs=0.05)


def test_cross_floor_knob_moves_the_cross_side_only():
    """package_floor_cross is read only on the cross-benchmarked path."""
    ts._cfg["crown_rate_market"] = 0.0
    v_max = max(GIVE + [NACUA])
    base = package_value_v2(GIVE, v_max, n_other=1, other_values=[NACUA])
    ts._cfg["package_floor_cross"] = 0.70
    softer = package_value_v2(GIVE, v_max, n_other=1, other_values=[NACUA])
    assert softer > base
    # …and the own-max path never reads it:
    ts._cfg["package_floor_cross"] = 0.10
    a = package_value_v2([9000.0, 2000.0], 9000.0, n_other=1,
                         other_values=[7000.0])
    ts._cfg["package_floor_cross"] = 0.90
    b = package_value_v2([9000.0, 2000.0], 9000.0, n_other=1,
                         other_values=[7000.0])
    assert a == b
