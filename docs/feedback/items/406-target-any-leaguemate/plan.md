# Batch plan — 2026-08-30 run (#406 + #407)

> Batch-level plan for the 2026-08-30 feedback run. Lowest selected ID is #406, so
> batch notes live here; [407-finder-forced-team/status.md](../407-finder-forced-team/status.md)
> links back. Operator selection: "G1 = #407 and #406" (chat, 2026-08-30).

## Groups

| Group | Items | Path | One-line scope |
|---|---|---|---|
| G-407 | #407 | Fast-track bug | Find-a-trade on the merged calculator surface incorrectly forces a partner team carried over from the calculator state below it (regression suspected in the v1.16.11 found-ideas-browse ship, PR #237). |
| G-406 | #406 | Polish/Feature (planner decides) | Let the user target "any league mate" as well as an individual one when shopping a player, so all options for the player being moved are shown. |

Groups are split (not one group) because #407 is a newest-build regression fix and
#406 is a targeting-surface extension — different scope class, per triage rules.
Shared-surface risk: both touch the TradesHome/merged-calculator area; Phase 2
file ownership must be checked for overlap before parallel build (if both need
`TradesScreen.tsx`/calculator files, serialize or single-own).

## Status corrections applied this run

- #402, #403 → `fixed` (shipped lit across 1.16.9→1.16.11; PRs #225/#234).

## Phase log

- 2026-08-30: Phase 0 complete — items marked `planned`, folders created, Phase 1
  planner agents launched (G-407 fast-track investigation; G-406 dual-agent loop).
