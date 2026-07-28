# #199 — Add-a-league option in the league switcher (polish)

**Status:** fixed (2026-07-27, branch `teardown-remediation`, worktree agent batch).

> "An easier/more upfront way to link other leagues… directly from the league
> switcher an add-a-league option should be available."

## What shipped

`LeagueSwitcherSheet` gains an optional `onAddLeague` prop. When passed, an
**"Add a league"** row renders pinned under the league list (above Cancel, so
it's reachable without scrolling a long list): `plus` icon + label in **ice**
(action accent), hairline top border, 44pt min target, disabled while a
league switch is in flight. testID **`league.switcher.add-league`**,
a11y label "Add a league" with a hint naming the destination.

`LeagueScreen` (the league switcher surface — hero tap + "Switch league"
button open the one sheet mount) passes `onAddLeague`: closes the sheet and
`navigation.navigate('LeaguePicker')` — the root-stack picker whose footer
already carries the link-platform flows (ESPN / MFL / Fleaflicker buttons +
Sleeper leagues list). No new flows; just the entry point.

## Scope notes

- The sheet is also mounted by `TradesScreen` and `TradeFinderHubScreen`;
  those mounts don't pass `onAddLeague` (outside this item's file ownership),
  so they render exactly as before. Wiring them is a trivial follow-up if
  wanted.
- LeaguePicker pushed over Main has no explicit back control (same as its
  other entry points); picking any league — including the current one —
  returns to Main via the normal `onLeaguePicked` replace.

## Files

- `mobile/src/components/LeagueSwitcherSheet.tsx` — prop + row + styles
- `mobile/src/screens/LeagueScreen.tsx` — wiring
- `mobile/src/components/CLAUDE.md` — testID registry tranche

## Verification

- `cd mobile && npx tsc --noEmit` — clean
