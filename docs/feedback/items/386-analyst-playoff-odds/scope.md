# Feature Scope — #386/#391 guide-spotlight layout notification on LeagueSummaryScreen

**Date:** 2026-08-24
**Entry point:** feedback #386 + #391 (2026-08-24 wave, Group D)
**Builder:** Group D author agent (branch `claude/new-user-feedback-55320e`); build agent TBD
**Operator sign-off on waivers:** not needed (the one waiver below is §1c "no NEW analytics"; existing instrumentation is named and unchanged)

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — guide beat rendering is already instrumented and this fix adds no new moment to measure. The v2 engine emits `guide_step_shown` with props `{step, pose, screen, spotlight}` (registered in `backend/analytics_taxonomy.py:78,895-896`; the `spotlight` prop exists precisely so a beat whose ring resolved can be told apart from a degraded one). `guide_step_advanced` / `guide_step_skipped` / `guide_step_suppressed` cover the rest of the beat lifecycle. The fix changes **when the overlay re-measures**, not when any event fires — no emitter is added, removed, or moved, and no property changes. Question answered by existing data: "did n5 show with a spotlight on this screen" (`guide_step_shown{step:'n5', spotlight}`). Verified there is no event for "spotlight re-measured"/"targets moved" in the taxonomy, and none is warranted: it would fire on every scroll tick.
- (a) not applicable — no new events. (c) not applicable — (b) answers it; nothing is waived beyond "no new events needed because the surface is already instrumented and unchanged."

## 2. Schema & flag scope

- New/changed tables or columns: **none** — no backend surface touched at all.
- New/changed feature flags: **none.** The fix is live whenever the guide itself is (existing `onboarding.v2` + `onboarding.guided_avatar` [+ `onboarding.guide_v2`] gates); with no tour active the added callbacks call into an empty listener set — a no-op — so a flag would gate nothing observable. Rollback lever is the ordinary revert of a 2-line diff.
- New env vars / `model_config` keys: **none.**

## 3. Evidence scope

- [x] **Structural guard:** extend rule 12 of the existing `mobile/tests/check-guide-spotlight-tracking.js` (`npm run test:guide-spotlight-tracking`, already wired in `mobile/package.json:38`) from calculator-only to a two-host list — pins: the wired ScrollView in `TradeCalculatorScreen.tsx` **and** `LeagueSummaryScreen.tsx` each carry `onLayout` + `onContentSizeChange` referencing `notifyGuideTargetsMoved`, with a loud `fail` (never a skip) when a host's `onScroll` wiring can't be found. Sabotage-proven per [prd.md](prd.md) §5a, including the not-self-satisfying demonstration. No new check file, so no new `npm run` script.
- [ ] **Unit tests:** none — no backend change (`backend/tests/` untouched); the mobile change is JSX props, which the structural guard covers mechanically.
- [x] **Code-walk proof:** required — outline in [prd.md](prd.md) §5b; build agent writes the full file:line trace against the landed diff.
- [x] **Manual TestFlight checklist:** required (runtime proof genuinely matters — the bug is a runtime measurement-staleness defect no static check can see end-to-end) — [prd.md](prd.md) §5c, 7 numbered steps with expected results.
- `testID`s added/renamed: **none** (`league-summary.pos-pills` and `guide.overlay` pre-exist, untouched); `mobile/scripts/testid-lint.sh` unaffected but runs in CI regardless.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed/changed — mobile-only, no network surface |
| `living-memory/LLD.md` | n/a | no convention shifted — this *applies* the existing B1 host-notification convention (already established by the calculator) to a second host |
| `docs/architecture.md` | n/a | no backend module wiring or data flow changed |
| `living-memory/HLD.md` | n/a | no architecture shift — 2 props on an existing component |
| `docs/cross-client-invariants.md` | n/a | no shared constant/enum/color touched |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | n/a | choice is precedented (mirrors the shipped #384 calculator fix), tradeoffs recorded in [plan.md](plan.md) §4 — nothing non-obvious left to log |
| `mobile/src/screens/CLAUDE.md` (extra row, honesty call) | **update at build** | the map's `TradeCalculatorScreen` row already documents its ScrollView announcing `notifyGuideTargetsMoved`; add the matching clause to the `LeagueSummaryScreen` row so the next editor doesn't strip the "unused-looking" props. One clause, no new section |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (untouched, must stay green) + `mobile-typecheck` (`tsc --noEmit` + the `check-*.js` suites, including the extended rule 12) + `maestro-testid-lint` — all on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming: guard run + both sabotage results (red) + restore (green), the code-walk proof location, and the TestFlight checklist handed to the operator.
- **TestFlight verification:** checklist in [prd.md](prd.md) §5c to be run by the operator; outcome logged in TEST_LEDGER. Note the fix rides a **client release** — it is not flag-flippable.
- Express lane declared by the operator? **No** — full gates (fast-track bug path, all four gates apply).
