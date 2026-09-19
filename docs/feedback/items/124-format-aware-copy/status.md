# #124 + #139 — Value-aware cross-format copy

**Status:** built + tested, 2026-07-17 (branch `trade-engine-v2`)
**Items (owner mattmurf77):**
- **#124** — "Copying the tier list from SF to the 1QB or 1QB to SF should be adjusted up or down during the copy (4+1st in SF doesn't = 4+ 1sts [in 1QB])"
- **#139** — "The copy list feature should prompt the player to map 1st round pick values (the tier labels) from SF to PPR or vice versa."

## What was wrong

`POST /api/tiers/copy-from-format` preserved each player's **tier label**
(+ within-tier rank) across formats. Since #117 the tier labels are
pick-denominated ("worth 4+ 1sts"), so a label-preserving copy asserts the
player is worth the same draft capital in both formats — false, and worst
for QBs: the SF QB premium doesn't exist in 1QB. SF→1QB copies overvalued
QBs by up to two tiers; 1QB→SF undervalued them symmetrically.

## Mapping chosen: rank-preserving re-seed from target consensus (`value_rank`)

For each position, the copy now:

1. Reads the source board in the user's rank order (every visibly-tiered
   player via `get_rankings()`, override or not — keeps the Kyler-Murray
   seed-tiered-player fix).
2. Wholesale-clears the target format's overrides (unchanged "copy =
   overwrite" semantics).
3. Deals out the copied group's **own target-format consensus seed Elos**,
   sorted desc, to the user's rank order — rank 1 gets the group's highest
   target seed, rank 2 the next, etc.
   (`RankingService.apply_value_map`, new.)

**Why this mapping**

- It is `apply_reorder`'s proven permutation trick (FB #60/#69, "44 elite
  QBs") pointed at the target seed distribution: order comes from the
  user, magnitudes come from the target format's consensus, so the convex
  value curve is never flattened and target tier occupancy ≈ target
  consensus occupancy.
- Ordinal user opinions survive exactly (a QB pinned above consensus stays
  above consensus in the target); only the *pricing* re-expresses.
- QBs move most between SF↔1QB because the two DP seed curves differ most
  at QB — which is precisely the #124 ask. WR/RB/TE curves are similar, so
  they barely move.
- Deterministic + idempotent: re-copying an unchanged source board yields
  identical target overrides. A copied player may fall below the target
  waivers floor and render unranked (correct — a board-worthy SF QB2x can
  be waiver fodder in 1QB).
- Rejected alternatives: percentile/linear interpolation into target bands
  (distorts the convex curve — the exact failure `apply_reorder` was
  rewritten to avoid); copying effective target Elos (mixes in the target
  swipe history the user asked to overwrite; non-deterministic to test).

**Example (DP 2026-07-10 snapshot, consensus order):**

| Asset | SF seed → tier | after SF→1QB copy → tier |
|---|---|---|
| QB1 | 1927 → 4+ 1sts | 1854 → 2 1sts (−2 rungs) |
| QB2 | 1908 → 3 1sts | 1810 → 2 1sts |
| QB5 | 1881 → 3 1sts | 1768 → 1st (−2 rungs) |
| WR1 | 1909 → 3 1sts | 1927 → 4+ 1sts (≈ steady/up) |

Cross-position: SF's top asset (QB1) correctly drops **below** the elite
WRs after copying to 1QB; the reverse copy promotes him back above them.

## Prompt (#139)

Mobile TiersScreen copy button now confirms with remap-explaining copy:
"Values will be adjusted to `<target>` pick values: players keep your
`<source>` rank order at each position, but tiers are re-set to what each
rank is worth in `<target>` — QBs shift the most." + destructive REPLACE
warning. **No "copy as-is" secondary**: a verbatim tier-label copy is
exactly the mispricing #124 reported, so offering it would keep the
footgun. Remap always, stated plainly.

## Files

- `backend/ranking_service.py` — new `RankingService.apply_value_map(position, ordered_ids)`
- `backend/server.py` — `copy_tiers_from_format_route` rewritten to rank-collect + value-map; response gains additive `mapping: 'value_rank'`
- `mobile/src/screens/TiersScreen.tsx` — confirm dialog rewritten (copy-flow region only); success toast "Copied N players — values adjusted"
- `mobile/src/api/league.ts` — contract comment + `mapping?` on `CopyTiersResponse`
- `backend/tests/test_copy_from_format.py` — NEW, 15 tests
- Docs: `docs/api-reference.md` (route row added — was previously undocumented), `docs/glossary.md` ("Value-aware copy (`value_rank` mapping)")

## Tests

- `python3 -m pytest backend/tests/ -q` → **609 passed** (15 new: unit
  `apply_value_map` — permutation, user-order-beats-consensus, epsilon
  tie-break, unknown-id skip, empty no-op; route — contract/counts,
  SF→1QB QB demotion incl. cross-position flip vs WRs, 1QB→SF QB
  promotion, rank-order preservation under source overrides,
  below-board exclusion, idempotent re-copy, per-format persistence +
  tiers-saved marking, stale-target-override drop, validation 400s).
- `cd mobile && npx tsc --noEmit` → clean.

## Follow-ups / notes

- **Web** (`web/positional-tiers.html`) hits the same endpoint, so its
  copy behavior is fixed server-side automatically. Its confirm-dialog
  text (plus the copy button tooltip and flow comments) was updated
  2026-07-17 to the value-aware wording, matching mobile.
- Older mobile builds calling the endpoint get the remap semantics too
  (server-authoritative by design; their dialog text is stale but the
  behavior is the corrected one).
