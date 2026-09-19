# Status — 199-switcher-add-league

```project-status
{
  "status": "shipped",
  "updated": "2026-07-27",
  "summary": "#199 — Add-a-league option in the league switcher (polish)",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-07-27 — `6f2ac95` — CHANGELOG 2026-07-27 (#196/#199/#201). Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

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
