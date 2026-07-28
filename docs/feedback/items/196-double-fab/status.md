# #196 / #197 — Two feedback flags on the Trades home (BUG, filed twice)

**Status:** fixed (2026-07-27, branch `teardown-remediation`, worktree agent batch). Covers feedback IDs **196** and **197** (same symptom, filed twice).

## Root cause

`TradeFinderHubScreen` (the Trades home since `trades.finder_hub` went ON,
tab-stack route `TradesHome`) mounted its own `<FeedbackFAB activeScreen="TradesHome" />`
— added in the hub-finish batch on the assumption it would overlap the RootNav
global mount pixel-identically. It doesn't: the RootNav mount is absolute
inside the root stack's Main screen (`bottom = safe-area inset + 64`, above
the tab bar), while the hub's mount was absolute inside the screen's own
`SafeAreaView`, which sits *above* the tab bar — so its FAB rendered at a
different height and both flags were visible at once.

Per the #188 convention only **root-stack pushes** (which cover the RootNav
mount) render their own FAB (`aboveTabBar={false}`); tab screens are covered
by the global mount, whose `activeScreen` comes from
`navigationRef.getCurrentRoute()` and correctly reports `TradesHome`.

## Fix

Removed the hub's local mount + its import
(`mobile/src/screens/TradeFinderHubScreen.tsx`), leaving a comment explaining
why the screen must NOT mount one. RootNav untouched (its mount was already
correct).

## Double-mount audit (grep `FeedbackFAB`)

- `RootNav.tsx` — the global mount over Main tabs (correct, kept)
- `TradeFinderHubScreen.tsx` — the duplicate (removed)
- `LeagueSummaryScreen.tsx` — mounts only when `!isTabRoot` (root-stack push
  variant), already correctly guarded against doubling on the League tab
- `FreeAgentsScreen.tsx` — root-stack push, single `aboveTabBar={false}` mount (correct)
- Tiers/QuickSet/QuickRank import only `setPinnedBottomBarHeight` (no mount)

## Verification

- `cd mobile && npx tsc --noEmit` — clean
- Docs updated: `mobile/src/screens/CLAUDE.md` (hub row),
  `mobile/src/components/CLAUDE.md` (hub-finish tranche note + new tranche entry)
