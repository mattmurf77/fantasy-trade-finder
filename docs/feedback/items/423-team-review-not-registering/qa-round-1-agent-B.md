# QA round 1 — agent B — 2026-09-08

Group G-423 (#423 + #424). Diff under test: `a8658cec..59236a18` (13 files: 6 mobile source, 1 new guard, `package.json`, 3 `CLAUDE.md`, `docs/config-reference.md`, `build-report.md`). Spec: [prd.md](prd.md) R-1…R-4, §5 guards, §8 checklist; rulings in [reconciliation-log.md](reconciliation-log.md). Independent of agent A; the builder's [build-report.md](build-report.md) was verified line by line, not trusted.

## Summary: PASS (4 findings — all minor; none blocks ship)

Every PRD §5 guard row holds, all six named sabotages go RED on the assertion the PRD maps them to, and every requirement's code path traces as specified. The four findings are: a transient "Not set" while the prefs fetch is in flight (F-1), a league-switch-on-the-plan-beat edge that marks the wrong league (F-2), three shape-only gaps in the new guard (F-3), and PRD §4 doc rows not in the diff (F-4). `pytest backend/tests` is recorded separately below (no backend file is in the diff).

## Environment

- Worktree: detached at `59236a18` (`G-423 docs: registry rows, config-reference fallback wording, build report with code-walk`), tree clean before and after every sabotage (`git status --porcelain` empty each time).
- node v24.14.1; `npx tsc --noEmit` via the repo-pinned TypeScript; `mobile/node_modules` populated symlink. Python 3.14.4, pytest 9.0.3.
- Flags pinned as `config/features.json` ships them: `trades.finder_hub` true (:14), `trade.outlook_direction` **false** (:67), `trades.team_review` true (:80), `calc.merged_layout` true (:93), `calc.inline_home` true (:95), `trades.edit_full_sheet` true (:230). Note `calc.merged_layout` is **not** in `LAUNCHED_FLAG_DEFAULTS` (`mobile/src/state/useFeatureFlags.ts:45-`), which matters for R-1's non-fire conditions.
- No simulator, no Maestro, no captures (D-056). Line numbers below are this tree's.

## Results

| Test | Verdict | Evidence |
|---|---|---|
| `cd mobile && npx tsc --noEmit` | PASS | exit 0 |
| Every `mobile/tests/check-*.js` (loop) | PASS | 99 guards, 0 failed (`GUARDS_TOTAL=99 GUARDS_FAILED=0`) |
| `bash scripts/testid-lint.sh` | PASS | `testid-lint OK`, exit 0 |
| New guard `check-outlook-row-source.js` baseline | PASS | `15 passed, 0 failed`, exit 0 |
| S1 restore literal `Outlook · Not set` (PRD §5 #1) | PASS (RED) | `13 passed, 2 failed` → `✗ 1a. fallback text derives from the saved team_outlook`, `✗ 1b. no literal "Outlook · Not set" line`; revert → 15/0, tree clean |
| S2 delete the prefs query (§5 #2) | PASS (RED) | `14/1` → `✗ 2. InLeagueCalculator queries ['league-prefs', leagueId] via getLeaguePreferences`; revert → 15/0 |
| S3 hand-copy the table into the calculator, drop the import (§5 #3) | PASS (RED) | `13/2` → `✗ 3a. InLeagueCalculator imports outlookDisplayName from ./OutlookBiasReceipt`, `✗ 3d. no hand-copied outlook name table outside the receipt`; revert → 15/0 |
| S4 remove the `savePrefs` invalidation (§5 #4) | PASS (RED) | `13/2` → `✗ 4a. every saveLeaguePreferences( caller invalidates ['league-prefs'`, `✗ 4b. TeamReviewScreen invalidates ['league-prefs', leagueId] INSIDE savePrefs`; revert → 15/0 |
| S5 delete the plan-beat completion effect (§5 #5) | PASS (RED) | `14/1` → `✗ 5a. markTeamReviewCompleted fires in a beat === 'plan' context`; revert → 15/0 |
| S6 revert the card to a mount-only read of the done key (§5 #6) | PASS (RED) | `14/1` → `✗ 6a. TeamReviewEntryCard derives \`completed\` from useTeamReviewCompletion`; revert → 15/0 |
| X1 finish button no longer records completion (extra) | PASS (RED) | `14/1` → `✗ 5b. the finish handler still records completion` |
| X2 `store.mark` persists before setting memory (extra) | PASS (RED) | `14/1` → `✗ 6c. store.mark sets memory synchronously before persisting` |
| X3 card minimizes on `collapsed` only (extra) | PASS (RED) | `14/1` → `✗ 6a. minimized = collapsed OR completed` |
| X4 TradesScreen re-hand-copies its own table (extra) | PASS (RED) | `14/1` → `✗ 3d. no hand-copied outlook name table outside the receipt` |
| X5 store persists to a different key (extra) | PASS (RED) | `14/1` → `✗ 6c. the store mirrors the SAME device key` |
| X6 plan effect kept but neutered `&& false` (weakness probe) | stays GREEN → F-3 | `15/0` — not a PRD-named sabotage; recorded as guard strength |
| X7 prefs query `enabled: false` (weakness probe) | stays GREEN → F-3 | `15/0` — builder's report §6 already admits guard 2 does not pin `enabled` |
| X8 row reads `inferred_outlook ?? team_outlook` (weakness probe) | stays GREEN → F-3 | `15/0` — violates the #394 "an inference is not set" ruling yet passes 1a |
| §5 #7 existing suites: `check-team-review.js`, `check-calc-merged-layout.js`, `check-finder-conditions-reachable.js`, `check-inline-home.js`, `check-team-review-depth.js` | PASS | all inside the 99/0 loop above |
| R-1 outlook row reads `['league-prefs', leagueId]` and maps through the shared table | PASS (code-walk §R-1) → F-1 minor | `InLeagueCalculator.tsx:443-449, 913, 943, 950-952`; `OutlookBiasReceipt.tsx:34-39, 50-56, 61-63` |
| R-2 every review write invalidates the key | PASS (code-walk §R-2) | `TeamReviewScreen.tsx:113, 159-200 (177, 185), 274, 287, 299, 1093-1102` |
| R-3 completion recorded on reaching the plan beat, and on finish | PASS (code-walk §R-3) → F-2 minor | `TeamReviewScreen.tsx:132, 140-142, 310, 341-342`; `backend/team_review.py:589-595` |
| R-4 card reads the store synchronously; persistence is read-merge-write | PASS (code-walk §R-4) | `TeamReviewEntryCard.tsx:55-57, 70-75, 97, 101-111`; `teamReviewCompletion.ts:60-67, 69-76` |
| Hunt: second `saveLeaguePreferences(` site | PASS (none) | `git grep`: `TeamReviewScreen.tsx:177` is the only one in that file; `check-team-review.js` #10 green |
| Hunt: TradesHome T-1 gate untouched | PASS | `git diff -U0` hunks in `TradesScreen.tsx` are only `@@ -68,0 +69` (import) and `@@ -9838,14 +9839,5` (alias); gate at `:6909` byte-identical; `grep -c canvasHost` on the diff = 0 |
| Hunt: stale closure / deps in the new `useEffect` | PASS | body references only `beat`, `leagueId`, a module import; deps `[beat, leagueId]` complete (`:140-142`); hook precedes every early return (`:202`, `:209`, `:216`) |
| Hunt: `hydrate` vs `mark` race | PASS | see §R-4 — no path drops a league |
| Hunt: `enabled: merged && !!leagueId` stranding the row on "Not set" | PASS (no stranding) → F-1 for the in-flight flash | row and query gate on the same `merged` boolean (`:446` vs `:913`) |
| Hunt: league switching keys the query and the store | PASS → F-2 for the plan-beat edge | `:444` key; `TradeBuildCanvas.tsx:212` remount key; `TradesScreen.tsx:7047-7049` card `leagueId`; store `byLeague[leagueId]` |
| `python3 -m pytest backend/tests -q -x` (regression; no backend file in the diff) | BLOCKED (see note) | run exceeded the 600 s foreground cap and was moved to the background by the harness; result not available at write time. No `backend/` path is in `git diff --stat a8658cec..59236a18`, so this cannot be affected by the change under test |

## Code-walk proofs

### R-1 — the outlook row reads the saved preference

1. **Query.** `InLeagueCalculator.tsx:443-449`: `prefsQ = useQuery({ queryKey: ['league-prefs', leagueId], queryFn: () => getLeaguePreferences(leagueId), enabled: merged && !!leagueId, staleTime: 5*60_000, placeholderData: (prev) => prev })`. `getLeaguePreferences` imported at `:6` from `../api/league` (`league.ts:62-66`; `LeaguePreferences.team_outlook: Outlook` at `:30`). Same key as the writers' invalidations (`TradeDnaSheet.tsx:444`, `TradeFinderHubScreen.tsx:353`, `TradesScreen.tsx:1362, 6533`, `TeamReviewScreen.tsx:185`) and the other readers (`TradesScreen.tsx:1286`, `OutlookBiasReceipt.tsx:83`, `TeamReviewScreen.tsx` Plan `prefsQ`).
2. **Render.** `:913` `{merged ? (` → `:943` `{outlookHidden ? (` → `:950` `<View testID="calc.outlook-fallback">` → `:952` `` {`Outlook · ${outlookDisplayName(prefsQ.data?.team_outlook) ?? 'Not set'}`} ``. `outlookHidden` is set by the receipt's `onHiddenChange` (`OutlookBiasReceipt.tsx:106-111`), true whenever `outlookReceiptCovers` is false — always, with `trade.outlook_direction` false (`:71-75`).
3. **Name table.** `outlookDisplayName` imported at `:30`; defined `OutlookBiasReceipt.tsx:61-63` → `value ? OUTLOOK_DISPLAY_NAME[value] ?? null : null`. `OUTLOOK_DISPLAY_NAME` `:50-56` maps `championship/contender/rebuilder/jets` to `LEAN.<k>.name` (`:34-39`: All-in / Contending / Rebuilding / Tanking) and `not_sure: 'Not sure'`. Only the declared `team_outlook` is read; `inferred_outlook` never is (#394 ruling). Null/absent/unknown → `null` → call-site `?? 'Not set'`.
4. **Operator repro.** Lakeview server row `team_outlook=rebuilder` → `prefsQ.data.team_outlook === 'rebuilder'` → `'Rebuilding'` → `Outlook · Rebuilding`.
5. **TradesScreen twin (ruling Q2).** `:69` imports `OUTLOOK_DISPLAY_NAME`; `:9843` `const OUTLOOK_FALLBACK_LABEL = OUTLOOK_DISPLAY_NAME;`; call site `:6915` unchanged.

**Does NOT fire when:** (a) `merged` is false — `calc.merged_layout` off, or the **first-ever boot** before `revalidateFlags` resolves, since the key is absent from `LAUNCHED_FLAG_DEFAULTS` (`useFeatureFlags.ts:45-`; `loadCachedFlags` is awaited at `App.tsx:96` so every later boot has it from first paint). In that state the whole `{merged ? …}` region including the row is not rendered, so no "Not set" is shown either; when `merged` flips, the zustand selector re-renders and react-query re-evaluates `enabled`. (b) `leagueId` null — but `canvasHost === 'flag'` itself requires `leagueId` (`TradesScreen.tsx:6084-6091`), so the calculator is not hosted at all. (c) `outlookHidden` false — the receipt covers (only when `trade.outlook_direction` is true and a directional value resolves) and renders its own line. (d) **Query in flight or errored** — `prefsQ.data` is `undefined` → the row reads "Not set" until data lands (F-1).

### R-2 — every review write invalidates `['league-prefs', leagueId]`

- `TeamReviewScreen.tsx:113` `const qc = useQueryClient();` (screen scope). `:159` `const savePrefs = useCallback(async (patch, action) => {` → `:162` `if (!leagueId) return false;` → `:177-179` `await saveLeaguePreferences(leagueId, { team_outlook: fallbackOutlook, ...patch })` — the ONE write site in the file (`git grep`) → `:185` `qc.invalidateQueries({ queryKey: ['league-prefs', leagueId] });` → `:200` deps `[leagueId, beat, emit, outlook, data, qc]`.
- **Callers, all three beats:** window Confirm `:287` `await savePrefs({ team_outlook: declared }, 'outlook_set')`; depth Save & continue `:299-302` `await savePrefs({ acquire_positions…, trade_away_positions… }, 'positions_set')`; plan beat `:274` `onSave={savePrefs}` → `Plan.commit` `:1093-1102` `const ok = await onSave({ team_outlook, acquire_positions, trade_away_positions }, action)`. The Plan's former `useQueryClient` + `if (ok) qc.invalidateQueries(...)` are gone (diff `-1019`, `-1085`), so each write invalidates exactly once.
- Observers refetch immediately: TradesHome (mounted beneath the pushed review — `TabNav.tsx:455-460, 506-509`, same `TradesStack`) holds active observers at `TradesScreen.tsx:1286` and `InLeagueCalculator.tsx:443`.

**Does NOT fire when:** `leagueId` is null (`:162`, returns before the write); the POST throws — control goes to `catch` (`:193-196`) and skips `:185`, which is correct since nothing changed server-side.

### R-3 — completion recorded on reaching the plan beat, and still on finish

- `:132` `const beat = beats[step];` → `:140-142` `useEffect(() => { if (beat === 'plan' && leagueId) markTeamReviewCompleted(leagueId); }, [beat, leagueId]);`. Sits above the early returns (`:202`, `:209`, `:216`) — hook order stable. `next()` (`:148-154`) advancing `step` to `beats.indexOf('plan')` re-renders with `beat === 'plan'` → effect fires → `markTeamReviewCompleted` (`TeamReviewEntryCard.tsx:55-57`) → `useTeamReviewCompletion.getState().mark(leagueId)`. Any exit afterwards (back gesture, header back `subScreenOptions('Team review','TradesHome')` at `TabNav.tsx:508`, tab bar) leaves the mark in place.
- Finish button kept: `:310` `testID="team-review.finish"` → `:341` `void markTeamReviewCompleted(leagueId as string);` → `:342` `nav.navigate('TradesHome')`. Second call is a no-op (`teamReviewCompletion.ts:70`).
- The server can never skip `plan`: `backend/team_review.py:589-595` only ever appends `divergence` and `partners` to `beats_skipped`.

**Does NOT fire when:** `beat` is `undefined` (`q` loading, `beats` empty — `:135-139`); `leagueId` null; the user exits before the plan beat (by design — operator ruling Q1). See F-2 for the league-switch edge.

### R-4 — the entry card sees the marker without a remount; persistence is read-merge-write

- **Store** `teamReviewCompletion.ts`: key `:27` `'ftf_team_review_completed'` (unchanged), sparse `{[leagueId]: true}` (unchanged). `mark` `:69-76`: `:70` guard (falsy id or already marked → return) → `:71` `set((s) => ({ byLeague: { ...s.byLeague, [leagueId]: true } }))` **synchronous** (zustand 5 `set` is sync) → `:72-75` `readStored().then((stored) => AsyncStorage.setItem(KEY, JSON.stringify({ ...stored, ...get().byLeague })))` — reads disk, merges memory over it, writes; `.catch` swallows. `hydrate` `:60-67`: returns resolved if already hydrated; otherwise one shared module-level promise (`:55`) that reads disk and sets `{ hydrated: true, byLeague: { ...stored, ...s.byLeague } }` — memory wins.
- **Race analysis.** (i) `mark(L)` before `hydrate` resolves: memory has L; hydrate merges disk under memory → L kept; mark's persist reads the same disk and writes disk ∪ memory → L on disk. (ii) two `mark`s for different leagues: each `setItem` serializes `get().byLeague` at write time, which already holds both. (iii) `readStored` never rejects (`:31-38` try/catch → `{}`), so `hydration` cannot stick in a rejected state. No path drops a league.
- **Card** `TeamReviewEntryCard.tsx`: `:70` `hydrated = useTeamReviewCompletion((s) => s.hydrated)`; `:71` `completed = useTeamReviewCompletion((s) => !!s.byLeague[leagueId])`; `:73-75` `hydrate()` once on mount; `:77-83` the "Not now" map still read once per `leagueId` (unchanged); `:97` `if (collapsed === null || !hydrated) return null;`; `:101` `if (collapsed || completed)` → row, label `:111` `'Team review · done'`, a11y `:108`.
- **Why the pop shows it:** TradesHome stays mounted beneath the pushed review (same `TradesStack`, `TabNav.tsx:455-460, 506-509`); `mark`'s `set` notifies the card's selector → re-render with `completed === true` before `nav.navigate('TradesHome')` (`:342`) or the back gesture lands. Persistence is decoupled, so the disk write cannot race the pop.
- **League switching:** the card's selector is keyed by TradesScreen's `leagueId` (`TradesScreen.tsx:458`, passed at `:7048`), the store map by league; FFV3's `true` never reads as Lakeview's.

**Does NOT fire when:** `trades.team_review` off or `leagueId` null → card not mounted (`TradesScreen.tsx:7047`); `hydrated` false or `collapsed === null` → null render until the AsyncStorage reads resolve; `mark('')` → no-op.

## Findings

### F-1: The row reads "Outlook · Not set" while the preferences fetch is in flight (and the previous league's name during a switch)
- Severity: minor
- Repro (code path): cold TradesHome mount → `TradesScreen.tsx:1286` and `InLeagueCalculator.tsx:443` share one in-flight fetch → `prefsQ.data === undefined` → `:952` renders `outlookDisplayName(undefined) ?? 'Not set'` = "Not set" until the response lands, then flips to the saved name. On a league switch `placeholderData: (prev) => prev` (`:448`) keeps the **previous league's** row (e.g. FFV3 "Contending" shown for a beat on Lakeview) until Lakeview's fetch resolves.
- Expected (R-1): "Not set" only for null/absent. Actual: also for "not loaded yet".
- Evidence: `InLeagueCalculator.tsx:443-449, 952`. The TradesScreen twin has the identical behavior (`:6913-6916`), and the PRD explicitly asked for the receipt's `placeholderData: prev` pattern (§3 R-1), so this is spec-conformant; flagged because the operator's checklist step 1 ("without relaunch") could catch the flash and misread it as the bug returning. A loading state (`prefsQ.isPending`) would close it; not fixed here per QA rules.

### F-2: Switching league from the global TopBar while on the plan beat marks the NEW league complete
- Severity: minor (edge case; requires a mid-review switch from the last beat)
- Repro: FFV3 → Team review → reach the plan beat → TopBar league cluster (mounted above the whole tab navigator, `TabNav.tsx:746`; `LeagueSwitcherSheet.tsx:51-53` switches and closes without navigating) → pick Lakeview → the review screen stays mounted, `leagueId` changes (`TeamReviewScreen.tsx:104-105`), `q` refetches, `step` is **not** reset, so once Lakeview's `beats` resolve with `beats[step] === 'plan'` the effect at `:140-142` fires with Lakeview's id → Lakeview's card reads "Team review · done" without a review. Deep-link switches (`MatchesScreen.tsx:584`) take the same path.
- Expected (R-3): completion recorded for the league that was reviewed. Actual: recorded for whichever league is active when `beat === 'plan'` becomes true.
- Evidence: `TeamReviewScreen.tsx:104-105, 132, 140-142`; no `setStep(0)` on `leagueId` change anywhere in the file. Pre-existing on the finish button (`:341` also reads the live session id), but the effect makes it automatic. Suggest keying the effect on the `leagueId` that was current when `step` advanced, or resetting `step` on league change.

### F-3: The new guard is shape-only — three semantic sabotages stay green
- Severity: minor (guard strength; none of these are PRD-named sabotages, so not a §5 failure)
- Repro: X6 `if (beat === 'plan' && leagueId && false)` → 15/0 (5a only requires the call within 3 lines of `=== 'plan'`). X7 `enabled: false` → 15/0 (guard 2 pins key + fn only; the builder's §6 admits this). X8 `outlookDisplayName(prefsQ.data?.inferred_outlook ?? prefsQ.data?.team_outlook)` → 15/0 — 1a only checks that the tokens `team_outlook` and `outlookDisplayName(` both appear in the block, so a row that prefers the **inference** (the #394 "an inference is not set" violation) passes.
- Expected: the build report's claim that guard 1 pins "derives from `team_outlook`". Actual: it pins token presence, not sole source.
- Evidence: `mobile/tests/check-outlook-row-source.js:76, 100-101, 179-181`. Cheap hardening for a later pass: assert the exact `outlookDisplayName(prefsQ.data?.team_outlook)` and `!/inferred_outlook/` inside the fallback block.

### F-4: PRD §4 doc rows outside the diff
- Severity: minor (process)
- Repro: `git diff --stat a8658cec..59236a18` — `mobile/src/state/README.md` (PRD §4 names it alongside `state/CLAUDE.md` for the new store; `grep teamReviewCompletion` on it returns nothing), `docs/feedback/items/423-*/status.md` and `424-*/status.md` (both still "planned"), `living-memory/TEST_LEDGER.md`, `CHANGELOG.md` are untouched. The status/ledger/changelog rows are plausibly ship-phase; the README row is a build-phase doc row the scope table should show as "updated" or "n/a because".
- Evidence: diff stat (13 files), `mobile/src/state/README.md` exists.

## TestFlight checklist (operator-run)

Preconditions: TestFlight build carrying `59236a18`; account with FFV3 and Lakeview linked; Lakeview has a saved outlook (the log shows `rebuilder`), FFV3 has one too. Note the F-1 flash: a sub-second "Not set" on first paint that resolves on its own is loading, not the bug; the bug is "Not set" that **stays**.

1. **TradesHome (Acquire landing)** → TopBar league cluster → switch to **Lakeview** → wait for the landing to settle. Expect: the row under "Show me around" reads **"Outlook · Rebuilding"** (whatever Lakeview has saved), not "Not set", with no relaunch.
2. **TradesHome** → the Team review entry. Expect: whatever state it was in before this build (full card, or "Team review · done" if the old code ever recorded it via Find my trades).
3. **TradesHome** → tap "Start team review" (or the row) → **TeamReview, window beat** → pick a **different** outlook than step 1 showed (e.g. Contending) → **Confirm**. Then **back out immediately** with the header back control (do not reach the plan beat). Expect on **TradesHome**: row reads "Outlook · Contending" **immediately** (R-2: window-beat write invalidated); entry is still the **full card** (plan beat not reached → not done).
4. **TradesHome** → open Team review again → **window beat** Confirm (any) → **depth beat** Save & continue → Skip through to the **plan beat** → on the plan beat tap a **third** outlook chip (e.g. Rebuilding) → leave with the **header back control** — NOT "Find my trades". Expect on **TradesHome**, without relaunch: row reads "Outlook · Rebuilding"; entry reads **"Team review · done"**.
5. Kill the app → relaunch → land on **TradesHome** on Lakeview. Expect: row still "Outlook · Rebuilding"; entry still "Team review · done" (store hydrated from `ftf_team_review_completed`).
6. **TradesHome** → tap the "Team review · done" row → run to the **plan beat** → tap **Find my trades**. Expect: back on TradesHome, entry still "done", row still current; no error, no duplicate toast.
7. TopBar → switch to **FFV3**. Expect: FFV3's own saved outlook in the row (never Lakeview's after the fetch settles) and FFV3's own done/not-done state. Switch back to **Lakeview**: Lakeview's values return.
8. A league **never reviewed** on this device (link a third league, or use a fresh install on a league with no saved outlook): **TradesHome** shows the **full** "Start team review" card and, with nothing declared, "Outlook · Not set" with a working **Change** that opens the DNA sheet. Save an outlook there → row updates without relaunch.
9. (F-2 probe, optional) On FFV3 reach the **plan beat**, then switch to Lakeview from the TopBar **without leaving the review**. Expect today: Lakeview's entry may read "done" — record what you see; this is the F-2 edge, not a regression of #423.
