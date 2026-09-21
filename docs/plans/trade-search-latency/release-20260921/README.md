# First-action backend latency release

2026-09-21. Owner authorized implementation and release after reviewing the research. This is the first backend increment, not the entire three-second program. Deployment status and exact commit will be recorded below after release verification.

## What changes

- Identical ordinary searches atomically share one worker. Changed preferences, exact fairness, intent or captured configuration do not reuse incompatible results. Ranking/preference invalidation fences in-flight work, not just completed cache entries. App-open/background preparation respects resolved request settings without replacing active interactive work.
- Structured diagnostic preparation retains actual immutable shared objects instead of repeatedly expanding and decoding equivalent JSON. Stored values, ownership, retention and valuations remain unchanged.
- After global ranking and final checks, the first 30 owner offers are published only after evidence commits. The remaining inventory continues in 100-row batches. Existing apps retain the same cumulative response contract, all offers, stable identities and order. There is no output cap or search-budget reduction.
- A late storage failure retains only earlier committed cards and reports an error. A timed-out, invalidated or superseded worker cannot revive itself. Status responses recheck revocation/model/significance after disposition I/O, closing a copied-snapshot race found in independent review.

No new mobile binary is needed for these compatible backend changes. Compact cursor-based mobile delivery, adaptive polling, durable cross-process prepared inventories and expanded nightly scheduling are not included. Existing final responses can remain large and polling can still add seconds. No arm, pricing, ranking, suitability or runtime setting is changed by this release.

## Measurements and parity

The parent ran three baseline and three updated full-worker reconstructions on the same local Python 3.14/SQLite environment. Every run retained **2,354 offers and 2,354 impressions**.

| Local reconstructed boundary | Baseline median | Updated median |
| --- | ---: | ---: |
| First durable actionable inventory | 12.974s | 8.754s |
| Entire worker | 12.983s | 11.333s |

First durable availability improved approximately 33%; complete-worker time approximately 13%. These are local observations, not a production, p95 or phone latency claim. Provider/history/pick context is partially reconstructed; pinned production runtime is Python 3.12. The three-second goal remains unqualified.

Ordered public cards and full expanded impression rows match after excluding only fresh occurrence IDs and wall-clock observation/expiry timestamps, explicitly listed in [full-worker-benchmark.json](full-worker-benchmark.json). Exact valuations, assets, order, attribution and other feature values are retained in the comparison. Separately, fixed-clock/ID actual-reference logger tests matched all 2,843 constructor rows and snapshot writes exactly while reducing assembly plus compaction from 3.711s to 2.027s; that boundary excludes SQL and publication.

## Evidence

- [Release scope](scope.md)
- [Structured storage, exact parity and negative control](implementation-validation-compute.md)
- [Real worker publication checks and manual TestFlight checklist](implementation-validation-delivery.md)
- [Cache/admission and preparation validation](implementation-validation-cache.md)
- Parent's four additional real-status tests cover ranking, force, model and significance revocation during a copied snapshot's disposition read without changing durable history.
- Parent negative control `NO_POST_READ_REVOCATION` restored only the baseline public-view function inside an isolated test process: all four race cases correctly failed. Restored current code and the publication timing observer passed all five checks. Shared source files were not altered for the negative control.
- Full-suite/hosted CI and deployment receipts are release gates, recorded when completed. No device checks, load benchmark or three-second qualification are implied by unit tests or successful deployment.

## Release and rollback

Pre-release readback at **2026-09-21 13:36 UTC**: Render service `srv-d7g37ftckfvc73a32gvg`, branch main, autodeploy disabled, live commit `4913ad0c68af5e75f864c46cff692ca5f9bf842b`. Preserve all model settings and flags. Merge only after exact-head current CI; explicitly deploy the tested merge commit and read back service/deployment/health and unchanged settings.

Rollback target: redeploy `4913ad0c68af5e75f864c46cff692ca5f9bf842b` without toggling model arms or removing recorded impressions. There is no schema migration to reverse. A restart discards process-local jobs; clients may need to regenerate, while persisted decisions/evidence retain their identities. New deployment availability does not retrospectively prove a phone-level latency improvement.
