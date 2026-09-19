# Mock-draft CPU noise model — calibration report, re-balanced split (interface I-10)

**Date:** 2026-08-06 · **Wave:** draft-extensions **W2d** (re-balanced fit/hold-out split + a third corpus)
**Supersedes:** [mock-calibration-2026-08c.md](mock-calibration-2026-08c.md) (W2c, the corrected snapshot) · [08b](mock-calibration-2026-08b.md) (W2b, the mixture) · [08](mock-calibration-2026-08.md) (W2a) — all kept as history
**Normative:** [plan.md](plan.md) §5 (amendment 2 + the W2 abort criterion) · [lld.md](lld.md) §4.2.3
**Pre-registration:** [build-w2d.md](build-w2d.md) §1 — the split change and the added corpus were decided, written and **committed in their own commit before the harness was touched or the fit re-run**
**Reproduced by:** `python3 -m pytest backend/tests/test_mock_draft.py -k "w2_16 or w2_17 or w2_19"`
**Harness:** `backend/mock_draft_service.reach_report` / `simulate_reaches` (the simulator drives the **shipped** `cpu_pick`) + the statistics in `backend/tests/test_mock_draft.py`.

> **This document is a GATE, not a report.** `mock_draft_service.CPU_MODEL_VALIDATED`
> mirrors the verdict below, and `test_w2_16_calibration_gate` fails if the two
> ever disagree — in either direction.

---

## VERDICT: **FAILED** — the W2 abort criterion stays fired

**The model family is FROZEN.** Same two-parameter mixture, same two bars, same
α = 0.05, same ±1.0, same remaining-pool `d_i`, same average-rank tie rule, same
excluded-and-counted unvalued picks. W2d changed exactly the two things the
operator decided in advance: **the split** and **the corpus set**. The two
parameters were re-fitted, as a re-run requires; nothing else moved.

| Stage | Corpus / block | n | Bar | Result | |
|---|---|---|---|---|---|
| Fit | `lakeview-complete`, interleaved fit block | 23 | min W₁ over the 110-point grid | `mock_bpa_prob` **0.10**, `mock_reach_decay` **0.70** — **interior in both**, W₁ **0.329** (worst 3.185) | ✓ well-posed |
| Hold-out | `lakeview-complete`, interleaved hold-out | 22 | KS not rejected at α = 0.05 | D = **0.198**, p = **0.317** | **PASS** |
| Hold-out | " | 22 | \|Δ mean\|d\|\| ≤ 1.0 | observed **3.591** vs simulated **1.943** ⇒ Δ = **1.648** | **FAIL** |
| Independent (no refit) | `mfl-complete` | 28 | KS at α = 0.05 | D = **0.147**, p = **0.546** | **PASS** |
| Independent (no refit) | " | 28 | \|Δ mean\|d\|\| ≤ 1.0 | observed **5.536** vs simulated **1.930** ⇒ Δ = **3.605** | **FAIL** |
| Independent (no refit) | **`mfl-partial` — NEW** | 29 | KS at α = 0.05 | D = **0.219**, p = **0.108** | **PASS** |
| Independent (no refit) | " | 29 | \|Δ mean\|d\|\| ≤ 1.0 | observed **3.966** vs simulated **1.939** ⇒ Δ = **2.026** | **FAIL** |

`CPU_MODEL_VALIDATED` stays `False`, `draft.mock` stays OFF, and
`POST /api/mock-draft` still answers the typed-empty
`200 {"empty": true, "reason": "cpu_model_unvalidated"}`.

**All three KS bars pass. All three paired-mean bars fail.** Six bars where W2c
had four — adding a corpus made the gate *harder*, deliberately.

---

## 1. What changed — the split and the corpus set, and nothing else

| | W2c | **W2d** |
|---|---|---|
| Fit block | `lakeview-complete` **rounds 1–2** (23 retained picks) | `lakeview-complete`, retained picks at **even index** (23) |
| Hold-out | `lakeview-complete` **rounds 3–4** (22) | retained picks at **odd index** (22) |
| Independent | `mfl-complete` (28) | `mfl-complete` (28) **+ `mfl-partial` (29)** |
| Bars in the gate | 4 | **6** |
| Model family · both bars · α · ±1.0 · tie rule · unvalued rule · `d_i` · candidate window `K` | — | **all identical** |
| Fitted parameters | 0.20 / 0.70 | **0.10 / 0.70** |

The split rule and its justification are in [build-w2d.md](build-w2d.md) §1.1;
the added corpus and how it enters are in §1.3. Both were committed before this
run existed.

### Why the split had to move (W2c's own diagnosis)

`d` is a **rank** distance and the consensus value curve is steep at the top and
almost flat in the tail, so the same human disagreement costs 1–2 slots in round
1 and 20+ in round 4. A round-based split therefore hands the fit the shallowest
part of the draft and validates on the deepest:

| Split | mean draft position, fit | mean draft position, hold-out | **depth gap** | observable drift |
|---|---|---|---|---|
| W2c — rounds 1–2 vs 3–4 | 12.17 | 35.59 | **23.42 picks** | **2.017 slots** |
| **W2d — interleaved** | **23.61** | **23.64** | **0.028 picks** | **1.439 slots** |

Pinned by `test_w2_19_the_rebalanced_split_removes_the_depth_drift`, and the
depth balance is asserted as a **precondition** by
`test_w2_19_the_split_balances_draft_depth_before_the_fit_consumes_it`
(tolerance ≤ 1.0 pick, plus per-round counts within 1) so the split can never
silently re-skew.

**The re-balance did what it was decided to do.** The structural depth drift is
gone — 23.42 picks → 0.028 — and the observable's residual block difference fell
from 2.017 to 1.439 slots, which is **~1.1 standard errors** of the hold-out
block's own mean (SE 1.330). What remains is sampling noise on a heavy tail, not
a property of the split: one pick (`d` = 29.5) landed in the hold-out block and
moves that block's mean by 1.34 on its own.

## 2. The observable — unchanged

`d_i` = how many better-valued **available** players the pick passed over: the
player's 1-based consensus rank in the pool *as it stood at that pick*, minus 1,
averaged over any consensus-tied block. `d_i > 0` is a reach; `d_i == 0` is
best-player-available. Ties are average-rank over the tied block, applied
identically to the observed and the simulated series. Picks the consensus cannot
price are **excluded and counted**. All four sentences are W2c's, verbatim.

One W2d correction to a *stated argument*, not to the observable: W2c's
`reach_report` docstring justified the remaining-pool reading partly by its
lower drift across the split. That comparison is **split-dependent**. Under the
round-based split the static-rank reading drifts 3.557 against this reading's
2.017; under the interleaved split it drifts **1.156 against 1.439** — slightly
*less*. Most of the static-rank reading's excess drift *was* the depth term the
re-balance removes. The choice of reading is unchanged and still correct on the
structural ground that survives: over a frozen pre-draft pool a pure-BPA draft
scores a large "fall" by construction, so that reading cannot falsify a noise
model at all. The docstring was corrected rather than left to rot.

## 3. Corpora — one added, and every corpus's own numbers

Shape is checked **before** use (T-W2-17). `mfl-multi-unit` stays excluded — it
is a two-unit conference-split draft, so "the pool as it stood at that pick" is
not well defined across units; that exclusion is about **units**, not round
count. `mfl-made0`, `startup-shaped`, `ffv3-predraft` and `empty-drafts` are
excluded for having **no made picks at all**.

| Corpus / block | role | rounds | picks made | crosswalked | **n (retained)** | skipped | tied | **own observed mean** | sd | **SE of the mean** | median | max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `lakeview-complete` — fit (even) | fit | 1–4 | 48 | n/a | **23** | — | — | **2.152** | 2.786 | 0.581 | 1.0 | 10.0 |
| `lakeview-complete` — hold-out (odd) | validate | 1–4 | 48 | n/a | **22** | — | — | **3.591** | 6.237 | **1.330** | 2.0 | 29.5 |
| `lakeview-complete` — whole draft | — | 1–4 | 48 | n/a | 45 | 3 | 3 | 2.856 | 4.793 | 0.715 | 1.0 | 29.5 |
| `mfl-complete` | validate, no refit | 1–3 | 30 | 29 | **28** | 1 | 2 | **5.536** | 11.380 | **2.151** | 1.0 | 51.5 |
| **`mfl-partial`** | validate, no refit | 1–3 (of 6) | 36 | 30 | **29** | 1 | 0 | **3.966** | 5.130 | **0.953** | 2.0 | 18.0 |
| *(`mfl-complete` + `mfl-partial`, pooled — diagnostic only)* | — | — | — | — | 57 | — | — | 4.737 | 8.731 | 1.156 | — | 51.5 |

**Formats.** Lakeview `sf_tep` (from its recorded `roster_positions`); both MFL
corpora `1qb_ppr`. Neither MFL fixture records league scoring settings — the
cassette is a `draftResults` export only — so `1qb_ppr` is an **assumption**,
the same one already recorded for `mfl-complete` (whose `sf_tep` alternative was
tested and rejected in 08c §3). It is stated here rather than discovered later.

**`mfl-partial`'s unmapped picks.** 36 picks were made; 30 carry an MFL id the
committed DynastyProcess crosswalk resolves to a Sleeper id, and 29 of those are
priced by the consensus. The 6 unmapped picks are dropped by the same
pre-existing `_mfl_corpus` rule that drops 1 in `mfl-complete`. That is a
crosswalk-coverage limit, not a modelling choice, and it is reported here
because it is the difference between the README's "36/72 made" and this table's
n = 29.

## 4. The procedure and its numbers

### 4.1 Split — the change

Fit on the 23 even-indexed retained Lakeview picks; validate on the 22
odd-indexed ones. The hold-out block is never fitted. Then `mfl-complete` (28)
and `mfl-partial` (29), each with **no refit**.

Because the blocks are no longer prefixes, the **simulated** side is selected the
same way: each seed replays the **whole** retained draft through the shipped
`cpu_pick` and the same index parity is taken. The simulated block's depth
profile is therefore identical to the observed block's by construction. (W2c
simulated a 23-pick prefix for the fit and took the *first* 22 picks of a full
replay for the hold-out — distributionally harmless, since the model is
depth-independent, but no longer defensible under an interleaved split.)

### 4.2 Fit — the same 2-D grid, 1000 seeded simulations per point

Same natural-domain grids (`bpa_prob` ∈ {0.00 … 0.90}, `reach_decay` ∈
{0.1 … 0.9, 0.95, 0.99}), same 110 points, same objective: the 1-D Wasserstein
distance W₁ between the simulated and the observed `|d|` on the fit block.

**Fitted: `mock_bpa_prob = 0.10`, `mock_reach_decay = 0.70`. W₁ = 0.329.**

| `reach_decay` at `bpa_prob = 0.10` | 0.1 | 0.3 | 0.5 | 0.6 | **0.7** | 0.8 | 0.9 | 0.95 | 0.99 |
|---|---|---|---|---|---|---|---|---|---|
| W₁ | 2.000 | 1.729 | 1.230 | 0.827 | **0.329** | 0.643 | 1.678 | 2.225 | 2.627 |

| `bpa_prob` at `reach_decay = 0.70` | 0.0 | **0.1** | 0.2 | 0.3 | 0.5 | 0.7 | 0.9 |
|---|---|---|---|---|---|---|---|
| W₁ | 0.371 | **0.329** | 0.433 | 0.630 | 1.057 | 1.481 | 1.896 |

Interior in both parameters; W₁ essentially unchanged from W2c's 0.323 on a
different fit block, with a 9.7× spread across the grid.

### 4.3 Hold-out validation (interleaved, n = 22)

| Bar | Threshold | Result | |
|---|---|---|---|
| Two-sample KS | not rejected at α = 0.05 | D = **0.198**, p = **0.317** | **PASS** |
| Paired mean | \|Δ mean\|d\|\| ≤ 1.0 | observed **3.591** vs simulated **1.943** ⇒ Δ = **1.648** | **FAIL** |

The KS bar passes far more comfortably than W2c's on the same corpus
(p 0.101 → 0.317), which is the re-balance showing up where it should.

### 4.4 Independent validation — NO refit

| Corpus | n | KS | verdict | Paired mean | verdict |
|---|---|---|---|---|---|
| `mfl-complete` | 28 | D = 0.147, p = **0.546** | **PASS** | obs 5.536 vs sim 1.930 ⇒ Δ = **3.605** | **FAIL** |
| `mfl-partial` | 29 | D = 0.219, p = **0.108** | **PASS** | obs 3.966 vs sim 1.939 ⇒ Δ = **2.026** | **FAIL** |

Two leagues, a different platform from the fit corpus, a different scoring
format, no refit — and the *shape* survives on both.

## 5. Are the mean bars still jointly satisfiable?

W2b's failure rested on the claim that they were not. With three blocks the
question is whether any single simulated mean sits within ±1.0 of all three:

| Block | observed mean | its ±1.0 window |
|---|---|---|
| Lakeview hold-out | 3.591 | [2.591, 4.591] |
| `mfl-partial` | 3.966 | [2.966, 4.966] |
| `mfl-complete` | 5.536 | [4.536, 6.536] |

The intersection is **[4.536, 4.591]** — non-empty, but only **0.055 slots
wide**, against a 2.00 allowance and a 1.945-slot spread between the extreme
blocks. So the bars remain *arithmetically* satisfiable and the W2b argument
stays dissolved, but the margin is now razor-thin and one more corpus could
close it. Pinned, as a live assertion, by
`test_w2_16_the_mean_bars_are_still_jointly_satisfiable_across_three_blocks`.

For reference, the maximum simulated mean reachable anywhere on the frozen grid
is **5.36** (at `bpa_prob = 0.00, reach_decay = 0.99`), so the window is inside
the model family's reach — the fit does not choose a point there because the fit
block's own mean is 2.152 and W₁ is a distributional objective, not a mean
match.

## 6. Why it still fails — the residual is now a SUPPORT failure

The split is balanced, the shape passes three times, and the mean misses three
times. The reason is visible in one number.

**`cpu_pick` only ever scans `available[:MOCK_CANDIDATE_WINDOW]`**, so every
simulated `d` is bounded by `K − 1` = **11** (11.5 once a tied block is
averaged). The corpora are not:

| Block | n | picks with `d` > 11 | those picks | slots of the block's mean they carry | mean if capped at `K` |
|---|---|---|---|---|---|
| Lakeview hold-out | 22 | 1 | 29.5 | **1.341** | 2.795 |
| `mfl-complete` | 28 | 4 | 13.0, 15.0, 33.5, 51.5 | **4.036** | 3.214 |
| `mfl-partial` | 29 | 2 | 18.0, 18.0 | **1.241** | 3.552 |
| **total** | **102** | **7 (6.9 %)** | | | |

Those seven picks have probability **exactly zero** under the shipped model, and
the slots they carry are — to within a few tenths — the three paired-mean
deltas (1.648 / 3.605 / 2.026). **The mean bar is failing because the model's
support does not contain the deepest reaches the corpora record.**

This is the same structural shape as W2a's failure — a model whose support
excludes observed data — except that it now lives in the **product cap `K`**
rather than in the noise family. `K` is deliberately **not** a fitted parameter
(lld §4.2.3, the W2b brief): the reach branch is truncated *by* it, not fitted
*to* it, and it was set once from the fit block alone, when the fit block was
rounds 1–2 of a **censored** 56-player universe. **W2d does not touch it.**
Retuning a product cap against the validation blocks is precisely the
fit-on-the-validation-set move amendment 2 exists to prevent. It is recorded
here as evidence for the operator and pinned by
`test_w2_16_the_candidate_window_cannot_produce_the_deepest_observed_reaches`.

## 7. Is the ±1.0 mean bar measurable at the available sample size?

The operator asked for a plain answer with numbers. It is **no for two blocks of
three, and yes for the third** — and that split is what makes the verdict
readable:

| Block | n | mean | sd | **SE of the mean** | bar measurable? | Δ in SE units |
|---|---|---|---|---|---|---|
| Lakeview hold-out | 22 | 3.591 | 6.237 | **1.330** | **no** — SE wider than the bar | 1.24 |
| `mfl-complete` | 28 | 5.536 | 11.380 | **2.151** | **no** | 1.68 |
| **`mfl-partial`** | 29 | 3.966 | 5.130 | **0.953** | **YES** — SE inside the bar | **2.13** |
| *(MFL pooled, diagnostic)* | 57 | 4.737 | 8.731 | 1.156 | no (just) | — |

**Adding a corpus achieved exactly what W2c said it would.** `mfl-partial` has a
lighter tail (max 18.0, against 51.5 and 29.5), so its mean is estimated to
±0.95 — inside the ±1.0 bar. On that block the bar is a real test, and the model
**fails it by 2.13 standard errors**. So the paired-mean failure is **not**
attributable to sampling noise alone: at least one block has the power to
reject, and it rejects.

Stated plainly, as asked:

* On `lakeview-complete`'s hold-out and on `mfl-complete`, the ±1.0 bar remains
  **tighter than the standard error of the statistic it bounds** — a
  perfectly-specified model would fail them a large share of the time on noise.
  That is a real limitation of the evidence and it has not gone away.
* On `mfl-partial` the bar **is** measurable, and the model misses it by more
  than two standard errors. That is a genuine rejection, not a power artifact.
* **No bar was widened, and none should be on the strength of this.** The
  measurable block failed; the honest conclusion is that the model's mean depth
  is wrong, and §6 says where the wrongness lives.

Pinned by `test_w2_16_the_mean_bar_is_measurable_on_one_block_of_three`.

## 8. Consequences and options (plan §5's abort criterion, applied)

**Applied now:**

1. **The CPU-bot mock stays CUT.** `CPU_MODEL_VALIDATED = False`; `advance_cpu`
   raises `CalibrationGateClosed` unless a caller explicitly opts in (the
   harness and the engine tests do; the routes never do).
2. **`draft.mock` stays OFF**, and with the flag ON `POST /api/mock-draft` still
   returns `200 {"empty": true, "reason": "cpu_model_unvalidated"}`.
3. **The re-balanced split, the added corpus and the re-fit all ship**, as W2a's,
   W2b's and W2c's did, so the verdict is reproducible and the next attempt
   starts from the better gate rather than the worse one.

**For the operator to choose between — none of these is decided here:**

| Option | What it costs | What it would settle |
|---|---|---|
| **A. Re-examine the candidate window `K` as a PRODUCT decision** | a product judgement about how deep a bot may reach before it reads as broken, followed by one gate re-run | §6 localises the whole residual here. `K = 12` was set from the fit block of a censored universe and it bounds every simulated `d` at 11.5 while 6.9 % of real picks reach 13–51.5. **It must be decided as a product cap on its own terms — "how deep a reach still looks like conviction" — and only then re-run.** Choosing `K` by what makes the gate pass is fitting on the validation set; that is why W2d left it alone despite having measured it. |
| **B. Keep adding corpora** | corpus collection | `mfl-partial` proved the point: it is the first block whose mean is estimable at ±1.0, and it turned a possible power artifact into a genuine rejection. More recorded rookie drafts would do the same for the other two blocks and would tighten §5's now-0.055-slot joint window into something meaningful. |
| **C. Accept a documented residual** — ship bots against the KS bar alone, with the paired-mean result published as a known, quantified deviation | a deliberate, recorded lowering of the ship bar — **not** a quiet one | The shape bar now passes on **three** blocks, two platforms, two scoring formats, two leagues beyond the fit corpus, with no refit. Whether "the depth distribution is right but the mean depth is short by 1.6–3.6 slots" is shippable for a mock-draft *opponent* is a product judgement, and it is the operator's. If taken, it should be taken explicitly in the plan, not by editing this artifact. |
| **D. Re-spec the model a third time** | another wave | **Still not recommended.** Three KS bars pass, the fit is interior with W₁ 0.329, and §6 locates the failure in a truncation constant rather than in the family. A third form would be re-specifying around a cap that was never fitted in the first place. |

**Practice/replay is deliberately absent — the operator has rejected it.**

**Recommended order: A (as a product decision, then re-run), B alongside;
C only as an explicit product decision. Do not do D.**

---

*Prepared under [build-w2d.md](build-w2d.md), whose §1 was committed before this
run. The engine, the harness and every number above are reproducible with
`python3 -m pytest backend/tests/test_mock_draft.py -k "w2_16 or w2_17 or w2_19"`.*
