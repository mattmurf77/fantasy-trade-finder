# #237 — Mirrored filters: roster section matches the league-summary bar chart

- **Reporter:** mattmurf77 · severity polish · screen LeagueRankings
- **Status:** built, typecheck green (2026-08-02)
- **Ask:** "The filter for the roster section should mimic the filter set for league summary bar chart. So both sections should have the buttons, but they should always match each other."

## Sections involved

Both sections live in ONE file — `mobile/src/screens/LeagueSummaryScreen.tsx`
(the component behind both the `LeagueRankings` tab-root route and the legacy
`LeagueSummary` root-stack route):

1. **Chart card** (league summary bar chart) — All/Starters/Bench segmented
   control (`league-summary.subset.*`) + position filter pills
   (`league-summary.posfilter.*`, incl. the conditional Picks pill).
2. **Drill-in roster panel** — the roster section rendered inline below the
   chart when a team is focused. Before #237 it had its OWN independent
   position-pill row (state `drillPos`, reset on every team open) and NO
   subset buttons, so the two sections could disagree.

## How state is shared

Same screen ⇒ plain lifted state, no new store/context (simplicity first):

- The panel's separate `drillPos` state was **deleted**. Both pill rows now
  bind to the single existing `posFilter` set; both subset controls bind to
  the single existing `subset` state. Changing either section updates both
  instantly — they cannot diverge.
- The chart's inline subset row was factored into a small `SubsetControl`
  component (same styles/markup, parameterized `idPrefix`) rendered twice:
  chart card (`league-summary.subset.*`, testIDs unchanged) and roster panel
  (`league-summary.roster-subset.*`, new). Both render only when the payload
  says `starters_available` (honest degradation, unchanged).
- The roster panel's pill row keeps its existing testID prefix
  (`league-summary.roster-posfilter.*`) and now uses the same
  `showPicks` condition as the chart (`hasPicks && subset === 'all'`), so the
  button sets are identical.
- Roster re-filtering already flowed from the shared state: the panel's rows
  come from `computeSubset(team, subset)` (server-derived `teams[].starters`
  — no new backend calls) and are grouped via `groupRows(rows, posFilter)`;
  the picks section honors `posFilter` too. Opening a team no longer clears
  the filter (the old `setDrillPos(new Set())` resets are gone) — the panel
  opens showing exactly what the chart is filtered to.

## Verification

- `cd mobile && npx tsc --noEmit` → pass (worktree, 2026-08-02).
- `grep drillPos` → no remaining code references.
- Behavior by construction: one `subset` + one `posFilter` state feed both
  sections' controls and both sections' data transforms, so any tap in either
  section re-renders both from the same values.
- Existing testIDs preserved: `league-summary.subset.*`,
  `league-summary.posfilter.*`, `league-summary.roster-posfilter.*`,
  `league-summary.roster-close`. New: `league-summary.roster-subset.all|starters|bench`.
