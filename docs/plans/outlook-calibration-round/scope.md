# Feature Scope — Outlook calibration round

**Date:** 2026-11-06
**Entry point:** direct user request: give app testers current and candidate trade arms to judge.
**Builder:** Codex implementation with independent evaluation.
**Operator sign-off on waivers:** not needed; no waivers.

## 1. Analytics scope

Existing grading sessions/cards cover build, exposure order, skips, verdicts and reason tags. Add round attribution, exact versions, immutable frozen-input identity and generation/selection denominators to their private records. This is calibration feedback only: no organic impression, exposure-training, rank update or proposal events. Aggregate reporting partitions old and new rounds, complete and partial responses, and shared/unique cards. A shared card is one observation credited to both arms, not two independent observations.

## 2. Schema & flag scope

Add nullable round identity, first-exposure timestamp and unique cohort key to grading_sessions; legacy rows remain null. Add the non-personal grading_build_leases table; keep captured source state in the existing session record. One active session per account/league/round; completed answers persist and retries cannot overwrite first feedback. Add grading.outlook_prepare and grading.outlook_round, both default false, independent of public grading.blind and normal model selection. Rollback disables new round starts/builds while already exposed owned sessions/results remain attributable and readable. No global owner-model switch. No new environment variables.

## 3. Evidence scope

- Structural guard: existing mobile/tests/check-blind-grading.js plus new round contract checks: neutral card flow, compatibility labels only after completion, honest unsupported/insufficient errors.
- Backend tests: new test_outlook_calibration_*.py and test_calibration_round_*.py route/adapter tests; extend legacy grading isolation, DB concurrency/retry and deletion/retention contracts.
- Code-walk proof: architecture.md in this directory records capture, both-arm generation, final gates, private persistence and public projection.
- Manual TestFlight: start new round without opening Acquire; resume mid-round; retry a saved final answer; finish and see results; unsupported/unlinked league shows explanation; old installed binary renders generic Today's/New results. Operator records runtime outcome; no simulator/Maestro.
- No new testIDs planned; lint all existing IDs.

## 4. Docs scope

| Doc | Updated? | Section / reason |
|---|---|---|
| docs/api-reference.md | updated | Calibration round selection, retry and report |
| living-memory/LLD.md | updated | Frozen two-arm session and immutable feedback |
| docs/architecture.md | updated | Isolated comparison builder |
| living-memory/HLD.md | updated | Public Calibration round orchestration |
| docs/cross-client-invariants.md | updated | Blinding and backward-compatible result aliases |
| docs/glossary.md | updated | Calibration round |
| ADR | updated | Frozen paired comparison and compatibility aliases |
| docs/data-dictionary.md | updated | Round columns and private capture |
| docs/config-reference.md | updated | Default-off round selector |

## 5. Ship gate declaration

Full exact-head CI, backend tests, mobile TypeScript/structural checks and testID lint; independent evaluation; TEST_LEDGER entry. Parent owns push, merge, activation and bounded pregeneration. Existing connected/authorized accounts only, no external league discovery. KTC=0, paid enforcement off, global prepared inventory off, decoder opt-in off, website456 held. Express lane: no.

## Acceptance and boundaries

- Round outlook-v2-v3-1 compares owner-v2-bilateral-2 with owner-v2-bilateral-3 from one captured league/rosters/boards/preferences/format/config snapshot; model selector is the only policy change. V2 adapter omits v3's diagnostic evidence argument but common hash includes captured facts.
- Both inventories use full budgets and real ownership, owner proof, roster, significance, presentment and quality gates; a failed gate fails the build. No stale deck sourcing or old-arm substitution.
- Equal per-arm selection up to20; require at least1 per arm (under10 explicitly labeled a limited descriptive sample), preserve all inventory and duplicate denominators on insufficient/error. Shared packages display once. Randomized balanced order is frozen.
- Current/value_core are wire compatibility aliases only; private exact versions and round are authoritative. No answer key or counterparty boards on next-card/session endpoints.
- All app users keep access. Eligibility requires an authorized connected league with sufficient observed safety inputs. Sleeper supported initially; ESPN/MFL unavailable where full provider roster evidence is missing. Account-only/unlinked users receive honest guidance.
- Neutral unknown production fit remains an experimental policy correction, not validated forecasting. Calibration collects opinions; it does not automatically activate the candidate or establish predictive validity.
