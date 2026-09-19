# Find a Trade latency investigation

2026-09-19. Status: performance changes prepared locally; not released. The approximately three-second production target is **not yet demonstrated**.

## Production evidence

Read-only Render logs and a read-only PostgreSQL transaction (10–15-second statement timeout), inspected September 19. No production generation, flags, budgets, infrastructure or records were changed.

Existing `trades_generated.props.gen_ms` includes the full worker, unlike `bakeoff_runs.total_ms`, which covers engine generation/composition only. In the bounded September 12–19 sample, 18 interactive completions took **18.14–75.44 seconds**, median **43.06 seconds**. The 25 background replenishment completions took 10.01–29.09 seconds, median 17.44 seconds. This excludes unfinished/failed requests, transport and device rendering; it does not bound the user's experienced delay.

Two September 19 interactive jobs completed in **43.79 and 47.99 seconds**, serving 1,647 and 1,933 cards. For the latter:

| UTC time | Evidence |
|---|---|
| 16:43:45.89 | Pick inputs injected; worker underway |
| 16:43:55.84 | Owner generation returned 2,190 cards; engine time 9.526 seconds |
| 16:44:05.74 | Final presentment count 1,933 |
| 16:44:22.90 | Client still polling an empty running snapshot |
| 16:44:33.28 | Deck storage completed: 1,933 rows, 3,348,178 inline feature bytes |
| 16:44:33.58 | Completed-worker analytics: 47.99 seconds |

The ~27.5 seconds between presentment and storage completion includes row assembly, compaction and database writes, not just SQL execution. A subsequent restart was a deployment, not evidence of an out-of-memory crash. Earlier September 14–15 disk-full errors are historical; do not attribute this September 19 search to them.

## Why it regressed

Owner-only generation now explores up to 4,096 candidates per opposing team (60,000 total) and returns all eligible offers. PR #287 removed the former offer-count cap. Thousands of offers also mean thousands of revalidations, annotations and impressions. The owner path withholds results until safety checks and durable impression recording succeed (`server._run_trade_job`); the old progress callback cannot publish provisional owner cards. The storage normalization added in #293 prevents repeated evidence filling the database, but its recursive serialization/hashing itself adds synchronous CPU work.

Profiling found three avoidable multipliers:

1. `FLAGS.attribute` scanned and normalized the registry on every price calculation, and `is_enabled` copied the whole flag map. The reconstructed search made millions of string transformations.
2. Every candidate rebuilt static player availability/age-adjusted lineup assets and repeatedly looked up the same personal tiers.
3. Each impression deep-copied captured request state immediately before JSON serialization; compaction then serialized the same nested structures repeatedly in its count and packing passes.

Ordinary unselected repeats already reuse compatible completed jobs. Forced/selected searches and changed settings intentionally regenerate. No blanket cache bypass was identified or changed.

## Prepared changes

- Resolve known flag attribute names once, while reading current values on every access. Preserve lazy initialization, reload, unknown-key behavior and declared extensions.
- Prepare player facts and memoize personal tier lookups within each owner search. Fresh evaluation/searches rebuild their context.
- Allow impression assembly to serialize a read-only owner projection directly; the default snapshot helper remains detached.
- Within each bounded storage page, cache subtree identities and skip repeated traversal of identical parents. Preserve user/job scope, lossless reconstruction, atomic writes and retention behavior.

Search budgets, eligible offers, ordering, valuation rules, final safety gates, API/client contracts and runtime settings are unchanged.

## Measurement and verification

A private reconstruction of the affected search uses the recorded owner input snapshot and a pinned local pick-price fixture. It reproduces 53,248 evaluations and 2,103 candidates on both revisions. It is **not an exact production replay**: the persisted player projection omits some live pick metadata, and production returned 2,190 candidates. Private inputs remain outside Git. Python is 3.14 locally; production/CI use 3.12.

Profiled component times on the same machine:

| Component | Before | After |
|---|---:|---:|
| Generate | 13.03 s | 6.01 s |
| Owner revalidation | 2.06 s | 1.09 s |
| Assemble diagnostic rows | 3.26 s | 0.95 s |
| Compact diagnostics | 5.20 s | 1.92 s |
| Total measured CPU stages | 23.55 s | 9.97 s |

A final unprofiled sequential comparison (fixed `PYTHONHASHSEED=0`, after the
full suite finished) measured generation **5.291→3.523s**, owner revalidation
**0.929→0.714s**, row assembly **1.343→0.817s**, and compaction
**3.609→1.628s**: **11.172→6.682s combined, about 40% less elapsed time**.
Both decision and expanded-evidence digests matched. These are local component
timings, not a full request benchmark or a production/device promise.

Profiler overhead is included in the preceding table. Database writes, complete final-policy/annotation work, transport and mobile rendering are excluded. Separately, fixed-hash-seed baseline/current runs produced identical SHA-256 digests for all ordered owner decisions and all original expanded feature payloads. The 48.18 MB pre-compaction payload is unchanged; packing representation can differ while decoding identically.

Focused owner generation/route suites: 111 passed before the added projection assertion; the owner-only suite then passed all 28 tests with that assertion. New latency and diagnostic suites: 15 passed. Full backend suite: **6,068 passed / 1 skipped in 353.53 seconds** (Python 3.14). Web structure and session-memory checks passed. Device and production-after-change latency are unexecuted.

## Release / remaining target

This is a measured CPU reduction, not a claim that the app is back to three seconds. Validate on the production-sized host and measure full job plus tap-to-card latency after an authorized release. If the full-deck critical path still exceeds the target, the next change must address first-result delivery and durable evidence work for thousands of offers, while preserving complete offer access and final safety checks. Do not silently lower search budgets, cap offers, bypass safety, or disable evidence as a latency fix. See the [scope and device checklist](scope.md).
