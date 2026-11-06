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
fully ranked owner batch. Source-list identity, current job state and strict
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
