# Build status — W2b: mock CPU model re-spec (two-parameter mixture) + re-fit

**Date:** 2026-08-06 · **Wave:** draft-extensions W2b · **Status:** re-specced, re-fitted, **gate STILL FAILS — but on one bar of four, not four of four**
**Predecessor:** [build-w2.md](build-w2.md) (W2a — the model-form failure that triggered this)
**Gate artifact (I-10):** [mock-calibration-2026-08b.md](mock-calibration-2026-08b.md) · W2a's is kept as history at [mock-calibration-2026-08.md](mock-calibration-2026-08.md)
**Spec:** [plan.md](plan.md) §5 + amendment 2 · [lld.md](lld.md) §4.2.3

---

## Headline

W2a's abort criterion fired correctly on a **model-form** failure: a single additive
uniform-noise term could not express a distribution that is 44 % exactly-BPA with a
21 % tail at 6–9 slots. W2b replaced the family, not the tuning.

**The new model:**

```
score(c)       = rank(c) − need_bonus(t, pos(c)) − reach_noise(c)
reach_noise(c) = 0                      with probability mock_bpa_prob      ← fitted
               = Gumbel(0, β) i.i.d.    otherwise,  β = −1/ln(mock_reach_decay)  ← fitted
```

By the Gumbel-max identity the argmin over `rank − Gumbel` is a softmax over `−rank`,
so the reach depth is **geometric** with per-slot ratio `mock_reach_decay`, truncated
by the candidate window. Two parameters, both interpretable; `K` and `mock_max_reach_slots`
are product caps and stay out of the fit.

**The gate was re-run completely unchanged** — same split, same two bars, same α, same
independent corpus with no refit, same `d_i` (remaining-pool reading, drift 0.30).

### The four validation numbers

| Stage | Corpus | n | Bar | W2a | **W2b** | |
|---|---|---|---|---|---|---|
| Fit | `lakeview-complete` r1–2 | 23 | min W₁ | 2.059, **pinned at the grid boundary** | **0.444, interior in both parameters** | ✓ |
| Hold-out | `lakeview-complete` r3–4 | 20 | KS not rejected at α=0.05 | D 0.567, p 2.3 × 10⁻⁶ | **D 0.207, p 0.324** | **PASS** |
| Hold-out | " | 20 | \|Δ mean\|d\|\| ≤ 1.0 | Δ 2.37 | **Δ 0.222** (obs 2.650 / sim 2.428) | **PASS** |
| Independent (no refit) | `mfl-complete` | 28 | KS at α=0.05 | D 0.570, p 9.4 × 10⁻⁹ | **D 0.216, p 0.127** | **PASS** |
| Independent (no refit) | " | 28 | \|Δ mean\|d\|\| ≤ 1.0 | Δ 5.06 | **Δ 2.935** (obs 5.357 / sim 2.422) | **FAIL** |

**Fitted parameters: `mock_bpa_prob = 0.50`, `mock_reach_decay = 0.95`.**
Not fitted: `mock_max_reach_slots = 3.0`, `MOCK_CANDIDATE_WINDOW = 12`.

**Verdict: FAILED.** Both bars must hold on both corpora, so `CPU_MODEL_VALIDATED`
stays `False`, `draft.mock` stays OFF, and the create route keeps answering the
typed-empty `200 {"empty": true, "reason": "cpu_model_unvalidated"}`.

### Is the mixture closer? Yes — and the residual is a different kind of failure

- **W₁ on the fit block: 2.059 → 0.444**, a 4.6× better fit on the same objective,
  the same block and the same observable.
- **The fit is well-posed now.** The optimum turns over on both sides in both
  parameters (W₁ 0.491 / **0.444** / 0.506 across `decay` 0.90/0.95/0.99; 0.701 /
  **0.444** / 0.579 across `bpa_prob` 0.4/0.5/0.6) and the objective has a 6.7×
  spread across the grid. W2a's was monotone to the boundary with a 1.14× spread.
- **Three of four bars pass**, including the *shape* bar on a completely independent
  league, platform and scoring format with no refit.
- **The one failure is not a model-form failure.** The two corpora's own observed
  mean `|d|` differ by 2.707 slots — 2.7× the ±1.0 bar — before any model is
  involved. Passing Lakeview's mean bar needs a simulated mean in `[1.65, 3.65]`;
  passing MFL's needs `[4.36, 6.36]`. **Those intervals are disjoint**, so no
  corpus-invariant noise model can satisfy both. (Simulated means: 2.428 Lakeview,
  2.422 MFL — a 0.006-slot difference. The reach law does not know which league it
  is in, and MFL's need term is inert because that corpus has no roster snapshot,
  so severity is uniformly 1.0 and cancels out of an argmin.)

### What actually drives MFL's mean — diagnosed, deliberately NOT fixed

Four picks (reaches of 11, 17, 26, 33) contribute 87 of the corpus's 150 total slots;
drop them and it reads mean 2.6, i.e. Lakeview. Those four sit inside a block of
players the hermetic consensus **cannot tell apart** — `Jack Endries` (d = 33) and
`Michael Trigg` (d = 26) carry the *identical* seeded Elo 1205.107, as do
`Zachariah Branch` (d = 11) and `Malachi Fields` (d = 7) at 1271.860. The trimmed
`player_pool_2026.json` fixture floors a long deep tail at repeated DP values, and
inside such a block the pool order is a `search_rank` tiebreak — so `d` there measures
*which arbitrary tiebreak a human happened to pick*, not how far he reached.

**No bar was loosened, no grid widened, no corpus edited, and the tie artefact was not
engineered out of the observable.** Identifying the thing that fails the gate and then
redefining it is the exact move amendment 2 exists to prevent. It is recorded so the
operator can decide whether the bar is testing the model or the corpus.

---

## Recommendation (for the operator, not decided here)

**A → re-run → B → C. Do not do D.**

| | Option | Why |
|---|---|---|
| **A** | **Re-derive the calibration consensus from a full, live-shaped snapshot** (KTC-blended, untrimmed) and re-run the gate unchanged | Highest value, lowest risk. It attacks the *measured* cause — the floored tie-block — with the model and both bars frozen, so it cannot be accused of tuning. If the corpora then agree, the mixture likely passes outright. |
| **B** | **Add corpora.** `mfl-partial` is already shape-checked and unused; more recorded rookie drafts beyond that | Two corpora cannot distinguish "the bar is wrong" from "one corpus is odd" at n = 28. |
| **C** | **Cut CPU bots; ship practice/replay** (plan O5, tester allowlist) | Needs no noise model — non-user picks come from a recorded corpus. Still the right fallback. |
| **D** | Re-spec the model a third time | **Not recommended.** The evidence no longer points at the model: the shape passes on both corpora and the hold-out passes on both bars. A third form would be fitting the corpus disagreement — precisely what the gate exists to catch. |

---

## What changed

| File | Change |
|---|---|
| `backend/mock_draft_service.py` | `cpu_pick` re-specced to the mixture (`bpa_prob` / `reach_decay` replace `jitter_slots`); new `_gumbel` + `_decay_to_scale`; `MOCK_CANDIDATE_WINDOW = 12` replaces `CANDIDATE_HEADROOM`, and `candidate_window()` now returns a fixed product cap floored by the need cap; `noise_params()` snapshots three keys; `advance_cpu` and `simulate_reaches` thread the new pair; gate comment + `CALIBRATION_ARTIFACT` re-pointed |
| `backend/tests/test_mock_draft.py` | 2-D grid in `_fit_and_validate`; new **T-W2-04b** (4 tests: `bpa_prob` is exactly the board-pick mass · the reach branch is geometric in `reach_decay` · `K` truncates and is not fitted · the branch is persona-independent); `test_w2_16_the_failure_is_structural_not_a_tuning_miss` → `test_w2_16_the_w2a_model_form_could_not_have_passed` (W2a's verdict kept falsifiable after its model was deleted) + new `test_w2_16_the_residual_failure_is_a_corpus_disagreement_not_a_model_form`; the "noise off" idiom is now `bpa_prob=1.0` |
| `docs/plans/draft-extensions/mock-calibration-2026-08b.md` | **the new I-10 gate artifact** |
| `docs/config-reference.md` · `data-dictionary.md` · `architecture.md` · `api-reference.md` · `glossary.md` | per the CLAUDE.md trigger table: the two new `model_config` keys, the `settings.noise` blob shape, the scoring function, the artifact link, and the "`jets` is pure BPA" claim (no longer true of the whole model) |

**Not touched:** any `mobile/` file · `backend/database.py` · every `server.py` route
region (the `cpu_model_unvalidated` short-circuit **stays**, because the gate still
fails) · `_MODEL_CONFIG_DEFAULTS` · every W1/W3 file.

## What was preserved, deliberately

1. **The gate, unchanged.** Same split, same two bars, same α = 0.05, same ±1.0,
   same independent-corpus-no-refit step. It rejected a wrong model twice and it
   is still the thing deciding the verdict.
2. **The both-directions gate test.** `test_w2_16_calibration_gate` still asserts
   `passed is CPU_MODEL_VALIDATED`, so an accidental future pass turns the suite red
   and forces a deliberate re-publish.
3. **The `d_i` definition.** The remaining-pool reading (drift 0.30), not the
   static-rank reading (drift 2.90), still pinned by
   `test_w2_16_the_observable_is_stationary_across_the_split`.
4. **The consensus-basis amendment.** The pool is still
   `draft_board_service._undrafted(basis="consensus")` itself, and the AST check that
   `mock_draft_service` contains **no `sorted`/`.sort` call at all** still passes —
   which is why the reach branch had to be expressible as per-candidate additive
   noise (a log-normal reach would have required re-sorting the pool by a
   need-adjusted key, which the amendment forbids). That constraint is what selected
   Gumbel over the alternatives.
5. **The simulator drives the shipped `cpu_pick`**, so the artifact's numbers and the
   engine's behaviour cannot drift.

## Deviations worth stating

1. **`K` moved from 8 to 12, once, from the fit block only.** Lakeview rounds 1–2 reach
   up to 9 slots, so a window under 10 cannot represent the fit data. Artifact §5 refits
   at `K ∈ {8, 10, 12, 16, 20}`: the hold-out passes at **every** K — including W2a's
   own K = 8, where the entire change is the noise family — and MFL's mean bar fails at
   every K (Δ 2.71–3.63). So the window is not doing the work; 12 is chosen because at
   `K ≤ 10` the fit pins `reach_decay` at the top of its grid (the same degeneracy that
   disqualified W2a's fit) and 12 gives an interior optimum at the lowest W₁.
2. **The reach branch is persona-independent** — see the artifact §1. The product
   consequence is that "a `jets` team is pure BPA" is now true only of the *need* term.
   T-W2-04 was restated to assert what the persona knob actually owns, with the branch
   off, and a new test pins the independence so it cannot be quietly reinterpreted.
3. **`mock_jitter_slots` is gone, replaced by `mock_bpa_prob` + `mock_reach_decay`.**
   No migration is needed: neither key was ever seeded into `_MODEL_CONFIG_DEFAULTS`
   (W2a deviation 4) and the feature has never been on, so no `mock_drafts` row exists
   in the wild carrying the old `noise` blob.
4. **The gate test is slower** — ~38 s, from 110 grid points × 1000 seeded simulations
   (lld §4.2.3 step 2's sim count, kept). The fitted point is identical at 300 sims.

## Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **1850 passed, 1 skipped, exit 0** (baseline 1845/1; +5 new tests) |
| `cd mobile && npx tsc --noEmit` | **clean, exit 0** — untouched, as required (`mobile/node_modules` symlinked from the main checkout for the run and removed after) |
| `test_w2_16_calibration_gate` | green **because it asserts the FAILURE is still real** — `passed is CPU_MODEL_VALIDATED` (`False`) |
| Amendment 1 (no second consensus) | `test_w2_14_the_service_declares_no_second_consensus` (AST, no `sorted`/`.sort`) + `test_w2_15_..._element_for_element` still green |
| Zero platform egress | T-W2-13's three checks still green |
