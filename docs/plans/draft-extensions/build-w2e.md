# Build status — W2e: the round-tiered reach policy (installed, NOT re-gated)

**Date:** 2026-08-07 · **Wave:** draft-extensions W2e · **Status:** policy shipped; calibration deliberately **not** re-run
**Predecessor:** [build-w2d.md](build-w2d.md) → [build-w2c.md](build-w2c.md) → [build-w2b.md](build-w2b.md) → [build-w2.md](build-w2.md)
**Gate artifact (I-10):** still [mock-calibration-2026-08d.md](mock-calibration-2026-08d.md) — see §4
**Spec:** [plan.md](plan.md) §5 + amendments · [lld.md](lld.md) §4.2.3

---

## 1. What this wave is, and what it deliberately is not

W2d's recorded finding was a **support failure**: `MOCK_CANDIDATE_WINDOW = 12`
bounded every simulated reach at 11.5 slots while 7 of 102 validation picks
reached 13–51.5, probability exactly zero, and those 7 carried essentially the
whole paired-mean gap. W2d refused to move the constant, because choosing a
support bound by what makes the gate pass is the fit-on-the-validation-set move
amendment 2 exists to prevent — and asked the operator to decide it on product
grounds instead ([08d §8 option A](mock-calibration-2026-08d.md)).

**The operator decided it.** W2e implements that decision and **stops there**.
It does **not** re-fit `mock_bpa_prob` / `mock_reach_decay`, does **not** re-run
the six-bar gate, and does **not** touch `CPU_MODEL_VALIDATED` or the create
route's `cpu_model_unvalidated` short-circuit. Re-fitting and re-gating is a
separate, later decision.

**The operator's rule, verbatim:**

> "For the first round, I expect no more than reaching 3 picks (and no more than
> 3 times a round). For the second round 5 picks (and only 2 times a round). For
> the third and fourth 15 picks (limit of 5 times a round)."

Formalised as a round-tiered reach cap with a per-round frequency budget:

| Round | Max reach (consensus slots) | Max reaching picks per round, league-wide |
|---|---|---|
| 1 | 3 | 3 |
| 2 | 5 | 2 |
| 3, 4, and every later round | 15 | 5 |

## 2. The semantics implemented, stated precisely

Each of these was a real choice; the alternative is named where one existed.

1. **"Reach" is measured on the pick's raw 0-based position in the remaining
   consensus pool** — the same remaining-pool reading `d_i` uses, before the
   average-rank tie adjustment. A pick at best-player-available is never a
   reach, and a pick at position `k` is a reach of `k` slots.

   *Why not the tie-averaged `d_i` itself:* the two clauses of the brief
   conflict under the frozen tie rule. A BPA pick that sits inside a
   consensus-tied block has tie-averaged `d > 0`, so scoring the policy on `d_i`
   would make "a pick at BPA is not a reach" false. The raw position is also the
   only quantity the engine can act on at decision time. The residual difference
   is bounded by the width of a tied block and is visible in two places on the
   *measured* series: a capped pick can measure slightly past its cap, and a
   round can measure one more `d > 0` than its budget. Both are the frozen tie
   rule showing through, not a policy leak.

2. **The cap truncates the candidate set** — `cpu_pick` scores over
   `candidates[:cap + 1]`. Because the noise is a per-candidate Gumbel whose
   argmin is a softmax, this truncates the geometric reach law at the cap
   exactly, without leaving the shipped per-candidate additive-noise code shape.
   A CPU can never reach past its round's cap at any parameter.

3. **The frequency budget is per round and shared across every CPU team** — not
   per team. It is consumed in pick order; once spent, the round's remaining CPU
   picks are handed `reach_cap=0`, which collapses the candidate set to the
   board pick.

4. **"Strict best-available" includes the need term.** With the budget spent a
   CPU takes the board pick even with a desperate positional need. A need-driven
   pick is a reach by the same measure as any other, so letting the need term
   keep pulling would leak past the budget it is meant to enforce.

5. **Determinism / replay.** The budget is re-derived from the persisted picks
   on entry to `advance_cpu` (`reaches_spent`) rather than carried in memory, for
   the same reason `_team_viable` is: the remaining pool at pick *j* is the
   frozen pre-draft pool minus picks `0..j-1`, so every prior pick's depth is
   reconstructible from the row alone. A mock resumed mid-round spends the
   budget exactly as one that never stopped, and INV-10 (same `rng_seed` ⇒
   byte-identical draft) still holds. The per-pick RNG is unchanged and is still
   a pure function of `(rng_seed, pick_no)`.

6. **The user is outside the policy.** A human's own reach neither consumes the
   budget nor is constrained by it. The rule describes how the bots draft, and a
   human reaching in round 1 should not force the field to BPA for the rest of
   it.

7. **`MOCK_CANDIDATE_WINDOW` is demoted to a performance bound** and widened
   **12 → 24**. The deepest round cap is 15, which needs 16 candidates; 24
   leaves 8 slots of headroom so the round tier is always what bites.
   `test_w2_04b_the_candidate_window_is_never_the_binding_constraint` asserts
   the slack at **every** round the engine can draft, plus that the round tier
   really is the binding bound through the engine.

8. **`mock_max_reach_slots` keeps its job, narrowed.** It scales the *need* term
   and nothing else; it is no longer any part of the support bound.

9. **The policy is a code constant, not a `model_config` key** — deliberately,
   even though it sits beside three keys that are. It is the model's support
   bound, and a DB row that could move it would silently invalidate whatever
   calibration verdict is on record. Changing either table is a product decision
   that requires a re-gate. Recorded in
   [docs/config-reference.md](../../config-reference.md).

## 3. What changed

| File | Change |
|---|---|
| `backend/mock_draft_service.py` | **new** `MOCK_REACH_CAP_BY_ROUND` / `MOCK_REACH_CAP_LATE` / `MOCK_REACH_BUDGET_BY_ROUND` / `MOCK_REACH_BUDGET_LATE` + `round_reach_cap()` / `round_reach_budget()`; `cpu_pick(..., reach_cap=None)` truncates the candidate set; `advance_cpu` tracks and enforces the round budget; **new** `reaches_spent()` (resume-safe re-derivation); `simulate_reaches(..., rounds_by_pick=…)` applies the identical policy; `MOCK_CANDIDATE_WINDOW` 12 → 24 and re-documented as a performance bound; `MOCK_MAX_REACH_DEFAULT` role narrowed; module docstring + gate comment updated |
| `backend/tests/test_mock_draft.py` | **new** T-W2-21 block (7 tests): the policy table is the operator's rule, no CPU exceeds its round's cap over 40 seeds at the flattest corner of the grid, no round exceeds its budget, a spent budget forces strict BPA including the need term, the budget is league-wide not per-team, the budget survives a resume from the row, and a user reach neither spends nor is bound by it. `test_w2_04b_the_candidate_window_truncates_the_tail_and_is_not_fitted` → **`test_w2_04b_the_candidate_window_is_never_the_binding_constraint`**. `test_w2_16_the_candidate_window_cannot_produce_the_deepest_observed_reaches` **removed** (see §5). Corpus helpers now carry each pick's recorded round |
| `docs/config-reference.md` | the policy tables, the semantics, why it is not a `model_config` key, and the window's demotion |
| `docs/architecture.md` · `glossary.md` | the reach bound is the round tier, and a re-gate is owed |

**Not touched:** any `mobile/` file · `backend/database.py` · `backend/server.py` ·
`CPU_MODEL_VALIDATED` · the create route's `cpu_model_unvalidated`
short-circuit · `_MODEL_CONFIG_DEFAULTS` · the corpora · the gate's bars, α,
±1.0, split, tie rule and `d_i` · every W1/W3 file.

## 4. The calibration gate — what its state is now

`CPU_MODEL_VALIDATED` is still `False`, `CALIBRATION_ARTIFACT` still points at
[08d](mock-calibration-2026-08d.md), and `draft.mock` still ships OFF. Two things
are worth stating plainly rather than leaving to be discovered:

* **08d's verdict table records the last run of the gate, and W2e changed the
  model's support underneath it.** Its §6 diagnosis is precisely what this wave
  acts on, so the numbers beside that diagnosis are no longer reproducible
  against this engine. **A re-fit and a re-gate are owed** before any figure
  from 08d is quoted again.
* **`mock_bpa_prob` / `mock_reach_decay` were left at their W2d values**
  (0.10 / 0.70) for the same reason — they were fitted under the old support
  bound. Nothing ships on them meanwhile: the routes refuse to generate CPU
  picks at all while the gate is closed.

`test_w2_16_calibration_gate` is intact and green. It pins a **boolean** —
`all_pass is CPU_MODEL_VALIDATED` — and the verdict is still `False`, so the
support change did not disturb it. The harness itself needed one mechanical
change to keep running: `simulate_reaches` now requires `rounds_by_pick`, so the
corpus helpers were extended to carry each pick's recorded round.

## 5. Deviations worth stating

1. **`test_w2_16_the_candidate_window_cannot_produce_the_deepest_observed_reaches`
   was removed, not repaired.** It asserted that the candidate window excludes
   the deepest observed reaches — which was W2d's *finding* and is exactly the
   property W2e deliberately removes. With `K = 24` the assertion is also
   arithmetically false (3 of 102 picks exceed 23, under its own 5 % floor). The
   claim it existed to protect — that the window is not the binding constraint —
   is now asserted in the opposite direction by
   `test_w2_04b_the_candidate_window_is_never_the_binding_constraint`.

2. **One harness bug was fixed in passing.** `_mfl_corpus` built its `drafted`
   list from the crosswalk-resolvable picks but its `owners` list from **all**
   made picks, so the two ran out of step by one position per unmapped MFL id (6
   on `mfl-partial`, 1 on `mfl-complete`) and the simulator fed the wrong team's
   positional needs into a pick. W2e adds a third parallel list (the recorded
   round), and a known misalignment sitting beside an aligned one would be worse
   than the bug. It affects the simulated side of the two MFL blocks only — one
   more reason the re-gate in §4 is owed.

3. **The policy is not snapshotted into `mock_drafts.settings.noise`,** unlike
   the three `model_config` values beside it. Those are snapshotted because an
   operator can retune them from the DB mid-mock; the policy is a code constant
   that cannot move without a deploy, so the same argument does not apply and
   the extra persisted surface is not worth it.

4. **`mobile/` typecheck could not be run in this worktree** — `mobile/node_modules`
   is not installed here. The claim it exists to support is proved directly
   instead: `git status --porcelain -- mobile/` is empty.

## 6. Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **1887 passed / 1 skipped, exit 0** (baseline 1881/1; +7 T-W2-21 tests − 1 removed W2d test, with one more replaced in place) |
| `git status --porcelain -- mobile/` | **empty** — `mobile/` untouched, as required |
| `test_w2_16_calibration_gate` | green, unchanged — `all_pass is CPU_MODEL_VALIDATED` (`False`) |
| T-W2-19 (split precondition) | green — depth gap 0.028 picks, tolerance 1.0 |
| T-W2-21 (the new policy) | green — caps, budget, strict-BPA exhaustion, league-wide scope, resume identity, user exemption |
| Amendment 1 (no second consensus) | `test_w2_14_the_service_declares_no_second_consensus` (AST, no `sorted`/`.sort`) + `test_w2_15_..._element_for_element` still green |
| Zero platform egress | T-W2-13's three checks still green |
