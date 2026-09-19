# Build status — W2c: re-derived calibration snapshot + re-fit (model and gate FROZEN)

**Date:** 2026-08-06 · **Wave:** draft-extensions W2c · **Status:** snapshot corrected, re-fitted, **gate STILL FAILS — now on two bars of four, and for a different reason**
**Predecessor:** [build-w2b.md](build-w2b.md) (the mixture re-spec) → [build-w2.md](build-w2.md) (W2a)
**Gate artifact (I-10):** [mock-calibration-2026-08c.md](mock-calibration-2026-08c.md) · W2a's and W2b's are kept as history
**Spec:** [plan.md](plan.md) §5 + amendment 2 · [lld.md](lld.md) §4.2.3

---

## Headline

W2b passed three of four bars and named its own residual cause: the calibration
consensus was a **trimmed** snapshot whose deep tail was floored at repeated
DynastyProcess values, so `d` there measured a `search_rank` tiebreak instead of
a human reach. W2c attacked exactly that, with **the model, both bars, α, the
split, the `d_i` definition and the corpora all frozen**.

**What changed — the snapshot only:**

* **Values:** the untrimmed 2026-07-17 DP `values-players.csv` (633/format)
  blended with the 441 matched KeepTradeCut rows through the **shipped**
  `data_loader._apply_consensus_blend`, instead of `player_pool_2026.json`'s
  seeder-side `dp_value_*` columns.
* **Universe:** the whole 2026 prospect class (new fixture
  `rookie_universe_2026.json`, 290 rows) restricted to the players the consensus
  prices — 89 in 1QB / 79 for Lakeview — instead of the 56 that survive a
  UI-seeder's top-N-per-position cut.
* **Ties:** an explicit **average rank over the tied block**, applied
  identically to the observed and the simulated series, instead of letting
  `_undrafted`'s `search_rank`-then-name tiebreak decide. Unvalued picks are
  **excluded and counted** (3 of 48 Lakeview, 1 of 29 MFL).

### The four validation numbers

| Stage | Corpus | n | Bar | W2b | **W2c** | |
|---|---|---|---|---|---|---|
| Fit | `lakeview-complete` r1–2 | 23 | min W₁ | 0.444, interior | **0.323, interior** | ✓ better |
| Hold-out | `lakeview-complete` r3–4 | 22 | KS at α=0.05 | D 0.207, p 0.324 | **D 0.253, p 0.101** | **PASS** |
| Hold-out | " | 22 | \|Δ mean\|d\|\| ≤ 1.0 | Δ 0.222 | **Δ 2.167** (obs 3.886 / sim 1.719) | **FAIL** |
| Independent (no refit) | `mfl-complete` | 28 | KS at α=0.05 | D 0.216, p 0.127 | **D 0.164, p 0.408** | **PASS** |
| Independent (no refit) | " | 28 | \|Δ mean\|d\|\| ≤ 1.0 | Δ 2.935 | **Δ 3.821** (obs 5.536 / sim 1.715) | **FAIL** |

**Fitted parameters: `mock_bpa_prob = 0.20`, `mock_reach_decay = 0.70`** (W2b:
0.50 / 0.95). Not fitted: `mock_max_reach_slots = 3.0`, `MOCK_CANDIDATE_WINDOW = 12`.

**Verdict: FAILED.** `CPU_MODEL_VALIDATED` stays `False`, `draft.mock` stays
OFF, and the create route keeps answering the typed-empty
`200 {"empty": true, "reason": "cpu_model_unvalidated"}`.

### The corpora's own observed means — the number that decides the question

| Block | W2b snapshot | **W2c snapshot** |
|---|---|---|
| Lakeview fit block (r1–2) | 2.348 | **1.870** |
| Lakeview hold-out (r3–4) | 2.650 | **3.886** |
| Lakeview whole draft | 2.488 | **2.856** |
| `mfl-complete` | 5.357 | **5.536** |
| **spread between the two VALIDATION blocks** | **2.707** | **1.649** |

**Yes — the corrected snapshot moved the corpora's own means substantially
closer**, on exactly the comparison the bars make: 2.707 → 1.649 slots. W2b's
central claim (that the two mean bars ask for **disjoint** simulated means, so
no corpus-invariant model can satisfy both) is **dissolved**: the windows now
overlap at [4.536, 4.886], and a point inside the frozen model family and the
frozen grid reaches it (`bpa_prob 0.1, decay 0.99` → simulated mean 4.83).

### So why does it still fail?

The failure moved from *between corpora* to *between the fit block and the
blocks it is validated against*:

```
mean|d|(Lakeview r3–4) − mean|d|(Lakeview r1–2) = 3.886 − 1.870 = 2.017 slots
```

— twice the ±1.0 bar, inside a single corpus, before any model. `d` is a RANK
distance, and the consensus value curve is steep at the top and flat in the
tail, so the same disagreement costs 1–2 slots in round 1 and 20+ in round 4.
Rounds 1–2 are what the procedure fits, so W₁ picks a short tail (`decay 0.70`,
simulated mean 1.72) and both validation blocks are then out of reach.

W2b could not see this because its 50-player universe **ran out of players**:
every Lakeview reach was censored at ≤ 9 slots and the same split measured a
drift of ~0.3. Uncensoring the tail exposed it.

Second, independent finding: **the bar is tighter than the statistic it tests.**
The hold-out estimates its own mean to ±1.33 and `mfl-complete` to ±2.15 (SE),
both worse than the ±1.0 bar, so a perfectly-specified model would fail the
paired-mean bar a large share of the time on sampling noise alone. Drop the
single deepest hold-out pick (29.5) and that block's mean falls to 2.67, which
passes.

---

## Recommendation (for the operator, not decided here)

**A → re-run → B alongside. C only as an explicit product decision. Not D.
Practice/replay is not offered — it has been rejected.**

| | Option | Why |
|---|---|---|
| **A** | **Re-balance the SPLIT for draft depth** (interleaved picks, or rounds sampled from both ends) and re-run the gate | The direct consequence of the diagnosis. The mean bars are now jointly satisfiable and both KS bars pass; the one thing between them is that the fit block is the shallowest two rounds. **This wave did not do it because it is a change to the GATE**, and it must be decided and recorded *before* it is run or it is fitting on the validation set. |
| **B** | **Add corpora** — `mfl-partial` is shape-checked and unused; more recorded rookie drafts | Now a precondition rather than a nice-to-have: with SEs of 1.33 and 2.15, the ±1.0 bar is inside the noise of its own statistic. |
| **C** | **Accept a documented residual** — ship against the KS bar with the mean deviation published | The shape bar passes on two leagues, two platforms and two scoring formats with no refit. Whether that is enough for a mock-draft *opponent* is a product judgement, and an explicit one. |
| **D** | Re-spec the model a third time | **Not recommended, more strongly than in W2b.** Both KS bars pass, the fit improved and stayed interior, and the failure localises to the split. A third form would be fitting the fit/hold-out disagreement. |

---

## What changed

| File | Change |
|---|---|
| `backend/tests/fixtures/rookie_universe_2026.json` | **new fixture** — the 2026 prospect class (290 rows) from the 2026-04-11 Sleeper bulk dump, provenance in its `_comment`. Records **no values**: they come from the already-committed `ktc_blend_pipeline_2026-07-17.json` through the shipped blend |
| `backend/mock_draft_service.py` | `reach_series` → `reach_report` (`{series, skipped, tied}`) + a thin `reach_series`; new `_block_rank` (average rank over a consensus-tied block, no sorting — the AST rule still holds); `simulate_reaches` applies the same rule to the simulated series and now returns floats; the fitted defaults move to 0.20 / 0.70; the gate comment and `CALIBRATION_ARTIFACT` re-point at 08c |
| `backend/tests/test_mock_draft.py` | `_rookie_universe` + `_blended_values` (the shipped `_apply_consensus_blend` on the committed live snapshot, blend weight pinned) replace the `dp_value_*` columns in `_rookie_ctx`; `_fit_and_validate` reports pool sizes, `skipped` and `tied`; `test_w2_16_the_residual_failure_is_a_corpus_disagreement_not_a_model_form` → **`test_w2_16_the_mean_bars_became_jointly_satisfiable_under_the_corrected_snapshot`** (W2b's claim, now falsified, replaced by the finding that replaces it); `test_w2_16_the_observable_is_stationary_across_the_split` → **`test_w2_16_the_observable_drifts_with_draft_depth`** (the same measurement, now pinning a failure); new **`test_w2_16_the_mean_bar_is_tighter_than_the_statistic_it_tests`**; `test_w2_16_the_w2a_model_form_could_not_have_passed`'s fraction re-derived (see deviations) |
| `docs/plans/draft-extensions/mock-calibration-2026-08c.md` | **the new I-10 gate artifact** |
| `docs/config-reference.md` · `architecture.md` · `glossary.md` · `api-reference.md` | per the CLAUDE.md trigger table: the two `model_config` defaults, and the four places that named the W2b artifact and its verdict |

**Not touched:** any `mobile/` file · `backend/database.py` · every `server.py`
route region (the `cpu_model_unvalidated` short-circuit **stays**, because the
gate still fails) · `_MODEL_CONFIG_DEFAULTS` · every W1/W3 file · the corpora
themselves.

## What was preserved, deliberately

1. **The gate, unchanged.** Same split (Lakeview r1–2 fit → r3–4 hold-out),
   same two bars, same α = 0.05, same ±1.0, same independent-corpus-no-refit
   step, same remaining-pool `d_i`. Only the snapshot `d` is measured against
   moved.
2. **The model, unchanged.** The W2b mixture ships byte-for-byte; only its two
   fitted values moved, which the brief expects of a re-fit.
3. **The both-directions gate test.** `test_w2_16_calibration_gate` still
   asserts `passed is CPU_MODEL_VALIDATED`, so an accidental future pass turns
   the suite red and forces a deliberate re-publish.
4. **Amendment 1.** The pool is still `draft_board_service._undrafted(basis="consensus")`
   itself, and the AST check that `mock_draft_service` contains **no
   `sorted`/`.sort` call at all** still passes — `_block_rank` scans neighbours
   in an already-ordered list rather than ordering anything.
5. **The simulator drives the shipped `cpu_pick`**, and now the calibration
   consensus is built by the shipped `_apply_consensus_blend` too, so neither
   the artifact's numbers nor its value curve can drift from the product's.

## Deviations worth stating

1. **`test_w2_16_the_w2a_model_form_could_not_have_passed`'s threshold was
   re-derived, 0.15 → 0.05.** The corrected consensus moves several mid-round
   picks up the board, so the share of picks beyond W2a's hard support bound
   reads 11 % (5 of 45) instead of 15 %+. The structural argument is unchanged
   and does not turn on the fraction — a model that assigns probability
   *exactly zero* to 1 pick in 9 is not the data-generating one — and the test's
   own docstring anticipated re-derivation. **No gate bar was touched.**
2. **The 56-row universe scores better and was not chosen.** With W2c's values
   but W2b's universe the verdict is 3 of 4 (hold-out Δ 0.799 PASS) rather than
   2 of 4. Choosing a universe by its effect on the verdict is the move
   amendment 2 exists to prevent; the row is published in artifact §7 so the
   sensitivity is visible rather than hidden.
3. **Pricing `mfl-complete` as `sf_tep` was tested and rejected.** Three of its
   four deepest picks are TEs, so a TE-premium format was a live hypothesis; it
   moves that corpus's observed mean the wrong way (5.54 → 5.93). Recorded in
   artifact §3 so it is not re-run hopefully.
4. **The fit is flatter than W2b's around its optimum.** At 300 sims/point the
   grid minimum sits at (0.40, 0.80) rather than (0.20, 0.70); every verdict
   number is at the shipped 1000 sims. Stated in artifact §4.2.
5. **The new fixture depends on a gitignored local artifact to *record*, not to
   *run*.** `rookie_universe_2026.json` was cut from `data/.sleeper_players_cache.json`
   the same way `player_pool_2026.json` was; the committed fixture is
   self-contained and the test suite reads no live source.

## Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | see the wave's final run — baseline 1866 passed / 1 skipped |
| `cd mobile && npx tsc --noEmit` | clean — `mobile/` untouched, as required |
| `test_w2_16_calibration_gate` | green **because it asserts the FAILURE is still real** — `passed is CPU_MODEL_VALIDATED` (`False`) |
| Amendment 1 (no second consensus) | `test_w2_14_the_service_declares_no_second_consensus` (AST, no `sorted`/`.sort`) + `test_w2_15_..._element_for_element` still green |
| Zero platform egress | T-W2-13's three checks still green |
