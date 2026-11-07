# First-page polling failure recovery

Date: 2026-11-07. Base: main `fabb5e36`. Trigger: physical build 178 testing reported two searches without a visible trade. This correction addresses an independently reproduced client failure state; it is not yet the proven cause of those device attempts.

## Defect and change

When a paged job has not delivered any card, six consecutive status failures stop its bounded polling loop. The screen currently keeps the job running and never sets its search-failure state. Its page-error UI requires at least one held card, so the actual render continues showing the loading spinner with no timer or retry control.

After that existing final failed poll, clear only the local running-job handle and show the existing `poll_abandoned` failure and Try again control. Retain the exact last model request for that explicit retry. Reuse the existing tap/search-ID accounting; no automatic generation retry, preview consumption, network deadline increase or unlimited polling. The existing six status attempts already allow transient failures to recover without generating a new job. Held-card pagination, validation/epoch guards, paywall handling and server jobs remain unchanged.

## Verification and scope checks

Execute the actual extracted page-fetch function and actual TSX render branch under Node with synthetic responses and timers. Cover zero-card failures, first-run skeleton, held-card behavior, recovery before the limit, obsolete/unmounted responses, gates, and an actionable retry using the actual tap/dispatch functions. Retain all mobile CI checks, TypeScript and test-ID lint; no simulator or Maestro.

No analytics schema, API, backend/model, feature flag, weekly forecast cadence or storage change. Existing failure events and test IDs remain authoritative. Update screen documentation and the test ledger. No production reads or writes in this implementation; release owner controls build and deployment. The 200 ms target remains unfulfilled.
