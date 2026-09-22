# Bilateral revision — release withheld, 2026-09-22

## Decision

**Current checkpoint: do not activate or deploy this revision.** The owner authorized either release
after evaluation or another implementation round. Independent review triggered
round2, which repaired preference-driven price escalation and presentation
reordering. Measured full-worker performance then triggered a separately scoped
round3 performance experiment. The owner subsequently requested continued
iteration until release fitness is established. Round4 repairs focal-direction
erosion in presentation; round5 investigates additional equivalent performance
changes. This is an ongoing decision record, not a declaration that work stopped.
Passing code tests is not a promotion decision.

Candidate `owner-v2-bilateral-2` and presentation policy
`bilateral-survivors-3` remain local and default-off. The locked results below
refer to its predecessor policy2; policy3 has a separate regression replay.
There has been no production
write, arm change, push, deployment or TestFlight upload in this initiative.
The production configuration was read, not modified; the capture time and source
are recorded in [evaluation evidence](evaluation-evidence.md).

## What the comparison established

The locked comparison completed **12 captured requests plus 57 constructed
scenarios for each model**, with zero subprocess errors. Captured requests are
not independent managers or leagues: shared participants connect the full source
corpus into only two components. The small holdout is not a generalization claim.

- Stronger preference alone no longer raises the first exact-target asking price
  for three matched exact-return packages in **one** frozen synthetic preference
  intervention: **0/3 violations**, versus 3/3 for the incumbent. These are not
  three independent contexts. Cheapest-retained-price violations fall 2/3 to 0/3.
- The average dominant outgoing-player repeat count in the first 30 cards falls
  **18→14.5** across the 12 captured requests; eight improve and four tie. This is
  a presentation diagnostic, not an acceptance rate.
- No new observed ownership, pin, expiry, own-next-pick or occurrence-duplication
  violations, integrity quarantines or hidden output cap. Both variants exhaust
  the same existing search budget in five contexts; preserving that budget does
  not mean every theoretically possible package was searched.
- Other results are mixed. Known initiating-manager focal-buy alignment declines
  **80.99%→76.65%**, and focal-sell alignment **81.76%→80.68%** in the measured
  final first 30 subsets. These are equal-request means across 10 development
  requests, not population acceptance estimates or fixed-identical-card effects.
  Of 300 displayed occurrences, known give-side focal evidence covers 274→258 and
  receive-side 256→266. The two held-out requests have no known A focal evidence
  and do not contribute to these means. Changing coverage/composition is part of
  the result; stage attribution belongs in the independent report. More offers
  and less repetition do not establish stronger owner alignment.
- Average additive market return changes **−3.262%→−3.643%**. Additive return is
  neither package-adjusted fairness nor likelihood of mutual acceptance.

All six independent bilateral dimensions still have material missing evidence.
Counterparty personal-rank coverage is especially sparse, and compatible starter
projections/cut decisions are absent. Unknown cells remain Unknown; no composite
score or claimed acceptance improvement is substituted for them.
Two exact-term meaningfulness failures (the counterparty lacks an individually
meaningful asset) are shared by both models in one development request; they are
not newly introduced by this revision and are not silently counted as passing.

## Performance blocks release independently

The matched isolated actual-worker smoke measured first durable 30 cards at
**8.69s incumbent versus 18.66s candidate**; completion 11.13s versus 22.90s.
Candidate inventory grew 40%, and both repeated serialization and expanded private
evidence contributed cost. These are local Python 3.14/SQLite measurements, not
production p95 or device tap-to-action latency. They nevertheless demonstrate a
material regression against the owner's three-second first-action objective.

A private single-freeze prototype preserves exact offers and evidence but only
reduces a fresh candidate pair from 18.82s to 16.14s first durable, still about
86% slower than the incumbent smoke. It is not integrated. Further measured
equivalent optimization is scoped separately in [round5](spec-round5-performance.md).

See [latency evidence](latency-evidence.md) for stage attribution and any subsequent
behavior-equivalent performance experiment. An optimization must retain every
eligible occurrence, exact terms/order, bilateral proof, durable impression and
search budget; reducing the deck or dropping safety evidence is not a repair.

### Subsequent completed checkpoints

Full backend validation now passes **6,690 tests with one optional-data skip**.
The policy3 retained replay passes all69 exact inventory bridges, with no errors;
this is regression evidence, not another blind holdout. Development focal sell/
buy means recover to82.64%/78.23%, compared with82.56%/78.25% immediately before
presentation. Mean maximum outgoing repetition is15.0 versus18 incumbent.
Three meaningfulness failures appear in the first360 occurrences: two persist
from the prior policy, and the third returns to its pre-presentation position,
not newly admitted inventory. The owner has been asked whether automatic offers
must be independently meaningful to both managers.

Round5's narrower detached-proof prototype saves31% against the unchanged
candidate, but remains49% slower than the incumbent first-durable boundary and
reaches793–1,033MB local peak RSS. It is not integrated. Its package-cache sibling
is rejected for a live feature-flag race and no demonstrated benefit.

The next parent-specified round investigates early completed-simple-phase
delivery and a truly authenticated request-local proof boundary, separately.
Future age-provenance collection is also being implemented without silently
changing age-based eligibility or current prices. These are continuing work,
not a release or a waiver of any missing evidence.

## Next development decision

Keep useful correctness improvements, but do not promote the whole model on this
evidence. Use development-only traces to isolate whether focal-alignment changes
come from constructor eligibility, construction ordering or survivor ordering.
Form mechanism-level regression cases before another semantic change; do not
tune weights against the disclosed holdout. Register a new independent test set
before calling a subsequent revision a release comparison.

Complete behavior-preserving performance work separately. Before activation,
rerun exact-source tests/CI and the matched benchmark, demonstrate no material
first-action regression, and obtain the missing independent evidence or an
explicitly bounded experiment decision with stated uncertainty. Physical-device
and production-load checks remain distinct from local worker timings.

Specifications, implementation history and verification are linked from
[scope](scope.md), [integration evidence](integration-evidence.md),
[evaluation evidence](evaluation-evidence.md) and [release checklist](release-checklist.md).
