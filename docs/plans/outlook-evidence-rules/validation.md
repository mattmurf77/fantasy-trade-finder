# Outlook evidence candidate — local validation and capacity limits

2026-11-06. Default off; activation withheld. Independent output review and
exact-head full CI are separate prerequisites. This records local evidence,
not a production-capacity or 200 ms claim.

## Correctness checks

Initial combined affected tests: 411 passed. After the consumed-evidence page-store
hash contract fix and candidate-only diagnostic caches: **537 passed in 23.42 s**,
including all prior 411 areas, the complete `test_trade_page_store.py` suite and
new full-proof parity/detached-reader tests. Page hashes now positively invalidate
on `trade_input_evidence.py` edits; unrelated Outlook simulator/provider-wrapper
edits remain excluded. Old pipeline pins remain append-only.

The first independent old-version 326-request replay preserved all 7,882 ordered
offers and full proof bytes. Independent new-version review, including the
corrected RB thesis/companion policy, is recorded separately; synthetic model
support is not an independent forecast or willingness label.

## Large isolated organic job

The persistent evaluation artifact bundle contains `large-pipeline/README.md`,
`comparison.json`, `storage-metrics.json`, exact source/harness SHA256 manifests,
logs and synthetic SQLite results. Twelve synthetic teams × 20 players run the real
scheduler/worker, constructor, exact revalidation, presentment and durable SQL
publication. Network is blocked. Standard decoder, macOS/Python 3.14, local SQLite
WAL; no production load, model activation or source-data fetch. Paired settings
match except the v3 selector.

| Configuration / version | Native → published | Pipeline seconds | Peak RSS MB |
|---|---:|---:|---:|
| Existing bulk fixture / v2 | 6,430 →6,430 | 28.34 | 605.4 |
| Existing bulk fixture / initial v3 | 6,420 →6,420 | 34.85 | 738.9 |
| Actual gates enabled / v2 | 6,430 →615 | 26.86 | 634.7 |
| Actual gates enabled / initial v3 | 6,420 →616 | 31.05 | 731.8 |
| Bulk fixture / memoized v3 source | 6,420 →6,420 | 34.54 | 714.1 |

Bulk fixture enforcement flags are off and retained unchanged to stress large
proof/publication volume. The gated pair enables actual roster protection,
market policy, significance 2 and deck-quality filtering for both versions using
provider-complete synthetic roster/position/inactive facts. Both retain619
roster-safe cards; cuts-required rejects 5,811/5,801 and quality removes 4/3 breakup
offers. A first gated harness attempt failed closed at the network blocker due
to missing fixture-roster transport; it is retained, not counted as a successful
measurement. The corrected harness replaces only that synthetic source loader.

Every published card and every stored full valuation is validated against its
immutable exact proof. Native proof hashing and explicit post-worker GC are in
the measured interval; full DB/public readback follows it. Whole-process RSS is
not per-worker memory. These single serial samples are not distributions,
production 1 CPU / 2 GB validation, overlap capacity or device latency.

## Diagnostic sharing and retained cost

An external controlled probe reused request-local per(team,player) window facts
and baseline coverage per team. It computed 1,096 window facts instead of 90,024
and 24 baseline coverages instead of 31,012 across generation and revalidation.
The compiled implementation shares exactly those read-only facts; the full
JSON proof serialization boundary still detaches each occurrence. The actual
6,420-card source run preserves all ordered native/final raw proof fingerprints,
normalized public output, persisted valuation fingerprints and native reports
(except elapsed). Memory falls 24.8 MB/3.4% versus initial v3; no meaningful timing
improvement is claimed. The remaining new-evidence overhead is explicit.

Read-only database aggregates show full valuation bytes 76.03→108.53 MB for bulk
(11,825→16,904 bytes/offer, +43%) and 6.77→9.47 MB after gates
(11,004→15,367 bytes/offer, +40%). These are serialized valuation bytes, not total
DB footprint. Sharing preserves these bytes; it does not reduce durable storage.
Default-off deployment retains v2 behavior/storage. Activation needs storage and
representative service-capacity review in addition to model-quality review.
