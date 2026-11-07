# Cooperative cancellation of obsolete owner work

2026-11-07. Isolated from main `974452ff`. Review candidate only; keep unmerged during the Calibration release. This unit does not depend on PR615/617 or activate their unwired interfaces.

## Problem and bounded change

An invalidated or superseded job already loses publication permission, but its worker continued full owner enumeration and fresh final evaluation. A prepared target checked for interactive work before entering the engine, then could compete with a new interactive request until completion. The existing prepared retry mechanism also charged interactive deferrals against the failure budget.

The actual worker now passes a private execution checkpoint into the owner search and final occurrence evaluator. The callback uses the job's existing registry/epoch liveness under the job lock. It is separate from captured model kwargs, model policy, candidate budgets and proof data. Constructors, opponent rounds, final occurrences and the boundaries around global ranking check it. Cancellation raises `TradeWorkCancelled`; it never returns a partial inventory, a normal shortage, or a failed bakeoff arm that allows fallback. The worker clears its own pending-final-check state and preserves the original terminal/invalidation reason. It never cancels the replacement job.

Prepared generation additionally checks for local interactive work and disabled preparation. At most once per second of cooperative progress it validates the existing durable generation stage/claim using the established participant lifetime, token, index and lease checks; it renews only that same eligible claim. A stopped, expired or replaced claim cannot complete its successor. This is an SQL polling interval, not a wall-time bound.

Interactive preemption first aborts staging, then atomically returns only the matching live claim to pending with reason `interactive_work` and a 30-second retry time. The attempt is refunded because scheduling pressure is not a generation failure. Repeated pressure remains truthfully pending, without claiming readiness or exhausting the failure budget. Real failures retain existing bounded retries. A transient durable-check outage raises a distinct typed stop, so bakeoff or selected-request error handling cannot turn it into a successful empty inventory. A stale token cannot refund or complete a new claim.

## Preserved contracts and limits

- All generation budgets, candidates, mathematical evaluation, complete ordering, fresh final evaluation, roster/quality checks and durable-publication fences remain intact for current jobs. No proof reuse, fast decoder activation, new global flags or model change.
- Cancellation is cooperative. Source calls, constructor work between checkpoints, one candidate's math, global ranking, later roster/quality/serialization/sealing calls can finish before another check. Existing publication/claim fences remain necessary and authoritative.
- Foreground pressure detection is process-local, as was the existing preparation admission guard. Durable preparation still has its existing global singleton lease; interactive workers are not newly bounded by a queue. Cross-process priority, fairness and sustained-load admission are a later unit.
- Prepared work may remain pending indefinitely under sustained interactive traffic. The target state/reason exposes this; no progress guarantee is made. Stopped/expired staging that cannot be deleted under its revoked claim remains subject to existing retention cleanup and is never adopted.
- Same-job cancellation is an execution control, not evidence of complete/atomic model-input capture or provider freshness. It does not repair missing invalidation writers.
- Cold current requests still perform full work. No local server measurement establishes tap-to-visible-card <=200 ms, including changed inputs, cold network/process and failure cases.

## Verification and release

Verification covers all four owner model entrypoints, exact full-proof/report parity with an always-live callback, cancellation before construction and during final occurrences, actual superseded worker/replacement completion, real prepared interruption/cleanup/retry, repeated deferral without retry exhaustion, and stopped/reassigned token fencing. Large synthetic worker comparisons must retain all ordered native/final/public/durable proof digests and full inventories. Timings diagnose overhead only; they are not a speedup claim.

Before merge, finish independent review, affected suites and exact-head CI. Keep this change unmerged until the parent coordinates the Calibration source-hash boundary: even behavior-preserving backend changes invalidate eligible unexposed comparison sources. No production operation is part of this unit. Rollback is a code revert; previously running threads are not reloaded in place. No data migration is introduced.

## Recorded evidence

Final affected suite: **1,302 passed,2 skipped in134.82s** across46 files. Independent final verification: **23 passed3.22s**, including seven reviewer controls plus sixteen builder cases, with all ten runtime hashes stable. The reviewer reported no outstanding reproduced defect.

Final actual-worker control/candidate comparison preserves **7,213 ordered cards** (6,430 organic,701 opponent,82 receive), complete native/final/public/durable proof digests and generation reports. Generated IDs/expiry and report elapsed time alone are excluded. Every persisted served valuation is reread from isolated SQLite. Synthetic first publication19.164→19.454s,1.952→1.865s,.385→.431s is mixed; no speedup/overhead bound or200ms claim follows from this one local diagnostic pair. Source hashes remained unchanged during the final sample.

## Next implementation slice

Measure simultaneous current interactive requests and prepared work on the deployed capacity before choosing an executor bound. Add a bounded priority admission mechanism only with explicit queued/running/deferred states, exact-request single-flight, latest-request cancellation, account/league scope isolation, restart/lease recovery and starvation accounting. Queue time must remain in the original tap attempt denominator. Preserve exact full-search quality and existing publication checks. Separate this resource-management work from coherent-input/proof-reuse research and from any claim that cold computation fits 200 ms.
