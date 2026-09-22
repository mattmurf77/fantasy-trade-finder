# Independent round5 performance review

Agent C reviewed the parent-written [performance specification](spec-round5-performance.md), Agent A's two private prototypes and the repaired measurement harness. No shared runtime or independent grader was changed. **The narrower detached-proof-copy prototype is a valid private parity result, not a release approval. The broader package memo is not suitable for runtime integration as written.**

## Correctness and trust

The narrow prototype retains the exact original `snapshot_json` as authority. Its immutable per-proof binary memo is created only by encoding that proof's own parsed JSON; no binary file, client payload or network data is deserialized. Each `as_dict()` call returns a fresh detached tree. The market header is an immutable tuple bound to the exact JSON string. Dataclass replacement starts a new proof; deep copy preserves immutable memo contents; neither memo appears in dataclass serialization. The proposed real patch still needs normal parent review and tests; a private monkeypatch is not integration.

C ran **127 independent synthetic comparisons** with the reference `matches()` bound to an unmodified JSON-loading `as_dict()` proxy. Cold and warm reads, nested mutation, array order, Unicode/surrogates, duplicate keys, integer/float/bool distinctions, malformed JSON/market data, changed terms/prices, deep copy, dataclass replacement and changed-snapshot defense all matched the old contract. Private oracle: `/private/tmp/bilateral-latency-20260922.eGQ8r0/independent_evidence_review.py`, SHA `2254f520c1ee54a689d33daa1f17cdc10efa865726e8a27bb48602cfdaa4b936`.

The broader request-local pricing memo keys ordered IDs/values and all current transitive pricing knobs, stud mode and crown flag; it does not use a process-global mutable board cache. However, the ambient crown flag is sampled separately for the key and uncached calculation. It is not atomically frozen by the request's configuration override. A mid-call refresh can associate a result with the wrong flag state. The frozen offline experiment does not test away this race. Agent A acknowledged the finding and rejected this prototype for integration; it was also slower than the narrower option. No third prototype or semantic change was requested to conceal the result.

## Repaired evidence checks

Initial review identified four gaps: Python equality can conflate `1`, `1.0` and `True`; prototype files were not source-bound; publication checks compared only IDs; and private exports represented persistence inputs rather than complete stored rows. Agent A repaired the private harness before the strict runs. C re-read the changes and independently reran the artifact comparisons.

Strict runs now require canonical type-sensitive hashes and equality; fingerprint every applicable prototype source before/after; check complete cumulative public-card content prefixes; reread every stored impression column and diagnostic snapshot; and verify all captured input fields against stored values. Expanded diagnostic structures are compared logically after only the declared volatile exclusions. Private `valuation_json` remains a byte-exact string. Generated IDs and enumerated timestamps/elapsed values alone are excluded; no terms, ordering, scores, support, board identity or eligibility evidence is discarded.

C independently verified current-policy3 versus both detached runs and the frozen package diagnostic: all **3,306 ordered public cards and complete persisted rows** match. Incumbent versus the shared proof-copy optimization likewise matches all **2,354** public/persisted rows. Native exports are byte-identical after their declared generated-ID/time exclusions: all **3,836 candidate cards** and complete generation report, and all **2,843 incumbent cards** and report. Every owner proof string remains exact. All seven strict workers share one runtime source manifest, including policy3 SHA `fe79474c3864fb78372396a134fc7c9a5f9cd5e5fc34e98c803c569d36aed887`.

| Independently verified normalized artifact | Matching SHA-256 |
|---|---|
| Candidate ordered public cards | `414f3bfddaddb0dccea5de413995ef0ae225506cb2ee9d29635c40e40c8d9fe8` |
| Candidate complete persisted rows | `ded339f205980abdf230a33f6cf19c5bdd51a02cd3c7f5f004348ae3317f7e1a` |
| Incumbent ordered public cards | `3ff38c9ea4ec30730f5f6785c66d1915cc266716bfe39c2531eaf560d0358cc2` |
| Incumbent complete persisted rows | `1b9ec1e4563ac05fc4ccc1405d17ab357cd2586ce285eab2a7b0f1d44cfa2a6c` |
| Candidate native cards and exact proofs | `5070cbcd96ca0bd77c1d287a9fe3231771c1bbb1f63e0cea932d051209a063c5` |
| Candidate complete generation report | `3baf157d373843562b29dd6fc0a9781e22d92da4ab471204d7c208be81fcdc3a` |
| Incumbent native cards and exact proofs | `d2d450f82d0d6879bf6cf77d82dced44b736fcbb401f2c330bd6f5e2de4712e7` |
| Incumbent complete generation report | `2c7c4ab629ccc82169f75b8e865a8d17c2e13d450b61ecf0ae2b09f9db07c5d3` |

## Performance remains a release blocker

The strict alternating pairs measured incumbent first-durable **8.572/8.783s** versus detached candidate **12.826/12.952s**, a residual **49.6%/47.5%** increase. Completion is11.474/11.672s versus16.809/17.020s. The unoptimized policy3 candidate measured18.801/23.982s; the narrow optimization therefore helps substantially but does not close the matched incumbent gap. The package memo measured14.335/18.922s, worse than the narrow option.

Peak process RSS is also a trade-off, not an improvement claim: paired incumbents used567/496MB versus detached793/1,033MB (decimal units). These two local runs are not a distribution; import/export and observer costs affect process peaks, and uncontrolled OS effects remain. The tests use local Python/SQLite, reconstructed context, socket-blocked execution and checked instrumentation; no production p95, complete preparation, PostgreSQL, device or three-second first-action result is established.

Strict private runs and complete exports remain under `/private/tmp/bilateral-latency-20260922.eGQ8r0/strict-*`. Harness SHA `3e18e73b580e1382443d6cc20526eb6c7e963cc8e32cdd9f5174d6af46b2d7d4`; detached prototype SHA `916bb6ba8a63cfcdbb001020ab52b40cbce13d0b2f8104501e32a740021b0aed`; its earlier single-freeze dependency SHA `8518e6aeb7f402f3c2546ee1ea9b269524cfd28f3aa49bbd56ac1a51397a268c`. The rejected package prototype SHA is `c271618e67ecc095d7f1d34a648176ef14ec595eec74c0f4918fa95f57f8e8b2`.

Disposition: retain the narrow proposal for a separately approved integration or experiment; reject the broader memo as written. No quality conclusion follows from equivalent bytes, and the existing independent evaluation's known failures, missing evidence and release limits remain unchanged.
