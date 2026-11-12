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
| 1 | TradesScreen reads the flag and arms the first-pass trigger only with the flag on and outside demo. The trigger reads the roster (`['league-rosters', id]`, seeded by session init, plus `['league-picks', id]`; owner or co-owner via `findMyRoster`) and hydrates the device store. Both the `TradesHome` deck and a pushed `TradeDeck` are `TradesScreen`, so both arm it. | `mobile/src/screens/TradesScreen.tsx:1020-1032`; `mobile/src/hooks/useRosterSetupPassTrigger.ts:34-62`; `mobile/src/hooks/useMyRosterAssets.ts:34-69` |
| 2 | **Trigger: the first committed pass** (operator amendment 2026-11-10; it replaced the focus-based push). Every deck pass (✕ button `:10198`, swipe gesture, VoiceOver action, bad-trade flag `:7926`) goes through `advance('pass')` (`:7034`), and the pass is recorded exactly as before: same guards, same events, same `swipeMutation.mutate` / held write. The trigger runs at three committed-pass points: **(a) plain pass**, after the swipe write (`:7221`) and the deck advance, at `:7240-7242`. It is skipped for a held pass, and for a reason-deferred pass, whose id layer 1 banked in `reasonBankedIdRef` before calling `advance`. The test is the ref, not a fourth `deferDeckAdvance` read, because `check-canvas-results` 11i pins exactly three; **(b) undo-held pass** (`ux.swipe_undo`), in the undo timer after the held write flushes (`:7213-7216`), so Undo cancels it and the Undo toast is never covered; **(c) reasoned pass** (`feedback.decline_reasons`), on the line after each of the three `commitReasonAdvance()` callers: layer 2 answered (`handleReasonLayer2Select` `:7426`, call `:7438`), layer 2 free text sent (`handleReasonLayer2Send` `:7451`, call `:7479`), or the ✕ overlay dismissed with a banked tile (`handleReasonOverlayDismissed` `:7506`, call `:7510`). That is after the capture has closed. `commitReasonAdvance` itself (`:7373`) is unchanged, because `check-canvas-results` 4d and `check-trade-disposition` pin and execute its body. Browse ✕ (`handleBrowsePass` `:7803`) goes through the same overlay and the same callers. The trigger is never called at layer 1 or the "Other" bank, in `flushPendingPass` (resets, league switch and unmount flush through it) or on Undo. | `TradesScreen.tsx` as cited; check-roster-setup 10d–10h |
| 3 | The trigger's condition is one pure function. It requires: flag, a league that is not `league_demo`, not demo, store hydrated, **no device record** for the league (read at call time), at least one asset, and not already pushed this app session. With no record, the first committed pass is the user's first declined suggestion in that league. | `mobile/src/utils/rosterSetup.ts:185-197`, called at `useRosterSetupPassTrigger.ts:65-82` |
| 4 | When it holds, the trigger pushes `RosterSetup {entry:'first_pass'}` on top of the deck. | `useRosterSetupPassTrigger.ts:80-81` |
| 5 | The TradesHome card no longer pushes anything. It is only the return card, mounted with the flag on, on the landing route, outside demo. | `TradesScreen.tsx:8563`; `mobile/src/components/RosterSetupEntryCard.tsx` (no focus hook; check-roster-setup 10a) |
| 6 | `RosterSetup` is a Trades-stack screen with the shared back control. It mounts no `FeedbackFAB`. | `mobile/src/navigation/TabNav.tsx:528`; check-roster-setup 1a/1b/1d |
| 7 | **The deck holds its position underneath.** The deck screen (TradesHome or TradeDeck) stays mounted beneath the push. `deckIdx` already moved past the passed card (or the browse idea was removed), and the job poller depends only on `job`, not focus. Nothing is reset or cancelled. | `TradesScreen.tsx:2620` (poller effect) |
| 8 | The screen re-checks the flag (`:190`) and loads asset prefs, consensus values and the caller's board per position (the same keys Quick Rank uses). It seeds toggle state **once** from saved tags: untouchable becomes Keep, trade_block becomes Move, anything else becomes open. | `mobile/src/screens/RosterSetupScreen.tsx:190-240, 303-312`; `rosterSetup.ts:40-52` |
| 9 | `roster_setup_shown` fires once per entry. | `RosterSetupScreen.tsx:323-335` |
| 10 | **Autosave.** A tap updates state and queues `desired[id]` (`:388-395`). `flush` keeps one POST in flight, coalesces repeat taps on an asset (last write wins), and drops a value equal to what the server holds. It writes `setAssetPref(leagueId, id, listForState(desired))`, the only write site, so the list can only be `trade_block`, `untouchable` or `none`. A failure reverts that asset unless the user has tapped it again. | `RosterSetupScreen.tsx:348-385`; `rosterSetup.ts:33-37` |
| 11 | **Continue** fires `roster_setup_toggles_done` and walks the rankable positions: QB→TE, at least 2 board-ranked roster players each. | `RosterSetupScreen.tsx:521-548`; `rosterSetup.ts` `rankSteps` |
| 12 | **Reorder.** The rank step renders the shared `RankChipGrid` (`:774`). Save posts `reorderRankings(rankPos, ids)` with no `via`. The ids are clicked order then unclicked in board order, and only this position's roster players. `roster_setup_rank_saved` fires on 2xx only. | `RosterSetupScreen.tsx:552-588`; `rosterSetup.ts` `orderedIdsForSave` |
| 13 | **Done.** The done step's effect calls `finalizeDone` and fires `roster_setup_completed`. `finalizeDone` writes the store `{status:'done', seenAssetIds, rankedPositions, prompt:null}`. The store updates memory synchronously, then persists by read-merge-write. | `RosterSetupScreen.tsx:446-460, 590-602`; `mobile/src/state/rosterSetup.ts:80-96` |
| 14 | **Bus marker.** `finalizeDone` posts `setPendingGuidedRegen('roster_setup')` only when a tag or a rank changed (AC-8). `'roster_setup'` is a new `GuidedRegenSource`. | `RosterSetupScreen.tsx:459`; `mobile/src/state/onboardingBus.ts:43` |
| 15 | **See trades** waits for queued tag writes to drain, so the forced job reads the final tags, then pops. | `RosterSetupScreen.tsx:605-611` |
| 16 | **Forced regen.** On the pop, the deck screen underneath (TradesHome, or the TradeDeck the pass happened on) refocuses, and its focus effect consumes the marker. The source is not `quickset`, so `pos = null`. It snapshots the old deck's packages, clears the deck, and dispatches `{force:true, repeat:true}`. | `TradesScreen.tsx:6245-6313` |
| 17 | When the forced job completes, the diff effect counts the new packages and fires `deck_regenerated {new_trades}`, with no `position`. | `TradesScreen.tsx:6336-6349` |

No change means no marker in hop 14, so hop 16 returns at `if (!marker …) return` and no regeneration runs.

## 2. Skip and back

- **Skip for now** on Step 1 (`RosterSetupScreen.tsx:510-514`): `recordSkip` (`:464-476`) stores `skipped`, but never downgrades a `done` record. `roster_setup_skipped {stage:'toggles'}` fires, then the screen pops. No bus marker is posted, so the deck stays as loaded. Taps already autosaved stay saved.
- **Back on Step 1** (header control or edge swipe) does the same bookkeeping through the `beforeRemove` listener (`:492-507`). The pop itself proceeds.
- **Back on Step 2** runs `finalizeDone`: toggles were confirmed with Continue, and earlier positions stay saved. Then `roster_setup_skipped {stage:'rank'}` fires. The regen marker posts if anything changed.
- **Done ranking** saves the current position if anything was tapped, then shows Step 3 (`saveRank(true)`).
- **Load error** shows "Couldn't load your roster." with Try again and **Skip to trades** (`roster-setup.error.skip`), which is the Step 1 skip.

## 3. Return paths

- **Entry card** (`RosterSetupEntryCard.tsx:94-200`): a `skipped` record shows "Set up your roster". A `done` record whose roster gained assets (`newAssetIds`) shows a title naming what was gained, e.g. "15 new players on your roster", "3 new picks on your roster" or "12 new players and 3 new picks on your roster" (`newOnRosterTitle` in `utils/rosterSetup.ts`, wording revised 2026-11-12 by operator request; executed by `check-roster-setup.js` 9i2). That card opens `RosterSetup {entry:'roster_changed', filterAssetIds}`, and the screen then lists and ranks only those assets and the positions they joined. Losing assets never prompts.
- **Snooze ladder** (`rosterSetup.ts` `cardView` / `ladderOnShow` / `ladderOnSnooze`): Not now → collapsed for the rest of the session → one full re-offer in a later session (onboarding `sessionCount`) → Not now again retires it. A retired entry card stays as a one-line row (D-025). A retired roster-changed card absorbs the new assets into `seenAssetIds`. The full-card impression fires `prompt_shown {surface:'roster_setup_card'}`. A tap fires `roster_setup_prompt_tapped`.
- **Trade DNA row:** TradesScreen passes `full.rosterSetup` only when the flag is on (`TradesScreen.tsx:8121-8135`). The sheet renders "Your roster: N to move · N to keep · Edit" (`dna.roster-setup`) only when that prop is present (`mobile/src/components/TradeDnaSheet.tsx:1049-1079`). Edit closes the sheet, fires `roster_setup_prompt_tapped {surface:'dna_row'}`, and pushes `{entry:'manual_dna'}`.

## 4. Flag off: nothing renders

With `trades.roster_setup` false, which is the default and absent from `config/features.json` on this branch:

1. `rosterSetupOn` is false (`TradesScreen.tsx:1020`). The trigger is armed with `enabled: false` (`:1026-1032`), so its roster reads are disabled, it never hydrates, and its function returns at its first line. The five pass-path calls (`:7215`, `:7241`, `:7438`, `:7479`, `:7510`) are no-ops, and the pass writes, events and deck advance around them are unchanged. The `RosterSetupEntryCard` mount at `:8563` evaluates to `null`, so its reads and card never exist.
2. `full.rosterSetup` is `undefined` (`:8153`), so `{full?.rosterSetup ? … : null}` in `TradeDnaSheet.tsx:1052` renders nothing. The sheet adds one new read, `assetPrefsQuery.data?.trade_block?.length`, which is a field access on data the sheet already fetched. It adds no request.
3. Nothing else navigates to `RosterSetup` (check-roster-setup 4f). The route is registered unconditionally, following the TabNav rule that flag-gated routes stay registered. A stale push renders the empty shell, because the screen returns early at `RosterSetupScreen.tsx:623` before any data render. Its queries are `enabled: rosterSetupOn`, so they are disabled too.
4. Shared code changes that run with the flag off:
   - **QuickRankScreen** renders `RankChipGrid` (`QuickRankScreen.tsx:390`). This is a verbatim extraction: same chip markup, styles, testIDs (`quick-rank.chip.<id>`), `numColumns`, `extraData`, `keyboardShouldPersistTaps` and empty component.
   - **`AssetPrefList` / `AssetPrefs` and `GuidedRegenSource`** each gain one union member. These are type-only.

## 5. Automated evidence

| Check | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | clean |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` (flows reference no new id; `quick-rank.chip.*` still resolves via `testID="quick-rank.chip"`) |
| `npm run test:roster-setup` (`mobile/tests/check-roster-setup.js`) | 91 passed. Pins the six scope §3 checks and the scope testIDs. §10 pins the first-pass trigger: no focus push in the card, exactly five call sites, each after the write / the undo window / the reason capture, none at layer 1, the "Other" bank, flush, Undo or inside `commitReasonAdvance`, and the `first_pass` enum. It also **executes** `utils/rosterSetup.ts`: prefill, Keep guard, pick cap, rank walk, save order, new-asset diff, trigger truth table and snooze ladder. Sabotage-checked: a `<FeedbackFAB />` mount, a `'quickrank'` via, a trigger at layer 1 and an unconditional pass trigger each turn it red. |
| All `mobile/tests/check-*.js` (the CI loop) | all pass |
| `backend/tests/test_analytics_taxonomy_roster_setup.py` | 5 passed |
| Every `backend/tests` file referencing the event registries (27 files) | 1078 passed |

## 6. Deviations and known interactions

- **Pick cap is mirrored, not served.** Neither `/api/league/picks` nor `/api/feature-flags` exposes `picks_pool_cap`, so the greyed "not in trade search" marker uses the model_config default, 6 (`rosterSetup.ts` `PICKS_POOL_CAP_DEFAULT`). It applies the server's own cut: top 6 by the priced `pool_value` the picks route already serves, and anything priced ≤ 0. If the knob is retuned server-side, the marker drifts until the cap is served. The toggle saves either way (AC-4).
- **Non-core positions.** K/DEF players, and ids neither the board nor the consensus pool can place, get no section. The prd's sections are fixed at QB/RB/WR/TE/Picks.
- **Rank membership.** The rank step orders the roster players that are **on the caller's board** for that position, because `apply_reorder` permutes only pool ids. `players_total` counts those players.
- **Abandoned-search telemetry: no longer applies.** TradesScreen's first-card trace marks an unsettled search `abandoned` on blur (`TradesScreen.tsx:5315`), but `failFirstCard` returns early once the trace has settled (`mobile/src/state/tradeSearchTrace.ts:235-237`). The push now follows a pass on a fronted card, so that search's first card was already shown and its trace settled. The blur records nothing extra.
- **First-run guide overlap: reduced, still present.** The landing-focus collision is gone, because the setup now arrives only after the user has acted on a card. But guide v2 beats key off dispositions in the same `advance()`: s2.2 advances on the swipe, and N1/N2 arm on the 3rd disposition or 3 passes. The Quick Set prompt can also show on a pass from swipe 2. If one of these fires on the same pass that triggers the setup, its bubble or inline card degrades to bubble-only, or waits under the push until the user returns. The trigger does not defer for an active guide step; that is an operator call if wanted.
- **Early flush of a held pass.** Under `ux.swipe_undo`, a held pass that is flushed early by the next disposition does not trigger, because only the expiring undo timer does. The next committed pass does, so the push is at most one pass late in that sequence.
- **Other pass surfaces not covered.** Two surfaces pass cards outside `TradesScreen`: the shop window (`ShopOffersBody`, `swipeTrade(..., 'shop')`) and presentation v2 (`usePresentationSignals`, flag `trades.presentation_v2`, dark). The trigger is only in the Find a Trade deck (TradesHome and TradeDeck), as briefed.

## Addendum 2026-11-12 — false "N new on your roster" count

**Bug.** The roster-changed card diffed every rostered id plus owned picks (`useMyRosterAssets.assetIds`) against `seenAssetIds`, but the setup screen wrote that snapshot from its own listed assets, which skip any player without a QB/RB/WR/TE section (`RosterSetupScreen.tsx`, `if (!section) continue;`). Kickers, defenses, IDP players and players neither the board nor the consensus values could place were never recorded as seen. Right after a completed setup they counted as new; the card opened a screen that said "Those assets are no longer on your roster", Skip kept the old snapshot on the roster-changed path, and the card returned every session. The operator saw "15 new on your roster".

**Fix.** One definition, `utils/rosterSetup.trackedAssetIds` (players with a section by `playerSection`, then every owned pick), applied to the same reads through one hook, `hooks/useSetupSections`. The screen lists players by `playerSection` and writes `allAssetIds = trackedAssetIds(...)` on every write path (`finalizeDone`, `recordSkip`, which the one-page tier step and Skip both reach). The card diffs `trackedAssetIds(...)` and its Not now retire absorbs that same set. The card now runs the board and values reads (shared keys) only for a `done` record, and waits for them before deciding.

Chosen over snapshotting every rostered id: that would stop the false count right after setup, but a kicker or IDP arrival would still raise the card and open an empty screen, and the count would still include assets the screen cannot list.

**Existing devices.** No migration. A record written before the fix holds the sectioned players and picks at that time (or everything, if the card was retired). The fixed card no longer counts unsectioned players, so the false count disappears on the next TradesHome render with no write, and a QB/RB/WR/TE player or pick added since setup is still tracked and unseen, so it still raises the card. One remaining case: a player who had no section at setup time and has since gained one (a consensus value appeared) now counts as new. He is listable and actionable, so that is a real prompt, not a dead end.

**"Those assets are no longer on your roster"** can still appear when the named assets left the roster between the card and the screen (traded or dropped, or a roster refetch in between), or when a player's section disappears between the two reads (his only values row drops out of the pool). It no longer appears because of K / DEF / IDP / unvalued players.

**Evidence.** `check-roster-setup.js` 9t1-9t9: the real `useSetupSections` hook executed over stub reads; the snapshot equals the tracked set; a completed roster with K / DEF / IDP / an unvalued player raises no card; a kicker or IDP arrival raises none; one real arrival gives "1 new player on your roster" and the filtered list is exactly him; a pre-fix record loses its false count and still flags a real arrival; the card, its retire path, `finalizeDone` and `recordSkip` all use the tracked set. Each assertion was sabotaged red and restored green.

**TestFlight.** In a league with a kicker or defense rostered: complete roster setup, return to Find a Trade: no "Roster changed" card. Add one QB/RB/WR/TE on the platform: the card reads "1 new player on your roster" and opens a list with exactly that player. Add a kicker: no card. On a device that already showed the false count: after the update the card is gone without any tap.
