# FB-162 + FB-165 — stuck in a ranking loop (nav topology)

- **Covers:** feedback #162 and #165 (same bug, filed twice)
- **Type:** bug, P1 · **Status:** fixed 2026-07-25 (branch `teardown-remediation` worktree) — unflagged bug fix
- **Screens:** Rank stack (TabNav) + RankHomeScreen; the surface the tester described ("Ja'Marr Chase is worth 4/3/2/1 firsts") is the Pick Anchor wizard (`PickAnchorScreen`, route `Anchors`)

## Root cause (stack topology)

Two compounding defects, either of which strands the user:

1. **`RankHomeScreen.choose` used `navigation.replace(route)`.** Picking a
   method from the Build-your-board chooser REPLACED the chooser in the Rank
   stack with the chosen surface, so back (header control, iOS edge-swipe,
   Android hardware back) from the wizard could never return to the chooser —
   it landed on whatever sat beneath (usually Quick Set). That is exactly
   "going back doesn't go back to all options."
2. **Every rank sub-screen's HeaderBack fallback pointed at a sibling surface
   (`'Trios'` or `'Tiers'`), never at the chooser.** Choosing a method also
   saves `rankingMethodPref`, so the NEXT launch mounts that surface as the
   stack's FIRST screen (no history). Back then used the fallback → Trios,
   which with `ux.rank_tab_destination` off is completely headerless (no back
   control at all — a dead end), and the RankMenu sheet doesn't list the
   chooser. With the flag on (current prod config), surfaces have a "More ways
   to rank" sheet link but no path back to RankHome either. Net: after one
   trip through the chooser, the "main rank page" was unreachable — the loop.

There was no completion-redirect loop: the Quick Set finish path
(`goBack() || navigate('Tiers')`) was fine and is unchanged.

## Fix

- `RankHomeScreen.choose`: `navigation.replace` → `navigation.navigate`. The
  chooser stays under the chosen surface; back/swipe/hardware-back pop to it.
  Launch routing is untouched (it reads the saved pref, not the stack).
- `TabNav` Rank stack: every rank surface's HeaderBack fallback is now
  `'RankHome'` (was `'Trios'`/`'Tiers'`) in BOTH `ux.rank_tab_destination`
  states — Anchors, Tiers, QuickSetTiers, QuickRank, ManualRanks, Trends. A
  surface mounted as stack root now has a guaranteed one-tap path to the
  chooser.
- Trios (`RankScreen`) now carries the shared always-on header back control in
  both flag states (it was headerless flag-off — the dead end above). Same
  unflagged-fix class as RankHome's S1B-05 header.
- The shared `HeaderBack` control got `testID="stack.back-btn"` +
  `accessibilityRole/Label` for Maestro (it had no ID). Existing IDs
  (`rank.more-ways`, `rank-home.card.*`, `rankmenu.*`) unchanged.

## Behavior matrix after the fix

| From | Back does |
|---|---|
| Any rank surface pushed from RankHome or the RankMenu sheet | pops to what's beneath (RankHome stays in the stack now) |
| Any rank surface as stack root (launch routing) | header Back → navigates to RankHome; iOS swipe has no history (nothing to swipe to) but the header control is always present |
| RankHome as stack root | Back → the preferred rank surface (`initial` fallback, unchanged) |

## Files

- `mobile/src/navigation/TabNav.tsx`
- `mobile/src/screens/RankHomeScreen.tsx`
- `mobile/src/navigation/CLAUDE.md` (topology pair-rule note)

## Verification

- `cd mobile && npx tsc --noEmit` clean.
- Manual reasoning matrix above; Maestro flow extension pending the next
  smoke-set pass (`stack.back-btn` is the hook).
