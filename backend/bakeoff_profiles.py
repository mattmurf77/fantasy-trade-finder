"""Bake-off — arm definitions (docs/plans/three-model-bakeoff/PLAN.md).

Two profiles live here, and they are **not** variants of each other:

* **arm A** (`baseline`) — a pinned reconstruction of the PAST. D-075 makes
  it a constant; see below.
* **arm D** (`challenger`) — the landability challenger, a proposal about the
  FUTURE. See `MODEL_CHALLENGER_PROFILE` at the bottom of this module and
  docs/plans/landability-challenger/PRD.md.

The challenger was originally briefed as "the new arm A". It is not, and the
PRD rejects that framing explicitly (N1): arm A is the only fixed point the
bake-off has, and overwriting it makes every comparison unfalsifiable. The
challenger is a **fourth arm**. Nothing in arm A's half of this file may move
to accommodate it — if a change here touches `MODEL_A_PROFILE`, `model_a()`
or `MODEL_A_REFERENCE_SHA`, it is out of scope by construction.

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

    from backend.bakeoff_profiles import model_a, model_challenger
    with model_a():
        cards_A = svc.generate_trades(...)
    with model_challenger():
        cards_D = svc.generate_trades(...)

`model_a()` is the only supported entry point — it applies the config
profile *and* the R4 bypass together, because applying one without the other
produces a silently wrong arm A. `model_challenger()` deliberately has **no**
bypass; the R4 exclusion is arm A's, and the challenger keeps it.
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
    # Knockout refine C4 (D-159) — pinned at the IDENTITY value, not a kill
    # value: `> 1` is the pre-wave rule (92c31d5 trade_optimizer.py:507) and
    # the post-merge bundle moves the LIVE row to 2; an unpinned arm A would
    # silently enumerate 3-for-1 shapes the pre-wave engine could not build.
    "v3_shape_max_delta":        1.0,

    "pick_gap_frac":             0.0,   # R3 off
    "need_gate_min_value":       0.0,   # R5 off
    # Engine quality — 2026-08-18 wave (docs/plans/engine-quality/scope.md)
    "rank_div_min_frac":         0.0,   # C1 off
    "min_package_band":          0.0,   # C2 off
    "pick_pair_strip_frac":      0.0,   # C3 off
    "deck_headliner_cap":        0.0,   # C4 off
    "deck_give_headliner_cap":   0.0,   # C4b off
    "mismatch_confidence_damp":  0.0,   # C5 off
    # D-085 placement tier clamp — 2026-08-19. Post-reference-SHA, and it
    # changes the personal value map, so arm A must pin it off. (Belt and
    # braces: bakeoff_runner does not pass `placements`, so the clamp is
    # already inert on every arm — see the D-085 note in living-memory.)
    "placement_tier_clamp":      0.0,   # D-085 off
    # Package-math wave — 2026-08-21 (operator-approved fix, evidence
    # docs/reviews/2026-08-21-market-curve-comparison.md §3b). Post-dates
    # the reference SHA and changes generation, so arm A pins it at its
    # kill value; the pre-wave own-max package math is byte-identical at
    # this setting, so the golden stands un-recaptured (verified: 10/10
    # green with the pin in place). Companion knob `package_floor_cross`
    # is deliberately absent — _package_value_market never reads it while
    # the benchmark knob is ≤ 0 (same rule as `max_overpay_min_value`).
    "package_bench_trade_wide":  0.0,   # own-max benchmark (pre-fix math)
    # Same wave: the gap auto-sweetener post-dates the reference SHA; at
    # ≤ 0 every generator skips the pass entirely (byte-identical), and
    # the pre-wave engine had no sweetener.
    "sweetener_gap_threshold":   0.0,   # gap auto-sweetener off
    # Negative-results memory — 2026-08-22 (docs/plans/negative-results-
    # memory/LLD.md §3.4, HLD D-6). negmem post-dates the reference SHA and
    # its seam multiplies `composite_score` inside generation, so arm A pins
    # it at 0.0 — the documented byte-identical M1 disable. The other five
    # `negmem_*` knobs are deliberately absent: at strength 0.0
    # `negmem.effective_mult` returns exactly 1.0 before any of them is read
    # (they shape the map, not the gate), same rule as `package_floor_cross`.
    # M2 is NOT killed here: its strength is the global
    # `gen2_accept_prior_strength`, and an arm overlay pin is expressly not
    # the sanctioned M2 kill (HLD §5.3).
    "negmem_strength":           0.0,   # M1 seam off (pre-negmem engine)
    # Age-preference consensus multiplier — 2026-08-29 (docs/business/
    # analytics/2026-08-29-trade-disposition-review.md). Post-dates the
    # reference SHA and re-prices the consensus accessors (_vs/_sv/cval),
    # so arm A pins both mults at the IDENTITY value: age_pref_value
    # short-circuits at exactly 1.0 and the accessors are byte-identical,
    # so the golden stands un-recaptured. `age_pref_boost_cap` is
    # deliberately absent — it is never read while both mults are 1.0
    # (same rule as `package_floor_cross`).
    "age_pref_mult_u23":         1.0,   # age boost off (pre-wave pricing)
    "age_pref_mult_30plus":      1.0,   # age discount off
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


# ---------------------------------------------------------------------------
# Arm D — `challenger`, the landability challenger (D-095, 2026-08-19)
# ---------------------------------------------------------------------------
# Spec: docs/plans/landability-challenger/PRD.md §4 (the lever table is the
# authority on every value below). Evidence: the two-round, seven-agent audit
# in docs/reviews/2026-08-19-armb-audit-consolidated.md.
#
# Arm A reconstructs what the engine USED to do. This asks what it SHOULD do:
#
#     show trades two sides could both take — even on consensus, dual-surplus
#     on boarded pairs — and stop ranking the most lopsided star deal first.
#
# It is dark. `bakeoff_serve_interleaved` stays 0, so the arm generates,
# attributes and logs while users keep seeing arm `current` (PRD N3, G7).
#
# Three of the nine keys are new `_DEFAULT_CFG` knobs that default to the LIVE
# IDENTITY (see the D-095 block in backend/trade_service.py); the other six
# are existing knobs whose live defaults are untouched. Together that makes
# the arm a pure overlay: with the context unentered, nothing here is
# reachable and arm B is byte-identical.

#: Arm D. **Not** a replacement for `MODEL_A_PROFILE` — a fourth arm.
MODEL_CHALLENGER_PROFILE: dict[str, float] = {
    # ---- generation: which cards EXIST ------------------------------------
    # P2 — shrink neither board. Live shrinks the user toward consensus by
    # comparison count while using the partner's `elo_ratings` raw, and that
    # asymmetry is the boarded-pair one-sidedness (86.9%). Shrink-both needs
    # comparison counts on `member_rankings`, which do not exist (PRD N8).
    "user_elo_shrink":            0.0,
    # P3 — the lever that changes the 84.5% identity. Drops the consensus
    # `rv >= gv` sign test and opens 1-for-2 enumeration, so an even trade can
    # surface in the direction where the PARTNER is the one who gains.
    "consensus_both_ways":        1.0,
    # …and the brake that makes P3 safe. Both directions at the live 0.50
    # floor is a 2:1 user-pays flood; at 0.75 the worst either side can be out
    # is exactly 1 - 0.75 = 25%. Measured offline (C1): 0.75 both-ways yields
    # 200.5% of the one-way baseline's cards, 61.2% of them user-pays.
    "consensus_fairness_floor":   0.75,
    # R5 (#304, the user-need kill) OFF. It hard-kills laterals for
    # championship/contender users with no partner-need term at all — 1,778
    # shapes across 30 ordered pairs, 61 of them with DUAL `need_fit >= 0.75`.
    # Disabled rather than converted into a ranker: a partner-need ranker is
    # a design question this profile does not try to settle (PRD §4).
    # NB this is the ONE key that coincides with `MODEL_A_PROFILE`, and the
    # coincidence is meaningless — arm A zeroes it because R5 postdates its
    # reference SHA, arm D because R5 kills landable trades.
    "need_gate_min_value":        0.0,
    # ---- ranking: which cards LEAD ---------------------------------------
    # P1 — compress the tier ladder. On consensus `composite = fairness x
    # tier_mult x consensus_score_scale`, and because the sign test forces the
    # user ahead, `1 - fairness` IS the viewer's surplus fraction. Live spans
    # 4.57x (0.35 -> 1.60) against fairness's 2.00x, so the biggest name wins
    # regardless of balance: an elite card outranks a perfectly even solid one
    # at fairness 0.625, i.e. while taking 60% more than it gives. Measured
    # elite-band mean absolute viewer surplus 790 vs 78 for depth/bench.
    #
    # The challenger ladder spans 1.44x against a fairness-at-0.75 span of
    # 1.33x, which moves that crossover to fairness 0.870 — an elite card must
    # be near-even to lead. Tier still breaks ties; it no longer overrules.
    "tier_mult_elite":            1.15,
    "tier_mult_starter":          1.08,
    "tier_mult_solid":            1.00,
    "tier_mult_depth":            0.90,
    "tier_mult_bench":            0.80,
}


@contextmanager
def model_challenger():
    """Run the enclosed generation as arm D (`challenger`).

    Thread-local, exactly like `model_a()`: concurrent trade jobs on sibling
    daemon threads are untouched, and `trade_optimizer` (v3) reads `_c` from
    `trade_service`, so the v3 optimizer honours the profile too.

    **No R4 bypass.** Arm A bypasses the windowless awaiting/matched exclusion
    because R4 postdates its reference SHA and has no kill knob. The
    challenger has no such excuse: it is the live engine under an overlay, and
    re-serving a trade the user already has pending is not a more landable
    trade. `r4_bypassed()` must stay False inside this context — asserted in
    backend/tests/test_bakeoff_challenger.py.
    """
    with _cfg_override(MODEL_CHALLENGER_PROFILE):
        yield
