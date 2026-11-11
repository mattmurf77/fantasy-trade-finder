# Build evidence — Roster-first setup (mobile half)

**Date:** 2026-11-10 · **Branch:** `feat/roster-setup-mobile` (from `feat/roster-first-trade-setup` `7465682b`) · **Scope:** the mobile client and analytics registration. The backend half (`trade_block` on `/api/league/asset-prefs`, the `trades.roster_setup` flag key, the engine reads) is a parallel branch, and this walk does not cover it.

This is the code-walk proof that [scope.md](scope.md) §3 asks for under D-056: no simulator, no Maestro. Line numbers are as of this branch, so re-grep before relying on them. Runtime proof is the manual TestFlight checklist in scope.md §3, run by the operator.

## Table of Contents
- [1. Happy path: entry to forced regen](#1-happy-path-entry-to-forced-regen)
- [2. Skip and back](#2-skip-and-back)
- [3. Return paths](#3-return-paths)
- [4. Flag off: nothing renders](#4-flag-off-nothing-renders)
- [5. Automated evidence](#5-automated-evidence)
- [6. Deviations and known interactions](#6-deviations-and-known-interactions)

---

## 1. Happy path: entry to forced regen

| # | Hop | Where |
|---|---|---|
| 1 | TradesScreen reads the flag. | `mobile/src/screens/TradesScreen.tsx:1019` |
| 2 | The card and auto-push component is mounted only with the flag on, a league, not demo, on the `TradesHome` route (never a pushed `TradeDeck`). | `TradesScreen.tsx:8529-8530` |
| 3 | The component hydrates the device store and reads the roster: `['league-rosters', id]` (seeded by session init) plus `['league-picks', id]`. Owner or co-owner comes from `findMyRoster`. | `mobile/src/components/RosterSetupEntryCard.tsx:66-76`; `mobile/src/hooks/useMyRosterAssets.ts:34-69` |
| 4 | The entry condition (prd §3.1) is one pure function: flag, league not `league_demo`, not demo, store hydrated, **no record** for the league, at least one asset, and not already pushed this app session. | `mobile/src/utils/rosterSetup.ts:181-192`, called at `RosterSetupEntryCard.tsx:78-92` |
| 5 | When it holds and the landing is focused, the component pushes `RosterSetup {entry:'first_use'}`. | `RosterSetupEntryCard.tsx:90-91` |
| 6 | `RosterSetup` is a Trades-stack screen with the shared back control. It mounts no `FeedbackFAB`. | `mobile/src/navigation/TabNav.tsx:528`; check-roster-setup 1a/1b/1d |
| 7 | The deck keeps loading underneath. TradesHome stays mounted beneath the push, and its job poller depends only on `job`, not focus, so nothing is cancelled. | `TradesScreen.tsx:2607` (poller effect) |
| 8 | The screen re-checks the flag (`:190`) and loads asset prefs, consensus values and the caller's board per position (the same keys Quick Rank uses). It seeds toggle state **once** from saved tags: untouchable becomes Keep, trade_block becomes Move, anything else becomes open. | `mobile/src/screens/RosterSetupScreen.tsx:190-240, 303-312`; `rosterSetup.ts:40-52` |
| 9 | `roster_setup_shown` fires once per entry. | `RosterSetupScreen.tsx:323-335` |
| 10 | **Autosave.** A tap updates state and queues `desired[id]` (`:388-395`). `flush` keeps one POST in flight, coalesces repeat taps on an asset (last write wins), and drops a value equal to what the server holds. It writes `setAssetPref(leagueId, id, listForState(desired))`, the only write site, so the list can only be `trade_block`, `untouchable` or `none`. A failure reverts that asset unless the user has tapped it again. | `RosterSetupScreen.tsx:348-385`; `rosterSetup.ts:33-37` |
| 11 | **Continue** fires `roster_setup_toggles_done` and walks the rankable positions: QB→TE, at least 2 board-ranked roster players each. | `RosterSetupScreen.tsx:521-548`; `rosterSetup.ts` `rankSteps` |
| 12 | **Reorder.** The rank step renders the shared `RankChipGrid` (`:774`). Save posts `reorderRankings(rankPos, ids)` with no `via`. The ids are clicked order then unclicked in board order, and only this position's roster players. `roster_setup_rank_saved` fires on 2xx only. | `RosterSetupScreen.tsx:552-588`; `rosterSetup.ts` `orderedIdsForSave` |
| 13 | **Done.** The done step's effect calls `finalizeDone` and fires `roster_setup_completed`. `finalizeDone` writes the store `{status:'done', seenAssetIds, rankedPositions, prompt:null}`. The store updates memory synchronously, then persists by read-merge-write. | `RosterSetupScreen.tsx:446-460, 590-602`; `mobile/src/state/rosterSetup.ts:80-96` |
| 14 | **Bus marker.** `finalizeDone` posts `setPendingGuidedRegen('roster_setup')` only when a tag or a rank changed (AC-8). `'roster_setup'` is a new `GuidedRegenSource`. | `RosterSetupScreen.tsx:459`; `mobile/src/state/onboardingBus.ts:43` |
| 15 | **See trades** waits for queued tag writes to drain, so the forced job reads the final tags, then pops. | `RosterSetupScreen.tsx:605-611` |
| 16 | **Forced regen.** TradesHome's focus effect consumes the marker. The source is not `quickset`, so `pos = null`. It snapshots the old deck's packages, clears the deck, and dispatches `{force:true, repeat:true}`. | `TradesScreen.tsx:6232-6300` |
| 17 | When the forced job completes, the diff effect counts the new packages and fires `deck_regenerated {new_trades}`, with no `position`. | `TradesScreen.tsx:6323-6336` |

No change means no marker in hop 14, so hop 16 returns at `if (!marker …) return` and no regeneration runs.

## 2. Skip and back

- **Skip for now** on Step 1 (`RosterSetupScreen.tsx:510-514`): `recordSkip` (`:464-476`) stores `skipped`, but never downgrades a `done` record. `roster_setup_skipped {stage:'toggles'}` fires, then the screen pops. No bus marker is posted, so the deck stays as loaded. Taps already autosaved stay saved.
- **Back on Step 1** (header control or edge swipe) does the same bookkeeping through the `beforeRemove` listener (`:492-507`). The pop itself proceeds.
- **Back on Step 2** runs `finalizeDone`: toggles were confirmed with Continue, and earlier positions stay saved. Then `roster_setup_skipped {stage:'rank'}` fires. The regen marker posts if anything changed.
- **Done ranking** saves the current position if anything was tapped, then shows Step 3 (`saveRank(true)`).
- **Load error** shows "Couldn't load your roster." with Try again and **Skip to trades** (`roster-setup.error.skip`), which is the Step 1 skip.

## 3. Return paths

- **Entry card** (`RosterSetupEntryCard.tsx:94-200`): a `skipped` record shows "Set up your roster". A `done` record whose roster gained assets (`newAssetIds`) shows "N new on your roster". That card opens `RosterSetup {entry:'roster_changed', filterAssetIds}`, and the screen then lists and ranks only those assets and the positions they joined. Losing assets never prompts.
- **Snooze ladder** (`rosterSetup.ts` `cardView` / `ladderOnShow` / `ladderOnSnooze`): Not now → collapsed for the rest of the session → one full re-offer in a later session (onboarding `sessionCount`) → Not now again retires it. A retired entry card stays as a one-line row (D-025). A retired roster-changed card absorbs the new assets into `seenAssetIds`. The full-card impression fires `prompt_shown {surface:'roster_setup_card'}`. A tap fires `roster_setup_prompt_tapped`.
- **Trade DNA row:** TradesScreen passes `full.rosterSetup` only when the flag is on (`TradesScreen.tsx:8121-8135`). The sheet renders "Your roster: N to move · N to keep · Edit" (`dna.roster-setup`) only when that prop is present (`mobile/src/components/TradeDnaSheet.tsx:1049-1079`). Edit closes the sheet, fires `roster_setup_prompt_tapped {surface:'dna_row'}`, and pushes `{entry:'manual_dna'}`.

## 4. Flag off: nothing renders

With `trades.roster_setup` false, which is the default and absent from `config/features.json` on this branch:

1. `rosterSetupOn` is false (`TradesScreen.tsx:1019`). The `RosterSetupEntryCard` mount at `:8529` evaluates to `null`, so its queries, auto-push effect and card never exist. The only reads it would add are `league-rosters` (already cached) and `league-picks`. Neither runs.
2. `full.rosterSetup` is `undefined` (`:8121`), so `{full?.rosterSetup ? … : null}` in `TradeDnaSheet.tsx:1052` renders nothing. The sheet adds one new read, `assetPrefsQuery.data?.trade_block?.length`, which is a field access on data the sheet already fetched. It adds no request.
3. Nothing else navigates to `RosterSetup` (check-roster-setup 4f). The route is registered unconditionally, following the TabNav rule that flag-gated routes stay registered. A stale push renders the empty shell, because the screen returns early at `RosterSetupScreen.tsx:623` before any data render. Its queries are `enabled: rosterSetupOn`, so they are disabled too.
4. Shared code changes that run with the flag off:
   - **QuickRankScreen** renders `RankChipGrid` (`QuickRankScreen.tsx:390`). This is a verbatim extraction: same chip markup, styles, testIDs (`quick-rank.chip.<id>`), `numColumns`, `extraData`, `keyboardShouldPersistTaps` and empty component.
   - **`AssetPrefList` / `AssetPrefs` and `GuidedRegenSource`** each gain one union member. These are type-only.

## 5. Automated evidence

| Check | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | clean |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` (flows reference no new id; `quick-rank.chip.*` still resolves via `testID="quick-rank.chip"`) |
| `npm run test:roster-setup` (`mobile/tests/check-roster-setup.js`) | 81 passed. Pins the six scope §3 checks and the scope testIDs, and **executes** `utils/rosterSetup.ts`: prefill, Keep guard, pick cap, rank walk, save order, new-asset diff, auto-push truth table and snooze ladder. Sabotage-checked: a `<FeedbackFAB />` mount and a `'quickrank'` via each turn it red. |
| All `mobile/tests/check-*.js` (the CI loop) | all pass |
| `backend/tests/test_analytics_taxonomy_roster_setup.py` | 5 passed |
| Every `backend/tests` file referencing the event registries (27 files) | 1078 passed |

## 6. Deviations and known interactions

- **Pick cap is mirrored, not served.** Neither `/api/league/picks` nor `/api/feature-flags` exposes `picks_pool_cap`, so the greyed "not in trade search" marker uses the model_config default, 6 (`rosterSetup.ts` `PICKS_POOL_CAP_DEFAULT`). It applies the server's own cut: top 6 by the priced `pool_value` the picks route already serves, and anything priced ≤ 0. If the knob is retuned server-side, the marker drifts until the cap is served. The toggle saves either way (AC-4).
- **Non-core positions.** K/DEF players, and ids neither the board nor the consensus pool can place, get no section. The prd's sections are fixed at QB/RB/WR/TE/Picks.
- **Rank membership.** The rank step orders the roster players that are **on the caller's board** for that position, because `apply_reorder` permutes only pool ids. `players_total` counts those players.
- **Abandoned-search telemetry.** Pushing the setup blurs TradesHome. TradesScreen's first-card trace marks an in-flight landing search `abandoned` on blur (`TradesScreen.tsx:5300-5305`). With the flag on, the first-use push will record `trade_first_card_failed {abandoned}` for that search. The job itself keeps running (hop 7). This branch leaves TradesScreen's trace untouched; whether the trace should exempt this push is an open call.
- **First-run guide overlap.** A brand-new user also meets the Analyst tour on the Trades landing. The auto-push does not defer for the tour, and the prd names no ordering. With both flags on, guide beats aimed at the landing degrade to bubble-only while the setup is on top.
