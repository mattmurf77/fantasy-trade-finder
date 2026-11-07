# Offline envelope validation and review packet

**2026-11-07; base e0aa9e36; branch `perf/owner-input-envelope`.** Keep unmerged pending independent review and parent release sequencing. A new non-test backend module changes Calibration's whole-backend source hash on deployment even though no runtime imports it. No serving optimization or 200 ms claim is made.

## Automated checks

Affected suite: **325 passed in 7.92 s**, local macOS/Python 3.14, isolated test data and existing network-blocked fixtures:

```sh
python3 -m pytest backend/tests/test_owner_evaluation_inputs.py backend/tests/test_trade_gen_owner.py backend/tests/test_bilateral_candidate.py backend/tests/test_bilateral_generation_freeze.py backend/tests/test_outlook_evidence_candidate.py backend/tests/test_trade_input_evidence.py -q
```

Coverage includes full record and detached-read preservation, numeric type/bit/Unicode handling, ordered pins/maps, canonical set membership, unrelated-player and both-side board/source/roster mutations, effective configuration/flag/table changes, explicit unsupported inputs, source-sidecar non-rebinding, original owner generation, all three bilateral versions and actual revision adapter/final validation. Eleven valid existing request cases run across all three bilateral versions, comparing complete generated values/reports and full final proofs. Invalid nonfinite requests remain explicitly unsupported by the observation helper; their existing evaluator rejection still runs unchanged.

Independent review reproduced two defects: a malformed exact provenance wrapper could execute an arbitrary row callback, and a very large native integer could escape as a JSON ValueError. Strict internal provenance schema checks now run before helpers; encoding limits return a structured refusal, including set ordering. Durable regressions cover both. The final independent focused run passed **94 checks** and independently repeated the 82-card worker comparison. Initial failing evidence and pre-fix worker results remain labeled in the external packet.

The source has no importer outside its new tests. No normal module, route, schema, flag, budget, quality threshold or selector is changed. Full CI remains pending; independent review found and verified fixes for two offline contract defects; local Python differs from production 3.12.

## Large controlled worker differential

A retained external harness uses the existing actual owner-worker fixture, a deterministic synthetic 12-team × 20-player league and isolated SQLite. It compares original generation kwargs with detached materialized kwargs; original serving/provenance context remains in place. Recorded ambient values are **not injected**. Each arm still runs native generation, full final owner evaluation, presentment and durable publication.

| Request | Ordered cards | Original first publication | Materialized first publication | Native/final proofs, public output, durable valuation parity |
|---|---:|---:|---:|---|
| Organic | 6,430 | 20.756 s | 19.946 s | Exact |
| Opponent | 701 | 2.029 s | 2.014 s | Exact |
| Pinned receive | 82 | 0.457 s | 0.576 s | Exact |

All 7,213 ordered cards have equal native/final full-proof hashes and equal reread persisted valuation hashes. Public comparisons exclude only generated trade/impression IDs and expiry; generator reports exclude only elapsed time. The worker also asserts each persisted JSON value equals the corresponding final proof's serialized data. Capture fingerprints match between arms under the controlled no-writer fixture. That equality is not evidence against an ABA race.

Across six captures, the private representation is 692,337–692,360 bytes, capture plus declared ambient observation takes 21.95–24.50 ms, and kwargs materialization takes 9.09–11.22 ms. These are single local samples, not a distribution, capacity limit, CPU attribution or optimization result. Both arms include observation/materialization measurement overhead. Peak process RSS and CPU are retained in raw aggregate results; later cases share process high-water memory and cannot isolate envelope allocation.

The organic original run attributes about 11.63 s to generation and 7.02 s to final owner validation before first publication. These stage observations identify substantial remaining work, not an immediately safe omission. Even eliminating repeated final evaluation would leave seconds of full generation. Exact request/input changes, cold processes, provider/DB/network latency and device visibility remain unresolved by this helper.

## Artifacts and reproduction

Synthetic-only logs, source harness, full ordered comparison summary and the frozen helper/test sources are retained in the existing external audit directory under `owner-input-envelope/`. No customer record, provider roster, private board or secret was used. Run the retained harness from this checkout with `PYTHONHASHSEED=0`, `FTF_OWNER_PROOF_FAST_JSON=0`, `PROFILE=0`, `PROFILE_CASES=organic,opponent,receive` and `MATERIALIZE_OWNER_INPUTS=0` or `1`; load the existing `backend.tests.conftest` plugin. The harness is kept external because it is a diagnostic worker experiment, not normal application code.

The comparison is a stable-input oracle only. It does not cover production deferred evidence/publishing, all request combinations, concurrent writes, ambient replacement, copied provenance authority, multi-process hash/layout equivalence, authorization, account deletion/recreation, worker leases or network/device behavior. Auxiliary personalization layers are disabled by the existing fixture. Those limitations must remain visible in any follow-on certificate design.

## Review focus and next unit

Review exact-type copying and exception behavior; verify schema omissions fail explicitly; check flag/config precedence against actual consumers; verify materialized kwargs cannot inherit object-bound evidence; and preserve the distinction between captured observations and consumed inputs. Do not add a reuse-authorizing API to this module without a separately reviewed coherence/currentness design. Release sequencing and unexposed Calibration regeneration remain parent-owned.
