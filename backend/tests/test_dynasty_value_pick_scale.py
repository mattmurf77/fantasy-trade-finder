"""Regression tests for the pick-value scale bridge in dynasty_value().

Background (docs/plans/competitor-top20/15-pick-capital-dashboard.md,
Open question 1): compute_pick_value() stores draft_picks.pick_value on a
0-100 round-tier scale (mid-1st = 67.5), but dynasty_value's PICK branch
used to return that number raw while its docstring claimed a 0-10000
scale — so any PICK pseudo-player reaching trade math priced near zero.
The fix bridges pick_value into the shared value space via the same
calibration the universal pool's generic picks use:

    seed_elo = 1200 + 6 * pick_value   (inverse of server.build_universal_pool)
    value    = elo_to_value(seed_elo)
"""
from dataclasses import dataclass

from backend.database import compute_pick_value
from backend.trade_service import dynasty_value, elo_to_value


@dataclass
class _Pick:
    """Minimal PICK pseudo-player (only the attrs dynasty_value reads)."""
    position: str = "PICK"
    pick_value: float | None = None
    search_rank: int | None = None


def test_mid_first_prices_like_its_generic_pool_twin():
    # The universal pool seeds "Mid 1st" at Elo 1650 with
    # pick_value = (1650 - 1200) / 6 = 75. A league pick carrying that
    # same pick_value must price identically (plan #15 FR4).
    assert dynasty_value(_Pick(pick_value=75.0)) == round(elo_to_value(1650.0), 1)


def test_compute_pick_value_output_no_longer_near_zero():
    # A 12-team mid 2026 1st: compute_pick_value → 67.5. Before the fix
    # dynasty_value returned 67.5 raw — bench-scrap territory in a value
    # space where startable players sit in the thousands.
    pv = compute_pick_value(1, 2026, 2026, league_size=12)
    assert pv == 67.5  # producer scale unchanged
    v = dynasty_value(_Pick(pick_value=pv))
    assert v == round(elo_to_value(1200.0 + 6.0 * pv), 1)
    assert v > 1000.0  # a 1st-round pick outprices a replacement-level asset


def test_future_pick_discount_survives_the_bridge():
    # 2027 1st (one year out) is worth less than the 2026 1st but still
    # far from zero — the year discount must stay meaningful post-bridge.
    v_now    = dynasty_value(_Pick(pick_value=compute_pick_value(1, 2026, 2026)))
    v_future = dynasty_value(_Pick(pick_value=compute_pick_value(1, 2027, 2026)))
    assert 0 < v_future < v_now
    assert v_future > 1000.0


def test_round_ordering_preserved():
    # 1st > 2nd > 3rd > 4th after the transform (monotone bridge).
    vals = [
        dynasty_value(_Pick(pick_value=compute_pick_value(r, 2026, 2026)))
        for r in (1, 2, 3, 4)
    ]
    assert vals == sorted(vals, reverse=True)


def test_missing_pick_value_falls_back_to_neutral_1000():
    # Pre-fix fallback returned 1000.0 for a PICK with no pick_value;
    # that exact behavior is preserved (= elo_to_value at reference Elo).
    assert dynasty_value(_Pick(pick_value=None)) == 1000.0
    assert dynasty_value(_Pick(pick_value=0)) == 1000.0
