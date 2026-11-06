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
