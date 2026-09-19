# FB-217 — Quick Set's back button is redundant with "More ways to rank"

- **Type:** bug · **Status:** fixed 2026-08-01 (branch
  `teardown-remediation` worktree)
- **Surface:** `QuickSetTiersScreen` header (Rank stack, TabNav).

## Root cause

QuickSetTiers is the Rank tab's DEFAULT launch route (#122), so it usually
mounts as the stack ROOT with no history. The #162/#165 nav-loop fix gave
every rank surface an always-on back control whose fallback is `RankHome` —
correct for pushed surfaces, but at the QuickSet root the control can only
fall through to RankHome, which duplicates the header's own "More ways to
rank" path (flag `ux.rank_tab_destination` off: the link navigates to
RankHome directly; flag on: it opens the RankMenu sheet). Two header
controls, one destination → the operator read the Back as removable.

## Fix (`mobile/src/navigation/TabNav.tsx`)

New `quickSetBackWhenPushed(navigation, route)`: renders the shared
`HeaderBack` only when the QuickSetTiers route's own position in the Rank
stack is above index 0 (found by `route.key` in `getState().routes` — a
positional check, not `canGoBack()`, so tab/root-stack parent history can
never leak a back button onto the tab's landing screen). Wired into the
QuickSetTiers screen options in BOTH `ux.rank_tab_destination` states.

- **Stack root (launch route, #122):** no back control; "More ways to
  rank" remains and is the path to the other ranking options.
- **Pushed** (RankHome chooser, Tiers header, Rank menu): real history
  exists → the shared `stack.back-btn` control renders exactly as before.

## #162/#165 guarantees preserved

- No rank surface is ever a dead end: the QuickSet root keeps the
  More-ways header path (flag off → RankHome chooser; flag on → the
  RankMenu sheet listing all seven methods); every pushed mount keeps the
  always-on back control with the `RankHome` fallback.
- All OTHER rank surfaces (Trios, Anchors, Tiers, QuickRank, ManualRanks,
  Trends) are untouched — they keep the always-on control even at stack
  root, per the nav-loop fix (only QuickSet carries the duplicate path
  that made the control redundant).
- The `RankHomeScreen.choose` navigate-not-replace pair rule is untouched.

## Files

- `mobile/src/navigation/TabNav.tsx`
- `mobile/src/navigation/CLAUDE.md` (topology note updated)

## Verification

`cd mobile && npx tsc --noEmit` clean. Behavior matrix reasoned above;
`stack.back-btn` remains the Maestro hook for the pushed case.
