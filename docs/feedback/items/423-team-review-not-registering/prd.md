# G-423 mini-PRD — outlook row reads the saved preference; team review records and shows completion

Date: 2026-09-08 · Feedback #423 + #424 (mattmurf77, 1.17.1 build 149, iOS 27.0, TradesHome) · Path: fast-track mobile bug · Investigation: [investigation.md](investigation.md) · Scope: [scope.md](scope.md) · Batch: [../422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md). Status: **planned, not built.**

## 1. Repro (operator path, from the log)

1. On FFV3, run the team review; switch to Lakeview (17:56:40).
2. Open Team review on Lakeview, Confirm an outlook on the window beat, Save on the depth beat, reach the **plan** beat and tap outlook chips (final: Rebuilding, chasing WR/TE) — every write 200, server row `team_outlook=rebuilder` from 17:58:47.
3. Return to the Acquire landing (via "Find my trades" or back — the log cannot tell).
4. **Seen:** outlook row reads "Outlook · Not set"; the Team review entry still shows the full "Start team review" card. **Expected:** "Outlook · Rebuilding"; the entry minimized to "Team review · done".

## 2. Root causes

**#424 (tier: deterministic code-walk; log corroborates).** On the merged landing (`trades.finder_hub`, `calc.inline_home`, `trades.edit_full_sheet` all true) the only outlook surface is the hosted calculator's `calc.outlook-row` (`TradesScreen.tsx:6083-6098` → `:8006-8020` → `InLeagueCalculator.tsx:922-955`); TradesHome's own #394-fixed row is suppressed by T-1 (`:6908`) and the legacy controls row sits behind `!consolidateOn` (`:7157`). With `trade.outlook_direction` **false** (`config/features.json:67`) `OutlookBiasReceipt` is always hidden (`OutlookBiasReceipt.tsx:49-53`, query disabled `:83-88`), and the calculator's fallback renders the **literal** string `Outlook · Not set` (`InLeagueCalculator.tsx:925-931`) — it has no preferences query at all. The 158-byte prefs GET at 17:58:47 shows the client cache already held `rebuilder`; the row simply doesn't read it. This is #394 regressed by route: T-1 retired the fixed row for the unfixed twin.

**#423 (tier: deterministic code-walk; one unknown in the operator path).** (i) `markTeamReviewCompleted` fires only from the plan beat's "Find my trades" button (`TeamReviewScreen.tsx:291-327`); leaving any other way records nothing. (ii) `TeamReviewEntryCard` reads the marker once per `leagueId` on mount (`TeamReviewEntryCard.tsx:70-83`); TradesHome stays mounted under the pushed review (`TabNav.tsx:455-460`) and `nav.navigate('TradesHome')` pops to it, so the card cannot show "done" until relaunch or league switch — even on the happy path.

**Latent, fix alongside:** window/depth-beat writes go through `savePrefs` (`TeamReviewScreen.tsx:148-183`) which never invalidates `['league-prefs']`; only the plan beat's `commit` does (`:1088`). Once the row reads the query, this becomes a visible 5-minute staleness (`TradesScreen.tsx:1288`, `queryClient.ts:29`).

## 3. Fix — one writer, one reader, per surface

**R-1 · Outlook row reads the saved preference.** `InLeagueCalculator` fallback (`:925-931`) subscribes to the same `['league-prefs', leagueId]` query the writers invalidate (mirror `OutlookBiasReceipt.tsx:83-89`: `getLeaguePreferences`, `enabled: !!leagueId`, `staleTime: 5*60_000`, `placeholderData: prev`) and renders `Outlook · <name>` where name is the declared `team_outlook`'s display name — All-in / Contending / Rebuilding / Tanking / **Not sure** for `not_sure` — and **"Not set" only for null/absent**. Declared values only; an inference is not "set" (#394 ruling). Single-source the names: export `outlookDisplayName(value)` from `OutlookBiasReceipt.tsx` (it owns `LEAN` `:34-39`) and use it in the calculator; `TradesScreen`'s private duplicate `OUTLOOK_FALLBACK_LABEL` (`:9837-9849`) may alias the export in the same change (3 lines) or stay — builder's call, note it.

**R-2 · Every review write invalidates.** Move `qc.invalidateQueries({ queryKey: ['league-prefs', leagueId] })` into `savePrefs` after a successful `saveLeaguePreferences` (`TeamReviewScreen.tsx:167-168`); drop the now-redundant call in `Plan.commit` (`:1088`) or leave it — keep exactly **one** `saveLeaguePreferences(` site (guard #10).

**R-3 · Completion is recorded when the review is gone through.** Call `markTeamReviewCompleted(leagueId)` when the `plan` beat becomes the current beat (effect on `beat === 'plan'`, or inside `next` when `beats[n] === 'plan'`), keeping the finish-button call (`:324`; the writer is idempotent `TeamReviewEntryCard.tsx:52`). Default definition, pending operator confirmation (§7 Q1): *reaching the plan beat*.

**R-4 · The entry card sees the marker without a remount.** New `mobile/src/state/teamReviewCompletion.ts` (zustand, pattern `presentationDismissed.ts`): `{ byLeague: Record<string,true>, hydrated, hydrate(), mark(leagueId) }`. `hydrate` reads `ftf_team_review_completed` once; `mark` sets the store **synchronously** then persists fire-and-forget (same key, same sparse-map format — no migration). `markTeamReviewCompleted` becomes a thin wrapper over `mark` (keeps its import site). `TeamReviewEntryCard` derives `completed` from the store (collapsed map unchanged); `collapsed` = own map OR completed. No focus hook — a focus re-read races the fire-and-forget write (investigation §3).

## 4. Files

`mobile/src/components/InLeagueCalculator.tsx` · `mobile/src/components/OutlookBiasReceipt.tsx` (export only) · `mobile/src/screens/TeamReviewScreen.tsx` · `mobile/src/components/TeamReviewEntryCard.tsx` · **new** `mobile/src/state/teamReviewCompletion.ts` · **new** `mobile/tests/check-outlook-row-source.js` + `test:outlook-row-source` in `mobile/package.json` · docs: `mobile/src/screens/CLAUDE.md` (TeamReviewScreen row), `mobile/src/state/CLAUDE.md`/`README.md` (new store), `docs/config-reference.md:371` ("honest 'Not set' fallback" → "reads the saved outlook; 'Not set' only when none"), `docs/feedback/items/423-*/status.md` + `424-*/status.md`, `living-memory/TEST_LEDGER.md`, `CHANGELOG.md`. Optional: `TradesScreen.tsx:9837-9849` alias.

## 5. Regression guards — `mobile/tests/check-outlook-row-source.js` (new, dependency-free, CI-globbed)

| # | Pins | RED by sabotage |
|---|---|---|
| 1 | Inside `InLeagueCalculator`'s `calc.outlook-fallback` block the rendered text derives from `team_outlook` (via `outlookDisplayName`) and the string `'Not set'` appears only as a null fallback (`?? 'Not set'` / `: 'Not set'`), never as the whole line | Restore the literal `Outlook · Not set` |
| 2 | `InLeagueCalculator.tsx` carries `queryKey: ['league-prefs', leagueId]` with `getLeaguePreferences` | Delete the query |
| 3 | `outlookDisplayName` is exported from `OutlookBiasReceipt.tsx` and imported by `InLeagueCalculator.tsx`; `LEAN` maps exactly the four directional values and the helper handles `not_sure` → "Not sure" | Hand-copy the table into the calculator |
| 4 | Every file with `saveLeaguePreferences(` also contains `invalidateQueries({ queryKey: ['league-prefs'` (TradesScreen, TradeDnaSheet, TradeFinderHubScreen, TeamReviewScreen); in `TeamReviewScreen` the invalidation lies between `const savePrefs` and its dependency array | Remove the `savePrefs` invalidation |
| 5 | `TeamReviewScreen` references `markTeamReviewCompleted` in a `beat === 'plan'`/`=== 'plan'` context **and** in the `team-review.finish` handler | Delete the plan-beat call |
| 6 | `TeamReviewEntryCard` derives `completed` from `useTeamReviewCompletion` and no longer calls `AsyncStorage.getItem`/`readMap` for the done key in the component body; `markTeamReviewCompleted` calls the store's `mark` before any `AsyncStorage.setItem` | Revert to the mount-only read |
| 7 | Existing suites stay green: `check-team-review.js` (13), `check-calc-merged-layout.js`, `check-finder-conditions-reachable.js`, `check-inline-home.js`, `testid-lint.sh`, `tsc --noEmit` | — |

QA proves RED for 1, 4, 5, 6 by applying the sabotage on a scratch copy and running the guard; logs the RED/GREEN pair in TEST_LEDGER.

## 6. Not changed

- **No server change.** Server stored and returned the right value every time (12× 200, GET shows `rebuilder`); GET/POST contracts, `load_league_preference`, and the 60 s team-review cache are untouched.
- **No flag change.** `trade.outlook_direction` stays false — it is an engine-weighting flag (bright line), not a display toggle; the fix makes the display honest in both flag states. No new flag: the change is a bug fix to surfaces already live.
- **No new analytics.** `team_review_beat_viewed {beat:'plan'}` and `team_review_exited {outcome:'completed'}` already describe both completion candidates; `outlook_saved {source:'review'}` covers the write.
- **Not touched:** the TradesHome row gate (`:6908`, pinned by two guards), T-1/T-2/T-3, `OutlookBiasReceipt`'s hide predicate, the `ftf_team_review_collapsed` "Not now" behaviour, `useSession` league switching, `seedLeagueSessionCaches`.

## 7. Open questions for the operator

1. **Completion definition:** "reached the plan beat" (recommended — it is the summary of everything set) vs "tapped Find my trades". Default: reached.
2. Alias `TradesScreen`'s duplicate label map to the exported helper in this change (3-line drive-by that closes the single-source guard) — yes/no. Default: yes, guard 3 then also pins TradesScreen.
3. Should the calculator fallback show a *second* line with chasing/shopping like TradesHome's row does? Out of scope here (#315 budget); flag if wanted.

## 8. Operator TestFlight checklist (the only runtime evidence, D-056)

1. Switch to Lakeview from the TopBar switcher. Acquire landing: note the row under "Show me around" — today it reads "Outlook · Not set". **Expected after fix:** "Outlook · Rebuilding" (or whatever is saved) without relaunch.
2. Tap Team review (row or card) → Confirm a *different* outlook on the window beat → Skip to the end → on the plan beat tap a third outlook → leave with **back** (not the button). **Expected:** landing row shows the plan-beat choice immediately; entry reads "Team review · done".
3. Relaunch the app on Lakeview. **Expected:** row and "done" state persist (store hydrated from the same key).
4. Run the review again, leave via **Find my trades**. **Expected:** unchanged — still "done", row still current.
5. Switch to FFV3 and back. **Expected:** each league shows its own outlook and its own done/not-done state; no "Not set" on a league with a saved outlook. A fresh account with nothing declared still reads "Outlook · Not set" with a working Change.
