# Round 6 — complete-simple-phase delivery feasibility

September 22, 2026. Parent spec: `spec-round6-early-delivery.md`.

## Decision

**Architecturally promising, not a release pass.** The completed simple subset
reached an actual durable first 30 in **2.254 seconds** locally, without skipping
the worker's owner/roster/market/significance/disposition/presentation/persistence
checks. Full constructor continuation preserves all 3,836 native cards and exact
proof/report bytes under the controlled hash seed. But unconditional simple-first
delivery loses known personal-direction coverage and some direction quality in
the development diagnostics. No runtime code, production flag or release changed.

This is one private architectural prototype, `complete-simple-phase-offline-1`.
It is **not integrated streaming**, does not demonstrate full-worker continuation
or append-only prefix safety, and does not establish a production three-second
SLA. The phase-only worker calls itself complete only inside this explicitly
labeled offline experiment; that behavior must not be copied into production.

## Private implementation and bindings

Scratch root: `/private/tmp/bilateral-latency-20260922.eGQ8r0`.

- `early_delivery.py` SHA256
  `c2664b89529f9f2e9e1f02e0387a885c0a0ff3891a8b52bff98698b03c3971b1`.
  Adds a private sentinel immediately before the existing companion expansion
  sort, after every simple candidate has been evaluated. A phase-aware copy of
  the unchanged constructor loop pauses each partner at that sentinel.
- `only` mode returns the complete ranked simple subset through the actual
  worker harness. `continue` mode keeps the same iterators/counters and resumes
  companion evaluation after making a detached, ranked phase copy. Neither
  mode changes eligibility, package construction, weights, pools or budgets.
- To prevent a binding global cap from allocating different per-partner work,
  the phase is admitted only when `total_budget >= members * pair_budget`.
  Otherwise `only` refuses publication; `continue` uses the original search.
  A per-pair cap that interrupts simple enumeration also prevents publication.
- Explicit pins, opponent-selected searches, exact-give and swap-position paths
  are excluded. Incumbent calls bypass the private phase loop.
- `early_quality.py` hard-allowlists only development organic contexts
  3, 16, 19, 31, 41, 42, 63 and 67. Its one source insertion installs the probe
  after the independent worker's isolation setup. Normalization, captured-fact
  overlay, significance proxy, policy3 and independent grader are unchanged.
- All source-guarded processes completed. HEAD was `6c53caf9`; actual-worker
  summaries bind the exact dirty age-capture source used for each run. Only
  scratch SQLite was used and networking was blocked. No held-out input/output
  was read. C verified the original latency input is development capture 10.

## Actual durable lower bound

`round6-early-worker-seed0/summary.json` is the controlled result; its command
used `PYTHONHASHSEED=0` and the worktree as cwd. The original unseeded successful
smoke is retained as `round6-early-worker-r2`; an earlier wrong-cwd launch failed
before worker execution and remains separately retained as `round6-early-worker-r1`.

| Observation | Controlled phase-only result |
|---|---:|
| Native simple candidates evaluated | 3,328, across all 13 partners |
| Eligible native simple offers | 530 |
| Final phase survivors after actual worker checks | 275 |
| First durable 30 | 2.254 s |
| Complete phase-only worker | 2.563 s |
| Constructor stage | 1.290 s |
| Owner final revalidation | 0.626 s |
| Disposition stage | 0.125 s |
| Entire durable evidence/publication stage | 0.345 s |
| Local process peak RSS | 326,074,368 bytes |

All four phase-publication snapshots (30/130/230/275 cumulative) were verified
against committed SQLite impressions. Exact proof/version, persisted input fields,
full persisted-row identity/order, contiguous indices, immutable public-content
prefix and source guards passed. The harness's `full_inventory_preserved` field
means **the 275-card phase inventory**, not the complete 3,306-card full-worker
candidate inventory. These experiments never publish companions.

The unseeded smoke was 2.267 s / 2.572 s and 269,746,176 bytes. Do not average
different hash seeds/source bindings into a controlled latency estimate. Prior
round5 incumbent first-durable means were 8.677 s, but those are historical local
comparators, not a new simultaneously paired production experiment. The worker
does not include provider fetch, real queue/network/poll/client render or
PostgreSQL latency; isolation uses frozen input and empty scratch history.

## Full-constructor continuation and memory

Fresh-process `round6-native-current-seed0` / `round6-native-continue-seed0`
and the later `*-rss` pair exactly match each other and the retained round5 full
candidate native export:

- All 3,836 cards: SHA256
  `5070cbcd96ca0bd77c1d287a9fe3231771c1bbb1f63e0cea932d051209a063c5`.
- Full report: SHA256
  `3baf157d373843562b29dd6fc0a9781e22d92da4ab471204d7c208be81fcdc3a`.
- Native terms, order, all private proof snapshot strings, per-partner evaluation
  counts/pools/rejections and all other card/report fields match. Only occurrence
  IDs/card timestamps and report elapsed time are excluded, as in round5.
- Full search evaluates 53,170 terms. The phase copy contains 530 detached
  objects with exact proofs; later full ranking does not change their phase
  scores. This verifies constructor copy isolation, not published server objects.

An initial unseeded pair differed in lineup-proxy fields, pool/rank and some
terms; even a fresh unmodified baseline differed from its prior baseline. With
`PYTHONHASHSEED=0`, the original baseline hash and full continuation both match.
The existing unordered roster/lineup path is a reproducibility limitation; no
model correction was made here. The independent panel already freezes this seed.

One observational native-export RSS pair measured current 10.088 s / 684,474,368
bytes versus phase-continuation 10.262 s / 678,608,896 bytes. This is not evidence
of a meaningful memory reduction; exports contribute to process peak RSS.
At the completed phase, live paused iterators retain 97,140 expansion entries,
and `_decisions` retains 3,328 proofs (2,798 rejected), with 10,388,877 UTF-8
snapshot bytes. By search end `_decisions` retains 53,170 proofs (49,334 rejected)
and 112,849,718 snapshot bytes. Counts include no Python-object/container overhead.

These are substantial retained allocations, but no allocation profile proves
they dominate RSS. This prototype does not retire either state. A real callback
would hold paused expansion arrays and decisions across early validation and
publication, alongside detached phase objects and serialized evidence. The
phase-only process discards continuation state and therefore understates the
integrated memory footprint. Local RSS is not Render memory consumption or
parallel capacity; [capacity readback](capacity-readback.md) remains separate.
Any future retirement optimization requires its own exact-lifetime proof, not
proof thinning or budget cuts.

## Development first-30 diagnostics

Each of the eight named contexts supplies 30 early and 30 full offers. Results
are in `round6-quality-{index}`; `round6-quality-summary.json` binds exact input,
configuration and source result hashes to retained incumbent and policy3 full
candidate results. They are correlated development contexts, not 240 independent
observations or a new blind holdout. No acceptance labels or ratified grade
thresholds exist here. Five independent dimensions remain wholly evidence-limited;
meaningfulness reports 2/240 known failures for incumbent and 3/240 for both full
candidate and early, all in context16; its remaining offers are evidence-limited.

| Across eight first-30 views | Incumbent | Full candidate policy3 | Early simple phase |
|---|---:|---:|---:|
| Mean distinct outgoing headliners | 6.25 | 6.25 | 9.125 |
| Mean maximum headliner repetitions | 16.125 | 13.75 | 9.875 |
| Mean distinct partners | 9.375 | 9.75 | 10.5 |
| Mean raw viewer market return | -5.77% | -6.26% | -7.68% |
| Mean best-asset seller raw return | +2.29% | +3.93% | -9.89% |
| A SELL focal hits / known focal count | 199/226 | 189/211 | 159/184 |
| A BUY focal hits / known focal count | 196/240 | 217/267 | 151/187 |
| B SELL focal hits / known focal count | 15/18 | 13/15 | 2/6 |
| B BUY focal hits / known focal count | 14/19 | 14/18 | 4/5 |

Focal counts include all independent tied headliners; they are not offer counts.
Known counterpart coverage is very sparse and falls further in the early page.
Unknown is never treated as a successful hit. A known focal coverage falls from
80.2%/92.1% (SELL/BUY) to 76.7%/77.9%; B falls from 5.68%/6.87% to 2.5%/2.08%.
The B SELL change is concerning but has a tiny denominator, not a precise estimate
of general counterparty preference quality.

Repetition improves in six contexts but worsens in context3 (10 to 23) and
context67 (6 to 7). The raw market return numbers are additive price facts,
not stud-adjusted fairness or willingness. On matched exact requested returns,
early price never increases versus candidate (48 matches; 14 cheaper) or
incumbent (58 matches; 13 cheaper). This does not erase lost focal coverage or
permit claiming globally more efficient pricing across different targets.

All early views pass the same independent meaningful-centerpiece proxy, but
that is not equivalent to both-side meaningfulness or the actual provider worker
gate. Mean A outgoing filler-value share increases from 25.4% to 33.3%, while
incoming falls from 11.5% to 1.3%; counterpart means remain source-limited.
Independent projected-starter support/true roster utility and acceptance remain
Unknown. Constructor eligibility is not a replacement independent quality grade.

## Smallest integration seam, if separately approved

Do not integrate unconditional simple-first delivery on this evidence. The
architecture is worth retaining, but the early-page policy needs an explicit
quality decision and another bounded validation before any activation.

The minimal implementation would expose one optional candidate-only completed
phase callback/event from the existing single search, carrying a named delivery
version, immutable phase metadata, detached ranked exact cards and the same
continuation counters. No recursive worker, fake completed job or duplicate
hidden generation. Off/selected/inbound/mixed-arm routes keep their current path.

The server seam should factor its existing owner-only safety pipeline into one
shared callable used by both early and final batches: revalidate exact owner
proofs, roster/market/significance, read current dispositions, present/serialize,
durably persist and then publish only while the captured policy/source/roster
authority remains live. An active job stays active after the first batch.

Publish a bounded first page only after ranking the **entire complete simple
subset**, not the first thirty generated terms. Resume the same search with the
same budgets. Rank the complete final inventory, omit exact already-published
identities and newly liked/passed/excluded offers, and append a suffix without
mutating any published card, proof, rank, impression ID or diagnostic metadata.
Separate immutable early-phase evidence from final-generation evidence rather
than overwriting earlier persisted diagnostics with a final report.

Required but unexecuted integrated tests: exact full inventory/no duplicate or
lost suffix occurrence; immutable publication prefix; current dispositions after
an early action; policy/source/roster changes and expiry at every existing check
including commit/publish/GET; cancellation releases paused search state and never
appends; failure after early durable publication never masquerades as complete;
small/empty phase falls back honestly; off/selected/inbound/mixed-arm parity;
combined actual-worker first-durable/full-completion latency and peak RSS. Fresh
flags must not bypass evidence, and retained early results must be revoked when
the existing live policy/source/roster authority is no longer valid.

## Validation and stopping point

Ten private synthetic contracts pass, including exact synthetic continuation,
all-partner completion, phase-copy isolation, five explicit-path exclusions,
global-cap exact fallback, per-pair incomplete-phase refusal and incumbent parity.
C's independent read-only review found no current-source blocker in the private
phase or diagnostic insertion. C recommended exact-one guards on every source
replacement before future reuse; production should use explicit phase APIs,
never source-text injection. All runtime source remains unchanged by this agent.
The one-prototype round is complete with a negative release recommendation.
