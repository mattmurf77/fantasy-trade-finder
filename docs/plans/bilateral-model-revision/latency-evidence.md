# Independent full-worker latency smoke

September 22, 2026. Agent A followed the parent-written [latency specification](spec-latency-validation.md). No model, policy, server, configuration source or production state was edited. The incumbent and candidate ran in separate fresh processes against the same frozen original request and September 22 captured configuration. **A material local latency regression was observed; this smoke does not establish production or phone performance.**

## Paired result

| Boundary / quantity | Incumbent `-1` | Candidate `-2` | Change |
|---|---:|---:|---:|
| Worker start → first 30 durable actionable cards | 8.688 s | 18.659 s | +114.8% |
| Worker completion | 11.135 s | 22.905 s | +105.7% |
| Worker CPU | 11.017 s | 22.684 s | +105.9% |
| Native generated cards | 2,843 | 3,836 | +34.9% |
| Final served cards / committed impressions | 2,354 / 2,354 | 3,306 / 3,306 | +40.4% |
| Publication batches | 25 | 34 | First 30, subsequent up to 100 |
| Process peak resident memory | 615,776,256 bytes | 864,010,240 bytes | +40.3% |
| Full public JSON size | 3,218,422 bytes | 4,549,075 bytes | +41.3% |
| Total private valuation JSON bytes | 19,275,002 | 40,226,960 | +108.7% |
| Mean private valuation JSON bytes / card | 8,188 | 12,168 | +48.6% |

All exact correctness checks passed in both processes: complete status; first published batch contains 30 already committed impression IDs; later snapshots preserve every prior prefix; final immutable owner proof matches every card; all persisted proof versions match the selected constructor; final public order and impression-ID order agree; database card indices are contiguous; final served inventory count equals committed impressions and final published cards; and all monitored runtime source hashes remain unchanged. First 30 is a durable delivery prefix, not a constructor/output cap. Both use pool 16 / per-opponent 4,096 / total 60,000 computational limits.

## Observed stage attribution

| Instrumented boundary | Incumbent | Candidate | Added time |
|---|---:|---:|---:|
| Construction | 5.511 s | 10.346 s | 4.835 s |
| Post-construction work | 0.503 s | 0.948 s | 0.445 s |
| Exact owner revalidation | 2.184 s | 5.189 s | 3.005 s |
| Disposition / candidate survivor ordering / proof observation | 0.207 s | 1.785 s | 1.578 s |
| Durable evidence assembly, writes and publication | 2.481 s | 4.303 s | 1.822 s |

The incumbent legacy `presentation` marker is almost empty in these exclusive-owner runs; the new candidate survivor pass executes inside the later disposition boundary. The private adapter also checks every final proof at that checkpoint, so this boundary includes assertion overhead and cannot all be attributed to the policy. Even excluding the entire disposition boundary from each first-durable time leaves 8.481 s versus 16.874 s; that is a robustness bound, not a corrected product timing.

Code inspection connects the measured stages to additional candidate evidence construction/JSON serialization, per-offer final revalidation of the same private diagnostics, bounded term-family comparisons in both native and survivor ordering, and 40% more final cards requiring durable evidence. Raw valuation evidence grows about 49% per card as well as increasing in count. These are supported causes to profile, not a claim that this stage-only smoke identifies exact function-level CPU shares. No candidate-budget reduction, cap, pruning, weight tuning or undocumented optimization was used to improve the result.

## Method and private provenance

Existing `scripts/research_trade_pipeline.py` recompiles the actual worker with timing markers and verifies that removing those markers recovers the original worker AST. A private adapter at `/private/tmp/bilateral-latency-20260922.eGQ8r0/run_latency.py` adds the newly required queued-job generator-version stamp, observes durable cumulative publication, and checks proof/order/identity invariants. It does not replace worker statements or bypass safety gates. The adapter's first-batch durability query and proof assertions are included in measured wall time; import, compilation, initial execution-context copy and private export are excluded by the existing harness.

Command shape:

```sh
PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/ktc-benchmark-venv/bin/python \
  /private/tmp/bilateral-latency-20260922.eGQ8r0/run_latency.py \
  --revision 0 --output NEW_PRIVATE_RUN_DIRECTORY
```

Repeat with `--revision 1` in another fresh process. Retained runs are `incumbent-r1/` and `candidate-r1/` under that private directory. They contain private rosters, normalized evidence and scratch SQLite and must not be committed. The only generated config difference is `owner_bilateral_revision_enabled: 0.0 → 1.0`; flags and every other captured config value are identical. This compares both versions through the current reviewed integration, not different server releases.

- Frozen request SHA-256: `a82fe15c0717db3e73c6d0a5d8853c5f716ff716f8b0fb6967719966aeee5582`.
- Current config capture checked at `2026-09-22T05:31:54.003901+00:00` from the parent's read-only v2 capture.
- Generated incumbent/candidate config hashes: `58f1e00f0b837381cefeeeb01a501846380918853cf033545d60425f83e79c32` / `664a394cc1a5cb33219dc6003c4e9c66736f014cc90652d63124ff3407f955eb`.
- Adapter SHA-256: `3a86f2b7965797083596a8e0471ae04c6ea723b69fbbb0cb41da444a14dcf584`.
- Candidate source SHA-256: `378e5b053ad924d51b613b633d3c6d32cb8a5845ef4dcedb36d3b3bbe9935c69`; presentment: `3cab9c58c21a515c6e2c4d4903328fa8be867d9e68807c2b97918270e198b5fd`; server: `752cbb27bebfd89dd167394bae1b9124e29b0d4fe64b3c24f34f8d236b167e5a`. Every monitored runtime source hash matched across both runs.

## Limits and disposition

One paired smoke, incumbent then candidate, ran on local macOS/arm64 Python 3.14.4 and scratch SQLite with network sockets blocked. Agent C paused its timed evaluator during this window and the parent had finished its full backend suite; unrelated operating-system load is uncontrolled. There is no sample distribution, confidence interval, p95 claim or three-second phone result. The clear regression is sufficient to require a separate performance repair or an explicit release block; additional repetitions alone cannot justify promotion.

The original frozen constructor context is preserved, but provider identity/settings are reconstructed as unknown, raw ranking-action history is unavailable, the isolated history/preferences database is empty, fresh projection/availability/cut evidence is missing, and the full validated owned-pick ledger is unavailable. Pinned local DP fixtures serve startup paths; captured request seed values supply actual construction. No credentials, network, production database, Render worker, PostgreSQL contention, queue/poll, transfer, parsing, rendering, device or warm-cache claim is involved.

Parent was notified immediately of the slowdown and retained source freeze for the locked quality comparison. The subsequent [round 3 specification](spec-round3-latency.md) authorizes only a private parity-preserving prototype until independently reviewed and explicitly integrated by the parent.

## Round 3 — bounded serialization prototype, not integrated

The follow-up is a **negative release result with a useful but insufficient optimization**. No shared runtime source, model rule, weight, budget, eligibility check, publication boundary or production state was changed. The parent chose to retain the tested private prototype rather than add a base-class hook while the larger release remains blocked.

A separate `cProfile` run (`candidate-profile/`) recorded 34.674 s worker wall time, 53.2 million calls including 173,309 JSON loads and 186,410 JSON dumps. Internal JSON decoding consumed 8.558 s; internal encoding consumed 6.645 s. Candidate `_decision` ran 57,450 times and cumulatively consumed 6.016 s. Inspection showed a redundant immutable freeze → parse → immutable freeze there: the incumbent froze its result before the candidate changed only version/construction labels and froze it again. The profile included observer/export work and overlapped Agent C's small synthetic workers; these function counts/times are attribution evidence, not the unprofiled latency result or mutually additive stage totals.

The private `optimize_candidate.py` installs only an in-process candidate override: it retains the incumbent decision body and enriches the version/construction fields immediately before the final owner proof freeze. All eligibility/reason logic and the immutable JSON representation remain intact. The proposed production equivalent, retained as `single-freeze.patch`, adds a narrow `_freeze_decision` hook to the incumbent and overrides it in the candidate; **this patch was checked for applicability but was not applied**. Its implementation would require normal review, incumbent compatibility tests, and binding to the locked quality inventories if ever resumed. There is no process-global mutable proof cache or production monkeypatch recommendation.

### Same-candidate timing and complete parity

After Agent C's timed comparison finished, two fresh processes ran with identical request/config/source hashes and the same observer (`run_latency.py` SHA-256 `7aad8d6a8ce0b8009a6bd1f5cdebb6c55ee95eba103359189801b8098d5cd8ae`). Order was current candidate then prototype, with no claim that unrelated operating-system load was controlled.

| Boundary | Current candidate `candidate-r2/` | Prototype `prototype-r2/` | Reduction |
|---|---:|---:|---:|
| First 30 durable actionable cards | 18.816 s | 16.136 s | 14.2% |
| Full worker | 23.182 s | 20.408 s | 12.0% |
| Worker CPU | 22.713 s | 20.136 s | 11.3% |
| Construction | 10.416 s | 8.321 s | 20.1% |
| Exact owner revalidation | 5.286 s | 4.653 s | 12.0% |
| Disposition / survivor ordering / proof observation | 1.766 s | 1.715 s | 2.9% |
| Durable evidence assembly, writes and publication | 4.427 s | 4.415 s | 0.3% |

Both produced 3,306 served cards and impressions, the same 34 cumulative publication batches, and passed every prior proof, durability, inventory and source-stability invariant. No memory improvement is established: process peak resident memory was 776,962,048 versus 843,087,872 bytes in this pair (+8.5%). The optimized first-durable result is still 85.7% slower than the original incumbent smoke; full worker is still 83.3% slower. Those residual comparisons are separate smoke runs, not a production distribution. Larger evidence/inventory and downstream publication costs remain; the bounded experiment stops here rather than changing model semantics to erase them.

The isolated prototype passed all 72 candidate/incumbent contract tests. `compare_runs.py` then compared every ordered public card and every ordered private impression **persistence-input** row, preserving multiplicity, diagnostic contents and **byte-exact `valuation_json` strings**. The round-three adapter re-read stored identity/order/proof-version fields, not every stored column; complete stored-row parity was strengthened and rerun in round five below. Separate fresh-process direct constructor runs (`native-current-flags/` and `native-prototype-flags/`) used the same frozen context/config/flags and compared all 3,836 native cards, every field including byte-exact owner proof strings, and the complete generation report. The complete native JSON and report files are equal, not only their aggregate counts.

| Exact normalized artifact | Matching SHA-256 |
|---|---|
| Ordered served public cards, 3,306 | `16b26aebc12e9a94c4937d325b95fdd4aae3a71c75acac51f1583e7bed7ff29c` |
| Ordered private impression rows, 3,306 | `b5e77caa7f0d21f15baeaccdf586216a976589d96af6eea9b528a04ea65b102b` |
| All native cards and exact proof strings, 3,836 | `5070cbcd96ca0bd77c1d287a9fe3231771c1bbb1f63e0cea932d051209a063c5` |
| Complete native generation report | `3baf157d373843562b29dd6fc0a9781e22d92da4ab471204d7c208be81fcdc3a` |

Explicit normalization exclusions, and no others:

- Public card: generated `trade_id`, `impression_id`, `expires_at`.
- Private impression row: generated `impression_id`, `candidate_set_id`, `served_at`.
- Private `features_json`: `owner_request.captured_at`, `roster_evaluation.observed_at`, `owner_generation.elapsed_seconds`.
- Native card: generated `trade_id`, `created_at`, `expires_at`.
- Native generation report: `elapsed_seconds`.

All remaining terms, prices, scores, support/components, identities, context, ordering, report counters, unknown-evidence fields and private records must match exactly. Each worker independently verifies that its own generated public impression IDs/order match its committed rows before cross-run IDs are excluded. No provenance, board hash or eligibility field is normalized away.

Agent B independently reviewed the prototype, proposed patch and parity exclusions read-only. No semantic blocker was found in this narrow transformation: the final owner method only stamps `eligible`/`reason` and freezes, and all incumbent eligibility corrections still precede it. This review is not an integration or a latency-gate approval.

Private reproducibility artifacts remain under `/private/tmp/bilateral-latency-20260922.eGQ8r0/`: `run_latency.py`, `optimize_candidate.py`, `compare_runs.py`, `native_parity.py`, `single-freeze.patch`, the two fresh full-worker runs, direct constructor runs, `parity-r2.json`, and `candidate-profile/private-profile.pstats`. Prototype SHA-256: `8518e6aeb7f402f3c2546ee1ea9b269524cfd28f3aa49bbd56ac1a51397a268c`; proposed patch: `5c0d61f852be07dc8556bfdd137ece23332db347f7321097ed0b2ef1dd731e9c`. These scratch records contain private captured inputs and must not be committed. Bounded result: preserve this evidence and proposal, leave the candidate dark, and do not treat the latency gate as passed.

## Round 5 — two additional equivalent experiments, still no latency pass

Agent A followed the parent-written [round-five specification](spec-round5-performance.md) after policy-three cross-review. Only private experiment scripts and this evidence were edited. Both model constructors and the reviewed `bilateral-survivors-3` policy remained unchanged. The two authorized experiments were completed; no third prototype or model tuning was performed.

1. **Detached proof memo plus exact market header**, layered on the prior single-freeze experiment. `optimize_detached.py` leaves `snapshot_json` authoritative. On first read it parses that exact JSON, records immutable process-local `marshal` bytes, and returns the detached parsed value; later reads deserialize a new independent mutable tree. A source-string-bound immutable price header avoids decoding the entire proof again for `matches()`. No binary payload is loaded from a file, network, database or caller. No returned mutable tree enters a cache. Dataclass replacement starts fresh; deepcopy safely copies immutable bytes; even deliberately bypassing frozen assignment to replace the JSON invalidates the cached source association. This private installer is not production monkeypatch code to ship.
2. **Request-local exact package-price memo**, layered on experiment one. `optimize_package.py` keys ordered IDs/values, the 12 current pricing knobs, stud mode and crown flag. Frozen-input parity passes, but independent review found that the ambient crown flag is not atomically pinned in production: it can change between memo-key capture and the underlying pricing reads. This prototype is **not safe to recommend for integration under live flag refresh**. It also showed no advantage over experiment one in the controlled runs. It remains a rejected diagnostic experiment, not an additional shipping change.

### Strengthened evidence and controlled alternating runs

Agent C's independent review tightened the private harness before final runs. Canonical SHA equality is required in addition to Python value equality, preventing numeric-type conflation. Every cumulative public-card prefix is fingerprinted in full, not only by impression ID. Both shared runtime and applicable private prototype file hashes are checked before/after. After worker completion, every actual impression column and the persisted diagnostic snapshot table are read from SQLite; diagnostic references are expanded from those stored snapshots, and every captured persistence-input field must match the corresponding stored value with canonical type-sensitive equality. Raw stored rows/snapshots and expanded rows are retained privately. This post-run verification does not enter worker timing; public-prefix fingerprinting does. Earlier round-five probe directories are retained but do not substitute for these strengthened `strict-*` runs.

The parent completed heavy backend tests and Agent C completed policy replay before the final timing window. Processes ran sequentially in the order incumbent → proof-only prototype → incumbent → proof-only prototype, followed by current candidate, optimized incumbent and package-prototype diagnostic. Unrelated operating-system load remains uncontrolled. All seven runs passed complete status, exact full-card prefix stability, first-batch durable commit, native/final proof binding, contiguous indices, final order/identity, full inventory, every re-read persistence field, and both source-stability guards.

| Variant | First 30 durable cards | Full worker | Peak process resident memory |
|---|---:|---:|---:|
| Incumbent, run 1 | 8.572 s | 11.474 s | 567,328,768 bytes |
| Proof-only candidate, run 1 | 12.826 s | 16.809 s | 792,903,680 bytes |
| Incumbent, run 2 | 8.783 s | 11.672 s | 496,336,896 bytes |
| Proof-only candidate, run 2 | 12.952 s | 17.020 s | 1,032,814,592 bytes |
| Current candidate, no prototype | 18.801 s | 23.982 s | 710,623,232 bytes |
| Incumbent with shared proof optimization | 7.728 s | 10.121 s | 573,898,752 bytes |
| Candidate with package memo, diagnostic only | 14.335 s | 18.922 s | 796,180,480 bytes |

The two-run means are descriptive, not a confidence interval: proof-only candidate first-durable **12.889 s versus 8.677 s incumbent (+48.5%)**, full worker **16.914 s versus 11.573 s (+46.2%)**. Relative to the unchanged candidate run, improvement is 31.4% first-durable and 29.5% completion. If a shared optimization were applied to the incumbent too, its measured first-durable result is faster still; that is not a reason to use a weaker comparison. Peak memory did not improve consistently and rose materially in the proof-only candidate runs. The metric includes process initialization and base-harness private export before the additional post-run persistence reread, not an isolated worker allocation measurement. No production memory-fit claim is established.

Cache bound and lifetime: each warmed proof retains at most one immutable detached-copy payload plus one immutable price header for its exact JSON; there is no process-global proof registry or cross-request memo. The source JSON strings are referenced, not copied. Re-encoding the retained exact artifacts with this same local marshal runtime gives **31,138,646 payload bytes across 3,836 candidate native proofs** (maximum 8,427 bytes/proof), versus **15,419,826 bytes across 2,843 incumbent native proofs** (maximum 5,540). Final candidate/ incumbent proof payloads alone total 26,941,778 / 12,822,820 bytes. These are exact payload-size estimates for this captured inventory, not total allocation or a universal byte cap; tuple/bytes/header/instance overhead, temporary detached trees and additional intermediate decisions also consume memory. Cache lifetime follows the proof object: a service/card cache can keep it after a worker finishes. There is no separate byte cap or eager end-of-request eviction. Thus total memo memory is linear in the bytes of all live warmed proofs, not a constant per-process bound.

The parent's separate [read-only capacity check](capacity-readback.md) reports one Render standard instance, 1 CPU / 2 GB RAM. This is neither measured free memory nor permission to translate local macOS RSS into Render footprint or parallel throughput. The observed peak and unmeasured concurrent retained-proof lifetime remain explicit integration risks; no infrastructure change was made.

Remaining observed stage cost in proof-only candidate run 1: construction 7.661 s, final owner revalidation 3.594 s, post-construction work 0.460 s, disposition/survivor ordering/proof observation 0.712 s, and durable evidence/publication 4.032 s. Matched incumbent run 1: construction 5.470 s, final owner revalidation 2.123 s and durable evidence/publication 2.935 s. Additional offer inventory and evidence still require real work. Nothing was trimmed, suppressed, reordered differently or published before its committed evidence to improve timing.

### Exact output, stored evidence and incumbent-off parity

All 3,836 candidate native offers, their full immutable proof strings and complete generation report match current-versus-proof-only and current-versus-package under the frozen offline inputs. All 3,306 final candidate cards match in exact order. All 2,843 incumbent native offers and 2,354 final incumbent cards also match unoptimized-versus-proof-optimized. No private proof string is normalized. The only exclusions are the previously enumerated generated IDs, observation timestamps and elapsed fields. Content-addressed diagnostic references are expanded from the actual database before comparison; their contents remain covered.

| Matching complete normalized artifact | SHA-256 |
|---|---|
| Candidate native cards / proof strings | `5070cbcd96ca0bd77c1d287a9fe3231771c1bbb1f63e0cea932d051209a063c5` |
| Candidate full native report | `3baf157d373843562b29dd6fc0a9781e22d92da4ab471204d7c208be81fcdc3a` |
| Policy-three candidate public cards | `414f3bfddaddb0dccea5de413995ef0ae225506cb2ee9d29635c40e40c8d9fe8` |
| Candidate complete persisted rows, expanded diagnostics | `ded339f205980abdf230a33f6cf19c5bdd51a02cd3c7f5f004348ae3317f7e1a` |
| Incumbent native cards / proof strings | `d2d450f82d0d6879bf6cf77d82dced44b736fcbb401f2c330bd6f5e2de4712e7` |
| Incumbent full native report | `2c7c4ab629ccc82169f75b8e865a8d17c2e13d450b61ecf0ae2b09f9db07c5d3` |
| Incumbent public cards | `3ff38c9ea4ec30730f5f6785c66d1915cc266716bfe39c2531eaf560d0358cc2` |
| Incumbent complete persisted rows, expanded diagnostics | `1b9ec1e4563ac05fc4ccc1405d17ab357cd2586ce285eab2a7b0f1d44cfa2a6c` |

Private contract tests plus candidate, incumbent, presentation and owner acceptance suites pass **267 tests**. Agent C independently executed a proxy-bound unpatched JSON oracle and **127 checks passed**, covering cold/warm decoding, detached mutation, malformed data, deepcopy/replacement, term ordering and stale prices. C independently re-ran stored-row/public comparisons. The package flag-refresh caveat is not covered up by those frozen-input passes.

The private proof-only proposal is narrowly: the previously tested single-freeze hook, then the exact per-proof detached-copy/header logic in `optimize_detached.py` as ordinary class methods, **not** the installer or package cache. Any production adaptation still needs explicit parent approval, review, fresh integration equality/tests and memory validation. No runtime patch is applied or recommended for release merely because this experiment is faster. The finite round-five result is substantial measured improvement with exact preserved outputs, but **the no-material-regression target remains failed** and the three-second device goal remains unmeasured.

Final artifact provenance under `/private/tmp/bilateral-latency-20260922.eGQ8r0/`: strict worker directories `strict-inc-r1`, `strict-detached-r1`, `strict-inc-r2`, `strict-detached-r2`, `strict-current`, `strict-inc-optimized`, `strict-package`; native directories `strict-native-inc`, `strict-native-inc-optimized`, `strict-native-current`, `strict-native-detached`, `strict-native-package`; full `parity-strict-*.json` records, original private scripts and independent review script. Final worker adapter SHA-256 `3e18e73b580e1382443d6cc20526eb6c7e963cc8e32cdd9f5174d6af46b2d7d4`; proof-only script `916bb6ba8a63cfcdbb001020ab52b40cbce13d0b2f8104501e32a740021b0aed`; package script `c271618e67ecc095d7f1d34a648176ef14ec595eec74c0f4918fa95f57f8e8b2`; comparator `76ce2b7176cee66e47d956ed380495e71a76ebc7b3aedd3d4aed2b217a3f84e7`. Each run also records all relevant exact shared source hashes. These contain private inputs and remain uncommitted scratch.
