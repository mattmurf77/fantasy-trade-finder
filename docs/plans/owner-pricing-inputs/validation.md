# Pricing execution validation and review

**2026-11-07; `perf/owner-pricing-inputs`; main `0eee4bb9` plus reviewed PR615 envelope.** This is a dormant pricing-domain execution seam. Keep unmerged pending parent release sequencing and full CI. No production mutations, quality changes, reuse certificate or latency improvement are claimed.

## Final automated evidence

**599 passed in 9.44 s** across execution/review/envelope, owner/bilateral/outlook, source-evidence, pick-exemption, fair-package, presentment, trade-breaker and actual route suites. Local macOS/Python 3.14; isolated fixtures, no customer records or provider calls. Exact-head CI on production-compatible Python remains required.

New tests run eleven stable request cases through all three bilateral versions, comparing complete generated card/proof/report data and freshly computed final proofs. Original owner generation/evaluation also match. Controls cover both boards, player availability, input mutation after capture and during actual generation, global configuration/crown/classifier changes, repeated-card checks, malformed config, unknown IDs, effective owner-limit precedence, nested and simultaneous thread scopes, exceptions and ordinary live callers. A final mutated offer is rejected by a fresh evaluator; no proof is reused.

Independent review: **151 passed in 2.49 s** (17 external plus focused execution/envelope cases), with all five runtime source hashes unchanged before/after. The external tests include **800 randomized exact arithmetic comparisons**, including 600 comparisons with pinned prechange formula source across off/heavy/market modes and both crown states. Historical-source tests remain external; ordinary CI includes the independent branch-reaching regressions and 200 randomized explicit-policy comparisons.

Three substantive review findings were corrected and verified:

- V3's incidental-RB companion overpay call initially omitted the policy. It now receives the same captured policy, with a fixture reaching that actual branch.
- Unknown IDs initially escaped refusal in raw-sum/disabled overpay shortcuts. Explicit policies validate both packages before those shortcuts; defaults are unchanged.
- Non-mapping `context.config` initially raised a Python expansion error. It now produces a structured unsupported result, with numeric/string/nonempty/empty-list cases.

## Full actual-worker differential

The external harness retains the existing real owner worker, synthetic 12-team × 20-player inputs and isolated SQLite. Diagnostic bakeoff selector wrappers choose either ordinary generation/final evaluation or the captured execution API. The latter runs **both** actual generation and fresh full final evaluation with the same policy. Original serving/provenance context, matching, roster/quality/presentment and durable publication remain in place.

| Exact request | Cards | Full ordered native/final/public/durable parity | Original first publication | Owned pricing first publication |
|---|---:|---|---:|---:|
| Organic | 6,430 | Exact | 19.694 s | 19.498 s |
| Opponent | 701 | Exact | 1.937 s | 1.962 s |
| Pinned receive | 82 | Exact | 0.428 s | 0.458 s |

All **7,213 ordered cards** retain complete native and final proof hashes and reread persisted valuation hashes. Each persisted JSON row is also compared directly with its final proof. Public comparisons exclude only generated trade/impression IDs and expiry; reports exclude only elapsed time. Policy fingerprints match under the controlled stable-input fixture. Runtime hashes match before/after the run.

Both arms include capture instrumentation. Six single captures took 32.79–65.30 ms; envelopes were 692,451–692,474 bytes, excluding policy object allocation. The retained records include worker CPU and process RSS, but they are not envelope allocation or capacity measurements. The mixed timing differences establish **no speedup**. This is one serialized local pair, not p95/p99, cold-process, deferred-pipeline, network or phone evidence; auxiliary personalization is disabled by the existing fixture. Every first publication remains above 200 ms.

## Retained artifacts and boundaries

The external audit folder `owner-pricing-inputs/` contains the frozen source/test copies, unit log, independent review link, actual-worker harness, all six worker results/logs, before/after runtime manifests and machine-readable parity summary. Only synthetic inputs are used. Reproduce the worker with `PYTHONHASHSEED=0 FTF_OWNER_PROOF_FAST_JSON=0 PROFILE=0 PROFILE_CASES=organic,opponent,receive`, `USE_PRICING_EXECUTION=0` or `1`, and the existing `backend.tests.conftest` plugin.

Tier/age/roster static state, source rebinding, coherent multi-source capture/ABA, account/request/provider currentness and later publication are not authenticated by this API. Original downstream context is retained in the worker experiment. The next extension must route those dependencies explicitly before any duplicated final math can be removed; [contract.md](contract.md) records that stop condition. The architecture research plan is unchanged.
