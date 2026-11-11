# Projection model v5 and outlook suggestion release — 2026-11-11

**Status: live. Model v5 and the suggestion shipped on `253136ac`; three same-day follow-ups shipped (#648, #649, #650, main at `74cbbce8`). All six supported forecasts completed on v5 at 19:34: two complete, four incomplete (no suggestion). iOS 1.22.0 (185) is on TestFlight and in the operator's hands; no device checklist has been run. The fast deck is off again (D-232).**

The operator's instruction (2026-11-11): the model and outlook spec, then "Merge it, push to
TestFlight if needed and enable the changes if hidden behind any flags". Code was written by
subagents and reviewed in the main session, at the operator's direction.

All times UTC.

## Release scope

One merge to `main`, a merge commit: [#647](https://github.com/mattmurf77/fantasy-trade-finder/pull/647),
head `55077b46`, merged `253136ac` at 15:36, pinned to the tested head.

- Backend: projection model `projected-lineup-universal-sd-v5`; outlook suggestion on the
  latest-run route and in Team Review.
- Web: Projected standings without the comparison and details panels; suggestion prompt.
- iOS: compact Home tile, selector mark, Team Review prompt, Standings cleanup.
- Flag: `league.projection_outlook` ships on. `league.projections` and
  `league.projections_provider_approved` were already on in production through `FTF_FLAGS`.

## Pre-flight checklist

| Item | Evidence | Result |
|---|---|---|
| CI green on the merged head | All four checks on `55077b46` (backend tests 23 min 52 s) | pass |
| Full backend suite, local | 14,453 passed, 42 skipped, 0 failed | pass |
| Mobile typecheck, 173 check suites, testID lint | TEST_LEDGER 2026-11-11 | pass |
| Web structure check | 260/260 | pass |
| Independent review of the backend change | Five findings, all fixed with tests | pass |
| Version | 1.22.0 kept (the What's New notice is keyed to it); build number 185 from EAS | pass |
| Schema, migrations, env vars | None | n/a |
| Docs triggers | API, config, invariants, glossary, architecture, HLD, LLD, D-229, D-230 | pass |
| Scope block before build | Written during the build; operator away with a detailed spec | **waived by circumstance, not by the operator** |
| Device evidence | None (D-056); 10-step checklist in `docs/plans/league-projections/v5-scope.md` | **open** |

## What happened

| Time | Step | Result |
|---|---|---|
| 15:36 | #647 merged | `253136ac` |
| 15:37 | Render deploy `dep-dbq8modbedkc739ird5g` | live 15:37:22; `/` 200 |
| 15:37 | Live flags | `league.projections`, `league.projections_provider_approved`, `league.projection_outlook` all true |
| 15:36 | EAS build `a17afb0f-39f0-4e65-83e6-be3900b747ed` from a clean checkout of `253136ac` (`npm ci`, `tsc` clean) | FINISHED 15:43:13, 1.22.0 (185) |
| 15:37 | Auto-submit `af821c81-4f03-427b-bcda-1e1ba7c6d898` | FINISHED 15:43:33 (uploaded) |

## After the deploy

- Every saved forecast read as stale (`model_current: false`), so no suggestion showed until a
  league's forecast was re-run.
- **The scheduled batch attempted all 12 targets by 17:31 and none produced a forecast.** Six
  (three leagues, the same six that completed on 2026-11-10) stopped with
  `incomplete_projections / player_team_changed`; three were `season_state_mismatch`, two
  `unsupported_divisions_median_bestball_or_manual_seeding`, one `league_membership_changed`
  (those six are the same every week).
- **Cause:** five rostered players changed NFL teams that day. Sleeper's player data had the new
  team; its projection rows for weeks 11 to 14 still carried the old one. A guard from 2026-11-07
  stopped the whole league on any such row. Not part of v5.
- **Fix:** [#648](https://github.com/mattmurf77/fantasy-trade-finder/pull/648) (D-231), head
  `bdb741f8`, merged `adead776` at 18:27 on four green checks; Render deploy
  `dep-dbqb7avavr4c739teggg` live 18:29. A dry run of the fixed code against Sleeper's live feeds
  completed all six: four (one league) incomplete with 2 lineup slots in weeks 11 and 14, two
  complete.
- **Re-run:** the six targets were on next week's slot and nothing could re-run them. A direct edit of `next_due_at` in the production database was blocked for the agent and not made. [#650](https://github.com/mattmurf77/fantasy-trade-finder/pull/650) added `{"retry_incomplete": true}` to the cron-gated batch route (head `0a6237a1`, merged `74cbbce8` at 19:22, deploy `dep-dbqc0rhsrm7s7389vbug` live 19:23). One call at 19:25 marked 6 and queued 3; a plain call at about 19:29 queued the other 3.
- **Result, 19:34:** 6 of 6 complete on `projected-lineup-universal-sd-v5`, SD 25.0, 12 teams each. Two are complete estimates. Four (one league) are incomplete: one lineup slot in week 11 had no projection for the only eligible player, so those accounts see the forecast and no outlook suggestion. All 12 targets are back on the 2026-11-17 slot.

## Feedback from the operator on build 185 (same day)

| Report | Finding | Change |
|---|---|---|
| "No trades found" in one league | `trade.fast_deck` (on since 2026-11-10): 150 cards served, 148 removed by the filters behind the page; the league had 66–94 cards before | Flag off (D-232) |
| "Still RB…" is weird wording | Fit block held-rank template | "RB stays 5th, WR stays 10th" |
| No link to the full projections | The percentage was the only link and opened Current standings | "View" link; both open the Projected segment |
| Expected one-page tier ranking in roster setup | The shipped step is the PRD's v1 (per-position order); tier placement was its deferred v2 | Not changed; operator to decide |

Shipped in [#649](https://github.com/mattmurf77/fantasy-trade-finder/pull/649), head `df989650`, merged `6891c195` at 18:56, deploy `dep-dbqbkk3m8hqs73cpfn6g` live 18:57; `trade.fast_deck` read false on the live flags route. The wording and the flag are server-side; the Home link waits for a build.

The fast-deck log evidence: Nov 9 full solve, 2,444 cards reached the quality filters and 67 survived; Nov 11 fast deck, about 129 of 150 reached them and 2 survived. The filters remove about 97% in both modes. Design for a replacement: [`../../plans/realtime-trade-engine/fast-deck-v2-design.md`](../../plans/realtime-trade-engine/fast-deck-v2-design.md) (a subagent's design and measurements, not re-verified, nothing built).

Open at the time of writing: the roster tier page ([#651](https://github.com/mattmurf77/fantasy-trade-finder/pull/651), D-233) and a before/after rank table for the trade card's fit block, both waiting on CI or review; TestFlight 186 after they merge. Research on win-now and rebuild pieces: [`../../research/window-asset-identification/README.md`](../../research/window-asset-identification/README.md).

## Rollback

- Suggestion only: set `league.projection_outlook` false and reload flags. No deploy.
- Everything projection-related: `league.projections` false in `FTF_FLAGS`.
- The model: revert `253136ac` and deploy. v4 results become current again, v5 results stale, and
  the batch refreshes each league once.
- The app: build 184 keeps working against v5 (old tile; "Historical weight: NaN%" inside a nested
  details panel; its comparison buttons fail with their existing message).

## Decisions needed

1. Run the device checklist on 185 (or on 186 once cut).
2. An analytics event for "suggestion shown / taken": none exists.
3. Whether one incomplete lineup slot should withhold the suggestion for a whole league. Four of the first six real forecasts were withheld for exactly one slot.
4. Calibrate the SD on real pregame snapshots (`docs/plans/league-projections/universal-sd/README.md`).
5. The fast-deck replacement: build the rules-first design, accept the order change, shadow for a week.
6. Win-now and rebuild pieces: the five decisions at the end of the research report.
