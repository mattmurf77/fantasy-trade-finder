# Trade search latency — scope

Date: 2026-09-19. Entry: direct operator report of minutes-long Find a Trade; target approximately three seconds. No express lane or gate waiver.

## 1. Analytics scope
Existing bakeoff_runs total_ms/arms_json and deck storage logs establish generation and storage costs. No new analytics events or collection. Timing regression evidence uses local synthetic inputs and an access-controlled replay; private inputs are not committed.

## 2. Schema and flag scope
No schema, flags, runtime settings or search-budget changes. Preserve every eligible offer, order, valuation, frozen evidence and fail-closed final checks. Revert the code change to roll back.

## 3. Evidence scope
Backend tests: live flag reload/unknown flags; lossless diagnostic compaction, scope isolation and atomic paging; owner search equivalence and relevant existing suites. Profile generation and diagnostic preparation before/after. Mobile structural guard/testIDs: n/a, no client change.
Manual TestFlight: on the existing compatible binary, cold-open the affected league, tap Find a Trade with an empty canvas, measure tap to usable first card; repeat warm, with SEND/GET selections, and after a ranking change. Confirm selections and fresh rankings apply, cards are actionable, and no results appear before final validation. Record measured times; target <=3 seconds, report misses. Repeat with simultaneous searches before making load claims.

## 4. Docs scope
Update docs/architecture.md for hot-path lookup and diagnostic processing. API reference, engineering conventions, cross-client invariants, glossary and ADR: n/a, contracts/terms/architecture unchanged. Historical HLD/LLD stubs are not update targets. Record investigation and benchmark limits in this initiative and TEST_LEDGER.

## 5. Ship gates
No merge or production change yet. Require current-head CI before release; record all executed checks and unexecuted device/production performance verification. A local benchmark cannot establish a production three-second result.
