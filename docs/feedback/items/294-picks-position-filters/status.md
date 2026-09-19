# FB-294 — Position filters drop draft-pick value

- **Type:** polish (design reversal) · **Status:** planned 2026-08-10
- **Group:** G3 — Pick value in subsets & position filters
- **Canonical folder:** [`293-picks-in-subsets/`](../293-picks-in-subsets/) —
  plan and PRD for #293/#294 both live there.
- **Batch plan:** [`289-mfl-draft-room-ids/batch-plan.md`](../289-mfl-draft-room-ids/batch-plan.md)
- **Branch:** `feedback-289-294` (base `origin/main` @ `7cea1fa`)

## Reported

Screen `LeagueRankings`, app 1.11.0, 2026-08-10, mattmurf77, immediately after
#293:

> "Neither do the position specific filters"

## Triage note — reversal of an explicit design decision

`LeagueSummaryScreen.tsx` (~L159-162) records today's behavior as intentional:
picks are a draft-capital group rather than a position, rendered in neutral ink
per `docs/cross-client-invariants.md`, and "Picks are neither starters nor
bench, so the Picks key only exists in the All subset." Filtering by position
therefore drops pick value by construction.

Both #293 and #294 are fallout from #285 (draft picks summed into league/team
values), which set the expectation that pick value is part of a team's value
everywhere.

## Operator ruling (contract for the build)

> "I'm talking about picks for value."

A team's draft-pick value contribution is **subset-independent and
filter-independent** — switching to Starters/Bench or filtering by position
must never make a team's value silently drop by its draft capital. The PRD in
the canonical folder turns this into the precise per-view spec.
