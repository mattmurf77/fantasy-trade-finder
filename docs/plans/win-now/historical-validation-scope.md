# Feature Scope — Win Now historical outcome validation

**Date:** 2026-09-04
**Entry point:** direct request to calibrate using prior Sleeper outcomes
**Builder:** parent with Astra subagents; parent reviews all changes
**Operator sign-off on waivers:** not needed; offline-only evidence scope explained before build

## 1. Analytics scope

**WAIVED:** an operator-run, read-only research tool has no product analytics events. Its capture manifest and validation report record collection, inclusion, exclusion, and source provenance directly.

## 2. Schema & flag scope

No database tables, API routes, feature flags, environment variables, or production model settings change. New local JSON captures contain league settings, anonymous roster IDs, weekly scores and player IDs, and playoff outcomes; user profiles and personal valuation boards are not collected. Network access is bounded to public Sleeper reads for the existing research cohort or explicitly selected leagues. Production probabilities stay experimental and default-off.

## 3. Evidence scope

Backend unit tests cover outcome extraction, historical-chain traversal, missing/unsupported seasons, cutoff and provenance rejection, join isolation, and calibration metric correctness. Parent performs a real read-only capture and an offline report run. No mobile/web behavior changes: structural UI tests, TestFlight, and testIDs are not applicable. No Maestro or simulator runs. A code-walk and reproducible commands will accompany the report.

## 4. Docs scope

| Doc | Status / reason |
|---|---|
| API reference | n/a: no routes change |
| Data dictionary / LLD | n/a: no production schema changes; local file contracts in validation guide |
| Architecture / HLD | updated both reference and memory with separate offline collection/evaluation flow; no production wiring changes |
| Cross-client invariants | n/a: clients unchanged |
| Glossary | existing calibration terminology; explained in validation guide |
| ADR / decision | add provenance distinction to existing ADR-017 / validation guide |
| Scripts README | document capture/evaluation commands |
| TEST_LEDGER / HANDOFF | updated with parent 119-test run, live capture, source audit and remaining evidence constraints |

## 5. Ship gate declaration

Local implementation and evidence only; no merge, push, release, automatic flag graduation, or scheduled capture. Run affected backend tests and source validation. Existing hosted CI and device release gates still apply before shipping the feature. Historical outcomes alone cannot prove the calibration of player forecasts captured after those outcomes; report that gap explicitly rather than relabeling a different model as validated.
