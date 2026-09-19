# Feature Scope — Security and data hardening

**Date:** 2026-09-04
**Entry point:** direct request to remediate review findings 1–5 using Astra medium subagents
**Builder:** Codex coordinating five bounded Astra medium subtasks
**Operator sign-off on waivers:** not needed; no waivers

## 1. Analytics scope

Existing events cover this change: signup/app_open/league_synced describe session initialization; deck_card_viewed/swipe_undone describe recommendation outcomes. No additional collection. Stop recording authentication tokens as analytics identifiers; validate existing outcome events before any write. Delete user-linked analytics when an account is deleted.

## 2. Schema & flag scope

No new product tables, columns, environment variables, or dependencies planned. Reuse verification/session/credential/identity and analytics schemas. Any cleanup uses an explicit, reviewable offline operation, never live production access in this task. Verified ownership is an authorization invariant; a feature flag must not reopen private data access. Retained flag compatibility and operational rollout implications will be documented.

## 3. Test scope

Per current D-056 policy, evidence consists of backend regression tests and a written code trace; no simulator or Maestro work. Cover unverified private read/write/export/deletion denial, verified and demo success, identity mismatch, authoritative platform/co-owner roster input, token-free analytics persistence, full credential/session/identity deletion, cross-user and unauthenticated outcome rejection, input validation and rate limits. Run focused tests first, then combined backend checks. Client changes, if required, get structural/type checks plus concrete manual TestFlight verification instructions. No testID or visual changes planned.

## 4. Docs scope

| Doc | Plan | Reason |
|---|---|---|
| docs/api-reference.md | Update | Auth/session/event/deletion contracts |
| docs/data-dictionary.md | Update | Session-id semantics and deletion coverage |
| docs/config-reference.md | Update if required | Remove authorization dependence on grace flag |
| docs/runbook.md | Update | Existing token cleanup/revocation and rollout |
| living-memory/LLD.md | Update | Verified ownership and telemetry invariants |
| docs/architecture.md | Update | Authoritative input and validated analytics data flow |
| living-memory/HLD.md | Updated | Document single-worker deletion coordination limit |
| docs/cross-client-invariants.md | Update if required | Shared session verification contract |
| docs/glossary.md | n/a | No new domain terms |
| living-memory/DECISIONS.md | Updated (D-183 / ADR-017) | Ownership compatibility and deletion-work coordination |

## 5. Delivery gate

Deliver reviewed local branch with scoped regression evidence and any remaining rollout requirements; no commit, push, deployment, production cleanup, or external messages requested. Preserve the original workspace's existing modifications. TestFlight checklist must include verified sign-in/league activation on Sleeper, co-owned Sleeper, ESPN/MFL imports; username-only verification recovery; sign-out; account deletion and relaunch. Deployment cannot be considered verified by local tests.


## Completion evidence

Implementation and follow-up review complete on the isolated branch. Final backend on Python 3.12: 4,707 passed / 1 skipped; actual PostgreSQL: 54 passed. Mobile: 91 guards, TypeScript, testID lint and Hermes export passed. Web: 23 auth checks, 180 structural checks and loaded-extension Chromium runtime passed. Reference docs, HLD/LLD, decisions, handoff and test ledger updated. No schema additions, new flags or product dependencies. See [review](review.md) and [mobile evidence](mobile-evidence.md) for the physical-device and production rollout checks still outstanding.

## Follow-up validation and release blockers

The operator authorized addressing the remaining blockers after the combined review. This extends the same isolated workstream with user-work fencing during deletion, concrete export/retention gaps, browser and extension verified ownership recovery, and Python 3.12 plus actual isolated PostgreSQL execution. Browser verification uses explicit extension-mediated Sleeper proof; ESPN/MFL browser entry must direct users to the supported mobile verification flow rather than claim ownership from a team selection. No new product data collection or production credential access is required.

Mobile review additionally covers late proof/source-link/initialization responses after account changes or unmount. Behavioral regressions must demonstrate the old failure before the fix. Build verification may export an iOS JavaScript bundle; this is not a native or TestFlight runtime pass. A physical-device availability check and an operator TestFlight handoff remain necessary when no device is accessible.

The delivery boundary above remains: reviewed local work and reproducible evidence, without merging, deployment, TestFlight distribution, or production cleanup.

## Deployment authorization — 2026-09-05

The operator subsequently requested “Deploy.” Release work now includes merging current main, green PR CI, publishing the unpacked extension package, Render deployment and the matching EAS/TestFlight submission. Physical-device verification remains outstanding as disclosed. Historical token cleanup and contaminated membership resync remain separate maintenance operations. See [deployment evidence](deployment.md).
