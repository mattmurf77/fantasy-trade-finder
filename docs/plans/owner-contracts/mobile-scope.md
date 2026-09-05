# Feature Scope — mobile trade request continuity

**Date:** 2026-09-05
**Entry point:** direct owner implementation request following the owner interview
**Builder:** Astra Ultra mobile subagent; parent reviews and integrates
**Operator sign-off on waivers:** not needed (no waivers)

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `calc_find_a_trade_tapped` records the canvas path, side counts and partner choice; `find_trades_tapped` records dispatch source/mode; `trade_card_viewed` and the existing #277 deck outcomes cover results. Reuse these names and their registered properties without new data collection. Existing error/empty presentation needs no new event family. If Off removal is coordinated, retain `stud_tax_mode_changed` for actual user changes only, not hydration.

## 2. Schema & flag scope

- Tables/columns, flags, env/model-config keys: none.
- Pass the existing `fairness_threshold` API argument; add client-only selected-asset handoff data. No new server contract, account-fairness storage, experiment policy or loss limit.
- Preserve current Win Now, telemetry, policy/security wiring and existing `calc.results_push`/`calc.inline_home` posture. Rollback is a reviewed code revert; no new knob.
- Hold both-options/minimum-coverage fallback, More Offers keep/release defaults and saved-tag persistence. Off UI removal is held until legacy-value normalization is approved with the policy owner.

## 3. Evidence scope

- [x] Structural and runtime-pure guard: `mobile/tests/check-owner-search-continuity.js`, registered as `test:owner-search-continuity`; update only obsolete assertions in directly affected existing guards.
- [x] Backend unit tests: none in this mobile-only branch; parent/policy agent own backend evidence. Pure JavaScript execution exercises the real TypeScript request helper.
- [x] Code-walk: `mobile-code-walk.md`, with final source lines and held pieces.
- [x] Manual TestFlight: `mobile-testflight.md`, concrete navigation/pending/empty/failure scenarios. No simulator or Maestro (D-056).
- Static testIDs for anchored empty/back recovery if needed; no retired-flow edits. Run testID lint, relevant guards and TypeScript.

## 4. Docs scope

| Doc | Updated? | Section / reason |
|---|---|---|
| `docs/api-reference.md` | n/a | Existing endpoint/optional fairness argument; no server route change. |
| `living-memory/LLD.md` | parent integration | Client handoff/state convention; parent owns central documentation. |
| `docs/architecture.md` | n/a | No backend/module architecture change; existing mobile search paths retained. |
| `living-memory/HLD.md` | n/a | No new client or major flow. |
| `docs/cross-client-invariants.md` | n/a | No constants/enums/colors changed. |
| `docs/glossary.md` | n/a | No new user-facing domain term. |
| ADR / `DECISIONS.md` | parent integration | Owner handoff is the authority; unresolved product decisions held. |

## 5. Ship gate declaration

- No push, merge, release, EAS build or worktree deletion in this subtask.
- Parent must review the complete diff, run integrated CI (backend tests, mobile guards/typecheck, testID lint), and write the central TEST_LEDGER before push.
- Manual TestFlight remains unrun until the operator executes the checklist.
- Express lane: no. Current dirty shared checkout remains untouched.
