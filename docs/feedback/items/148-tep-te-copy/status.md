# #148 — SF-TEP TE rankings copied from 1QB demote TEs — status

**State:** built + tested (2026-07-17, branch `trade-engine-v2`). Seed-layer
fix, grouped with **#145** (the KTC blend) — both live in the consensus-seed
layer. Batch/build notes live in the lowest-ID folder:
`docs/feedback/items/145-ktc-blend/status.md`.

**Owner ask:** "SF TEP TE rankings copied from 1QB doesn't copy right — TEs
downgraded; they should be slightly upgraded (worth more)."

## Investigation → root cause

Compared DP `value_1qb` vs `value_2qb` for TEs on the real snapshot. DP's
`value_2qb` column is **plain superflex — it carries no tight-end premium**,
and worse, superflex compresses all non-QB values (QBs soak up the top), so
DP sf TE values sit ~25–30% *below* their 1QB analogs (e.g. 2026-07-10
snapshot TE1: 1qb 5849 vs sf 4506 = 0.77×). Our format is **sf_TEP** (TE
premium), not plain superflex — so plain `value_2qb` is the wrong source for
TEs. When a user copied a 1QB board to SF-TEP, the #124 `value_rank` remap
re-seeded each TE from the target format's (too-low) sf consensus and demoted
them. That is the reported bug — a *source* gap, not a copy-logic bug.

KTC verification: KTC exposes a TEP toggle; the accessible page data includes
`superflexValues.tep` (the TE-premium variant), which #145's blend already
uses for `sf_tep`. KTC's own TEP effect is ≈ +11% — real but not enough to
lift sf TEs above 1QB given SF's non-QB compression.

## Fix

`tep_te_uplift` (model_config, default **1.18**) — a multiplier applied to TE
values in `sf_tep` **only**, after the KTC blend, in
`data_loader._apply_consensus_blend`. Calibrated from evidence so the top-8
sf_tep TE seeds clear their 1QB analogs at the default blend weight (KTC's
+11% TEP + the uplift jointly overcome the DP plain-SF gap). Result: SF-TEP
TEs read as *slightly* upgraded (top-8 ratios 1.02–1.24), matching the
operator's expectation. `tep_te_uplift = 1` disables it.

### Before / after — top TEs (2026-07-17 pool, w=0.5)

| TE | blended 1qb | sf-TEP (uplift 1.18) | sf/1qb | tier 1qb → sf_tep |
|---|---|---|---|---|
| Brock Bowers | 7519 | 7855 | 1.05 | firsts_3 → firsts_3 |
| Trey McBride | 6714 | 7461 | 1.11 | firsts_2 → firsts_3 |
| Colston Loveland | 5451 | 5574 | 1.02 | firsts_2 → firsts_2 |
| Tyler Warren | 4699 | 5102 | 1.09 | first_1 → firsts_2 |
| Tucker Kraft | 3194 | 3932 | 1.23 | first_1 → first_1 |

(DP-only, uplift off: sf TE1 4506 < 1qb TE1 5849 — the demotion. Pinned by
`test_uplift_off_leaves_sf_tep_te1_below_1qb`.)

## Copy-level pin

`test_copy_1qb_to_sf_tep_does_not_demote_top_te` drives the #124 `value_rank`
remap (`RankingService.apply_value_map`) on a 1QB→SF-TEP copy and asserts the
top TE's SF-TEP tier is **no worse** than its 1QB tier — the operator's
expectation now holds end-to-end.

## Files

Same source change as #145 (`backend/data_loader.py`,
`backend/database.py` default), plus the #148 pins in
`backend/tests/test_ktc_blend.py`. Knob documented in
`docs/config-reference.md` → Consensus seed blend.
