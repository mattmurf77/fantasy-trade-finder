# First-action latency: initial backend release scope

Date: 2026-09-21. Direct owner authorization: “I'm aligned. Let's push it live.” This implements a bounded first production increment from the reviewed research, not every exploratory architecture proposal. No express lane or waived CI gates.

## Outcome and boundaries

Prevent duplicate/stale in-flight searches, preserve actual shared diagnostic objects through storage, and publish the first 30 fully checked owner cards after durable evidence commits while the remainder continues. Existing clients receive cumulative running snapshots and eventually every eligible offer. Preserve final global ranking, exact terms, immutable action IDs, personal valuation and all safety gates; no candidate budget or output cap changes. Reject the ineffective package-price cache.

New cursor/page/mobile interfaces, expanded nightly scheduling, cross-process durable inventories, paid infrastructure and vendor changes are deferred. They need their own integration and rollout. This backend increment does not establish a three-second cold-search result. No model/arm/config changes are authorized as a side effect of deployment.

## 1. Analytics

Existing `trades_generated` and bakeoff run events retain their semantics; record completion only for a successful live job. Existing application logs plus local measurements distinguish first durable batch and total completion. No new analytics events, raw-data collection or changed exposure definition. Phone tap-to-first-action tracing remains deferred with the new mobile delivery work and must not be inferred from worker timing.

## 2. Schema and flags

No new tables, columns, credentials, dependencies, paid resources or runtime arm settings. Structured feature roots are private in-process preparation only; stored expanded diagnostics and valuation fields must remain lossless and equivalent. Existing persistence/ownership semantics continue. First-batch size is a bounded delivery implementation detail, not an offer count cap. Rollback is redeployment of the pre-release commit; no schema rollback required. A new production toggle, if found necessary, must be explicitly documented before introduction.

## 3. Evidence

- Unit/integration regressions: actual route/job concurrent admission, preference/rank invalidation during work, force/selected search isolation, timeout/supersession, first-batch commit, later failure, global ordinals, stable IDs, complete final inventory and structured/legacy diagnostic parity and atomic rollback.
- Differential replay: frozen fixture with exact candidate/package/order/evidence checks where the harness can reproduce the changed boundary; report incomplete fixture context and pinned-runtime differences.
- Full backend pytest and current CI mobile typecheck/structural/test-ID and web checks. No simulator/Maestro. No mobile source changes or test IDs expected.
- Concrete manual existing-TestFlight checklist: cold search first cards while running; actions on first cards; continued cumulative growth without losing front card; full inventory accessible after completion; rapid re-entry joins; ranking/outlook change refreshes; selected/forced search isolation; background/resume; failure/timeout does not publish unchecked offers. Physical checks remain explicitly unrun until the operator supplies results. Automated release does not imply a device latency pass.
- Read deployment SHA/status/health and arm/settings preservation after deployment. Do not forge user sessions or run test/seeding scripts against production.

## 4. Canonical docs and ownership

Parent owns scope, API/architecture/data reference updates, release/runbook evidence and test ledger. No HLD/LLD stub updates (current workflow supersedes the template's legacy entries). API reference documents cumulative partial availability and terminal/error semantics; architecture documents job claim/freshness and commit-before-publication; data dictionary clarifies structured preparation and global ordinals, with no schema change. No new shared enum, glossary term, feature flag or settled platform ADR.

Compute agent owns diagnostic compaction/database and logger assembly. Delivery agent owns worker publication. Cache agent owns admission/invalidation/freshness. Coordinate shared helper signatures; parent reviews all diffs. Unrelated canonical checkout work is preserved; implementation stays on `codex/trade-first-action-release` based on current main plus research-only evidence.

## 5. Ship gate

Require exact-head green current CI, independent parent review, regression evidence and an explicit rollback SHA before merge/deploy. Deploy tested main explicitly if Render autodeploy remains disabled; verify actual effective deployment without toggling arms. Backend-only release requires no new TestFlight binary. Record unrun physical-device/scale/three-second gates honestly; broader latency plan remains in progress.
