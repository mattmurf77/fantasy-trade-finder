# Feature Scope — current-input trade delivery

**Date:** 2026-11-05. **Entry:** authorized Find a Trade delivery investigation.
**Builder:** backend/privacy subagent. **Status:** local implementation; parent
owns model review, GitHub CI, release and any production change.

## 1. Analytics scope

Existing `find_trades_tapped`, first-card shown/failed, `trades_generated`,
`api_request` and publication timing cover the problem. No new event, private
payload collection or provider delivery. The switched-league report was a cold
320-offer/33-second generation; parent live aggregate found two stored scopes,
with that league's input captured only four seconds before the tap. No ready
prior page is established for that immediate switch. No production query or
mutation was performed by this implementation.

## 2. Schema, flags and API scope

No schema, env, model knob, generator, quality threshold or output-limit changes.
No preparation activation. Add an opt-in header and acknowledgement/error fields
on the existing generate/status routes, leaving legacy response fields intact.
All ordinary auth, verification, paywall/prewarm decisions remain authoritative.

Strict real-league recommendations require a current stored roster/value read,
matching request/policy/model identity and live input epochs. Stale kickoff pages
are bypassed; stale continuations fail before evidence/preview consumption.
Stored-page freshness cannot use legacy linked/no-rebuild relabelling as proof.
The controlled demo retains its existing synthetic, no-provider-roster flow.
Valid zero-result inventories remain successful empty results. Disabling I-1
fingerprint reads leaves real-league strict delivery unavailable, preserving the
operator's kill switch and legacy behavior.

`ranked_prefix_ready` is limited to live evidence actually committed by the
fully ranked owner batch or a prepared-adoption batch whose evidence and
checkpoint have committed and whose inputs have been revalidated. Source-list identity, current job state and strict
validation bind it; another publisher, revocation or completion ends authority.
Deferred/preparation captures never qualify. This does not guarantee instant
cold generation: full candidate generation/ranking still precedes publication.

Publication AST changes require append-only pipeline **9**, digest
`28d212cdc5c6cb05`; version 8 is preserved. The deployment invalidates older
pipeline pages once. This is a model-review/release consideration, not a flag flip.

## 3. Evidence scope

Real Flask routes cover current and stale stored/job/P2 continuations, linked
ESPN/MFL with positive and missing inputs, demo with modes 0/1/2, organic and
give/receive/opponent/intent Bilateral2 searches, genuine empty results,
store/paging-off fallback, missing authorization, participant edits during
projection, and actual free-preview consumption controls. A refused page must
record no evidence delivery and spend no preview. A legacy positive control
still serves/spends under its unchanged contract.

Actual owner worker/batch/SQL tests prove first-prefix IDs commit before their
running response, match the final ranked first 30, and preserve all 64 offers.
Changed-publication identity and deferred mode suppress the prefix marker.
Ready durable inventory is adopted through the real strict HTTP kickoff without
regeneration; all pages retain original order and impression identities, while
known empty inventory completes without exposure. Existing P1/P2, read-lock,
prepared-runtime, preview/auth and pipeline suites are the regression gate.

No local timing result establishes a production first-card SLA. Mobile/web
protocol and runtime QA are owned by their integration workers; no device,
capture or live-provider action was performed by this backend change.

## 4. Docs scope

API reference, shared wire invariants, architecture and LLD are updated. Test
ledger records exact executions. HLD/data dictionary/config reference/glossary
need no change: the existing services/stores/controls remain. Pipeline pin change
is explicit and requires parent model review; no prior pin was rewritten.

## 5. Ship gates

Parent integrates all client acknowledgements, invalidates old held device
proofs, reviews the pipeline change, and obtains full exact-head GitHub CI.
No express-lane waiver, no activation or deployment in this scope. Ready durable
supply is a demonstrated path when available; broad preparation rollout and cold
generation cost remain separate work.

## Browser input changes — 2026-11-06

Changing fairness, player selections or writing league/ranking inputs now
withdraws visible old cards immediately, cancels their pending page handle and
drops the passive request reference. Late replies cannot restore that deck.
The exact-scope replacement still uses strict server validation; clearing the
screen is not a first-card success or a claim of 200 ms. Runtime regressions
cover both visible-card withdrawal and a late response after withdrawal.


## Prepared-prefix delivery follow-up — 2026-11-06

The prepared runtime transfers the unused deferred-generator evidence sink to
its own durable ownership atomically with first publication, under the job lock.
Legacy and paged prepared adoption retain the complete sealed order and private
valuation evidence. The publication marker references the current immutable
list; completion, error or revocation clears it. Preview slicing retains that
server-owned reference without extending the preview window or granting Pro.
Delivered/withdrawn evidence uses the original preparation's private job identity;
public polling and preview consumption keep the interactive job identity.

A failed first evidence write may fall back to ordinary generation. Once any
adoption evidence commits, a failed checkpoint or later write terminates that
adoption instead of appending regenerated offers. Changed inputs revoke visible
cards; existing historical evidence is retained. Local tests exercise real SQL
commits and strict HTTP responses between batches, actual delivered_at stamps,
preview bounds/passive refusal, and failure/revocation boundaries. These prove
an earlier usable prefix, not a physical-device or universal 200ms result.
Preparation activation and deployment remain the parent's separate release gate.


### Local validation — 2026-11-06

- **496 passed in 99.88s**: 15 selected backend files covering the new prepared
  prefix boundaries, both prepared runtimes, runtime/chunk/graph/store review,
  strict current delivery, P1/P2, paywall preview, fingerprint-lock safety,
  pipeline digest, and fair packages. This is targeted local regression evidence,
  not a claim that the entire backend suite or GitHub CI has passed.
- The new `test_prepared_prefix_delivery.py` contributes **14 cases**. It runs
  the real worker after kickoff's HTTP context exits and polls strict HTTP at
  evidence batch boundaries. It checks real committed delivery timestamps,
  source identity, deferred-sink transfer, first-preview consumption/passive
  refusal, commit/checkpoint/suffix failures, and input changes before/after
  visibility. Existing runtime tests retain full sealed-order/valuation parity.
- A separate instrumented synthetic 64-card v2 run observed first usable HTTP
  prefixes at **1123.1ms** (ordinary) and **1106.6ms** (first preview), versus
  completion at **1471.9ms** and **1453.8ms**. These include test observation
  overhead; they are not phone tap-to-frame timings or a production benchmark.
  Both exceed 200ms. They demonstrate delivery before the remaining evidence
  writes; arbitrary cold generation and unseen filter scopes remain unresolved.
- Initial combined attempts exposed test-context/recorder teardown pollution.
  The final tests run background work outside kickoff's request context and
  restore only their own dynamic-harness recorder. The shared fair-package
  fixture remains unchanged; the identical final regression selection passes.
  No product guard, evaluation rule, pipeline pin, or preparation flag was
  weakened to pass the tests.

## Browser save/pagination race follow-up — 2026-11-06

A tap during overlapping input writes waits for all writes to settle without
resetting its R1 clock. Context uses persisted-input epochs and exact payload;
asynchronously applied preference labels cannot replace that manual search.
Pagination ownership is per search, so an old continuation cannot disable a
new empty-page search or clear its busy state. Runtime tests cover these races
and fail if pending promises leave the suite unfinished. Independent review
caught six deliberately broken variants. This improves correctness and removes
accidental waits; it does not certify native or network latency.


## Immutable scalar proof projections — 2026-11-06

The cold-worker profile found repeated parsing of the same frozen private JSON
for model identity, selection coverage and fairness floor. These reads now use
lazy immutable scalar projections on `OwnerDecisionContext`; `as_dict()` still
returns a new detached full snapshot. Replacing a decision derives fresh
projections, deepcopy remains safe, and malformed list/dict floors still return
detached values. Public serialization retains required model-key behavior while
reading those two keys from one detached snapshot. All final owner evaluation,
package matching, current-input validation, ranking and publication gates remain.
No candidate limit, solver, cache freshness or production flag changed.

The affected server AST requires append-only pipeline **10**,
`cdabd9935a58d51d`; all earlier pins, including 9, are preserved.

Local timing used the actual Bilateral2 worker and existing worker fixtures with
12 synthetic teams of 20 players, deterministic boards, seed 20261106 and
`PYTHONHASHSEED=0`. Baseline was `f51de7ed`; candidate changes only scalar reads.
The harness uses live local SQLite evidence and disables auxiliary personalizing
layers. It does not measure production's deferred worker, network or phone UI.
The final HTTP page is the authenticated legacy path; the direct worker fixture
does not carry the strict request stamps. First publication is recorded at the
worker's first durable card callback, after its first evidence commit.

| Cold scope | Cards, unchanged | First durable publication before / after | Worker completion before / after |
| --- | ---: | ---: | ---: |
| Organic | 6,430 | 20.260 / 19.099 s | 27.340 / 25.171 s |
| Opponent selected | 701 | 2.171 / 1.891 s | 3.161 / 2.763 s |
| Receive player selected | 82 | 414 / 387 ms | 492 / 457 ms |

These are single unprofiled samples, not a statistical speedup claim or a
200 ms result. Generation and solver work remain dominant. Organic public-card
serialization measured 1.465 / 1.070 s across all 6,430 cards; SQL evidence time
was 2.968 / 2.880 s. Those spans overlap the full worker and must not be summed.

Exact ordered full frozen-decision JSON hashes match before/after both immediately
after generation and after final revalidation in all three scopes. Final hashes:

- Organic: `d1518f9cf831d0f0d1e9ee7f00cf765b019df225b29be41064031767bcc4d8c4`
- Opponent: `4e679a2d211064e4889c53bdd4240315e8513e76fe66d0554ba3ef3ef5dbfe0f`
- Receive: `863df2372fef1dd169d39e4ac4ffb5f9c724a8959725392980d5885e6bd23feb`

Each proof's UTF-8 bytes are length-prefixed before hashing in card order; no
private fields are omitted. Ordered public-semantic hashes and card counts also
match. Reproducible local script, raw results and comparison are in
`/private/tmp/fleeced-cold-profile/test_profile_cold.py`,
`{organic,opponent,receive}-{before,after}-projection-wall.json` and
`scalar-comparison.json`. Invocation:

```sh
PYTHONHASHSEED=0 PROFILE=0 PROFILE_CASES=organic,opponent,receive RUN_TAG=after-projection- python3 -m pytest -p backend.tests.conftest /private/tmp/fleeced-cold-profile/test_profile_cold.py -q -s
```


A separate cProfile pass counted 135,612 -> 116,322 full decision `as_dict()`
reads for the organic fixture: exactly 19,290 fewer decodes (14.2%). Profiled
full ordered frozen/public hashes also matched. Profiled durations include
substantial instrumentation overhead and are not used as latency measurements.
Affected regression gate: **453 passed in 40.18 s** across owner/pipeline pin,
revision/owner-only/presentment/bilateral routes, contracts/overhaul, prepared
prefix and current-only suites. Independent reviewer checked scalar immutability,
malformed-floor detached fallback, replacement/deepcopy, required public model
keys, unchanged final reevaluation and exact output parity.


## Local proof decoder candidate — 2026-11-06

The isolated `perf/exact-request-reuse` candidate changes only decoding of
immutable, locally standard-encoded owner proofs. `orjson==3.11.7` is optional
at import and pinned for requirements installs. Standard `_dump` bytes, full
final evaluations, candidate limits, solver, order and all input/serve guards
remain unchanged. This is a backend candidate, not a production activation or
a universal 200 ms result.

A private immutable marker binds to the exact encoded string. New internal
`_with_data` calls replace the two existing local re-encoding sites; ordinary
`dataclasses.replace` never inherits the marker or scalar caches. Manual/stored
JSON keeps standard decoding. Every 19+ digit integer token, including a root
primitive, falls back to the standard decoder to avoid silent int-to-float
conversion. Standard encoding rejects nonfinite values before marking. Decoder
rejection (including escaped lone surrogates) falls back to the original decoder
and its result/exception. No decoded mutable tree is cached or shared.

A broad solver-memo prototype was rejected: 16,384 retained entries consumed
11.09 MB including shared inputs and saved only about 0.7 seconds to first
publication in the organic fixture. No solver memo is part of this change.
A direct unguarded decoder replacement was also rejected: adversarial tests
found nine behavior differences (out-of-range integers, nonfinite/overflow
numbers and lone surrogates). Marking only the initial proof factory missed the
Bilateral2 re-encoding site, so that intermediate prototype is not the final
candidate. Splitting root integer fullmatch from nested integer search preserves
the same domain guard and avoids scanning every character for a root anchor.

The final integrated candidate ran the actual existing worker in the isolated
checkout, with no decoder monkeypatch. Its control disabled the marker helper
and used the standard decoder. Both use the same deterministic 12x20-player
synthetic fixture and no network/customer data. The live-evidence, local-SQLite,
legacy-status and disabled auxiliary-personalization limitations described above
still apply. The matched wall samples were:

| Scope | First durable publication, standard / candidate | Full worker, standard / candidate | Worker process CPU, standard / candidate |
| --- | ---: | ---: | ---: |
| Organic, 6,430 cards | 20.072 / 16.714 s | 26.655 / 21.488 s | 26.127 / 21.235 s |
| Opponent, 701 cards | 1.922 / 1.635 s | 2.759 / 2.353 s | 2.756 / 2.346 s |
| Receive-pinned, 82 cards | 381 / 351 ms | 451 / 409 ms | 450 / 408 ms |

All three ordered full frozen-JSON hashes match at generation and after final
revalidation, along with ordered public semantic hashes and complete card
counts. Final frozen hashes are unchanged from the preceding scalar-projection
section. These are local samples, not p95/device guarantees. The guarded
prototype independently measured organic first 16.616 s versus its 20.210 s
standard control; the final integrated candidate confirms the direction.

Memory is not claimed flat. The organic final proof markers total 308,640 bytes
(48 bytes each); their strings are the exact existing snapshot objects and the
summed proof dictionary sizes remain 2,983,520 bytes in both variants. Process
peak RSS was 765.7 MB standard versus 868.0 MB final candidate (an earlier
candidate pass was 782.5 MB). This process-wide high-water figure includes the
whole fixture, libraries, allocator and temporary evaluation objects. It is not
an isolated retained-cache size; deployment memory headroom remains a review
consideration. The change introduces no request/global decision-result cache.

Raw reproducible fixture and evidence:
`/private/tmp/fleeced-cold-next-profile/test_profile_decoder.py`,
`{organic,opponent,receive}-candidate-{control,final}-wall.json`, and
`final-decoder-comparison.json`. Run with the pinned package on `PYTHONPATH`,
`FTF_OWNER_PROOF_FAST_JSON=1 PYTHONHASHSEED=0 PROFILE=0 PROFILE_CASES=organic,opponent,receive DECODER=native`.
The dependency note records the exact compatibility/upgrade contract. A Python
3.12 manylinux x86_64 wheel was downloaded successfully; Python 3.12 runtime and
full repository CI still belong to the parent release gate.


A second clean, sequential organic memory pair confirms a cost, not flat memory:
standard/candidate peak RSS **807.0 / 875.2 MB**; before-worker RSS
147.8 / 146.9 MB; end-worker RSS 454.4 / 497.7 MB. After explicit GC with final
cards still retained, RSS was 630.5 / 662.3 MB (touching/scanning pages raised
resident memory in both processes; this is not a retained-object census).
Candidate current RSS peaked during final reevaluation, while its end-worker
memory was substantially lower. Every measured sample is retained above and in
`organic-memory-{standard,candidate}-wall.json`; none is selected as a formal
maximum. This repeat preserved full hashes and measured first publication
19.716 / 16.594 s, completion 25.798 / 21.887 s, process CPU 25.662 / 21.562 s.
No concurrent CPU tests ran during the pair.

Parent's read-only Render readback reports one Standard instance, limit
2,147,483,600 bytes, with the latest deployment's observed 60-second memory
peak 175,755,260 bytes. [Render compute plans](https://render.com/docs/compute-plans)
identify legacy Standard as 1 CPU / 2 GB. Those observed production samples do
not contain a demonstrated heavy-search load and do not bound concurrent cold
requests or OOM spikes. The reproducible synthetic peak increase (68.2 MB in the
repeat, 102.3 MB in the first final pair) is an explicit release-review tradeoff.
No capacity, concurrency, provider or production-flag mutation is included.

Validation: **494 affected tests passed in 40.27 s** with the actual pinned
package. Independent reviewer ran the decoder module with it (41 passed) and
without it (40 passed, one fast-path check skipped), 199,910 random finite
floating-point bit comparisons and 112 root/nested adversarial cases. Tests
cover missing import in a fresh process, marker identity/forgery rejection,
root/nested big integers, nonfinite refusal, escaped Unicode/surrogates,
detached mutation, deepcopy, ordinary replacement cache clearing, canonical
re-encoding and conflicting snapshot keywords. All three integrated generator
reports are also identical after removing elapsed time (44,446 / 4,077 / 552
candidates evaluated). No output count, solver budget or quality check changed.


### Activation remains off pending overlap validation

The implementation now requires exact process-start
`FTF_OWNER_PROOF_FAST_JSON=1`; default/unset/other values neither import nor use
the fast decoder. Installing the dependency or merging the source does not
activate the measured optimization. Process environment changes after import do
not toggle it; rollback requires a restart with the variable removed or `0`.
No production environment was changed.

The complete backend CI suite explicitly opts in; fresh-process tests prove the
default-off and actual opt-in paths, missing-package fallback and startup-only
behavior. The [runbook](../../runbook.md#owner-proof-decoder-activation) gates
production activation on representative scheduling/overlap memory and load
validation. Pinned/opponent/forced requests and superseded background work can
overlap despite deduplication, so single-worker parity and timing evidence is
insufficient. The independent reviewer will use isolated synthetic real-worker
scheduling, preserving all outputs/checks and reporting peak/end RSS, active
workers, CPU, first durable results and failures against actual instance limits.
No admission or model-policy rewrite is included in the decoder change.
