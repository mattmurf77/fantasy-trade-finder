# First-action latency: initial research results

2026-09-21. Three Astra Ultra workstreams completed; parent reviewed the reports and prototypes and independently ran all 31 research tests. This is an initial research milestone, not completion of the full qualification plan or a production release. Application code, production records, arm settings and infrastructure are unchanged.

## Decision

Continue code-first. The strongest path to the owner's three-second first-action goal is **version-valid prepared inventory, compact early delivery, and faster construction/evidence processing**. Existing app-open preparation is a starting point, not proof that fresh results will be ready. Fix duplicate work and invalidation before relying more heavily on reuse. Keep every eligible offer accessible; 20–30 is an initial delivery batch, not a search or output cap.

Do not promise three seconds for an entirely cold search yet. Current global ranking happens after construction, and the owner constructor does not stream. Publishing an arbitrary early candidate would change the best-first contract. A cold path needs measured construction improvements, a proven stable-prefix method, or a separately reviewed progressive-order tradeoff; it cannot be solved by paging alone.

## What the evidence establishes

| Boundary | Observation | What it does not establish |
| --- | --- | --- |
| Production, seven completed jobs | Worker median 61.094 seconds; engine median 13.323 seconds | Tap-to-tile, p95, failed-job distribution or stage attribution |
| Reconstructed local full worker, three runs | 13.015–13.200 seconds; first durable cards near completion | Production host/Postgres/device performance |
| Local worker median stages | Construction 5.910s; revalidation 2.144s; evidence/publication 3.858s | Safe removal of any checks or direct production savings |
| Reconstructed public response | 2,354 final cards; exact Flask body 3,218,422 bytes | Production wire bytes or phone decode/render time |
| Matched compact response encoding | Full deck 2,980,527 bytes; first 30 cards 37,348 bytes, 98.75% smaller | A working paged mobile contract or earlier server readiness |
| Structured evidence experiment | Local preparation/compaction median 2.126s to 0.784s, exact storage/evidence parity | Integrated worker improvement; fixture interning was outside timing |
| Exact package-price memoization | Full candidate/output parity, no meaningful speed improvement | A useful optimization; reject this variant |

Production jobs and local reconstruction are different samples and environments. Their counts and times must not be combined into a synthetic end-to-end speedup. Local Python was 3.14; production pins 3.12. The seven production engine/worker matches use account/league and close timestamps, not a common trace ID.

## Prioritized implementation experiments

1. **Make reuse safe and measurable.** Add a full input/version fingerprint, atomic same-search admission and supersession fencing. Reproductions currently show duplicate cold-job admission, stale running-job reuse after outlook invalidation, and missed invalidation when rankings change during a job. Ensure app-open and scheduled preparation use the actual saved request settings. Instrument tap, request, first durable availability, response and first visible enabled tile with one trace. Preserve the existing exposure-event definition.
2. **Reduce evidence CPU without losing evidence.** Preserve actual shared immutable objects through row assembly and compaction, measure all preparation costs, and verify exact expanded evidence, identity, storage atomicity and memory. Then evaluate deferred proof encoding and reuse of unchanged evaluations only under complete input/package validation. The price-cache experiment should not enter production.
3. **Publish committed prefixes after final ranking.** Allocate immutable offer IDs and global ordinals once; atomically commit validation evidence and availability for the first useful batch, then continue all remaining offers. Exercise failures before/after commit and supersession. This reduces the post-construction barrier without pretending generation itself is streamed.
4. **Negotiate compact pages with mobile.** Separate worker completion from client exhaustion. Preserve legacy cumulative responses; existing clients would stop after a truncated `complete` response. New clients must apply equal-size successive pages, retain the front card, handle eligibility removals, resume/retry safely and prefetch before depletion. Test adaptive foreground polling against request load; current scheduled idle gaps can reach 4.4 seconds.
5. **Prepare the right work before the tap.** Use measured active-league app-open reuse first, then event-driven dirty-dependency refresh and targeted periodic batches. Persist inventories with scoped versions if cross-process/restart reuse is needed. Time-based expiry alone is not correctness. Run background work without unsolicited notifications or competing with interactive work.
6. **Qualify cold searches and scale.** Benchmark on pinned Python and a production-sized isolated environment, then real devices and representative concurrent load. Measure current/10x/100x demand scenarios using observed workload. Consider dedicated workers/shared job state before extra web replicas; evaluate hardware or platform changes only against the measured bottleneck.

Steps 1–4 are implementation-sized follow-ups, not application changes made by this research. Step 5 is the most credible route to common-case three-second results; step 6 must separately qualify cache misses rather than hide them in a blended average.

## Three decision options

- **Smallest safe improvement:** production-shaped evidence optimization plus correct in-flight reuse and committed-prefix publication. Likely reduces waiting, but no three-second claim.
- **Credible three-second path:** current prepared inventory, compact first-page delivery and measured client actionability, with a separately qualified cold path and no offer cap.
- **Long-term scale:** durable scoped inventories, shared job claims/leases, dedicated compute and dependency-aware background refresh. This is not a recommendation to buy or migrate infrastructure now.

## Validation and unfulfilled gates

The parent independently ran the three research suites together with `DATABASE_URL=sqlite:///:memory:`, fixed hash seed and socket connection functions blocked: **31 passed in 2.12 seconds** (7 pipeline, 17 delivery, 7 compute). Test duration is not an app latency measurement. Prototype tests cover protocol/representation properties; they do not replace integration CI.

Still unexecuted: full tap-to-tile tracing with at least 95% attribution, representative 30-run distributions, production-shaped Postgres integration, Python 3.12 timing, full affected application CI, physical TestFlight checks, concurrent-load/resource tests, actual cache-hit/waste rates, and verified full monthly infrastructure cost scenarios. No three-second SLA, cold-search p95 or production speedup is established. See the delivery report's concrete device checklist before any release.

## Evidence and reproducibility

- [Revised full research plan](../research-plan.md)
- [Scope and boundaries](scope.md)
- [Full worker and cache correctness investigation](pipeline.md), [sanitized measurements](pipeline-results.json)
- [Delivery contract, payload measurements and device checklist](delivery.md)
- [Compute/storage experiments](compute.md), [compute results](compute-summary.json), [storage results](compute-storage-summary.json)
- [Render, precompute, capacity and platform review](infrastructure-and-precompute.md), [sanitized production observation](production-observation.json)

Research code and tests live on local branch `codex/trade-latency-research-plan`, based on freshly fetched main `4913ad0c68af5e75f864c46cff692ca5f9bf842b`, in `/private/tmp/fleeced-trade-latency-plan`. Run reproduction commands there, not against the unrelated historical/canonical branch. The canonical project contains a durable copy of these reports. Source links in reports refer to the pinned research baseline. Private fixtures, credentials and raw user offers remain outside Git; sanitized aggregates and digests are retained. Nothing was pushed or deployed.
