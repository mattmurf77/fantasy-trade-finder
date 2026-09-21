# Compute and diagnostic-storage experiments — 2026-09-21

This report concerns isolated research at `4913ad0c68af5e75f864c46cff692ca5f9bf842b` (PR #302). No live application source, settings, infrastructure or production data changed. The private September 19 input and September 20 configuration are frozen reconstructed inputs, not fresh league state. Constructor results exclude the worker's later significance/roster/pick-ledger/authorization checks; they must not be described as actionable offers.

## Reproduction and safety

Use `PYTHONHASHSEED=0 python -m scripts.research_trade_compute --snapshot PRIVATE_CAPTURE --config PRIVATE_CONFIG --output NEW_PRIVATE_DIRECTORY --samples 2 --profile`. Optional `--rows PRIVATE_IMPRESSION_ROWS` runs the diagnostic experiment instead. The output contains aggregate timings, function names/counts and SHA256 digests only. Raw fixtures, impressions and the isolated SQLite database stay outside Git. The CLI refuses a pre-imported database/server, fixes the SQLite destination before importing backend code, verifies the resolved engine URL and blocks socket `connect`, `connect_ex` and `create_connection`.

All runs use the same laptop, Python 3.14.4 arm64, a fixed hash seed and fixed card clock. Production/CI pin Python 3.12.3; no 3.12 interpreter was available. The parent coordinated exclusive CPU windows with the pipeline and delivery agents. Local SQLite and this machine cannot establish production p95, memory fit, database contention or tap-to-tile performance. Process peak RSS is a cumulative high-water mark, not an experiment-specific memory comparison.

## Where repeated work remains

The initial cProfile constructor measured 53,172 evaluated candidates and 2,843 survivors. Its instrumented time was 10.08 seconds; separate unchanged-card final re-evaluation was 2.72 seconds. Inclusive times overlap and must not be added:

| Constructor hot path | Calls | Inclusive seconds |
| --- | ---: | ---: |
| Bilateral `_owner` | 13,710 | 3.185 |
| Full usable-roster `_lineup` | 14,872 | 1.750 |
| Package pricing | 80,570 | 1.950 |
| Immutable JSON `_dump` | 54,169 | 1.403 |
| Proof `as_dict` | 14,274 | 0.835 |

Final re-evaluation rebuilt the search and performed another 5,922 lineup assignments and 9,470 proof decodes. [Bilateral generation/evaluation](../../../../backend/trade_gen_bilateral.py) already caches core evaluations, side evaluations, per-asset plans and tier coordinates. PR #300 also bounds diversity ranking to a 32-card lookahead. The remaining opportunities are distinct from those shipped caches.

[Owner `_lineup`](../../../../backend/trade_gen_owner.py) reconstructs usable assets and runs exact slot matching; [package pricing](../../../../backend/trade_service.py) computes both sides repeatedly with package-dependent discounts, crown credit and first-round exemptions. Replacing either with additive per-asset scores is not supported by the model.

[Impression assembly](../../../../backend/server.py) checks frozen proof/package binding, decodes the proof for valuation, decodes it again for the effective floor, serializes features, and subsequently serializes augmented owner features. `_owner_request_snapshot` already projects per-offer values before copying; it retains references to shared request configuration and manager preferences. [Diagnostic storage](../../../../backend/database.py) compacts each 100-row page inside one transaction. [Compaction](../../../../backend/deck_diagnostics.py) decodes rows and hashes repeated trees; normalized storage already exists, so this experiment does not propose removing evidence or merely inventing deduplication that is already shipped.

## Exact package-price cache

The isolated monkeypatch caches prices per search using the complete **ordered** numeric values for both sides, first-round exemption masks and stud-tax mode. Every miss calls existing pricing. The reversed orientation reuses the same ratio and swaps side values. Configuration and feature flags remain fixed for the entire experiment; production adoption would need the same immutable-context guarantee. No budgets, traversal order, candidate filters, thresholds, output limits or evidence fields change.

Parity compares the full ordered evaluated-candidate proof stream, all emitted card fields and immutable evidence, full generation report and final re-evaluation proofs. Fresh UUIDs alone are excluded; card creation and expiry times are controlled by a fixed clock. Early exploratory harness attempts correctly failed because uncontrolled card creation/expiry times differed between repetitions; those attempts are not the confirmed result and indicated no candidate-proof differences.

**Result: reject this cache as a latency improvement.** The confirmed [compute artifact](compute-summary.json) contains two unprofiled samples per variant, in alternating baseline/cache then cache/baseline order, and one separate baseline profile. Timings include identical candidate-proof hashing overhead:

| Variant | Constructor samples (s) | Constructor median (s) | Final validation median (s) |
| --- | --- | ---: | ---: |
| Current baseline | 6.156, 6.361 | 6.258 | 1.770 |
| Exact package cache | 6.160, 6.461 | 6.310 | 1.803 |

The cache recorded 43,980 hits and 52,523 misses across construction plus validation, yet yielded no meaningful saving. Building full correctness-preserving keys and retaining cached values consumes the avoided pricing work. With only two samples, the approximately 1% median slowdown should not be treated as a precise regression estimate; it is sufficient to withhold an optimization claim. No broader timing sweep is justified for this version.

All four repetitions agree on 53,172 evaluated candidates, 2,843 emitted cards, 2,843 eligible final proofs, all rejection counts and the following full-scope digests:

| Compared content | SHA256 |
| --- | --- |
| Ordered candidate identities and complete proofs | `75b369b1830922758656d6dafcef8e5d9301f25ca1fa7053076e4abdb30f4fc6` |
| Complete card inventory, evidence and order | `642fb3ca2016ba3eb6b6cafbc2858ee59fd05fc0fd47270bfc0f7cf81701e360` |
| Generation report | `662390152209a717ff9697c67cf9fea803702dc48f4d0599cd3f45fcc02dd333` |
| Final re-evaluation proofs | `ef52fe56f6bb523c4f71d1f6f40c9443a83d84bad2681cd110058e8ff5a50550` |

Peak process RSS was 488,718,336 bytes across the entire multi-run command, including profile and comparison structures. This is neither production memory usage nor a clean cache-versus-baseline memory delta.

## Structured diagnostic compaction

The second prototype passes detached structured feature roots to the unchanged production compaction algorithm, retaining shared immutable nested objects until it emits final JSON. It avoids first expanding all repeated diagnostics into feature strings and then decoding them again for deduplication. All non-feature columns and every expanded feature value must match; compacted row and snapshot-write digests must also match exactly.

Private exported rows have lost Python object sharing. Fixture preparation reconstructs identical nested objects by canonical value, outside the timed region. This is deliberately an **upper-bound representation experiment**, not an achieved worker optimization: today's source already shares generation/configuration objects, but the experiment interns more broadly. A production-shaped follow-up must preserve the actual shared objects at the assembly boundary and include preparation cost, transaction duration, memory and failure atomicity in its timing. No write is bypassed and no evidence is marked durable by this script.

The pipeline agent provided 2,354 private impression rows assembled by the current worker. The [storage artifact](compute-storage-summary.json) records two samples per variant, alternated as above, using the existing 100-row page size:

| Variant | JSON freeze median (s) | Compaction median (s) | Total median (s) |
| --- | ---: | ---: | ---: |
| Eager feature JSON then current compactor | 0.371 | 1.754 | 2.126 |
| Structured features through current compactor | effectively zero | 0.784 | 0.784 |

The representation experiment saves 1.342 seconds in this isolated boundary. All compacted rows, snapshot-write order/content and fully expanded evidence agree exactly; no metadata or valuation column changes. This measurement omits SQL, commit, full impression assembly, actual shared-object preparation, client work and publication. It must not be subtracted from production latency. It identifies a promising production-shaped experiment, not a demonstrated worker improvement.

Both variants emit 2,450 snapshot write rows representing 2,358 unique scoped snapshots: the extra 92 rows are repeated shared nodes across the 24 storage pages. Inline feature JSON is 4,039,199 bytes and unique diagnostic payload JSON is 7,013,287 bytes in both variants; these counts omit valuation JSON and other columns. The existing normalized design already removes most repeated stored data. Its remaining CPU cost is largely encoding/hashing before persistence: the separate baseline profile records 61,010 JSON encodes and 107,656 identity calls. Increasing insert pages is not supported by these measurements and would revisit the prior large-statement memory risk.

Compacted-row SHA256 is `e5c3a2038a6894e496fc5ac3fec2a689ab3a816b9d43962d5338db13c76728b8`; snapshot-write SHA256 is `a12d121cff407930d788298c85257cc94e020dcdc1d14480dc5639b9e09cd6f2`. Storage-process peak RSS was 415,219,712 bytes, including raw JSON loading, broad fixture interning, comparison structures and all repeated runs; no production memory claim follows.

## Validation and next decisions

`python -m pytest backend/tests/test_research_trade_compute.py -q` passes **7 tests**. The research tests cover fresh-process refusal, exact reverse orientation, ordered package context, first-round masks, request-local cache isolation, real asymmetric pricing across market/heavy/off modes and exemption/benchmark settings (96 directional comparisons), zero-value rejection, structured-output identity, cross-user scope separation, repeat normalization, complete expansion and no caller mutation. Negative asset values do not enter the search and are outside this experiment's supported domain. A named sabotage dropping the first-round mask from the cache key made the relevant test fail, then the restored implementation passed.

Priorities after confirmed measurements are: preserve actual immutable evidence references through compaction; remove repeated decoding/freezing of unchanged proof values without weakening their immutable/detached contracts; separately test deferring encoding of rejected/unused candidate proofs while retaining every required rejection reason and complete diagnostic reconstructability; measure whether unchanged captured contexts can safely reuse construction evaluations at final validation; then consider exact incremental lineup algorithms. The deferred-proof idea has **not** been measured or parity-tested here. Re-evaluation must remain when ownership, package terms, inputs or required policy context change. Finite candidate budgets mean traversal changes are a separate quality experiment.

Neither a constructor-only cache nor faster storage proves a three-second first actionable tile. Full current search coverage and durable initial 20–30-card publication need the pipeline/delivery experiments, plus valid prepared-inventory reuse or further measured construction savings. Read [pipeline](pipeline.md) and [delivery](delivery.md) for their distinct boundaries.
