# Build status — W2d: re-balanced calibration split + create-contract gaps

**Date:** 2026-08-06 · **Wave:** draft-extensions W2d · **Status:** _in progress — §1 is the PRE-REGISTERED decision, written and committed before the fit was run_
**Predecessor:** [build-w2c.md](build-w2c.md) → [build-w2b.md](build-w2b.md) → [build-w2.md](build-w2.md)
**Gate artifact (I-10):** [mock-calibration-2026-08d.md](mock-calibration-2026-08d.md) (08 / 08b / 08c kept as history)
**Spec:** [plan.md](plan.md) §5 + amendments · [lld.md](lld.md) §2.3 / §3.3 / §4.2.3

---

## 1. PRE-REGISTERED DECISION — the gate change, recorded before it was run

> **This section was authored and committed in its own commit BEFORE the harness
> was modified or the fit re-run.** A gate change decided after seeing its own
> results is worthless; the separate commit is the evidence of ordering. Nothing
> below was revised after the numbers came in — corrections, if any, appear in
> §4 as explicit deviations.

W2c's verdict (FAILED, both paired-mean bars) localised its own cause: the
observable drifts **2.017 slots** between the fit block (Lakeview r1–2, observed
mean 1.870) and the hold-out (r3–4, observed mean 3.886) — twice the ±1.0 bar,
inside one corpus, before any model. `d` is a *rank* distance and the consensus
value curve is steep at the top and flat in the tail, so the fit block is
systematically the shallowest part of the draft. The operator's decision is
**option A (re-balance the split) plus option B (add corpora)**. Practice/replay
(rejected) is not on the table, and no bar, α, tie rule, model family or `d_i`
definition moves.

### 1.1 The new split — alternating interleave over the retained pick sequence

Take `lakeview-complete`'s 48 picks **in draft order**, drop the picks the
consensus cannot price (the unchanged `reach_report` `skipped` rule) to get the
**45 retained picks**, indexed `0..44` in draft order. Then:

| Block | Rule | n |
|---|---|---|
| **Fit** | retained picks at **even** index (0, 2, 4, …) | 23 |
| **Hold-out** | retained picks at **odd** index (1, 3, 5, …) | 22 |

Block sizes are **identical to W2c's** (23 / 22), so every n, SE and bar
comparison against 08c is like-for-like and the change is visible as a change of
*composition*, not of *power*.

**Why alternation, and not stratified sampling from both ends** (both were
offered; one had to be chosen and justified):

1. **Determinism.** Alternation is a pure function of the corpus — no RNG, no
   seed, nothing an operator could re-roll until the gate passed. A stratified
   sample needs either an RNG or an arbitrary within-stratum rule, and both are
   degrees of freedom the gate should not have.
2. **The finest possible depth balance.** Adjacent retained picks sit one draft
   slot apart, so alternation pairs every fit pick with its immediate
   neighbour. The two blocks' depth distributions therefore match at the
   granularity of a single pick. Stratified-by-round sampling balances only to
   *round* granularity — it would still let the two blocks differ by up to half
   a round of depth, which on this corpus is ~6 slots.
3. **Every round is in both blocks.** Each 12-pick round contributes 6 picks to
   each block (±1 where a pick was skipped), so no round is fit-only or
   hold-out-only and no round-level idiosyncrasy can be mistaken for a model
   failure.

**Not changed, deliberately:** the hold-out is still never fitted; the fit
objective is still W₁ on `|d|` over the same 110-point grid; the observable is
still the remaining-pool `d_i`; ties are still average-rank over the tied block;
unvalued picks are still excluded and counted.

### 1.2 The precondition that makes the split un-skewable

A new test, **T-W2-19**, asserts the balance **before** the fit consumes the
split, so it can never silently re-skew (e.g. if a corpus is re-recorded or the
`skipped` set changes):

* **Depth balance.** `|mean(draft position of fit block) − mean(draft position
  of hold-out block)| ≤ 1.0 pick.` The tolerance is one pick position — the
  finest granularity the observable has, and the number the ±1.0 mean bar is
  denominated in.
* **Round balance.** In every round, `|count(fit) − count(hold-out)| ≤ 1`.

Stated as a bar, in the test, in the same units as the gate. If either fails the
suite goes red and the split has to be re-derived deliberately.

### 1.3 The corpora — one added

| Corpus | Role | Why it qualifies |
|---|---|---|
| `lakeview-complete` | fit (interleaved) + hold-out (interleaved) | unchanged from W2a/b/c |
| `mfl-complete` | independent, **no refit** | unchanged |
| **`mfl-partial`** | **independent, no refit — NEW** | single `draftUnit`, 6 rounds ⇒ rookie-shaped (≤ `ROOKIE_MAX_ROUNDS`), 36 of 72 picks made and all in rounds 1–3. Already shape-checked by T-W2-17 and unused since M1. `mfl-multi-unit` stays excluded — it is a two-unit conference split, so "the pool as it stood at that pick" is not well defined across units; that exclusion is about units, not round count |
| `mfl-made0`, `startup-shaped`, `ffv3-predraft`, `empty-drafts` | excluded | **no made picks at all** — nothing to measure |

**How the new corpus enters the gate:** as its **own** independent validation
block with **both** bars applied to it, exactly like `mfl-complete`, with **no
refit**. The gate therefore becomes **six bars** (KS + paired mean on each of
three validation blocks) where W2c had four. Adding a corpus this way can only
make the gate **harder** to pass, which is the point: it removes any suspicion
that the corpus was added because it helps.

**Pricing:** `mfl-partial` is priced `1qb_ppr`, the same default `mfl-complete`
uses. Neither MFL corpus records league scoring settings — the fixture is a
`draftResults` export only — so this is an assumption, and it is the *same*
assumption already recorded for `mfl-complete` (whose `sf_tep` alternative was
tested and rejected in 08c §3). It is recorded here rather than discovered
later.

### 1.4 What is FROZEN

Restated so the diff can be checked against it: **the model family** (the W2b
two-parameter `bpa_prob` + Gumbel-reach mixture), **both bars** (KS not rejected
at α = 0.05; `|Δ mean|d|| ≤ 1.0`), **α = 0.05**, **the ±1.0 constant**, **the
tie rule** (average rank over the tied block, applied identically to observed
and simulated series), **the unvalued-pick rule** (excluded and counted), and
**`d_i`** (the remaining-pool reading). The two parameters `mock_bpa_prob` and
`mock_reach_decay` **may** be re-fitted — that is what a re-run means.

### 1.5 What a pass and a fail each commit to

* **All six bars pass** ⇒ flip `CPU_MODEL_VALIDATED = True`, remove the create
  route's `cpu_model_unvalidated` short-circuit, keep the both-directions gate
  test intact. `draft.mock` still ships **OFF**.
* **Any bar fails** ⇒ `CPU_MODEL_VALIDATED` stays `False` and the short-circuit
  stays. If the failure is again the paired-mean bar *and* the blocks' SEs still
  exceed ±1.0, the artifact says so with the numbers and states plainly whether
  the bar is measurable at the available sample size. **The bar is not widened
  unilaterally under any outcome.**

---

_§2 onwards is written after the run._
