# G-423 build report — mobile (#423 + #424)

Date: 2026-09-08 · Branch `feat/fb423-outlook-row-and-marker` (base `a8658cec`) · Spec: [prd.md](prd.md) §3 R-1…R-4, rulings in [reconciliation-log.md](reconciliation-log.md). Line numbers are post-edit on this branch.

## 1. Code-walk — the outlook row's read path after the fix (#424, R-1)

1. **Query.** `InLeagueCalculator.tsx:443-449` — `prefsQ = useQuery({ queryKey: ['league-prefs', leagueId], queryFn: () => getLeaguePreferences(leagueId), enabled: merged && !!leagueId, staleTime: 5*60_000, placeholderData: prev })`. `getLeaguePreferences` imported at `:6` from `../api/league` (`league.ts:62`, returns `LeaguePreferences` with `team_outlook: Outlook` at `:30`). Same key as `OutlookBiasReceipt.tsx:83-84`, `TradesScreen.tsx:1286`, `TeamReviewScreen.tsx` Plan (`prefsQ`, `refetchOnMount:'always'`).
2. **Render.** `InLeagueCalculator.tsx:943` `{outlookHidden ? (` → `:950` `<View testID="calc.outlook-fallback">` → `:952` `` {`Outlook · ${outlookDisplayName(prefsQ.data?.team_outlook) ?? 'Not set'}`} ``. Still inside the `{merged ? (` region opened at `:913` (guard `check-calc-merged-layout.js` #5 green).
3. **Name.** `outlookDisplayName` imported at `:30` from `./OutlookBiasReceipt`; defined `OutlookBiasReceipt.tsx:61-63` — `value ? OUTLOOK_DISPLAY_NAME[value] ?? null : null`. Table `:50-56`: `championship/contender/rebuilder/jets` → `LEAN.<k>.name` (`:34-39`: All-in / Contending / Rebuilding / Tanking), `not_sure: 'Not sure'`. Null/absent/unknown → `null` → the call site's `?? 'Not set'` is the only source of that string. Declared value only — `inferred_outlook` is never read here (#394 ruling).
4. **Operator repro:** Lakeview's server row `team_outlook=rebuilder` → GET `/api/league/preferences` → `prefsQ.data.team_outlook === 'rebuilder'` → `OUTLOOK_DISPLAY_NAME.rebuilder === LEAN.rebuilder.name === 'Rebuilding'` → row text `Outlook · Rebuilding`.
5. **TradesScreen twin (ruling Q2).** `TradesScreen.tsx:69` imports `OUTLOOK_DISPLAY_NAME`; `:9843` `const OUTLOOK_FALLBACK_LABEL = OUTLOOK_DISPLAY_NAME;`; call site `:6915` untouched. The T-1 gate at `:6909` is byte-identical (`check-finder-conditions-reachable.js` #2, `check-inline-home.js` #11 green).

## 2. Code-walk — invalidation after each preference write (#424 latent, R-2)

- `TeamReviewScreen.tsx:113` `const qc = useQueryClient();` (screen level, new).
- `:159` `const savePrefs = useCallback(async (patch, action) => {` → `:177-179` `await saveLeaguePreferences(leagueId, { team_outlook: fallbackOutlook, ...patch })` (the ONE write site; literal still leads with `team_outlook:` — `check-team-review.js` #10 green) → `:185` `qc.invalidateQueries({ queryKey: ['league-prefs', leagueId] });` → `:200` deps `[leagueId, beat, emit, outlook, data, qc]`.
- Callers: window Confirm (`:287` `savePrefs({ team_outlook: declared }, 'outlook_set')`), depth Save & continue (`:299-302`), plan-beat `commit` (`Plan`, `onSave(...)` = `savePrefs`). The plan beat's own `if (ok) qc.invalidateQueries(...)` and its `useQueryClient` were removed (redundant; would have double-refetched). Every successful write now invalidates once; readers on the key: `TradesScreen.tsx:1286`, `OutlookBiasReceipt.tsx:83`, `InLeagueCalculator.tsx:444`, `TradeDnaSheet`, `TradeFinderHubScreen`, the Plan beat.
- Cross-file: all four `saveLeaguePreferences(` callers (`TradeDnaSheet.tsx:437`, `TradeFinderHubScreen.tsx:341`, `TradesScreen.tsx:1351/6523`, `TeamReviewScreen.tsx:177`) invalidate `['league-prefs'` (guard 4a).

## 3. Code-walk — completion write on reaching the plan beat (#423, R-3)

- `TeamReviewScreen.tsx:132` `const beat = beats[step];` → `:140-142` `useEffect(() => { if (beat === 'plan' && leagueId) markTeamReviewCompleted(leagueId); }, [beat, leagueId]);` — sits before the early returns (`:202+`), so the hook order is stable. `next()` (`:148-154`) advancing to `beats[n] === 'plan'` re-renders with `beat === 'plan'` → effect fires → completion recorded regardless of how the user leaves.
- Finish button kept: `:310` `testID="team-review.finish"` → `:341` `void markTeamReviewCompleted(leagueId as string);` → `:342` `nav.navigate('TradesHome')`. Second call is a no-op (`teamReviewCompletion.ts:70` early return).
- `markTeamReviewCompleted` (`TeamReviewEntryCard.tsx:55-57`) → `useTeamReviewCompletion.getState().mark(leagueId)`.

## 4. Code-walk — the store and the store-driven card read (R-4)

- **Store** `mobile/src/state/teamReviewCompletion.ts`: key `:27` `TEAM_REVIEW_DONE_KEY = 'ftf_team_review_completed'` (unchanged key, unchanged sparse `{[leagueId]: true}` shape — no migration). `mark` `:69-76`: guard → `:71` `set(...)` **synchronously** → `:72-75` `readStored().then(stored => AsyncStorage.setItem(KEY, JSON.stringify({ ...stored, ...get().byLeague })))` fire-and-forget (read-merge-write, so a mark racing hydrate cannot drop other leagues). `hydrate` `:60-67`: idempotent, shares one promise, merges `{ ...stored, ...s.byLeague }` so an early `mark` wins.
- **Card** `TeamReviewEntryCard.tsx`: `:70` `hydrated = useTeamReviewCompletion(s => s.hydrated)`; `:71` `completed = useTeamReviewCompletion(s => !!s.byLeague[leagueId])`; `:73-75` `hydrate()` once on mount; `:77-84` own "Not now" map still read once per `leagueId` (unchanged behaviour); `:97` `if (collapsed === null || !hydrated) return null;`; `:101` `if (collapsed || completed) {` → row `:108/:111` reads `completed` for label/a11y.
- **Why it now shows on the way back:** TradesHome (and its card) stays mounted beneath the pushed review (`TabNav.tsx:455-460`); `mark` mutates the zustand store → the card's selector re-renders immediately → `completed === true` → "Team review · done" is already on screen when the pop lands. No focus hook, no re-read, no race with the disk write.

## 5. Evidence

- `npx tsc --noEmit` — exit 0.
- `node tests/check-outlook-row-source.js` — 15 passed, 0 failed. RED by sabotage (apply → run → revert via `git checkout`, tree clean after each):
  - S1 restore literal `Outlook · Not set` → `13 passed, 2 failed`: ✗ 1a, ✗ 1b
  - S2 delete the prefs query → `14/1`: ✗ 2
  - S3 hand-copy the table into the calculator → `13/2`: ✗ 3a, ✗ 3d
  - S4 remove the `savePrefs` invalidation → `13/2`: ✗ 4a, ✗ 4b
  - S5 delete the plan-beat completion call → `14/1`: ✗ 5a
  - S6 revert the card to a mount-only read → `14/1`: ✗ 6a
- Existing suites: `check-team-review.js` 13/0, `check-calc-merged-layout.js` exit 0, `check-finder-conditions-reachable.js` 6/0, `check-inline-home.js` exit 0, `check-team-review-depth.js` 8/0, `scripts/testid-lint.sh` OK.
- Runtime proof: PRD §8 TestFlight checklist (operator).

## 6. Deviations from the PRD

- **Query `enabled: merged && !!leagueId`** (PRD said `!!leagueId`). The fallback only renders under `merged`, and the component's documented contract is "OFF is byte-identical to the shipped stacked page"; gating the fetch keeps the flag-off page request-identical. Moot in prod (`calc.merged_layout` is true for all users). Guard 2 pins key + fn, not the `enabled` clause.
- **`outlookDisplayName` returns `null` for an unknown value** (not only null/absent), so an enum string this table does not know reads "Not set" rather than `undefined`. TradesScreen's aliased map keeps its previous `undefined`-for-unknown behaviour at the untouched call site.
- **TradesScreen import line `:69`** was touched in addition to the `:9837-9849` alias — the alias cannot reference the export without it (one added line).
- Plan's now-unused `const qc = useQueryClient()` removed alongside its redundant invalidation (would otherwise be an unused local).
