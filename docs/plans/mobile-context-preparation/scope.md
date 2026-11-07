# Exact-context mobile preparation lifecycle

Date: 2026-11-07. Direct authorized 200 ms follow-up; baseline7e52047e. No production changes or model/selector changes. This unit removes serial preparation work and fixes stale storage/context races; it does not establish a universal200ms result.

## Analytics scope

Existing find-trade tap, first-visible and input-change events retain their semantics. No new event or identifier is needed for an internal preparation/storage lifecycle fix. Synthetic executable tests measure ordering and requests; physical timing remains a separate acceptance task.

## Schema and flags

No database/schema/flag/setting change. Existing v2 organic device-page envelope, five-minute bound, exact user/league/format/scope, preview guard and server currentness checks remain. No selected-result persistence, old-scope filtering, preview grant or passive exposure is added.

## Implementation and evidence

- Serialize page persistence and clear barriers; delayed hydration checks global and per-key invalidation/discard state.
- Run disk hydration independently of fresh preparation. Resolve fairness/request and shared session readiness concurrently; bind current identity/token after readiness and throughout polling/adoption.
- All focus/foreground callers cancel replaced contexts. Captured valid scoring format is passed to existing request-local server header support. Existing scoring invalidation is retained, with a fence through server and local mirror completion.
- Tests execute actual TypeScript modules/effects with delayed storage, context swaps, writes, cancellation and late responses. Keep selected model/fair handoff and paywall assertions. TypeScript and test-ID lint required. No simulator/Maestro under D-056.

## Documentation scope

Architecture/internal flow and existing prewarm documentation updated; no route/schema/HLD/shared enum/glossary contract change. API semantics remain the existing request-local scoring header and current-only envelope. Living-memory ledger/handoff records tests and limits. A manual TestFlight checklist will cover active/background, league/format/preference changes and immediate taps; no device result is claimed from Node tests.

## Release gate

Independent review, full CI on final head and root-coordinated release. No express waiver. No backend production activation, benchmark load or forecast regeneration. The previously shipped scheduled projection capability stays intact.

## Execution boundary and remaining risks

`state/tradePagePreparation.ts` is shared by the tab hook and Trades focus/foreground effects. It starts hydration independently, joins request resolution and session readiness, then captures the session revision. The store captures scalar key/scope/format and a detached organic request, rejects unknown formats or scope mismatch, and sends the same `X-Scoring-Format` and `X-FTF-Prewarm` on generation and every status poll. Request-local format handling already exists on the backend. Neither a delayed old response nor its finalizer may adopt over or unthrottle a newer attempt.

Storage mutations use one ordered promise queue. Already dispatched writes finish before a clear/global invalidation barrier; subsequent valid page writes follow it. Global invalidation includes pages still only on disk. Per-key hydration checks reject a page invalidated while disk reads were pending. Storage failures remain best effort under the existing age/current-only gates; this is not a new durable transactional store.

The scoring wrapper extends the existing pending-write counter through POST acknowledgement, AsyncStorage/module mirror, and zustand mirror. It releases in `finally`, including failure, without opening a gap between overlapping writes. Existing eviction remains; completed pages are not retained across format writes. The pre-existing scoring application queue itself is not account/league-generation bound; this unit protects passive-page preparation, not every foreground scoring request. A separate coordinated format-transition contract is still needed before claiming all account/format switch races solved.

No changes to selected-player model requests, fairness-only sweep, exact one-tap handoff, preview admission, model search/gates, backend source hashes, Calibration or scheduled projections. Preference or selected-player changes that require fresh computation can still take seconds. No local server, Node ordering test or prepared-cache hit establishes all-context tap-to-visible 200 ms.

## Manual TestFlight checks (not yet performed)

1. With a valid connected league, cold launch to Home/Rank; navigate to Acquire while disk recovery is slow. Verify the current organic page can prepare and its tap still records the normal first-visible event.
2. Switch league A→B→A and format SF→1QB→SF, including background/resume mid-request. No previous context's cards should replace the selected context; in-flight input writes must not use a held page.
3. Change fairness/rankings during a pending warm job, then tap. Verify exact new request and current server validation; no earlier preference page adoption.
4. Logout/account replacement during preparation, relaunch and return to the same account. A cleared page must not reappear from an earlier disk write.
5. With paid enforcement on in a test environment, a non-entitled passive request must neither grant/consume a preview nor open a paywall; the real tap retains its existing access gate. Test a selected model request and a give-side fairness sweep to confirm selectors remain exact.
6. Record real-device tap-to-first-visible durations, cold/no-page/error and abandoned attempts separately. Fast empty/error states are not card successes. No 200 ms acceptance is recorded by this patch.

## Local verification — 2026-11-07

- `npx tsc --noEmit`: pass.
- `bash mobile/scripts/testid-lint.sh`: pass (run from `mobile/` as `bash scripts/testid-lint.sh`).
- Exact CI mobile glob, `for f in tests/check-*.js; do node "$f" || exit 1; done`: all **165 scripts pass**. This includes existing selected model/fair handoff (28 cases), paywall, projection/Home and current-only device-page guards.
- Focused new/expanded checks: 21 tab/shared prewarm cases; 10 storage/request-context cases; three actual format-application cases; 13 shared-helper/actual screen-effect cases. New copied controls have portable TypeScript imports and fail on uncompleted asynchronous cases. Final formatting-only test changes reran all 26 copied cases successfully.
- Independent reviewer executed the same five runtime files separately: 26 synthetic JS controls plus four actual backend request-local format/generation/status capture checks. Backend tests stayed in external audit artifacts to retain a mobile-only patch. Final commit binding follows the source freeze.
- `git diff --check`: pass. Read-only living-memory audit records inherited CHANGELOG/TEST_LEDGER header/TOC/reference drift separately; no broad cleanup. Handoff remains below 2,000 bytes.
- These results establish control flow and regression behavior. Full CI on the committed head, independent exact-SHA binding and physical TestFlight checks remain distinct release evidence.
