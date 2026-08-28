# Champion recommendation (Phase 4), 2026-08-27

> **Purpose:** which candidate engine should be champion, on today's evidence. This thread
> RECOMMENDS; the operator makes every flip. All flips listed are deploy-free `model_config` /
> flag writes with stated kill values. Evidence: [data-readout-2026-08-27.md](data-readout-2026-08-27.md),
> [hypothesis-results.md](hypothesis-results.md), [current-state.md](current-state.md).

## Contents

- [The decision in plain words](#the-decision-in-plain-words)
- [The measured case](#the-measured-case)
- [Method note — what "offline replay first" turned into](#method-note--what-offline-replay-first-turned-into)
- [Recommended flips and holds](#recommended-flips-and-holds)
- [What stays dark and why](#what-stays-dark-and-why)
- [Sequencing vs the knockout programme](#sequencing-vs-the-knockout-programme)
- [TEST_LEDGER entries drafted](#test_ledger-entries-drafted)

## The decision in plain words

**Keep the incumbent engine (arm `current`, as configured today) as champion, and keep the
interleaved bake-off running to accumulate a powered read.** Nothing measured justifies promoting
`challenger` or `gen_v2` now, and two things argue actively against promoting `gen_v2`: its card
mix concentrates on the single worst-performing card type we can measure (asking users to give
far-year firsts — 46.4% of its cards vs the users' 9.3% like-rate on that cut), and Q-030(b)
already rules its grading basis should be match-rate/honest-offer likes, which nobody can measure
yet at n=15 matches. The biggest wins available are not an engine swap — they are (1) stopping the
incumbent from spending users' far-year firsts as currency (H1), (2) a divergence-side insult rule
(H8), and (3) resolving the QB/format weak spot (H5) — all candidate work items, none of them
today's flip.

## The measured case

**Live interleaved reads (the only fair arm comparison, ≥2026-08-21):** current 46.9% (15/32),
challenger 44.6% (33/74), gen_v2 40.4% (19/47) — all anecdote-grade, CIs fully overlapping. No arm
separates. A ±5 pp per-arm read needs ~385 decided per arm ≈ **5–7 weeks** at current traffic.

**Offline profiles (all logged cards per arm — what each engine wants to serve):**

| | current | challenger | gen_v2 |
|---|---|---|---|
| give-far-1st share (users like these at 9.3%) | 10.3% | 13.8% | **46.4%** |
| 1:1 share (users' best shape, 36.9%) | 77.4% | 64.8% | **3.6%** |
| first-5 insult, raw I1 rule | 5.37% | **7.98%** | 6.15% |
| fairness median | 0.840 | 0.886 | 0.906 |

**Deck-eval gates on the champion as served:** empty-deck 4.89% overall / 5.05% August —
**marginal** against <5%, concentrated in targeted (non-bakeoff) jobs; insult on the comparable
population (consensus-basis first-5) **1.48% — PASS**, identical to the 2026-08-15 report.

**H7 (the reason a challenger might have earned promotion):** divergence-basis cards do NOT yet
outperform consensus-basis anywhere — the core-pitch hypothesis is unproven, so a promotion argued
on "more personalization" (challenger's overlay, gen_v2's 100%-divergence sourcing) has no measured
footing today.

## Method note — what "offline replay first" turned into

The plan ordered: offline replay (F8) → deck-eval gates → live read. What we found: the live read
is **already running** (interleaved serving lit 2026-08-21, before this review), and the bake-off
logs every arm's full decks — which is *stronger* offline evidence for engine-level candidates than
F8's IPS replay, whose scorer-replay design compares rankers over a shared card pool, not engines
that generate different pools. So Phase 4 used: logged-arm composition + gate metrics (offline leg,
above), deck-eval gates re-applied (this doc + readout §Guardrails), and the accumulating
interleave read (live leg). The F8 harness (`backend/eval/`) remains the right tool for RANKER
candidates (F5 η, F6) and was not rebuilt or modified.

## Recommended flips and holds

Operator actions, each independently revertible via the admin config API; **none is urgent**:

1. **HOLD champion = current.** No write needed.
2. **HOLD `bakeoff_serve_interleaved` = 1.0** (kill: 0.0 = instant dark mode, arm B only) — **but
   this is conditional on the operator's pending [Q-031](../../../living-memory/OPEN_QUESTIONS.md)
   call.** Q-031 (escalated 2026-08-26) records that the gen_v2 share of every organic deck
   silently ignores Chasing/Shopping positional preferences — a live defect that holding the knob
   perpetuates. This review adds a measurement argument to Q-031's option (c) (accept + disclose
   while the bake-off runs: killing interleave restarts a 5–7-week clock) and a product argument to
   option (b) (gen_v2's mix is 46% give-far-1st, the worst-measured card type — its serving share
   is currently *hurting* deck quality by the H1 read; `bakeoff_include_gen_v2` = 0.0 is a narrower
   kill that drops only arm C while preserving the current-vs-challenger read). The operator picks;
   this thread's preference order is (c) with `bakeoff_include_gen_v2` → 0.0, then plain (c), then
   (b). Deck-shrink watch: `bakeoff_runs` shows median deck 33, 0 empty runs — the 08-19 shrink
   problem has not recurred.
3. **DECIDE `overpay_adjusted` (currently 0.0).** The 08-24 batch turned the D-159 R1 currency
   change OFF the same minute the rest of the bundle went ON, and no living-memory record says why
   (logged as an open question). If unintentional: `= 1.0` restores the D-159 behavior (kill: 0.0).
   If intentional: one line in DECISIONS closes the question. This thread recommends whichever the
   operator *meant* — the record, not the value, is the defect.
4. **HOLD `v3_shape_max_delta` = 2.0** (kill: 1.0). Only 5 decided 3:1-family cards; no evidence
   either way; R2 starter-relief (the operator's actual positional protection) is lit.
5. **No new knob flips for H1/H5/H8.** The needed levers don't exist yet as knobs; they are
   candidate build items (give-side far-first exposure treatment; divergence-side insult rule;
   SF/TEP de-conflation + QB pricing settlement). Each goes through the full feature gates when
   built — and the far-first item must respect D-079/D-161 as standing operator rulings on *price*
   (twice ruled); the treatment is exposure/presentment, not repricing.

## What stays dark and why

| Surface | Stays | Why |
|---|---|---|
| `trade_gen.v2` (flag) | **dark** | Arm C's live read is parity-at-best on viewer likes, its mix is 46% give-far-1st, and its ruled grading basis (Q-030b: match rate, honest-offer likes) is unmeasurable at n=15 matches. Interleave exposure via the bake-off continues without the flag |
| Negmem (`trade.negmem` + allowlist) | **dark** | D-147 stands: rollout is two operator flips at a round boundary, the TestFlight checklist is written and unrun, and no runtime evidence exists. Nothing in this review's data bears on negmem either way — its precondition (reasoned declines at volume) is accruing (346 `trade_pass_reasons`) |
| `deck.value_model` (F6) | **dark** | Its own pre-registered gate (an F8 replay win) has not been attempted |
| Challenger promotion | **no** | Parity on likes, worst first-5 insult profile (7.98%) — its landability overlay loosens exactly the gates holding H8 |
| D-079/D-161 pick pricing | **unchanged** | Operator-ruled twice with market evidence in view; H1's fix is exposure, not price |

## Sequencing vs the knockout programme

NEXT.md's knockout item ("R5 dual-need rescue → consolidation bundle measured in the replay
harness before any flip → R2 starter-depth") is **partially overtaken by events**: the bundle knobs
were flipped live on 2026-08-24 and R5 dual-rescue + R2 starter-relief ship lit (seeds 1.0). What
remains of that item and this review are now **the same measurement stream** — the interleaved
read + deck-eval gates on the live config. They must be sequenced as one item, not run in parallel
(same knobs, same harness, per the plan's write-back rule). Concretely: hold the current config
stable for the read window; any further knockout flip (e.g. `filler_min_frac` 0.10, R2
starter-depth predicate work, viewer-must-win Q-030a) restarts the arm clock and should wait for
either the powered read or an explicit operator call to trade the read for the flip.

## TEST_LEDGER entries drafted

Drafted for TEST_LEDGER (the session write-back applies them):

- `2026-08-27 — trade-model-review Phase 2 mirror: prod SELECT-copied to local SQLite (69 tables;
  trade_impressions 18,830, deck_impressions 16,675, trade_decisions 1,452, deck_outcomes 1,454,
  model_config 234). Prod read-only; backend.server never imported. measured`
- `2026-08-27 — deck-eval guardrails recomputed on served data: empty-deck 4.89% all-time / 5.05%
  Aug (gate <5%: MARGINAL); insult (08-15 rule, floor 500) consensus-basis first-5 1.48% PASS
  (identical to 08-15), divergence-basis 8.18% flagged-not-comparable (rule premise breaks;
  divergence-specific rule = candidate work). measured`
- `2026-08-27 — interleaved arm read (2026-08-21→): current 15/32, challenger 33/74, gen_v2 19/47
  liked — no separation; ~385/arm needed, ~5–7 weeks. Offline arm profiles logged (gen_v2 46.4%
  give-far-1st). measured`
- `2026-08-27 — H1–H8 matrix verdicts recorded in docs/plans/trade-model-review/
  hypothesis-results.md; headline: give-far-1st cards 9.3% like vs 38.8% player-only; consensus-
  basis outperforms divergence for every user (H7 not supported yet). measured`
