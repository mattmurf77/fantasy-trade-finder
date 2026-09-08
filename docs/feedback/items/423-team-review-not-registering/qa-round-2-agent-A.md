# QA round 2 — agent A — 2026-09-08

Group G-423 (#423 + #424). Full re-verification after the Phase 4 resolution, not a delta check. Diff under test: `a8658cec..7ad630f6` (19 files: 6 mobile source, 1 new guard, `package.json`, 4 registry docs, `docs/config-reference.md`, 6 item docs). Spec: [prd.md](prd.md) R-1…R-4, §5 guards, §8 checklist; rulings and the round-1 resolution in [reconciliation-log.md](reconciliation-log.md); builder's [build-report.md](build-report.md) verified line by line, not trusted. Round-1 reports: [qa-round-1-agent-A.md](qa-round-1-agent-A.md), [qa-round-1-agent-B.md](qa-round-1-agent-B.md).

## Summary: PASS (2 findings — both minor, guard-strength / observation; nothing blocks ship)

Every PRD §5 row holds; all eleven named sabotages (six PRD + five build-report §5 resolution sabotages, plus the builder's sixth `S-a2`) go RED on the assertion they are mapped to; every requirement's code path traces at the new line numbers. The round-1 confirmed defect (A F-1 / B F-2 — a TopBar league switch on the plan beat marked the NEW league done) is closed by the render-phase reset at `TeamReviewScreen.tsx:127-135`: it cannot loop, it does not fire on a same-value re-render, it is same-component setState only (no React cross-component warning), and after it neither the completion effect nor `savePrefs` can attribute league A's state to league B. Round-1 F-3 (guard shape-only) is closed by assertions 1d / 2b / 5c / 5d, each proven RED here. Round-1 F-4 (`state/README.md`) is in the diff. Round-1 A F-5 / B F-1 (loading-state "Not set" flash) stands as accepted; it is restated in the checklist preconditions. `pytest backend/tests`: **not applicable — no backend files in the diff** (`git diff --stat a8658cec..7ad630f6` lists none).

## Environment

- Worktree: detached at `7ad630f6` (`G-423 Phase 4 docs: round-1 resolution log, build-report code-walk for the league-switch reset, status lines`); `git status --porcelain` empty before and after every sabotage (asserted by the sabotage script, `dirty=0` each time).
- node v24.14.1; `npx tsc --noEmit` via the repo-pinned TypeScript; `mobile/node_modules` is a populated symlink. Python 3.14.4 (unused — see pytest row).
- Flags pinned as `config/features.json` ships them: `trades.finder_hub` true (`:14`), `trade.outlook_direction` **false** (`:67`), `trades.team_review` true (`:80`), `calc.merged_layout` true (`:93`), `calc.inline_home` true (`:95`), `trades.edit_full_sheet` true (`:230`).
- No simulator, no Maestro, no captures (D-056). Nothing was fixed or committed. Line numbers are this tree's (`7ad630f6`).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| `cd mobile && npx tsc --noEmit` | PASS | exit 0 (35 s) |
| Every `mobile/tests/check-*.js` (loop over the glob) | PASS | 99 guard files, 0 failed (`GUARD_FILES=99 FAILED=0`) |
| `bash scripts/testid-lint.sh` | PASS | `testid-lint OK`, exit 0 |
| `check-outlook-row-source.js` baseline | PASS | `19 passed, 0 failed` |
| S1 restore literal `Outlook · Not set` (PRD §5 #1) | PASS (RED) | `16/3` → `✗ 1a`, `✗ 1b`, `✗ 1d` |
| S2 delete the prefs query (§5 #2) | PASS (RED) | `17/2` → `✗ 2. InLeagueCalculator queries ['league-prefs', leagueId] via getLeaguePreferences`, `✗ 2b. the prefs query block is isolable` |
| S3 hand-copy the table into the calculator, drop the import (§5 #3) | PASS (RED) | `17/2` → `✗ 3a`, `✗ 3d` |
| S4 remove the `savePrefs` invalidation (§5 #4) | PASS (RED) | `17/2` → `✗ 4a`, `✗ 4b` |
| S5 delete the plan-beat completion effect (§5 #5) | PASS (RED) | `17/2` → `✗ 5a`, `✗ 5c. the completion effect is isolable` |
| S6 revert the card to a mount-only read of the done key (§5 #6) | PASS (RED) | `18/1` → `✗ 6a. TeamReviewEntryCard derives \`completed\` from useTeamReviewCompletion` |
| S-a row reads `team_outlook ?? inferred_outlook` (build-report §5, resolution) | PASS (RED) | `18/1` → `✗ 1d. the fallback reads the DECLARED team_outlook only` |
| S-a2 row reads `inferred_outlook ?? team_outlook` | PASS (RED) | `18/1` → `✗ 1d` |
| S-b1 effect condition `beat === 'plan' && leagueId && false` | PASS (RED) | `18/1` → `✗ 5c. the completion effect's condition is exactly beat === 'plan' && leagueId` |
| S-b2 prefs query `enabled: false` | PASS (RED) | `18/1` → `✗ 2b. the prefs query is live (enabled gates on !!leagueId, never false)` |
| S-c delete the `setStep(0)` line | PASS (RED) | `18/1` → `✗ 5d. step is reset to 0 when leagueId changes` |
| S-c2 move the reset block into a `useEffect` | PASS (RED) | `18/1` → `✗ 5d. the step reset runs during render, not in an effect` |
| X-r2-2 (extra) effect deps `[beat]` only | PASS (RED) | `18/1` → `✗ 5c. the completion effect depends on [beat, leagueId]` |
| X-r2-1 (weakness probe) drop `setStepLeague(leagueId)` from the reset block | stays GREEN → F-1 | `19/0`; at runtime this is an unconditional render-phase setState → React "Too many re-renders" |
| X-r2-3 (weakness probe) keep `setStep(0)` but drop the five selection resets | stays GREEN → F-1 | `19/0`; reintroduces the second half of round-1 F-1 (A's `outlook` as B's `savePrefs` fallback) |
| §5 #7 existing suites: `check-team-review.js` 13/0, `check-team-review-depth.js` 8/0, `check-calc-merged-layout.js`, `check-finder-conditions-reachable.js` 6/0, `check-inline-home.js`, `check-trades-banner-region.js` | PASS | inside the 99/0 loop |
| R-1 outlook row reads the saved preference | PASS (code-walk) | `InLeagueCalculator.tsx:443-449, 913, 943, 950-952`; `OutlookBiasReceipt.tsx:34-39, 50-56, 61-63`; `TradesScreen.tsx:69, 6909, 6913-6917, 9843` |
| R-2 every review write invalidates | PASS (code-walk) | `TeamReviewScreen.tsx:113, 179, 197-199, 205, 220, 294, 307, 319-322, 1113-1123` |
| R-3 completion on reaching the plan beat, and on finish | PASS (code-walk) | `TeamReviewScreen.tsx:152, 160-162, 168-174, 330, 361-362`; `backend/team_review.py:589-603` |
| R-4 card reads the store synchronously; persistence read-merge-write | PASS (code-walk) | `TeamReviewEntryCard.tsx:55-57, 70-75, 77-83, 97, 101, 108, 111`; `teamReviewCompletion.ts:27, 55, 60-67, 69-76` |
| Round-1 resolution (a) reset precedes the completion effect, no loop, no cross-league values | PASS (code-walk §5a) | `TeamReviewScreen.tsx:127-135, 137-142, 160-162, 179-220, 246` |
| Round-1 resolution (b) same-value re-render does not discard progress | PASS (code-walk §5b) | `:104-105, 127-128`; `useSession.ts:126, 428` |
| Round-1 resolution (c) same-component setState only | PASS (code-walk §5c) | `:106-111, 116, 127-135` |
| Hunt: second `saveLeaguePreferences(` site in the file | PASS (none) | `git grep`: `TeamReviewScreen.tsx:197` only; five sites repo-wide, all five invalidate (`TradeDnaSheet.tsx:437/444`, `TradeFinderHubScreen.tsx:341/353`, `TradesScreen.tsx:1351/1362, 6523/6533`) |
| Hunt: hook order across the reset | PASS | the block (`:128-135`) contains no hooks; `useState` at `:127` is unconditional; early returns start at `:222` |
| Hunt: T-1 gate / TradesScreen row untouched | PASS | `:6909` gate byte-identical in the diff; only `:69` (import) and `:9839-9843` (alias) changed |
| `python3 -m pytest backend/tests` | N/A | not applicable: no backend files in diff |

## Code-walk proofs (line numbers at `7ad630f6`)

### R-1 — the outlook row reads the saved preference

1. **Query.** `InLeagueCalculator.tsx:443-449`: `prefsQ = useQuery({ queryKey: ['league-prefs', leagueId], queryFn: () => getLeaguePreferences(leagueId), enabled: merged && !!leagueId, staleTime: 5*60_000, placeholderData: (prev) => prev })`; `getLeaguePreferences` imported at `:6`; `merged = useFlag('calc.merged_layout')` at `:311`. Same key as every writer's invalidation (listed under R-2) and every other reader (`TradesScreen.tsx:1286`, `OutlookBiasReceipt.tsx:108`, `TradeDnaSheet.tsx:289`, `TradeFinderHubScreen.tsx:230`, `TeamReviewScreen.tsx:1071`).
2. **Render.** `:913` `{merged ? (` → `:943` `{outlookHidden ? (` → `:950` `<View testID="calc.outlook-fallback">` → `:952` `` {`Outlook · ${outlookDisplayName(prefsQ.data?.team_outlook) ?? 'Not set'}`} ``. `outlookHidden` (`:317`) is set by the receipt's `onHiddenChange` (`OutlookBiasReceipt.tsx:120-124`); with `trade.outlook_direction` false, `outlookReceiptCovers` returns false (`:75`) → hidden → the fallback row is the outlook surface.
3. **Name table.** `outlookDisplayName` (`OutlookBiasReceipt.tsx:61-63`) → `value ? OUTLOOK_DISPLAY_NAME[value] ?? null : null`; `OUTLOOK_DISPLAY_NAME` (`:50-56`) maps the four LEAN names (`:34-39`: All-in / Contending / Rebuilding / Tanking) plus `not_sure: 'Not sure'`. Only `team_outlook` is read; `inferred_outlook` never (#394 ruling; guard 1d).
4. **Operator repro.** Lakeview row `team_outlook=rebuilder` → `prefsQ.data.team_outlook === 'rebuilder'` → `'Rebuilding'` → `Outlook · Rebuilding`.
5. **TradesScreen twin (ruling Q2).** `:69` imports `OUTLOOK_DISPLAY_NAME`; `:9843` `const OUTLOOK_FALLBACK_LABEL = OUTLOOK_DISPLAY_NAME;`; call site `:6913-6917` unchanged.

**Does NOT fire when:** `merged` false (the whole `:913` region, row included, is not rendered — so no "Not set" either); `leagueId` null (the calculator is not hosted: `canvasHost === 'flag'` requires it); the receipt covers (`trade.outlook_direction` true with a directional value → the receipt renders its own line); the query is in flight or errored (`prefsQ.data` undefined → "Not set" until data lands — the accepted round-1 flash).

### R-2 — every review write invalidates `['league-prefs', leagueId]`

- `TeamReviewScreen.tsx:113` `const qc = useQueryClient();` → `:179` `const savePrefs = useCallback(async (patch, action) => {` → `:180` `if (!leagueId) return false;` → `:197-199` `await saveLeaguePreferences(leagueId, { team_outlook: fallbackOutlook, ...patch })` (the one write site in the file) → `:205` `qc.invalidateQueries({ queryKey: ['league-prefs', leagueId] });` → `:206` `done.current.add(action)` → `:220` deps `[leagueId, beat, emit, outlook, data, qc]`.
- **Callers:** window Confirm `:307` `savePrefs({ team_outlook: declared }, 'outlook_set')`; depth Save & continue `:319-322` (`positions_set`); plan beat `:294` `onSave={savePrefs}` → `Plan.commit` `:1113-1123` posts the full triple. `Plan` no longer owns a `useQueryClient`/invalidation (its `prefsQ` at `:1071-1077` is read-only with `refetchOnMount: 'always'`), so each write invalidates exactly once.
- **Observers refetch on the way back:** TradesHome stays mounted beneath the pushed review (`TabNav.tsx:455-460` TradesHome, `:506-508` TeamReview, same `TradesStack`), holding active observers at `TradesScreen.tsx:1286` and `InLeagueCalculator.tsx:443`.

**Does NOT fire when:** `leagueId` null (`:180`); the POST throws → `catch` (`:213-216`) skips `:205` — correct, nothing changed server-side.

### R-3 — completion recorded on reaching the plan beat, and still on finish

- `:152` `const beat = beats[step];` → `:160-162` `useEffect(() => { if (beat === 'plan' && leagueId) markTeamReviewCompleted(leagueId); }, [beat, leagueId]);` — above every early return (`:222`, `:229`, `:236`). `next()` (`:168-174`) advancing `step` to the plan index re-renders with `beat === 'plan'` → effect fires → `markTeamReviewCompleted` (`TeamReviewEntryCard.tsx:55-57`) → `useTeamReviewCompletion.getState().mark(leagueId)`. Any exit afterwards (back gesture, header back via `subScreenOptions('Team review','TradesHome')` `TabNav.tsx:508`, tab bar) leaves the mark in place.
- Finish button kept: `:330` `testID="team-review.finish"` → `:361` `void markTeamReviewCompleted(leagueId as string);` → `:362` `nav.navigate('TradesHome')`. Second call is a no-op (`teamReviewCompletion.ts:70`).
- The server never skips `plan`: `backend/team_review.py:589-595` only appends `divergence` / `partners` to `beats_skipped` (`:603`).

**Does NOT fire when:** `beat` undefined (loading, or `beats` empty); `leagueId` null; the user exits before the plan beat (ruling Q1); a TopBar league switch while parked on the plan beat (see §5a — the round-1 defect, now closed).

### R-4 — the card sees the marker without a remount; persistence is read-merge-write

- **Store** `teamReviewCompletion.ts`: key `:27` `'ftf_team_review_completed'`, sparse `{[leagueId]: true}` (unchanged; no migration). `mark` `:69-76`: `:70` guard (falsy or already marked → return) → `:71` `set(...)` synchronously → `:72-75` `readStored().then(stored => AsyncStorage.setItem(KEY, JSON.stringify({ ...stored, ...get().byLeague })))` fire-and-forget. `hydrate` `:60-67`: idempotent, one shared promise (`:55`), merges `{ ...stored, ...s.byLeague }` so an early `mark` wins. `readStored` (`:31-38`) never rejects.
- **Card** `TeamReviewEntryCard.tsx`: `:70` `hydrated`, `:71` `completed = useTeamReviewCompletion((s) => !!s.byLeague[leagueId])`; `:73-75` `hydrate()` once; `:77-83` the "Not now" map still read once per `leagueId`; `:97` null until both sources are ready; `:101` `if (collapsed || completed)` → row, a11y `:108`, label `:111` `'Team review · done'`.
- **Why the pop shows it:** the card sits mounted beneath the review (TabNav cites above); `mark`'s `set` re-runs the selector → `completed === true` before the pop lands. Mounted at `TradesScreen.tsx:7047-7049` with TradesScreen's `leagueId`, so FFV3's `true` never reads as Lakeview's.

**Does NOT fire when:** `trades.team_review` off or `leagueId` null (card not mounted, `:7047`); pre-hydration (`:97`); `mark('')`.

### 5. Round-1 resolution — the render-phase reset (`TeamReviewScreen.tsx:127-135`)

```
127  const [stepLeague, setStepLeague] = useState(leagueId);
128  if (stepLeague !== leagueId) {
129    setStepLeague(leagueId);
130    setStep(0);
131    setOutlook(null);
132    setAcquire([]);
133    setShed([]);
134    setScoped(null);
135    done.current = new Set();
136  }
```

**(a) It runs before the completion effect can fire for the new league; it does not loop; league A's values cannot post as league B's.**

- *Ordering.* `leagueId` is derived at `:104-105` from `useSession((s) => s.league)` (zustand → `useSyncExternalStore`, a synchronous re-render). In the first render where `leagueId` reads B, `stepLeague` still holds A → the six updates at `:129-135` are queued **during render**. React's contract for render-phase setState on the component's own state is to discard that render's output and re-run the function immediately, before rendering children and before commit; effects from the discarded render are never scheduled. The re-run sees `stepLeague === B`, `step === 0`: `q` (`:137-142`, key `['team-review', B]`, **no** `placeholderData`) yields B's cached data or `undefined`; `beats` (`:145-149`) is B's list or `[]`; `beat = beats[0]` is `'standing'` or `undefined` — never `'plan'`. The completion effect's deps go from `['plan', A]` to `['standing'|undefined, B]`, so it re-runs after commit with the condition false → no mark. There is **no commit** in which `leagueId === B` and `step === 5`. Builder's trace in build-report §3 is confirmed.
- *No loop.* The only render-phase writes are inside `if (stepLeague !== leagueId)`; the first write is `setStepLeague(leagueId)` (`:129`), so the immediate re-run evaluates the predicate false. Exactly one extra render per league change (React would throw "Too many re-renders" at ~25). Hook order is unaffected: `:127` is an unconditional `useState` between `useRef` (`:116`) and `useQuery` (`:137`), and the block itself calls no hooks.
- *Selections.* After the reset, `savePrefs`' fallback (`:195-196`) is `outlook ?? data?.window.declared ?? data?.window.inferred ?? 'not_sure'` with `outlook === null` and `data` B's (the key carries `leagueId`; no placeholder) — B's own values. The window Confirm patch (`:307`) uses `declared` from `:246` (`outlook ?? data.window.declared ?? …` — B's); the depth patch (`:319-322`) falls back to `data.depth.*` — B's; `scoped` (`:134`) is null so the finish button's `setHandoff` (`:346-351`) sends nothing that belongs to A. The user must re-walk B from `standing` to reach any writer.
- *In-flight write across the switch.* A `savePrefs` promise created under A carries A's `leagueId` and `beat` in its closure (`:220` deps), so a POST in flight during the switch lands on A, invalidates A's key, and emits with A's id. Its late `done.current.add(action)` (`:206`) lands in B's fresh set — harmless: `done` is **write-only** in this file (`:116, :135, :206, :285` are all writes; the only `.has(` mention is the historical comment at `:1027`).

**(b) A same-value re-render does not discard an in-progress review.** The predicate compares the string `league?.league_id ?? null` (`SavedLeague.league_id: string`, `useSession.ts:126`). `setLeague` (`useSession.ts:428`) replaces the `league` object, but the same league yields the same string → predicate false → no reset. Every other re-render source (`q` settling, `saving` toggling, `outlook`/`acquire`/`shed` edits, `formatExplicit`, flag changes) leaves `leagueId` unchanged → no reset. The only spurious fire is `null → id` on a screen mounted before a league exists, which shows "Pick a league first" (`:222-228`) and can hold no progress.

**(c) No React cross-component warning.** "Cannot update a component while rendering a different component" is emitted only when render-phase setState targets *another* component. All six setters at `:129-134` are `useState` hooks declared in `TeamReviewScreen` itself (`:106-111` and `:127`); `:135` mutates a `useRef` of the same component. No zustand `set`, no react-query mutation, no parent setter is called in the block. Confirmed same-component.

*Observation (not a defect):* writing `done.current` during render (`:135`) is against React's purity guidance for refs, but the write is idempotent, the ref is write-only, and the update path is synchronous (external-store update), so no observable consequence exists. Noted so a future reader does not mistake it for the bug.

## Findings

### F-1: Guard 5d pins `setStep(0)` but not the rest of the reset block — two round-2 probes stay green
- Severity: minor (guard strength; the app code is correct)
- Repro: on a scratch copy, (X-r2-1) delete `:129` `setStepLeague(leagueId);` → `check-outlook-row-source.js` 19/0, `tsc` cannot see it either — at runtime the block fires on every render and React throws "Too many re-renders"; (X-r2-3) delete `:131-135` (the five selection resets) → 19/0, yet league A's `outlook` chip would again be `savePrefs`' fallback for league B — the second half of the round-1 finding the resolution log says is fixed.
- Expected: the resolution's claim ("`step`, `outlook`, `acquire`, `shed`, `scoped` and the `done` ref reset") is pinned. Actual: only `setStep(0)` inside an `if (<prev> !== leagueId) {` block is pinned (`check-outlook-row-source.js:234-244`).
- Evidence: sabotage log above; `mobile/tests/check-outlook-row-source.js:237`. Cheap hardening for a later pass: require `set<Prev>(leagueId)` as the first statement of the block and `setOutlook(null)` within it.

### F-2: Loading-state "Not set" flash and previous-league placeholder on switch (carried from round 1, accepted)
- Severity: minor (accepted as spec-conformant in the Phase 3 ruling; restated only so the checklist reads it correctly)
- Repro: `InLeagueCalculator.tsx:952` renders `outlookDisplayName(undefined) ?? 'Not set'` while `prefsQ` is in flight; on a league switch `placeholderData: (prev) => prev` (`:448`) shows the previous league's name until the new fetch lands.
- Expected vs actual: unchanged from round 1; no action.
- Evidence: `InLeagueCalculator.tsx:443-449, 952`.

## TestFlight checklist (operator-run)

Preconditions: TestFlight build carrying `7ad630f6` (or its merge); account with FFV3 and Lakeview linked; Lakeview has a saved outlook (the log shows `rebuilder`), FFV3 has one too. A sub-second "Not set" (or the previous league's name) on first paint that resolves on its own is loading (F-2), not the bug; the bug is "Not set" that **stays**.

1. **TradesHome (Acquire landing)** → TopBar league cluster → switch to **Lakeview** → wait for the landing to settle. Expect: the row under "Show me around" reads **"Outlook · Rebuilding"** (whatever Lakeview has saved), not "Not set", with no relaunch.
2. **TradesHome** → the Team review entry. Expect: whatever state it was in before this build (full card, or "Team review · done" if the old code ever recorded it via Find my trades).
3. **TradesHome** → tap "Start team review" (or the row) → **TeamReview, window beat** → pick a **different** outlook than step 1 showed (e.g. Contending) → **Confirm**. Then **back out immediately** with the header back control (do not reach the plan beat). Expect on **TradesHome**: row reads "Outlook · Contending" **immediately** (R-2); entry is still the **full card** (plan beat not reached → not done).
4. **TradesHome** → open Team review again → **window beat** Confirm (any) → **depth beat** Save & continue → Skip through to the **plan beat** → tap a **third** outlook chip (e.g. Rebuilding) → leave with the **header back control** — NOT "Find my trades". Expect on **TradesHome**, without relaunch: row reads "Outlook · Rebuilding"; entry reads **"Team review · done"**.
5. Kill the app → relaunch → land on **TradesHome** on Lakeview. Expect: row still "Outlook · Rebuilding"; entry still "Team review · done" (store hydrated from `ftf_team_review_completed`).
6. **TradesHome** → tap the "Team review · done" row → run to the **plan beat** → tap **Find my trades**. Expect: back on TradesHome, entry still "done", row still current; no error, no duplicate toast.
7. TopBar → switch to **FFV3**. Expect: FFV3's own saved outlook in the row (never Lakeview's after the fetch settles) and FFV3's own done/not-done state. Switch back to **Lakeview**: Lakeview's values return.
8. A league **never reviewed** on this device (link a third league, or a fresh install on a league with no saved outlook): **TradesHome** shows the **full** "Start team review" card and, with nothing declared, "Outlook · Not set" with a working **Change** that opens the DNA sheet. Save an outlook there → row updates without relaunch.
9. **League switch on the plan beat (round-1 fix probe).** Use a league whose entry is still the **full card** as the target (the never-reviewed league from step 8, or clear the app's data first). On **FFV3** open Team review → reach the **plan beat** → open the TopBar league cluster **without leaving the review** → pick the target league. Expect: the review **restarts on the target league's first beat** (progress ticks back to the start; no chip selections carried over). Leave with the header back control. On **TradesHome** for the target league: the entry is still the **full "Start team review" card** — the NEW league is **not** marked done — and its row shows its own outlook (or "Not set"). Switch back to FFV3: FFV3 reads "Team review · done" (it reached its plan beat before the switch) with its own outlook.
10. **Same-league re-render does not reset progress.** On any league open Team review → Confirm on the window beat → on the depth beat toggle a chasing chip, do **not** save → pull the TopBar cluster open and close it **without picking a league** (or background and foreground the app). Expect: still on the depth beat with the toggled chip intact — nothing restarted.
