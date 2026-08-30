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

## Final status (2026-08-30)

| Item | Path taken | Outcome |
|---|---|---|
| #407 | Fast-track bug | **SHIPPED** — fix `8f722676`, 1 production file; QA-A PASS + QA-B approve (1 non-blocking, closed by #406's R-10) |
| #406 | Polish (client-only) | **SHIPPED** — build `c138507c`, 3 production files + new `check-any-partner.js`; QA-A PASS all 10 R + QA-B approve, zero blocking; D-168 |

Both merged in PR [#250](https://github.com/mattmurf77/fantasy-trade-finder/pull/250) → `main` @ `287aed09`; EAS build 139 (v1.16.12) auto-submitting to TestFlight. Statuses `fixed`.
Status corrections applied this run: #402/#403 → `fixed` (shipped 1.16.9–1.16.11, never flipped).
Evidence: [TEST_LEDGER 2026-08-30](../../../living-memory/TEST_LEDGER.md) · QA reports in both item folders.
