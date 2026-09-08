# G-423 build report — mobile (#423 + #424)

Date: 2026-09-08 · Branch `feat/fb423-outlook-row-and-marker` (base `a8658cec`; round-1 resolution `cb893b09`) · Spec: [prd.md](prd.md) §3 R-1…R-4, rulings in [reconciliation-log.md](reconciliation-log.md). Line numbers are post-edit on this branch; §3 and §5 were updated after the Phase 4 resolution (`TeamReviewScreen.tsx` lines shifted by +20 from the build tip).

## 1. Code-walk — the outlook row's read path after the fix (#424, R-1)

1. **Query.** `InLeagueCalculator.tsx:443-449` — `prefsQ = useQuery({ queryKey: ['league-prefs', leagueId], queryFn: () => getLeaguePreferences(leagueId), enabled: merged && !!leagueId, staleTime: 5*60_000, placeholderData: prev })`. `getLeaguePreferences` imported at `:6` from `../api/league` (`league.ts:62`, returns `LeaguePreferences` with `team_outlook: Outlook` at `:30`). Same key as `OutlookBiasReceipt.tsx:83-84`, `TradesScreen.tsx:1286`, `TeamReviewScreen.tsx` Plan (`prefsQ`, `refetchOnMount:'always'`).
2. **Render.** `InLeagueCalculator.tsx:943` `{outlookHidden ? (` → `:950` `<View testID="calc.outlook-fallback">` → `:952` `` {`Outlook · ${outlookDisplayName(prefsQ.data?.team_outlook) ?? 'Not set'}`} ``. Still inside the `{merged ? (` region opened at `:913` (guard `check-calc-merged-layout.js` #5 green).
3. **Name.** `outlookDisplayName` imported at `:30` from `./OutlookBiasReceipt`; defined `OutlookBiasReceipt.tsx:61-63` — `value ? OUTLOOK_DISPLAY_NAME[value] ?? null : null`. Table `:50-56`: `championship/contender/rebuilder/jets` → `LEAN.<k>.name` (`:34-39`: All-in / Contending / Rebuilding / Tanking), `not_sure: 'Not sure'`. Null/absent/unknown → `null` → the call site's `?? 'Not set'` is the only source of that string. Declared value only — `inferred_outlook` is never read here (#394 ruling).
4. **Operator repro:** Lakeview's server row `team_outlook=rebuilder` → GET `/api/league/preferences` → `prefsQ.data.team_outlook === 'rebuilder'` → `OUTLOOK_DISPLAY_NAME.rebuilder === LEAN.rebuilder.name === 'Rebuilding'` → row text `Outlook · Rebuilding`.
5. **TradesScreen twin (ruling Q2).** `TradesScreen.tsx:69` imports `OUTLOOK_DISPLAY_NAME`; `:9843` `const OUTLOOK_FALLBACK_LABEL = OUTLOOK_DISPLAY_NAME;`; call site `:6915` untouched. The T-1 gate at `:6909` is byte-identical (`check-finder-conditions-reachable.js` #2, `check-inline-home.js` #11 green).

## 2. Code-walk — invalidation after each preference write (#424 latent, R-2)

- `TeamReviewScreen.tsx:113` `const qc = useQueryClient();` (screen level, new).
- `:179` `const savePrefs = useCallback(async (patch, action) => {` → `:197-199` `await saveLeaguePreferences(leagueId, { team_outlook: fallbackOutlook, ...patch })` (the ONE write site; literal still leads with `team_outlook:` — `check-team-review.js` #10 green) → `:205` `qc.invalidateQueries({ queryKey: ['league-prefs', leagueId] });` → `:220` deps `[leagueId, beat, emit, outlook, data, qc]`.
- Callers: window Confirm (`:307` `savePrefs({ team_outlook: declared }, 'outlook_set')`), depth Save & continue (`:319-322`), plan-beat `commit` (`Plan`, `onSave(...)` = `savePrefs`). The plan beat's own `if (ok) qc.invalidateQueries(...)` and its `useQueryClient` were removed (redundant; would have double-refetched). Every successful write now invalidates once; readers on the key: `TradesScreen.tsx:1286`, `OutlookBiasReceipt.tsx:83`, `InLeagueCalculator.tsx:444`, `TradeDnaSheet`, `TradeFinderHubScreen`, the Plan beat.
- Cross-file: all four `saveLeaguePreferences(` callers (`TradeDnaSheet.tsx:437`, `TradeFinderHubScreen.tsx:341`, `TradesScreen.tsx:1351/6523`, `TeamReviewScreen.tsx:197`) invalidate `['league-prefs'` (guard 4a).

## 3. Code-walk — completion write on reaching the plan beat (#423, R-3)

- `TeamReviewScreen.tsx:152` `const beat = beats[step];` → `:160-162` `useEffect(() => { if (beat === 'plan' && leagueId) markTeamReviewCompleted(leagueId); }, [beat, leagueId]);` — sits before the early returns (`:222+`), so the hook order is stable. `next()` (`:168-174`) advancing to `beats[n] === 'plan'` re-renders with `beat === 'plan'` → effect fires → completion recorded regardless of how the user leaves.
- Finish button kept: `:330` `testID="team-review.finish"` → `:361` `void markTeamReviewCompleted(leagueId as string);` → `:362` `nav.navigate('TradesHome')`. Second call is a no-op (`teamReviewCompletion.ts:70` early return).
- **League switch while on the plan beat (round-1 A F-1 / B F-2, fixed `cb893b09`).** `:127` `const [stepLeague, setStepLeague] = useState(leagueId);` → `:128` `if (stepLeague !== leagueId) {` → `:129-135` `setStepLeague(leagueId); setStep(0); setOutlook(null); setAcquire([]); setShed([]); setScoped(null); done.current = new Set();`. This runs in the render phase: React discards that render's output and re-renders with `step === 0` before committing, so the commit in which `leagueId` becomes B sees `beat === beats[0]` (`'standing'`, or `undefined` while B's review loads) — never `'plan'`. Trace for the QA repro: A on plan (`step` = 5) → TopBar switch → render with `leagueId = B`, `stepLeague = A` → reset → `step = 0` → effect deps `[beat, leagueId]` = `['standing', B]` → no mark. If B's review is cached (A→B→A within the 60 s `staleTime`), `q.data` is present on that very render and the render-phase reset is what keeps `beats[5]` from being read; an effect-based reset would have let the completion effect fire first in the same commit. `saving` is not reset (its `finally` clears it) and the `q` key already carries `leagueId`.
- `markTeamReviewCompleted` (`TeamReviewEntryCard.tsx:55-57`) → `useTeamReviewCompletion.getState().mark(leagueId)`.

## 4. Code-walk — the store and the store-driven card read (R-4)

- **Store** `mobile/src/state/teamReviewCompletion.ts`: key `:27` `TEAM_REVIEW_DONE_KEY = 'ftf_team_review_completed'` (unchanged key, unchanged sparse `{[leagueId]: true}` shape — no migration). `mark` `:69-76`: guard → `:71` `set(...)` **synchronously** → `:72-75` `readStored().then(stored => AsyncStorage.setItem(KEY, JSON.stringify({ ...stored, ...get().byLeague })))` fire-and-forget (read-merge-write, so a mark racing hydrate cannot drop other leagues). `hydrate` `:60-67`: idempotent, shares one promise, merges `{ ...stored, ...s.byLeague }` so an early `mark` wins.
- **Card** `TeamReviewEntryCard.tsx`: `:70` `hydrated = useTeamReviewCompletion(s => s.hydrated)`; `:71` `completed = useTeamReviewCompletion(s => !!s.byLeague[leagueId])`; `:73-75` `hydrate()` once on mount; `:77-84` own "Not now" map still read once per `leagueId` (unchanged behaviour); `:97` `if (collapsed === null || !hydrated) return null;`; `:101` `if (collapsed || completed) {` → row `:108/:111` reads `completed` for label/a11y.
- **Why it now shows on the way back:** TradesHome (and its card) stays mounted beneath the pushed review (`TabNav.tsx:455-460`); `mark` mutates the zustand store → the card's selector re-renders immediately → `completed === true` → "Team review · done" is already on screen when the pop lands. No focus hook, no re-read, no race with the disk write.

## 5. Evidence

- `npx tsc --noEmit` — exit 0.
- `node tests/check-outlook-row-source.js` — 19 passed, 0 failed after `cb893b09` (15 at the build tip). RED by sabotage (apply → run → revert via `git checkout`, tree clean after each):
  - S1 restore literal `Outlook · Not set` → `13 passed, 2 failed`: ✗ 1a, ✗ 1b
  - S2 delete the prefs query → `14/1`: ✗ 2
  - S3 hand-copy the table into the calculator → `13/2`: ✗ 3a, ✗ 3d
  - S4 remove the `savePrefs` invalidation → `13/2`: ✗ 4a, ✗ 4b
  - S5 delete the plan-beat completion call → `14/1`: ✗ 5a
  - S6 revert the card to a mount-only read → `14/1`: ✗ 6a
  - Round-1 resolution (`cb893b09`, baseline 19/0):
    - S-a row reads `team_outlook ?? inferred_outlook` → `18/1`: `✗ 1d. the fallback reads the DECLARED team_outlook only`
    - S-a2 row reads `inferred_outlook ?? team_outlook` → `18/1`: `✗ 1d. the fallback reads the DECLARED team_outlook only`
    - S-b1 effect condition `beat === 'plan' && leagueId && false` → `18/1`: `✗ 5c. the completion effect's condition is exactly beat === 'plan' && leagueId`
    - S-b2 prefs query `enabled: false` → `18/1`: `✗ 2b. the prefs query is live (enabled gates on !!leagueId, never false)`
    - S-c delete the `setStep(0)` line → `18/1`: `✗ 5d. step is reset to 0 when leagueId changes`
    - S-c2 move the reset block into a `useEffect` → `18/1`: `✗ 5d. the step reset runs during render, not in an effect`
- Existing suites: `check-team-review.js` 13/0, `check-calc-merged-layout.js` exit 0, `check-finder-conditions-reachable.js` 6/0, `check-inline-home.js` exit 0, `check-team-review-depth.js` 8/0, `scripts/testid-lint.sh` OK — re-run green on `cb893b09`, `tsc --noEmit` exit 0.
- Runtime proof: PRD §8 TestFlight checklist (operator).

## 6. Deviations from the PRD

- **Query `enabled: merged && !!leagueId`** (PRD said `!!leagueId`). The fallback only renders under `merged`, and the component's documented contract is "OFF is byte-identical to the shipped stacked page"; gating the fetch keeps the flag-off page request-identical. Moot in prod (`calc.merged_layout` is true for all users). Guard 2 pins key + fn, not the `enabled` clause.
- **`outlookDisplayName` returns `null` for an unknown value** (not only null/absent), so an enum string this table does not know reads "Not set" rather than `undefined`. TradesScreen's aliased map keeps its previous `undefined`-for-unknown behaviour at the untouched call site.
- **TradesScreen import line `:69`** was touched in addition to the `:9837-9849` alias — the alias cannot reference the export without it (one added line).
- Plan's now-unused `const qc = useQueryClient()` removed alongside its redundant invalidation (would otherwise be an unused local).
