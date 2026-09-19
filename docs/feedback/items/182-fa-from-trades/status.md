# #182 — Free agents entry on the find-a-trade page — status

**State:** shipped (2026-07-25, worktree branch off `teardown-remediation`).
**Owner ask:** "Free agents should be presented on the find a trade page
as a page to route to."

## What shipped

An **Explore** section at the bottom of the standalone Trades home
(`mobile/src/screens/TradesScreen.tsx`) with a "Free agents" entry row —
the same explore-row construction as the League tab's Explore list
(hairline list row, `type.title` label + `type.bodySm` chalk-dim meta +
chevron; Chalkline tokens only). testID `trades.explore.free-agents`.

Navigation: `navigation.navigate('FreeAgents')` — FreeAgents is a
ROOT-stack route, so the call bubbles up from the tab navigator exactly
as LeagueScreen's `league.free-agents-row` does.

Visibility rules (matches the screen's existing chrome policy):

- Hidden during **first-run** (onboarding collapses Trades chrome to the
  deck + one control row).
- Hidden in **hub-launched deck modes** (`finderMode` set — the FB #156
  TradeDeck launches are focused single-purpose surfaces with their own
  mode bar).

## Tests / verification

- `cd mobile && npx tsc --noEmit` clean.
- testID registered in `mobile/src/components/CLAUDE.md`; a Maestro step
  (`tab.trades` → `trades.explore.free-agents` → assert
  `free-agents.list`) is the natural smoke addition.

## Files changed

- `mobile/src/screens/TradesScreen.tsx` — Explore section + row + styles.
- `mobile/src/components/CLAUDE.md` — testID registry.
