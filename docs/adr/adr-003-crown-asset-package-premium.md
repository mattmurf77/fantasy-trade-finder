# ADR-003 — Crown-Asset Package Premium

**Status:** Accepted (shipped dark)
**Date:** 2026-06-11
**Initiative:** Competitor backlog #10 (docs/plans/competitor-top20/10-key-asset-package-adjustment.md); closes the trade-engine-v2 "1-for-1 fairness-gate / package-discount" watch item (memory: project_ftf_trade_engine_v2).

---

## Context

The v2 engine handled only *half* of the package-asymmetry problem. `package_value_v2` (amendment A2) discounts the **depth** side — each asset contributes `v · (0.15 + 0.85 · (v/v_max)^γ)`, so lesser assets bottom out at 15% of raw value ("four quarters ≠ a dollar"). What no path had was the **premium** side: in an N-for-1, the single consolidated asset is worth *more* than its sticker price because consolidation is scarce.

Two independent competitors converge on the same fix (docs/competitor-teardown-web-tools.md): FPTrack's **Crown Asset** boost ("best asset gains value in 1-for-many deals") and Dynasty Daddy's **Value Adjustment** ("I wanted to make sure the fair trades weren't splitting a dollar into 100 pennies… the formula takes into consideration who is the key player and what proportion of the trade he accounts for"). The recorded resolution for the watch item was explicitly "explicit multiplier, not a hard gate."

## Decision

Add a crown premium to `package_value_v2`, gated by `trade.crown_asset` (default false).

1. **Premium shape.** The top asset of a side gains `crown_rate · max(0, share − floor)/(1 − floor)` on its base contribution, where `share = v_top / Σ(side raw values)`. Monotone in share, zero at/below `crown_share_floor`. Defaults `crown_rate=0.12`, `crown_share_floor=0.50` (both `model_config`-tunable).

2. **Neutral on equal-count trades by construction.** The premium fires **only when the side has fewer assets than the other side** (`len(values) < n_other`). Callers pass the opposing side's count via a new optional `n_other` param. This makes 1-for-1, 2-for-2, etc. byte-identical to flag-off — closing the gap raised in the plan's open question 3 (a pure per-side share would have fired on a 1-for-1, where both sides sit at share=1.0, scaling both surpluses and changing the gate). The count guard is the cleanest formulation that satisfies both the fairness-ratio neutrality *and* the surplus neutrality the acceptance criteria demand.

3. **Backward-compatible signature.** `package_value_v2(values, v_max, n_other=None)`. `n_other=None` (the default, and every unmigrated/legacy caller) → no crown, ever. Only the v2 divergence, consensus, and v3 call sites were migrated to pass `n_other`; the legacy `package_value` path is untouched.

4. **Top-asset-only, raw-share based** (plan open questions 1 & 2). The premium boosts the single crown asset (FPTrack's model, more explainable for the #20 transparency page) rather than reweighting the whole side (Dynasty Daddy's). Share is computed on the side's values in whatever space the call uses (consensus for fairness, user/opp/marginal for surpluses) — consistent within each space.

5. **Ship dark, tune with telemetry** (plan open question 4, operator-confirmed). The constants are reasonable placeholders, not calibrated values. The watch item couples `fairness_threshold`, `package_adj_gamma`, and now `crown_rate` to real `trade_impressions` data; all three are tuned together once telemetry volume lands (`GET /api/admin/engine-metrics`, shape breakdown by 1-1 / 2-1 / 3-2). A standalone calibration sweep script is deferred until there is decision data to calibrate *against* — building one now would optimize against synthetic fixtures only.

## Consequences

- **Positive:** Asymmetric-count trades price the way the market (KTC/FPTrack/Dynasty Daddy) adjudicates them; fewer "quantity-beats-quality" steals surface; the long-standing watch item is closed with a tunable knob. Provably zero blast radius when off or on symmetric trades.
- **Negative / watch:** A third coupled tuning knob before rich telemetry. Mitigated by the kill switch (flag off restores exact prior math) and by keeping all three knobs independently live-tunable in `model_config`. Sweetener-band classification (`sweetener_band` is relative to `fairness_threshold`, which crown shifts on asymmetric trades) should be re-checked when the flag is enabled.
- `fairness_score` values move on asymmetric cards when enabled; shape is unchanged (still a 0–1 ratio), so no client change. Documented in config-reference.

## Alternatives considered

- **Pure per-side share, no count guard** (plan's original proposal): rejected — fires on 1-for-1 and fails the surplus-neutrality acceptance criterion.
- **Crown only in the consensus fairness gate** (smaller blast radius): viable fallback, but applying it consistently across fairness + both surplus spaces keeps the engine coherent and was provably safe via the count guard + flag.
- **Whole-side reweight (Dynasty Daddy style):** deferred to calibration; top-asset-only is simpler to explain and tune first.

## References

- Plan: docs/plans/competitor-top20/10-key-asset-package-adjustment.md
- Teardown: docs/competitor-teardown-web-tools.md (FPTrack Value Boosts, Dynasty Daddy Value Adjustment)
- Tests: backend/tests/test_crown_asset.py (unit precision + 1-for-1 neutrality + N-for-1 effect)
- Config: docs/config-reference.md (`trade.crown_asset`, `crown_rate`, `crown_share_floor`)
- Prior art: ADR-002 (v2/v3 rebuild, `package_value_v2` origin)
