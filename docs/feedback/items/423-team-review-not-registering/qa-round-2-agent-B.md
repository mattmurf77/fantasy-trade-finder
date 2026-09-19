# QA round 2 — agent B — 2026-09-08

Group G-423 (#423 + #424). Full re-verification after the Phase 4 resolution, not a delta check. Diff under test: `git diff a8658cec..7ad630f6` (19 files: 6 mobile source, 1 new guard, `package.json`, 3 `CLAUDE.md`, `state/README.md`, `docs/config-reference.md`, 2 `status.md`, 5 item docs). Spec: [prd.md](prd.md) R-1…R-4, §5 guards, §8 checklist; rulings in [reconciliation-log.md](reconciliation-log.md); round-1 findings in [qa-round-1-agent-A.md](qa-round-1-agent-A.md) / [qa-round-1-agent-B.md](qa-round-1-agent-B.md); the builder's [build-report.md](build-report.md) §3 league-switch walk was re-derived line by line, not trusted.

## Summary: PASS (1 finding — minor, docs; nothing blocks ship)

Every requirement R-1…R-4 traces as specified at the resolved tip; all eleven sabotages (six PRD §5 + five build-report §5) go RED on the assertion they name and green on revert with a clean tree; tsc, all 99 `check-*.js` suites and testid-lint are green. The round-1 resolution (`cb893b09`) is verified: the render-phase reset at `TeamReviewScreen.tsx:127-135` runs in the same render pass that first sees the new `leagueId`, React discards that pass and re-renders with `step === 0` before any commit, so the completion effect at `:160-162` can only ever observe `beats[0]` (`'standing'`) or `undefined` for the new league — never `'plan'`; it cannot loop, cannot fire on a same-value re-render, and every setter it calls belongs to `TeamReviewScreen` itself, so no cross-component render warning. The one finding is a stale guard citation in `mobile/src/screens/CLAUDE.md`.

## Environment

- Worktree: detached at `7ad630f6` (`git log -1` = "G-423 Phase 4 docs: round-1 resolution log, build-report code-walk for the league-switch reset, status lines"). Chain from base: `4cca4020` (build) → `59236a18` (docs) → `9097a688` (round-1 reports) → `cb893b09` (resolution: `TeamReviewScreen.tsx` +20, `state/README.md`, guard +57) → `7ad630f6`. Tree clean before and after every sabotage (`git status --short` → 0 tracked changes, checked after each revert and at the end).
- node v24.14.1; react 19.1.0, react-native 0.81.5, `@tanstack/react-query` ^5.99.2, zustand ^5.0.12 (`mobile/package.json:124,140,142,154`). `mobile/node_modules` is a populated symlink. No `StrictMode` wrapper anywhere in `App.tsx`/`src/` (grep → 0).
- Flags pinned as `config/features.json` ships them: `trades.finder_hub` true, `trade.outlook_direction` **false** (:67), `trades.team_review` true, `calc.merged_layout` true, `calc.inline_home` true, `trades.edit_full_sheet` true.
- No simulator, no Maestro, no captures (D-056). Backend pytest: **not applicable — no backend files in the diff** (`git diff --stat a8658cec..7ad630f6` lists nothing under `backend/`).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| `cd mobile && npx tsc --noEmit` | PASS | exit 0 |
| Every `mobile/tests/check-*.js` (loop, 99 files) | PASS | `total failing=0`; PRD §5 #7 suites by name: `check-team-review.js` 13/0, `check-team-review-depth.js` 8/0, `check-calc-merged-layout.js` pass, `check-finder-conditions-reachable.js` 6/0, `check-inline-home.js` pass |
| `bash scripts/testid-lint.sh` | PASS | `testid-lint OK`, exit 0 |
| `pytest backend/tests` | N/A | not applicable: no backend files in diff |
| New guard `check-outlook-row-source.js` baseline | PASS | `19 passed, 0 failed` (15 at the build tip + 1d/2b/5c/5d from `cb893b09`) |
| S1 restore literal `Outlook · Not set` (`InLeagueCalculator.tsx:952`) | PASS (RED) | `16/3` → `✗ 1a. fallback text derives from the saved team_outlook`, `✗ 1b. no literal "Outlook · Not set" line`, `✗ 1d. the fallback reads the DECLARED team_outlook only`; revert → 19/0 |
| S2 delete the `prefsQ` query (`:443-449`) | PASS (RED) | `17/2` → `✗ 2. InLeagueCalculator queries ['league-prefs', leagueId] via getLeaguePreferences`, `✗ 2b. the prefs query block is isolable`; revert → 19/0 |
| S3 hand-copy the table into the calculator, drop the `:30` import | PASS (RED) | `17/2` → `✗ 3a. InLeagueCalculator imports outlookDisplayName from ./OutlookBiasReceipt`, `✗ 3d. no hand-copied outlook name table outside the receipt`; revert → 19/0 |
| S4 remove the `savePrefs` invalidation (`TeamReviewScreen.tsx:205`) | PASS (RED) | `17/2` → `✗ 4a. every saveLeaguePreferences( caller invalidates ['league-prefs'`, `✗ 4b. TeamReviewScreen invalidates ['league-prefs', leagueId] INSIDE savePrefs`; revert → 19/0 |
| S5 delete the plan-beat completion effect (`:160-162`) | PASS (RED) | `17/2` → `✗ 5a. markTeamReviewCompleted fires in a beat === 'plan' context`, `✗ 5c. the completion effect is isolable`; revert → 19/0 |
| S6 revert the card to a mount-only `readMap('ftf_team_review_completed')` (`TeamReviewEntryCard.tsx:71`) | PASS (RED) | `18/1` → `✗ 6a. no mount-time read of the done key in the component`; revert → 19/0 |
| S-a row reads `team_outlook ?? inferred_outlook` | PASS (RED) | `18/1` → `✗ 1d. the fallback reads the DECLARED team_outlook only`; revert → 19/0 |
| S-a2 row reads `inferred_outlook ?? team_outlook` | PASS (RED) | `18/1` → `✗ 1d. the fallback reads the DECLARED team_outlook only`; revert → 19/0 |
| S-b1 effect condition `beat === 'plan' && leagueId && false` | PASS (RED) | `18/1` → `✗ 5c. the completion effect's condition is exactly beat === 'plan' && leagueId`; revert → 19/0 |
| S-b2 prefs query `enabled: false` | PASS (RED) | `18/1` → `✗ 2b. the prefs query is live (enabled gates on !!leagueId, never false)`; revert → 19/0 |
| S-c delete the `setStep(0)` line (`:130`) | PASS (RED) | `18/1` → `✗ 5d. step is reset to 0 when leagueId changes`; revert → 19/0 |
| S-c2 wrap the `:128-136` reset block in `useEffect(() => { … });` | PASS (RED) | `18/1` → `✗ 5d. the step reset runs during render, not in an effect`; revert → 19/0 |
| R-1 outlook row reads the saved preference | PASS | code-walk §R-1 |
| R-2 every review write invalidates | PASS | code-walk §R-2; `git grep "saveLeaguePreferences("` → one site in the screen (`:197`) |
| R-3 completion on reaching plan + on finish; league switch cannot mark the new league | PASS | code-walk §R-3 + §Resolution (a)–(c) |
| R-4 card reads the store synchronously; persistence read-merge-write | PASS | code-walk §R-4 |
| Round-1 A F-1 / B F-2 (league switch on plan beat marks new league) | PASS (resolved) | §Resolution (a) |
| Round-1 A F-3 / B F-3 (guard shape-only) | PASS (resolved) | S-a, S-a2, S-b1, S-b2, S-c, S-c2 all RED above |
| Round-1 A F-4 / B F-4 (`state/README.md`) | PASS (resolved) | diff: store count 12→13 with `teamReviewCompletion`; persistence-key row for `ftf_team_review_completed` with the not-user-scoped note |
| Round-1 A F-5 / B F-1 (loading flash) | accepted per Phase 3 ruling | unchanged; checklist step 1 carries the caveat |
| Hunt: T-1 gate untouched | PASS | `TradesScreen.tsx:6909` `consolidateOn && !outlookReceiptShown && !firstRun && canvasHost !== 'flag'` byte-identical; diff touches only `:69` and `:9839-9843` |
| Hunt: stale closure in the new hooks | PASS | completion effect deps `[beat, leagueId]` complete; `savePrefs` deps `:220` `[leagueId, beat, emit, outlook, data, qc]`; all hooks precede the early returns at `:222/:229/:236` |
| Docs: `docs/config-reference.md:371`, `state/CLAUDE.md`, `components/CLAUDE.md`, `screens/CLAUDE.md`, both `status.md` | PASS with F-1 | all present in the diff; `screens/CLAUDE.md` cites a pre-resolution guard range (F-1) |

Note on RED counts vs. build-report §5: S1, S2 and S5 now trip one more assertion each than the builder recorded (1d, 2b, 5c respectively) because those assertions did not exist at the build tip. More RED on the same sabotage is consistent, not a discrepancy.

## Code-walk proofs (line numbers at `7ad630f6`)

### R-1 — the outlook row reads the saved preference

1. **Host chain (unchanged).** `trades.finder_hub` ⇒ guided `TradesHome` (`TabNav.tsx:457`); `calc.inline_home` ⇒ `canvasHost === 'flag'` mounts `TradeBuildCanvas` → `InLeagueCalculator`. TradesHome's own row is suppressed by `TradesScreen.tsx:6909` (`canvasHost !== 'flag'`), so the calculator's `calc.outlook-row` is the only outlook surface.
2. **Query.** `InLeagueCalculator.tsx:443-449` `prefsQ = useQuery({ queryKey: ['league-prefs', leagueId], queryFn: () => getLeaguePreferences(leagueId), enabled: merged && !!leagueId, staleTime: 5*60_000, placeholderData: (prev) => prev })`. `getLeaguePreferences` imported `:6`; `league.ts:30` `team_outlook: Outlook` is the declared value, `:49` `inferred_outlook?` is a separate GET-only field the row never reads.
3. **Render.** `:913` `{merged ? (` → `:938` `<View testID="calc.outlook-row">` → `:941` `onHiddenChange={setOutlookHidden}` → `:943` `{outlookHidden ? (` → `:950` `<View testID="calc.outlook-fallback">` → `:952` `` {`Outlook · ${outlookDisplayName(prefsQ.data?.team_outlook) ?? 'Not set'}`} ``.
4. **Why the fallback is the live branch in prod.** `OutlookBiasReceipt.tsx:105` `directionOn = useFlag('trade.outlook_direction')` (false) → `:110` its query disabled → `:120` `hidden = !outlookReceiptCovers(false, …)` (`:75` returns false when `!directionOn`) → `:123` `onHiddenChange?.(true)`.
5. **Name.** `outlookDisplayName` imported `:30`; `OutlookBiasReceipt.tsx:61-63` `value ? OUTLOOK_DISPLAY_NAME[value] ?? null : null`; table `:50-56` maps `championship/contender/rebuilder/jets` → `LEAN.<k>.name` (`:34-39`: All-in / Contending / Rebuilding / Tanking) and `not_sure: 'Not sure'`. Null/absent/unknown → `null` → the `:952` `?? 'Not set'` is the only source of that string. Operator repro: `rebuilder` → `Outlook · Rebuilding`.
6. **TradesScreen twin (ruling Q2).** `:69` imports `OUTLOOK_DISPLAY_NAME`; `:9843` `const OUTLOOK_FALLBACK_LABEL = OUTLOOK_DISPLAY_NAME;`; call site `:6915` untouched.

**Does not fire when:** `merged` is false (the whole `:913` region, row included, is absent); `leagueId` empty; `trade.outlook_direction` true AND a directional outlook resolves (receipt covers, fallback hidden — by design); prefs GET not yet resolved on a cold cache (accepted flash); a server value outside the five known strings (reads "Not set" — builder-documented).

### R-2 — every review write invalidates `['league-prefs', leagueId]`

- `TeamReviewScreen.tsx:113` `const qc = useQueryClient();` → `:179` `const savePrefs = useCallback(async (patch, action) => {` → `:197-199` `await saveLeaguePreferences(leagueId, { team_outlook: fallbackOutlook, ...patch })` (the ONE write site; `check-team-review.js` #10 green) → `:205` `qc.invalidateQueries({ queryKey: ['league-prefs', leagueId] });` inside the `try`, after the awaited write → `:220` deps include `qc`.
- Callers: window Confirm `:307` `savePrefs({ team_outlook: declared }, 'outlook_set')`; depth Save & continue `:319-322` `savePrefs({ acquire_positions…, trade_away_positions… }, 'positions_set')`; plan beat `:294` `onSave={savePrefs}` → `Plan.commit`. Plan's former `useQueryClient` + `if (ok) qc.invalidateQueries(...)` are removed (diff `-1019`, `-1085`), so each write invalidates exactly once.
- Observers that refetch: `TradesScreen.tsx:1286`, `InLeagueCalculator.tsx:443`, `OutlookBiasReceipt.tsx:108`, Plan's own `prefsQ`; TradesHome stays mounted beneath the pushed review (`TabNav.tsx:457`, `:506-508` same `TradesStack`), so the observers are live when the invalidation lands.

**Does not fire when:** `leagueId` null (`:182` early return; screen shows "Pick a league first" at `:222`); the POST throws (`catch` skips `:205` — correct, nothing changed server-side).

### R-3 — completion recorded on reaching the plan beat, and still on finish

- `:152` `const beat = beats[step];` where `beats` (`:146-150`) = server `meta.beats` minus `meta.beats_skipped`. Server order is fixed: `backend/team_review.py:48-50` `BEATS = ("standing", "window", "depth", "divergence", "partners", "plan")`; `:589-595` only ever skips `divergence` and `partners`. So `beats[0] === 'standing'` always and `'plan'` is always last.
- `:160-162` `useEffect(() => { if (beat === 'plan' && leagueId) markTeamReviewCompleted(leagueId); }, [beat, leagueId]);` — fires on the render in which `beat` first equals `'plan'`, whichever control advanced `step` (`next()` `:168-174` from Next / Skip / Confirm / Save & continue). Every exit after that render (back gesture, header back, tab bar) leaves the mark.
- Finish button kept: `:330` `testID="team-review.finish"` → `:361` `void markTeamReviewCompleted(leagueId as string);` → `:362` `nav.navigate('TradesHome')`. Second call is a no-op (`teamReviewCompletion.ts:70`).
- `markTeamReviewCompleted` (`TeamReviewEntryCard.tsx:55-57`) → `useTeamReviewCompletion.getState().mark(leagueId)`.

**Does not fire when:** `beat` undefined (`q` loading, `beats` empty); `leagueId` null; the user exits before the plan beat (operator ruling Q1); **a TopBar league switch while parked on the plan beat** — see §Resolution (a).

### R-4 — the entry card sees the marker without a remount; persistence is read-merge-write

- **Store** `teamReviewCompletion.ts`: `:27` key `'ftf_team_review_completed'`, sparse `{[leagueId]: true}` — both unchanged, no migration. `mark` `:69-76`: `:70` guard → `:71` synchronous `set` → `:72-75` `readStored().then(setItem(KEY, { ...stored, ...get().byLeague }))` fire-and-forget. `hydrate` `:60-67`: idempotent, one shared promise, merges `{ ...stored, ...s.byLeague }` so an early `mark` wins. `readStored` (`:31-38`) never rejects.
- **Card** `TeamReviewEntryCard.tsx`: `:70` `hydrated` selector; `:71` `completed = useTeamReviewCompletion((s) => !!s.byLeague[leagueId])`; `:74` `hydrate()` once on mount; `:79` "Not now" map still read once per `leagueId`; `:97` `if (collapsed === null || !hydrated) return null;`; `:101` `if (collapsed || completed)` → row; `:111` `'Team review · done'`.
- **Why the pop shows it:** the card is mounted under the pushed review; `mark`'s synchronous `set` re-renders its selector before `nav.navigate('TradesHome')` or the back gesture lands. No focus hook, no disk race.

**Does not fire when:** `trades.team_review` off or `leagueId` null (`TradesScreen.tsx:7047` gate — card not mounted); AsyncStorage reads never resolve (null render, pre-existing gate); `mark('')` no-op.

## Round-1 resolution — the render-phase reset (`TeamReviewScreen.tsx:127-135`)

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

**(a) Runs before the completion effect can fire for the new league; does not loop; clears every value `savePrefs` could carry across.**

- *Ordering.* The switch path is `LeagueSwitcherSheet.tsx:51` `switchLeague` → `useSession.ts:472` `setLeague` → `:428` `set({ league: lg, … })`. `TeamReviewScreen.tsx:105-106` derives `leagueId = league?.league_id ?? null`, so the screen re-renders with `leagueId = B`, `stepLeague = A`. Line 128 is true on that very pass; the six setters are queued *during render*. React's contract for a render-phase `useState` update on the component being rendered (the documented "adjusting state when a prop changes" pattern; React 19.1.0 here) is: discard this pass's output, re-run the component immediately with the queued state applied, and commit only the re-run. Effects belong to the committed pass, so the effect at `:160-162` is evaluated with `step === 0`, i.e. `beat = beats[0]`. Per `backend/team_review.py:48-50` that is `'standing'` when B's review is cached, or `undefined` while `q` (`:138-143`, keyed on `leagueId`) is loading. Neither is `'plan'` → no mark for B. This is the case an effect-based reset would lose: with B cached, `beats[5] === 'plan'` on the commit, and both the reset effect and the completion effect would run in that same commit, with the completion effect winning. Guard 5d pins the render-phase placement (S-c2 RED above).
- *No loop.* The re-run sees `stepLeague === leagueId` (line 129 applied) → line 128 false → no further setState. Exactly one extra render pass per league change. The `useState(leagueId)` initializer also means a mount with a league already set never triggers the block; the one incidental case — `leagueId` null at mount, then a league arrives — runs the block once with `step` already 0, harmless.
- *What the reset clears and why it closes the `savePrefs` hole.* `savePrefs` (`:179-220`) builds `fallbackOutlook = outlook ?? data?.window.declared ?? data?.window.inferred ?? 'not_sure'` (`:195-196`) and posts `{ team_outlook: fallbackOutlook, ...patch }` to `leagueId`. After the reset: `outlook` is null (`:131`), so A's session chip cannot become B's fallback; `data` is B's (`q` keyed on `leagueId`, `:139`); `acquire`/`shed` are `[]` (`:132-133`), so the depth beat's `acquire.length ? acquire : data.depth.acquire_positions` (`:320-321`) falls through to B's server defaults; `scoped` is null (`:134`), so the finish handler's `if (scoped) setHandoff(...)` (`:346-351`) cannot point B's finder at A's manager; `done.current` is a fresh Set (`:135`), so B's plan-beat recap cannot list A's actions. `savePrefs` itself is recreated with the new values (deps `:220`). The `Plan` component unmounts when `beat` leaves `'plan'` (`:289` conditional), and on a later remount for B its draft is seeded from B's `prefsQ` (`:1096-1106` `saved.team_outlook ?? data.window.declared …`), so no A value survives in Plan-local state either.
- *An in-flight A write.* A `savePrefs` promise started on A before the switch captured A's `leagueId` in its closure, so it posts to A and invalidates `['league-prefs', A]` — correct. Its `finally` clears `saving`, which the reset deliberately leaves alone.

**(b) A same-value re-render does not discard an in-progress review.**

- `leagueId` is a string primitive compared with `!==` (`:128`). `useSession.setLeague` (`:428`) replaces the `league` *object* on every call (e.g. `formatExplicit` resets, revalidation), but `league.league_id` is the same string, so `stepLeague !== leagueId` stays false and `step`/selections survive. `switchLeague` additionally no-ops on the same league (`useSession.ts:458`). Any other re-render of the screen (a `saving` flip, `q` refetch, `useFlag` change) leaves `leagueId` untouched. The only path into the block is a genuine change of the league id string.

**(c) No React warning risk.**

- The setters called during render — `setStepLeague` (`:127`), `setStep`/`setOutlook`/`setAcquire`/`setShed`/`setScoped` (`:107-111`) — are all `useState` hooks declared in `TeamReviewScreen` itself, the component whose render is in progress. React's "Cannot update a component while rendering a different component" warning fires only for setState on *another* component; same-component render-phase updates are the sanctioned pattern and emit nothing. `done.current = new Set()` is a ref write during render; React does not warn on it, and the assignment is idempotent under a double-invoked render (no `StrictMode` in this app anyway). Nothing else runs during the block: no `qc` call, no `emit`/`track`, no navigation.

## Findings

### F-1: `mobile/src/screens/CLAUDE.md` `TeamReviewScreen` row cites the guard as `check-outlook-row-source.js (4b, 5a–b)` — stale after `cb893b09`
- Severity: minor (docs)
- Repro: `grep -o "#423[^|]*" mobile/src/screens/CLAUDE.md` → "…Pinned by `mobile/tests/check-team-review.js` (13 assertions) + `check-outlook-row-source.js` (4b, 5a–b)". The resolution added 5c (effect condition exact) and 5d (render-phase reset), both about this screen; the row also does not mention the league-switch reset, which is now part of the screen's contract.
- Expected: the row names 4b, 5a–d and one clause on the render-phase reset (the `TeamReviewScreen.tsx:118-126` comment already explains it). Actual: pre-resolution range.
- Evidence: `mobile/src/screens/CLAUDE.md:30`; `mobile/tests/check-outlook-row-source.js` §5 (5c, 5d). `state/CLAUDE.md` and `state/README.md` are current.

### Observations (not findings)
- Build-report §5 RED counts for S1/S2/S5 (2, 1, 1) are now 3, 2, 2 because 1d/2b/5c did not exist at the build tip — consistent, not a discrepancy.
- Guard 5d's regex `if \([A-Za-z]+ !== leagueId\) \{` would also accept a block keyed on any other identifier compared to `leagueId`; that is a looser pin than the exact `stepLeague`, but S-c and S-c2 both go RED, so it holds for the two failure modes round 1 named.
- Theoretical only: a `savePrefs` from league A that is *still awaiting its POST* when `leagueId` flips to B would run `done.current.add(action)` (`:206`) against B's fresh Set. Unreachable in practice — `switchLeague` awaits the backend session init (`useSession.ts:467-472`) before `setLeague`, so the flip lands seconds after any review POST has resolved.
- `TeamReviewEntryCard.tsx:67` `collapsed` is still not reset to `null` on a `leagueId` change (pre-existing; unchanged by this diff; the new `hydrated` gate does not alter it).

## TestFlight checklist (operator-run)

Preconditions: build carrying `7ad630f6` or later; account with FFV3 and Lakeview linked; Lakeview has a saved outlook (`rebuilder` per the log), FFV3 has one too; ideally a third league never reviewed on this device. A sub-second "Outlook · Not set" on first paint that resolves on its own is the accepted loading flash (Phase 3 ruling), not the bug; the bug is "Not set" that **stays**.

1. **TradesHome (Acquire landing)** → TopBar league cluster → switch to **Lakeview** → let it settle. Expect: the row under "Show me around" reads **"Outlook · Rebuilding"** (Lakeview's saved value), not "Not set", with no relaunch.
2. **TradesHome** → note the Team review entry: full "Start team review" card, or "Team review · done" if the old build ever recorded it via Find my trades. Either is correct here.
3. Tap the entry → **Team review, window beat** → pick a **different** outlook (e.g. Contending) → **Confirm** → immediately leave with the **header back control** (do not reach the plan beat). Expect on **TradesHome**: row reads "Outlook · Contending" **immediately** (R-2); entry is still the **full card** (plan beat not reached → not done, R-3 ruling).
4. Open Team review again → Confirm on window (any) → depth **Save & continue** → **Skip this** through to the **plan beat** → tap a **third** outlook chip (e.g. Rebuilding) → leave with the **header back control**, NOT "Find my trades". Expect on **TradesHome**, without relaunch: row "Outlook · Rebuilding"; entry **"Team review · done"** (R-1, R-3, R-4).
5. Kill the app → relaunch on Lakeview. Expect: row still "Outlook · Rebuilding" (after the prefs load); entry still "Team review · done" (store hydrated from `ftf_team_review_completed`).
6. Tap the "Team review · done" row → run to the **plan beat** → tap **Find my trades**. Expect: back on TradesHome, entry still "done", row still current; no error, no duplicate toast.
7. TopBar → switch to **FFV3**. Expect: FFV3's own saved outlook in the row once the fetch settles (never Lakeview's), and FFV3's own done/not-done state. Switch back to **Lakeview**: Lakeview's values return.
8. A league **never reviewed** on this device (third league, or fresh install): **TradesHome** shows the **full** "Start team review" card and, with nothing declared, "Outlook · Not set" with a working **Change** that opens the Trade DNA sheet. Save an outlook there → row updates without relaunch. A saved `not_sure` must read "Outlook · Not sure", never "Not set".
9. **League-switch-on-plan-beat probe (round-1 A F-1 / B F-2, corrected expectation).** Pick a league whose entry is currently the **full card** (call it B — the never-reviewed league from step 8 is ideal). On **FFV3** open Team review → reach the **plan beat** → *without leaving the review* open the TopBar league cluster → pick **B**. Expect: the review **restarts on B's standing beat** (first tick lit, progress bar at the start), with no outlook chip preselected from FFV3. Leave with the header back control. Expect on **TradesHome for B**: the entry is **still the full card** — B is **not** marked done; B's outlook row shows B's own saved value (or "Not set" if none). Switch back to FFV3: its entry reads "done" (FFV3 genuinely reached its plan beat before the switch).
10. **Same-league re-render probe.** On any league open Team review → advance to the **depth beat** and toggle a chasing position → background the app (home gesture) for ~10 s → foreground it. Expect: still on the depth beat with the toggled chip intact — a session revalidation on the same league must not restart the review.
11. **Regression:** on the plan beat change chasing/shopping positions; back out. Expect no crash and TradesHome's finder still runs. Tap **Change** on the outlook row. Expect the Trade DNA sheet opens over the landing; saving there updates the row immediately.
