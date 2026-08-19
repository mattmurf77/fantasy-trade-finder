"""Three-model bake-off — arm definitions (docs/plans/three-model-bakeoff/PLAN.md).

Arm **A** (`baseline`) is the trade engine as it behaved *before* the
2026-08-16 G6 presentment wave and the 2026-08-18 engine-quality wave. The
original logic was modified **in place**, never forked, so "original" exists
only as a set of knob kill-values plus one flag bypass. That set is pinned
here, as a constant, and golden-tested in
`backend/tests/test_bakeoff_arm_a_golden.py` against output captured at
`MODEL_A_REFERENCE_SHA`.

Without the pin + the golden, arm A silently becomes "whatever the knobs
happen to mean today" every time someone adds a knob, and the bake-off
becomes unfalsifiable with no visible symptom. Two tests defend it:

* the golden — arm A's deck on a literal fixture must equal the pre-wave
  deck, byte for byte;
* the knob inventory — adding any key to `trade_service._DEFAULT_CFG` fails
  a test until someone decides, in writing, whether arm A must disable it.

Arms B (`current`, live defaults) and C (`gen_v2`) need no profile: B is the
absence of one, C is a separate module.

Usage (Phase 3's runner)::

    from backend.bakeoff_profiles import model_a
    with model_a():
        cards_A = svc.generate_trades(...)

`model_a()` is the only supported entry point — it applies the config
profile *and* the R4 bypass together, because applying one without the other
produces a silently wrong arm A.
"""

from __future__ import annotations

from contextlib import contextmanager

from .trade_service import _cfg_override, r4_bypass

#: The commit immediately BEFORE the G6 wave (`20b40db`) landed on main —
#: `git log --first-parent main`. Arm A's golden was captured here.
MODEL_A_REFERENCE_SHA = "92c31d5"

#: Pinned 2026-08-18. **DO NOT edit without re-capturing the golden.**
#: Every key is a post-reference-SHA generation knob at its documented
#: disable value. Companion knobs (`max_overpay_min_value`,
#: `pick_gap_min_value`, `need_gate_upgrade_margin`) are deliberately absent:
#: their predicates return early at the kill value above and never read them.
#: Exclusions and their reasons are recorded in
#: docs/plans/three-model-bakeoff/scope-phase2.md § Scope.
MODEL_A_PROFILE: dict[str, float] = {
    # G6 presentment rules — 2026-08-16 wave (#340 #341 #339 #304)
    "max_overpay_frac":          0.0,   # R1 off
    "pos_net_cap":               0.0,   # R2 off
    "pick_gap_frac":             0.0,   # R3 off
    "need_gate_min_value":       0.0,   # R5 off
    # Engine quality — 2026-08-18 wave (docs/plans/engine-quality/scope.md)
    "rank_div_min_frac":         0.0,   # C1 off
    "min_package_band":          0.0,   # C2 off
    "pick_pair_strip_frac":      0.0,   # C3 off
    "deck_headliner_cap":        0.0,   # C4 off
    "deck_give_headliner_cap":   0.0,   # C4b off
    "mismatch_confidence_damp":  0.0,   # C5 off
}


@contextmanager
def model_a():
    """Run the enclosed generation as arm A (`baseline`).

    Thread-local, like the `_cfg_override` it wraps: concurrent trade jobs on
    sibling daemon threads are untouched, and `trade_optimizer` (v3) reads
    `_c` from `trade_service`, so the v3 optimizer honours the profile too.
    """
    with _cfg_override(MODEL_A_PROFILE), r4_bypass():
        yield
