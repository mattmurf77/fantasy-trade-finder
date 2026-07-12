# #136 — Quick Rank (rank players within a tier) — status

**State:** built + backend contract pinned by test (2026-07-12, branch
`trade-engine-v2`). Awaiting QA/ship.

## What was built

`QuickRankScreen` (`mobile/src/screens/QuickRankScreen.tsx`, Rank-stack route
`QuickRank`) — the within-tier polish pass after Quick set, per the owner's
spec:

- Same guided construction as the Quick set walk: position tabs, tier-by-tier
  walk down the 8-tier ladder, tick-label step header + `Tier N of M`
  progress, Back / Skip / primary Save footer, quick-set chip grid.
- Every player currently IN the tier is presented; tapping a tile stamps the
  next rank number (click order) as a numbered badge (ice border, Plex Mono
  numeral); tapping again unclicks and renumbers cleanly.
- Save posts the tier's players to `POST /api/rankings/reorder` scoped to the
  position: **clicked order first, unclicked players appended in their
  current (elo-desc) order** — e.g. 10 in the tier, 6 clicked → the other 4
  become ranks 7–10. Zero clicks = same as Skip.
- Empty and 1-player tiers auto-skip by construction (the walk's steps are
  derived from live tier membership, filtered to 2+ players).
- Cache invalidation mirrors ManualRanks' reorder save (`rankings` for the
  active format, `tiers-status`, `progress`).

## Save-contract verification

`/api/rankings/reorder` → `ranking_service.apply_reorder` verified
subset-safe: it permutes the sorted Elo multiset of exactly the submitted ids
(v1.7.0 permutation semantics), so a within-tier save (a) never touches
players outside the subset, (b) keeps every submitted player inside its tier
(same multiset), and (c) yields exactly the requested order on an elo-desc
sort. Pinned by the new backend test
`backend/tests/test_tier_occupancy.py::test_subset_reorder_within_tier_preserves_tier_membership`.
The route requires ≥2 ids — satisfied because <2-player tiers never render.

## Entry points

1. **Quick set finish** — `QuickSetTiersScreen`'s end-of-walk now shows
   "Tiers set — Rank within your tiers?" (Not now → Tiers board as before;
   Quick rank → the walk for the same position).
2. **Rank menu** — "Quick rank" row directly below "Quick set" in the Rank
   tab's action sheet (`TabNav.tsx`, testID `rankmenu.quickrank`), with the
   same QB rankings prefetch as Quick set.
3. Deliberately NOT a `rankingMethodPref` launch route / RankHome card —
   that's #122 (unselected).

## Files

- new `mobile/src/screens/QuickRankScreen.tsx`
- `mobile/src/navigation/TabNav.tsx` (route, menu row, prefetch)
- `mobile/src/screens/QuickSetTiersScreen.tsx` (finish prompt)
- `backend/tests/test_tier_occupancy.py` (subset-reorder regression test)
- docs: `docs/design/components.md` (Quick rank walk pattern),
  `docs/glossary.md` ("Quick rank"), `mobile/src/screens/CLAUDE.md`,
  `mobile/src/navigation/CLAUDE.md`, testID registry in
  `mobile/src/components/CLAUDE.md`. No API contract changes →
  `docs/api-reference.md` untouched.

## Test results

- Backend: 556 passed (`python3 -m pytest backend/tests/ -q`).
- Mobile: `npx tsc --noEmit` clean.

## Deferred

- Maestro flow for the Quick rank walk (testIDs are in place per the
  registry conventions; flow authoring is the QA group's pass).
- Consensus-order fallback for unclicked players uses the CURRENT board
  order (per spec, "their current order") — no alternative ordering option.
