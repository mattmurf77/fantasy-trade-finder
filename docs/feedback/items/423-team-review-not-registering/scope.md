# Feature Scope — G-423: outlook row reads saved preference; team-review completion recorded and shown

**Date:** 2026-09-08
**Entry point:** feedback #423 + #424 (fast-track bug path; batch [../422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md))
**Builder:** G-423 build agent (planner: investigation session 2026-09-08; [prd.md](prd.md), [investigation.md](investigation.md))
**Operator sign-off on waivers:** not needed (no waivers) — two product questions in PRD §7 need an answer before build, they are defaults not waivers

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it:** `team_review_beat_viewed {beat:'plan'}` (fires in `next`, `TeamReviewScreen.tsx:137-142`) marks "gone through it"; `team_review_exited {outcome:'completed'}` (`:296-298`) marks the button exit; `outlook_saved {source:'review'}` (`:173`) and `team_review_action_taken` cover the writes. Together they answer "did users who reached the plan beat see the minimized entry next visit" and "does the landing outlook match the last review write". No new property.
- [ ] **(c) WAIVED:** not applicable.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. Device storage key `ftf_team_review_completed` keeps its sparse-map format; the new store reads and writes the same key (no migration).
- New/changed feature flags: **none**. `trade.outlook_direction` stays `false` — it is an engine-weighting flag, not a display toggle; the fix is correct in both states. No kill switch added: the change is a bug fix on surfaces already live (`calc.inline_home`, `calc.merged_layout`, `trades.team_review`), and those remain the rollback levers for their surfaces.
- New env vars / `model_config` keys: **none**.

## 3. Evidence scope

- [x] **Structural guard:** new `mobile/tests/check-outlook-row-source.js` (+ `npm run test:outlook-row-source`) — pins: the calculator fallback's data source and null-only "Not set"; the single-sourced display-name helper; invalidation at every `saveLeaguePreferences` site incl. inside `savePrefs`; the plan-beat completion write; the store-backed read in `TeamReviewEntryCard`. Full table PRD §5. Existing `check-team-review.js` (13), `check-calc-merged-layout.js`, `check-finder-conditions-reachable.js`, `check-inline-home.js` must stay green.
- [x] **Unit tests:** none added — no backend change. `pytest backend/tests` runs unchanged in CI.
- [x] **Code-walk proof:** [investigation.md](investigation.md) §2 (the "Not set" read path, 8 cited steps) and §3 (marker write/read points); build agent re-cites post-edit lines in `code-walk.md`.
- [x] **Manual TestFlight checklist:** PRD §8, five steps — runtime proof matters because the bug is a rendered string and a stack-mount lifecycle, neither of which a structural guard can execute.
- [ ] **WAIVED because:** —
- `testID`s added/renamed: none expected (`calc.outlook-fallback`, `calc.outlook-fallback.change` unchanged and must stay inside the `merged ?` region for `check-calc-merged-layout.js` #5). `mobile/scripts/testid-lint.sh` stays in CI.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/changed; `GET/POST /api/league/preferences` contracts untouched |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifts; the "one writer per preference, shared `['league-prefs', leagueId]` key" convention is reaffirmed, not changed |
| `docs/architecture.md` | n/a | no module wiring change (a per-league device-local completion store is client-internal) |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | outlook enum strings and display names unchanged (All-in/Contending/Rebuilding/Tanking/Not sure already the #253/#394 vocabulary) |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` | updated (build) | one entry: "team review completion = reaching the plan beat; marker lives in a synchronous store mirrored to `ftf_team_review_completed`" — pending PRD §7 Q1 |
| `docs/config-reference.md:371` | updated (build) | `calc.merged_layout` row: the fallback now reads the saved outlook; "Not set" only when none is declared |
| `mobile/src/screens/CLAUDE.md`, `mobile/src/state/CLAUDE.md`/`README.md` | updated (build) | TeamReviewScreen row (invalidation in `savePrefs`, plan-beat completion); new store row |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs every `tests/check-*.js`, `.github/workflows/ci.yml:47`) + `maestro-testid-lint` — required on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the new guard's assertion count, the RED-by-sabotage pairs (PRD §5 rows 1, 4, 5, 6), and the four existing suites re-run.
- **TestFlight verification:** PRD §8 run by the operator on Lakeview + FFV3; outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **no** — full gates; `FTF_SKIP_SIM_GATE=1` on push per D-056 with the evidence above noted.
