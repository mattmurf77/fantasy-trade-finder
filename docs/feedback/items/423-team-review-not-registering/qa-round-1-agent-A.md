# QA round 1 — agent A — 2026-09-08

Group G-423 (#423 + #424). Spec: [prd.md](prd.md) §3 R-1…R-4, §5 guards, §8 checklist; rulings in [reconciliation-log.md](reconciliation-log.md); builder's claims in [build-report.md](build-report.md) (re-verified line by line below, not trusted). Diff under test: `git diff a8658cec..59236a18`.

## Summary: PASS (5 findings — all minor; none blocks ship)

Every requirement R-1…R-4 is proven by code-walk; every PRD guard goes RED under its named sabotage and green after revert; tsc, all 100 `check-*.js` suites and testid-lint are green on the build tip. The one app-behavior defect found (F-1) is an edge path the diff makes automatic (league switch while sitting on the review's plan beat). F-2/F-3 are guard blind spots I demonstrated with two extra sabotages; F-4 is a doc the PRD named and the diff missed; F-5 is a bounded loading-state ambiguity the orchestrator may choose to accept.

## Environment

- Worktree: detached at `59236a18` (build tip; `git log -1` = "G-423 docs: registry rows, config-reference fallback wording, build report with code-walk"). Base `a8658cec`. Tree clean before and after every sabotage (`git status --short` → 0 tracked changes).
- Node v24.14.1; `@tanstack/react-query` 5.101.0 (package pin `^5.99.2`); zustand `^5.0.12`. `mobile/node_modules` is a populated symlink to the parent worktree's install.
- No simulator, no Maestro, no captures (D-056). No backend change in the diff → `pytest` not in scope for this group (mobile-only diff; `git diff --stat` shows 13 files, none under `backend/`).
- Flags pinned from `config/features.json`: `trades.finder_hub` true (:14), `trade.outlook_direction` **false** (:67), `trades.team_review` true (:80), `calc.merged_layout` true (:93), `calc.inline_home` true (:95), `trades.edit_full_sheet` true (:230). `calc.merged_layout` is **not** in the baked `LAUNCHED_FLAG_DEFAULTS` (`mobile/src/state/useFeatureFlags.ts:45-112` lists only `calc.canvas_results` / `calc.results_push` under `calc.*`), so on a first-ever launch `merged` is false until cached or fetched flags load.

## Results

| Test | Verdict | Evidence |
|---|---|---|
| `cd mobile && npx tsc --noEmit` | PASS | exit 0 (46 s wall) |
| All `mobile/tests/check-*.js` (100 files, loop) | PASS | 100 PASS / 0 FAIL — full list captured in the run log; no failures by name |
| `bash mobile/scripts/testid-lint.sh` | PASS | `testid-lint OK`, exit 0 |
| PRD §5 #7 named suites | PASS | `check-team-review.js` 13/0 (incl. #10 single write site carrying `team_outlook:`), `check-team-review-depth.js` 8/0, `check-calc-merged-layout.js` all passed, `check-finder-conditions-reachable.js` 6/0, `check-inline-home.js` all passed |
| New guard `check-outlook-row-source.js` baseline | PASS | `15 passed, 0 failed` |
| Sabotage S1 — restore literal `Outlook · Not set` (`InLeagueCalculator.tsx:952`) | PASS (RED as claimed) | `13 passed, 2 failed` — `✗ 1a. fallback text derives from the saved team_outlook`, `✗ 1b. no literal "Outlook · Not set" line`; revert → 15/0 |
| Sabotage S2 — delete the `prefsQ` query (`:443-449`, replaced with `{ data: undefined }`) | PASS (RED) | `14/1` — `✗ 2. InLeagueCalculator queries ['league-prefs', leagueId] via getLeaguePreferences`; revert → green |
| Sabotage S3 — hand-copy the five-name table into the calculator and drop the import (`:30`) | PASS (RED) | `13/2` — `✗ 3a. InLeagueCalculator imports outlookDisplayName from ./OutlookBiasReceipt`, `✗ 3d. no hand-copied outlook name table outside the receipt`; revert → green |
| Sabotage S4 — remove `qc.invalidateQueries` from `savePrefs` (`TeamReviewScreen.tsx:185`) | PASS (RED) | `13/2` — `✗ 4a. every saveLeaguePreferences( caller invalidates ['league-prefs'`, `✗ 4b. TeamReviewScreen invalidates ['league-prefs', leagueId] INSIDE savePrefs`; revert → green |
| Sabotage S5 — delete the plan-beat effect (`:140-142`) | PASS (RED) | `14/1` — `✗ 5a. markTeamReviewCompleted fires in a beat === 'plan' context`; revert → green |
| Sabotage S6 — revert the card to a mount-only `readMap('ftf_team_review_completed')` (`TeamReviewEntryCard.tsx:70-75`) | PASS (RED) | `14/1` — `✗ 6a. TeamReviewEntryCard derives \`completed\` from useTeamReviewCompletion`; revert → green |
| Sabotage S6′ — delete the finish-button call (`:341`) | PASS (RED) | `14/1` — `✗ 5b. the finish handler still records completion`; revert → green |
| Sabotage S6″ — store persists to disk **before** `set(...)` (`teamReviewCompletion.ts:71-76` reordered) | PASS (RED) | `14/1` — `✗ 6c. store.mark sets memory synchronously before persisting`; revert → green |
| Sabotage S7 (QA extra) — keep the `hydrated` subscription, replace `completed` selector with `const completed = false` | **guard stays GREEN** → F-2 | `15 passed, 0 failed` on a build that can never show "done" |
| Sabotage S8 (QA extra) — row reads `team_outlook ?? inferred_outlook` | **guard stays GREEN** → F-3 | `15 passed, 0 failed` on a build that violates the #394 "inference is not set" ruling |
| R-1 outlook row reads the saved preference | PASS | code-walk §R-1 below |
| R-2 every review write invalidates | PASS | code-walk §R-2; exactly one `saveLeaguePreferences(` in the screen (`git grep` → `TeamReviewScreen.tsx:177` only) |
| R-3 completion on reaching plan + on finish | PASS (F-1 edge) | code-walk §R-3 |
| R-4 card reads the store synchronously; persistence read-merge-write | PASS | code-walk §R-4 |
| Hunt: second `saveLeaguePreferences(` site | PASS (none) | `git grep -n "saveLeaguePreferences("` → `api/league.ts:68` (def), `TradeDnaSheet.tsx:437`, `TeamReviewScreen.tsx:177`, `TradeFinderHubScreen.tsx:341`, `TradesScreen.tsx:1351`, `:6523` — each file also carries `invalidateQueries({ queryKey: ['league-prefs'` (`:444`, `:185`, `:353`, `:1362`/`:6533`) |
| Hunt: TradesHome T-1 gate untouched | PASS | `git diff a8658cec..59236a18 -- TradesScreen.tsx` touches only `:69` (import) and `:9838-9843` (alias); gate `:6909` `consolidateOn && !outlookReceiptShown && !firstRun && canvasHost !== 'flag'` byte-identical; `check-finder-conditions-reachable.js` #2 and `check-inline-home.js` #11 green |
| Hunt: stale closure / deps in the new `useEffect` | PASS | `TeamReviewScreen.tsx:140-142` deps `[beat, leagueId]`; `beat` is a string from `beats[step]` (`:132`), `markTeamReviewCompleted` is a module import (`:20`) — nothing captured that can go stale; effect declared before the early returns at `:202/:209/:216`, so hook order is stable |
| Hunt: `hydrate` vs `mark` race | PASS | `teamReviewCompletion.ts:60-68` merges `{ ...stored, ...s.byLeague }` (memory wins); `:69-77` `mark` sets memory first (`:71`) then `readStored().then(setItem({ ...stored, ...get().byLeague }))` (`:72-75`) — read-merge-write, so neither order can drop a league; functional `set` updates are synchronous in zustand |
| Hunt: `enabled: merged && !!leagueId` leaving "Not set" | PASS with caveat → F-5 | while `merged` is false the row is not rendered at all (`InLeagueCalculator.tsx:913` `{merged ? (`); when true, the observer shares TradesHome's already-running `['league-prefs', leagueId]` query (`TradesScreen.tsx:1285-1291`, `enabled: !!leagueId`), so cached data is served immediately; only a cold cache leaves `prefsQ.data` undefined for one round-trip |
| Hunt: league switching keys query + store | PASS | query key carries `leagueId` (`:444`); `TradeBuildCanvas.tsx:211-213` remounts the calculator with `key={\`${leagueId}-…\`}` so `placeholderData: (prev) => prev` (`:448`) cannot carry FFV3's value onto Lakeview (new observer ⇒ `prev` undefined); store is a global sparse map keyed by league id, card selector `!!s.byLeague[leagueId]` (`TeamReviewEntryCard.tsx:71`) re-evaluates on the prop change |
| Docs: `docs/config-reference.md:371` reworded | PASS | diff shows "reads the saved outlook; 'Not set' only when none" |
| Docs: `mobile/src/state/README.md` | FAIL → F-4 | not in diff; PRD §4 lists it |

## Code-walk proofs

### R-1 — the merged landing's outlook row reads `['league-prefs', leagueId]` and maps `team_outlook` through the shared table

Host chain (unchanged, verified at tip): `trades.finder_hub` ⇒ `TradesHome` guided (`TabNav.tsx:457`); `calc.inline_home` ⇒ `canvasHost === 'flag'`; `TradesScreen.tsx:8006` mounts `<TradeBuildCanvas leagueId={leagueId!} …>` → `TradeBuildCanvas.tsx:211-213` `<InLeagueCalculator key={…leagueId…} leagueId={leagueId}>`. TradesHome's own row is suppressed by `:6909` (`canvasHost !== 'flag'`), so the calculator's `calc.outlook-row` is the only outlook surface.

1. Query — `InLeagueCalculator.tsx:443-449`: `useQuery({ queryKey: ['league-prefs', leagueId], queryFn: () => getLeaguePreferences(leagueId), enabled: merged && !!leagueId, staleTime: 5*60_000, placeholderData: (prev) => prev })`. `getLeaguePreferences` imported `:6` from `../api/league` (`league.ts:62-66`, returns `LeaguePreferences` whose `team_outlook: Outlook` is the declared value, `:30`; `inferred_outlook` is a separate optional field `:50`). Same key as `TradesScreen.tsx:1286`, `OutlookBiasReceipt.tsx:108`, `TeamReviewScreen.tsx:1052`, `TradeDnaSheet.tsx:444`, `TradeFinderHubScreen.tsx:353`.
2. Render — `:913` `{merged ? (` → `:938` `<View testID="calc.outlook-row">` → `:939-942` `<OutlookBiasReceipt onHiddenChange={setOutlookHidden}>` → `:943` `{outlookHidden ? (` → `:950` `<View testID="calc.outlook-fallback">` → `:952` `` {`Outlook · ${outlookDisplayName(prefsQ.data?.team_outlook) ?? 'Not set'}`} ``. Only `team_outlook` is read; `inferred_outlook` is never referenced in the file (`grep -c inferred_outlook` → 0 on the clean tree).
3. Why the fallback is the live branch in prod — `OutlookBiasReceipt.tsx:105` `directionOn = useFlag('trade.outlook_direction')` (false, `features.json:67`) → `:110` its query is disabled → `:120` `hidden = !outlookReceiptCovers(false, …)` (`:70-78` returns false when `!directionOn`) → `onHiddenChange(true)` → `outlookHidden` true (`:317` state).
4. Name table — `OutlookBiasReceipt.tsx:61-63` `outlookDisplayName(value) = value ? OUTLOOK_DISPLAY_NAME[value] ?? null : null`; `:50-56` table: `championship/contender/rebuilder/jets` → `LEAN.<k>.name` (`:34-39`: All-in / Contending / Rebuilding / Tanking), `not_sure: 'Not sure'`. Null, undefined, and unknown strings all yield `null` → the call site's `?? 'Not set'` is the only source of that string. Operator repro: server `team_outlook=rebuilder` → `'Rebuilding'` → `Outlook · Rebuilding`.
5. TradesScreen twin (ruling Q2) — `TradesScreen.tsx:69` imports `OUTLOOK_DISPLAY_NAME`; `:9843` `const OUTLOOK_FALLBACK_LABEL = OUTLOOK_DISPLAY_NAME;`; call site `:6913-6917` untouched (`prefsQuery.data?.team_outlook ? OUTLOOK_FALLBACK_LABEL[…] : 'Not set'`). tsc accepts the `Readonly<Record<string,string>>` index.

**Does not fire when:** `calc.merged_layout` is false (row not rendered at all — including the first-ever launch before flags load, see Environment); `leagueId` is empty (prop is `string`, `:63`; TradesScreen only mounts the canvas with `leagueId!`); `trade.outlook_direction` is true AND a directional outlook resolves (then the receipt covers and the fallback is hidden — by design); the prefs GET has not yet resolved on a cold cache (F-5); the server value is a string outside the five known (reads "Not set" — builder-documented deviation, acceptable).

### R-2 — every preference write in TeamReviewScreen invalidates `['league-prefs', leagueId]`

- `TeamReviewScreen.tsx:113` `const qc = useQueryClient();` (screen scope).
- `:159-200` `savePrefs = useCallback(async (patch, action) => { … await saveLeaguePreferences(leagueId, { team_outlook: fallbackOutlook, ...patch }) (:177-179); qc.invalidateQueries({ queryKey: ['league-prefs', leagueId] }) (:185); … }, [leagueId, beat, emit, outlook, data, qc]) (:200)`. The invalidation is inside the `try` after the awaited write, so it runs only on a landed write; a thrown write goes to `catch` (`:193-197`) and returns false without invalidating — correct (nothing changed on the server).
- Window beat — `:286-289` Confirm `onPress` → `await savePrefs({ team_outlook: declared }, 'outlook_set')` → `next()`.
- Depth beat — `:299-303` Save & continue → `await savePrefs({ acquire_positions, trade_away_positions }, 'positions_set')` → `next()`.
- Plan beat — `:274` `<Plan onSave={savePrefs}>`; `Plan.commit` `:1093-1104` → `await onSave({ team_outlook, acquire_positions, trade_away_positions }, action)`; its former `useQueryClient` and `if (ok) qc.invalidateQueries(...)` were removed (diff), so each write invalidates exactly once.
- Cross-file: all four other writers already invalidate (table in Results). Guard 4a walks `src/` for `saveLeaguePreferences(` callers; guard 4b isolates `const savePrefs = useCallback(` … `}, [`.

**Does not fire when:** the POST rejects (the row keeps the last-known server value — correct); `leagueId` is null (`:162` early `return false`; the screen also renders "Pick a league first" at `:202-208` so no beat is reachable).

### R-3 — completion recorded when the plan beat is reached, and still on the finish button

- `:132` `const beat = beats[step];` where `beats` (`:126-131`) = server `meta.beats` minus `meta.beats_skipped`. Backend `team_review.py:590-596` only ever skips `divergence` and `partners`, so `plan` is always the last beat.
- `:140-142` `useEffect(() => { if (beat === 'plan' && leagueId) markTeamReviewCompleted(leagueId); }, [beat, leagueId]);` — runs on the render in which `beat` first equals `'plan'`, whichever control advanced `step` (`next()` `:148-154` from Next, Skip this `:353-357`, Confirm, Save & continue). Every exit after that render (back control, tab bar, header) leaves the mark in place.
- Finish button — `:310` `testID="team-review.finish"` → `:341` `void markTeamReviewCompleted(leagueId as string);` → `:342` `nav.navigate('TradesHome')`. Second call is a no-op: `teamReviewCompletion.ts:70` `if (!leagueId || get().byLeague[leagueId]) return;`.
- `markTeamReviewCompleted` — `TeamReviewEntryCard.tsx:55-57` → `useTeamReviewCompletion.getState().mark(leagueId)`; import site `TeamReviewScreen.tsx:20` unchanged.

**Does not fire when:** the review never reaches `plan` (user backs out on standing/window/depth/divergence/partners — by the operator's ruling this is *not* completion); `data` is still loading or errored (`beats` = `[]`, `beat` undefined, screen shows `team-review.loading`/`team-review.error` at `:209-224`); `leagueId` null. **Fires when it should not:** F-1 (league switch with `step` parked on the plan index).

### R-4 — the entry card reads the completion store synchronously; persistence is read-merge-write

- Store `mobile/src/state/teamReviewCompletion.ts`: `:27` key `'ftf_team_review_completed'` (same key and same `{[leagueId]: true}` shape the card wrote before → no migration); `:31-38` `readStored` (try/catch → `{}`); `:60-68` `hydrate` idempotent (`if (get().hydrated) return`; shared module promise `:55`) merging `{ ...stored, ...s.byLeague }` so an early `mark` survives; `:69-77` `mark`: guard → `:71` synchronous `set` → `:72-75` `readStored().then(stored => setItem(KEY, { ...stored, ...get().byLeague }))` fire-and-forget, `.catch` swallowed `:76`.
- Card `TeamReviewEntryCard.tsx`: `:70` `hydrated` selector; `:71` `completed = useTeamReviewCompletion((s) => !!s.byLeague[leagueId])`; `:73-75` `hydrate()` once on mount; `:77-83` the "Not now" map still read once per `leagueId` (unchanged); `:97` `if (collapsed === null || !hydrated) return null;`; `:101` `if (collapsed || completed)` → row with `:108` a11y label and `:111` `'Team review · done'`.
- Why it shows on the pop back: TradesHome (`TabNav.tsx:457`) and TeamReview (`:506-509`) are both `TradesStack` screens; TradesHome stays mounted beneath the push, so the card's zustand selector re-renders on `mark` while the review is still on top; `nav.navigate('TradesHome')` / back pops to that already-updated instance. No focus hook, no re-read, no dependence on the disk write.
- Relaunch: the card's mount effect calls `hydrate()` → `readStored()` → the disk mirror written by `mark` → `completed` true. `ftf_team_review_completed` is AsyncStorage, not the react-query persister, so `PERSIST_KEYS` (`App.tsx:61`) is irrelevant to it.

**Does not fire when:** `trades.team_review` is false or `leagueId` null (`TradesScreen.tsx:7047` `{teamReviewOn && leagueId ? <TeamReviewEntryCard …>}` — card not mounted, nothing to show); AsyncStorage `getItem` never resolves (card renders null forever — same as the pre-existing `collapsed === null` gate); both `getItem` and `setItem` fail (memory still shows done this session; next launch falls back to the full card — documented tradeoff `:49-54`).

## Findings

### F-1: Switching league from the TopBar while parked on the review's `plan` beat marks the *new* league completed without it being gone through
- Severity: minor (edge path; requires opening the switcher from inside the review)
- Repro (code path): open Team review on league A → advance to the plan beat (`step` = index of `'plan'`, e.g. 5) → open the global `TopBar` league switcher (`TabNav.tsx:746` mounts `<TopBar />` above every tab stack; `TopBar.tsx` has no route-based hide, `LeagueSwitcherSheet` at `:424`) → pick league B. `useSession.league` changes → `TeamReviewScreen.tsx:105-106` `leagueId` = B; `step` state (`:108`) is **not** reset; `q` refetches `['team-review', B]`; while loading `beats=[]` (effect no-op); once B's data lands, `beats[step]` — for a league with the same beat count — is `'plan'` again → `:140-142` fires with `leagueId === B` → `mark(B)` → B's entry card reads "Team review · done" although B's review was never walked.
- Expected (R-3 / operator ruling): completion means *this league's* plan beat was reached. Actual: B is marked on arrival at a beat the user did not step through. Before this diff the same league switch only dropped the user on B's plan beat (pre-existing quirk); the button-only write needed a tap to mis-mark, so the effect makes the mis-mark automatic.
- Evidence: `TeamReviewScreen.tsx:108` (`useState(0)` with no reset on `leagueId`), `:132`, `:140-142`; `TabNav.tsx:746`. Suggested (not applied): reset `step` to 0 on `leagueId` change, or key the effect on the league the beats were loaded for.

### F-2: Guard 6a passes when `completed` is hard-wired `false` while the store is still subscribed for `hydrated`
- Severity: minor (guard weakness, no app defect)
- Repro: replace `TeamReviewEntryCard.tsx:71` with `const completed = false;` → `node tests/check-outlook-row-source.js` → `15 passed, 0 failed`. The 6a regex `useTeamReviewCompletion\(\s*\(s\)\s*=>` is satisfied by the `hydrated` selector on `:70`, and `\bcompleted\b` / `collapsed || completed` remain textually present.
- Expected (PRD §5 #6): "derives `completed` from `useTeamReviewCompletion`". Actual: the guard pins that *some* selector exists, not the `completed` one. Suggest pinning `completed = useTeamReviewCompletion((s) => !!s.byLeague[leagueId])` (or `byLeague\[leagueId\]` inside a selector).

### F-3: Guard 1a passes when the row falls back to `inferred_outlook`
- Severity: minor (guard weakness; the #394 "an inference is not set" ruling is unpinned)
- Repro: change `InLeagueCalculator.tsx:952` to `outlookDisplayName(prefsQ.data?.team_outlook ?? prefsQ.data?.inferred_outlook)` → guard `15 passed, 0 failed`. 1a only requires `outlookDisplayName(` and `team_outlook` inside the `calc.outlook-fallback` block.
- Expected (R-1, "Declared values only; an inference is not 'set'"): a guard that RED-lines `inferred_outlook` inside the fallback block. Actual: nothing pins it. The shipped code is correct (`inferred_outlook` does not appear in the file); only the guard is short.

### F-4: `mobile/src/state/README.md` not updated (PRD §4 named it)
- Severity: minor (docs)
- Evidence: not in `git diff a8658cec..59236a18 --stat`. README's zustand-store row still says "(12)" and lists neither `teamReviewCompletion` nor `presentationDismissed`; the Persistence-keys table (README ~:37-48) has no `ftf_team_review_completed` row. `mobile/src/state/CLAUDE.md:40` was updated correctly. Note also README's rule "persisted state is user-scoped (`<user_id>` in the key)" — the reused key is device-scoped by design (no-migration decision, `teamReviewCompletion.ts:18-22`); worth one line in the README so the exception is visible.

### F-5: Loading state renders as "Outlook · Not set" for one round-trip on a cold cache
- Severity: minor (bounded; orchestrator may accept as-is)
- Repro (code path): cold cache — first launch of the session, or after `gcTime` (30 min, `queryClient.ts`) with `league-prefs` outside `PERSIST_KEYS` (`App.tsx:61`) — the calculator renders with `prefsQ.data === undefined` until the GET resolves; `:952` `outlookDisplayName(undefined) ?? 'Not set'` → "Not set" for a league that has a saved outlook. Mitigations already present: TradesHome's `prefsQuery` (`TradesScreen.tsx:1285-1291`) starts the same fetch on mount; the fallback row itself appears one effect-tick after the receipt reports hidden. On a warm cache (the operator's repro: 158 B GET at 17:58:47 already cached) there is no flash.
- Expected (R-1 "'Not set' only for null/absent"): arguably satisfied — `undefined` is absent. Flagging because a tester on a cold launch may report the old symptom for ~1 s; the checklist step 3 below says what to expect.

### Observations (not findings)
- `TeamReviewScreen.tsx:66-72` `OUTLOOK_LABEL` is a third name table with *different* words for the review's own chips (`'Contender'`, `'Rebuilder'`, `'Full teardown'`) — a user picks "Rebuilder" on the plan beat and the landing row reads "Rebuilding". Out of scope for G-423 (guard 3d deliberately checks only the calculator and TradesScreen), but the "one vocabulary" claim in the receipt comment is narrower than it reads.
- `docs/feedback/items/423-*/status.md`, `424-*/status.md`, `living-memory/TEST_LEDGER.md`, `CHANGELOG.md` are PRD §4 items not in this diff — presumed Phase 5.
- `TeamReviewEntryCard.tsx:67` `collapsed` is not reset to `null` on a `leagueId` change, so the *old* league's collapsed state renders until `readMap` resolves (pre-existing, untouched by this diff; the new `hydrated` gate does not change it).

## TestFlight checklist (operator-run)

Preconditions: build ≥ this sha; account with FFV3 and Lakeview linked; Lakeview has a saved outlook (server row `team_outlook=rebuilder` per the log); a third league that has never been reviewed on this device (or clear the app's data for step 9).

1. **TopBar → league switcher → Lakeview.** Screen: Trades tab, Acquire landing (TradesHome, merged calculator). Under "Show me around", the outlook row — **expect** `Outlook · Rebuilding` (the saved value), *not* "Not set", without relaunch. If the app was cold-launched a moment ago, a ≤1 s "Not set" while the preferences load is F-5, acceptable; steady state must read the saved name.
2. **Tap the Team review entry** (full card "Start team review" or the row). Screen: Team review — standing beat. **Expect** the review opens on Lakeview's data.
3. **Advance to the window beat, pick a different outlook (e.g. All-in) and tap Confirm.** **Expect** it advances to the depth beat; no error.
4. **Immediately leave with the header back control** (do NOT reach the plan beat). Screen: Acquire landing. **Expect** the outlook row now reads `Outlook · All-in` (R-2: the window-beat write invalidated the row) and the Team review entry is **still the full card** — completion requires reaching the plan beat (R-3 ruling).
5. **Re-open Team review, tap "Skip this" through to the plan beat.** Screen: plan beat ("Here's every dial…"). **Expect** the Window chips show All-in selected. **Tap the Rebuilder chip.** **Expect** it selects with no inline failure.
6. **Leave with the header back control** (NOT "Find my trades"). Screen: Acquire landing. **Expect** the outlook row reads `Outlook · Rebuilding` **and** the entry is minimized to `Team review · done` — both without relaunch or league switch (R-1, R-3, R-4).
7. **Kill and relaunch the app; stay on Lakeview.** Screen: Acquire landing. **Expect** `Outlook · Rebuilding` (after the preferences load) and `Team review · done` (store hydrated from `ftf_team_review_completed`).
8. **Tap the "Team review · done" row → advance to the plan beat → tap "Find my trades".** Screen: Acquire landing. **Expect** unchanged: still `done`, row still `Rebuilding`; no double-toast, no error.
9. **Switch to FFV3 (reviewed on 2026-09-06 under the old build).** **Expect** FFV3's own saved outlook name in the row (whatever was confirmed there), and — because the old build wrote the same device key when "Find my trades" was tapped — `Team review · done` if that button was used, else the full card. Either outcome is correct; a *Lakeview* value or state showing on FFV3 is a failure.
10. **Switch to a league never reviewed on this device.** **Expect** the full "Start team review" card, and `Outlook · Not set` only if that league has no saved outlook (a saved `not_sure` must read `Outlook · Not sure`).
11. **F-1 probe (optional):** open Team review on any league, advance to the plan beat, then open the TopBar switcher *from inside the review* and pick another league. Back out to the landing. **Observe** whether the second league's entry reads `done` without having been walked — report the result either way.
12. **Regression:** on the plan beat change chasing/shopping positions; back out. **Expect** no crash, and TradesHome's finder still runs. Tap **Change** on the outlook row. **Expect** the Trade DNA sheet opens over the landing; saving there updates the row immediately.
