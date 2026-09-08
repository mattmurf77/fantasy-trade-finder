
## Orchestrator rulings 2026-09-08 (Phase 1 exit)

- Q1 completion definition: **reached the plan beat** (planner default). Q2 alias TradesScreen label map to the export: **yes**. Q3 second chasing/shopping line: **out of scope**. No unresolved blocking objections; fast-track path, single planner.

## Phase 3 round 1 — 2026-09-08

QA-A PASS (5 minor), QA-B PASS (4 minor). Both independently found: a TopBar league switch while parked on the plan beat marks the NEW league done (A F-1 / B F-2) — confirmed, fix in Phase 4. Both found the guard does not pin the #394 rule against reading `inferred_outlook` and lets a neutered effect pass (A F-3 / B F-3) — strengthen. `state/README.md` row missing (A F-4 / B F-4) — add. Loading-state "Not set" flash (A F-5 / B F-1): accepted as spec-conformant; noted for the checklist. QA-B pytest row BLOCKED (no backend files in the diff) — accepted.

## Round 1 resolution — 2026-09-08 (Phase 4, commit `cb893b09`)

- **A F-1 / B F-2 (league switch on the plan beat marks the new league done)** — fixed. `TeamReviewScreen.tsx:127-135`: `step`, `outlook`, `acquire`, `shed`, `scoped` and the `done` ref reset **during render** when `leagueId` differs from the league the current step belongs to (`stepLeague`). Render-phase, not an effect: when the new league's review is already cached, an effect-based reset would run in the same commit as the completion effect at `:160-162` and lose the race. The completion effect and the finish-button call are untouched; one `saveLeaguePreferences(` site remains.
- **A F-3 / B F-3 (guard shape-only)** — hardened. `check-outlook-row-source.js` +1d (`inferred_outlook` anywhere in the fallback block, or an expression other than `outlookDisplayName(prefsQ.data?.team_outlook)`, is RED — #394), +2b (prefs query `enabled` must gate on `!!leagueId`, never `false`), +5c (effect condition exactly `beat === 'plan' && leagueId` with deps `[beat, leagueId]`; `&& false` is RED), +5d (`setStep(0)` inside an `if (<prev> !== leagueId) {` block, and not inside a `useEffect`). Every one proved RED by sabotage → revert → green; evidence in [build-report.md](build-report.md) §5.
- **A F-4 / B F-4 (`state/README.md`)** — added: store row (13) and a `ftf_team_review_completed` persistence-key row carrying the deliberate not-user-scoped note.
- **A F-5 / B F-1 (loading flash)** — accepted per Phase 3 ruling; no change. QA-B pytest row — accepted, no backend file in the diff.
- Verification on `cb893b09`: `tsc --noEmit` 0 errors; `check-outlook-row-source` 19/0; `check-team-review` 13/0; `check-calc-merged-layout` pass; `check-finder-conditions-reachable` 6/0; `check-inline-home` pass; `check-team-review-depth` 8/0; `testid-lint` OK.
