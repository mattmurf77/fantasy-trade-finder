# Mock-draft CPU noise model — calibration report, corrected snapshot (interface I-10)

**Date:** 2026-08-06 · **Wave:** draft-extensions **W2c** (re-derived consensus snapshot + re-fit)
**Supersedes:** [mock-calibration-2026-08b.md](mock-calibration-2026-08b.md) (W2b, the mixture against the *trimmed* snapshot) and [mock-calibration-2026-08.md](mock-calibration-2026-08.md) (W2a) — both kept as history
**Normative:** [plan.md](plan.md) §5 (amendment 2 + the W2 abort criterion) · [lld.md](lld.md) §4.2.3
**Reproduced by:** `python3 -m pytest backend/tests/test_mock_draft.py -k w2_16`
**Harness:** `backend/mock_draft_service.reach_report` / `simulate_reaches` (the simulator drives the **shipped** `cpu_pick`) + the statistics in `backend/tests/test_mock_draft.py`.

> **This document is a GATE, not a report.** `mock_draft_service.CPU_MODEL_VALIDATED`
> mirrors the verdict below, and `test_w2_16_calibration_gate` fails if the two
> ever disagree — in either direction.

---

## VERDICT: **FAILED** — the W2 abort criterion stays fired

**The model and the gate were FROZEN.** Same two-parameter mixture, same two
bars, same α = 0.05, same ±1.0, same fit/hold-out split, same corpora, same
remaining-pool `d_i`. The only thing W2c changed is the thing W2b's §6 named as
the measured cause: **the consensus snapshot the observable is measured
against.** The two parameters were re-fitted on the corrected snapshot, as the
brief expects; nothing else moved.

| Stage | Corpus | n | Bar | Result | |
|---|---|---|---|---|---|
| Fit | `lakeview-complete` r1–2 | 23 | min W₁ over the 110-point grid | `bpa_prob` **0.20**, `reach_decay` **0.70** — **interior in both**, W₁ **0.323** (worst 3.475) | ✓ well-posed |
| Hold-out | `lakeview-complete` r3–4 | 22 | KS not rejected at α = 0.05 | D = **0.253**, p = **0.101** | **PASS** |
| Hold-out | " | 22 | \|Δ mean\|d\|\| ≤ 1.0 | observed **3.886** vs simulated **1.719** ⇒ Δ = **2.167** | **FAIL** |
| Independent (no refit) | `mfl-complete` | 28 | KS at α = 0.05 | D = **0.164**, p = **0.408** | **PASS** |
| Independent (no refit) | " | 28 | \|Δ mean\|d\|\| ≤ 1.0 | observed **5.536** vs simulated **1.715** ⇒ Δ = **3.821** | **FAIL** |

`CPU_MODEL_VALIDATED` stays `False`, `draft.mock` stays OFF, and
`POST /api/mock-draft` still answers the typed-empty
`200 {"empty": true, "reason": "cpu_model_unvalidated"}`.

**Both KS bars pass — the second one more comfortably than in W2b (p 0.127 →
0.408) — and the fit is better and still interior (W₁ 0.444 → 0.323). Both
paired-mean bars fail.** W2b failed one bar of four; W2c fails two, and for a
*different, sharper* reason. §6 derives it and §7 says what it means.

---

## 1. What actually changed — the snapshot, and nothing else

| | W2b | **W2c** |
|---|---|---|
| Values | `player_pool_2026.json`'s `dp_value_1qb` / `dp_value_2qb` columns — a 2026-07-10 DP scrape, seeder-side, with a **floored deep tail** (4 rookies at 7.0, 3 at 17.0 in 1QB) | the **untrimmed 2026-07-17 DynastyProcess `values-players.csv`** (633 players/format) **blended with the 441 matched KeepTradeCut rows** through the **shipped** `data_loader._apply_consensus_blend` at the shipped default weight |
| Universe | the 56 prospects that survive `player_pool_2026.json`'s cut — **top-N per position across ALL players by `value_1qb`** (QB 55 / RB 100 / WR 120 / TE 65), a UI-seeder rule that no product path ever applies to a rookie board | the **whole 2026 prospect class** (`rookie_universe_2026.json`, 290 rows) restricted to the players the consensus **prices** — 89 in 1QB, 79 after Lakeview's pre-rostered subtraction |
| Ties | broken by `_undrafted`'s `search_rank`-then-name tiebreak, i.e. by insertion order | **average rank over the tied block**, applied identically to the observed and the simulated series (`mock_draft_service._block_rank`) |
| Model | mixture, `bpa_prob` + Gumbel reach | **identical** |
| Gate | split, both bars, α, ±1.0, `d_i`, corpora | **identical** |

**Provenance of the new fixture.** `backend/tests/fixtures/rookie_universe_2026.json`
is every QB/RB/WR/TE row with `years_exp == 0` in `data/.sleeper_players_cache.json`
— the Sleeper `players/nfl` bulk dump of 2026-04-11, *the same dump
`player_pool_2026.json` was cut from* — trimmed to the four fields the consensus
ordering reads (`full_name`, `position`, `team`, `search_rank`). It records **no
values**: those come from the already-committed
`ktc_blend_pipeline_2026-07-17.json` through the shipped blend, so the
calibration consensus and the product's consensus cannot drift apart. The name
join is `normalise_name(full_name) in values`, which is
`server.build_universal_pool`'s join verbatim.

**Why this is a correction and not a tuning.** The 56-row cut is an artifact of
a UI-test seeder: a rookie is in it only if he out-values enough *veterans* at
his position. Nothing in the product ranks a rookie board that way —
`load_rookie_player_ids(season)` returns the class, and `_undrafted` prices it
with `_get_universal_pool`'s seed. W2c replaces a seeder rule with the product
rule and a stale trimmed scrape with the live blended one. The model, the bars
and the corpora were untouchable throughout, which is what makes the resulting
numbers admissible.

## 2. The observable — unchanged, plus an explicit tie rule

`d_i` = how many better-valued **available** players the pick passed over: the
player's 1-based consensus rank in the pool *as it stood at that pick*, minus 1.
`d_i > 0` is a reach; `d_i == 0` is best-player-available. This is W2a's
remaining-pool reading, carried over verbatim for the third time.

Two things are now **explicit** rather than left to insertion order:

1. **Ties → the average rank of the tied block** (`_block_rank`). Inside a block
   of equal-valued players the shipped `_undrafted` tiebreak (`search_rank`,
   then name) decides who is "first", which is not an opinion the consensus
   holds; charging a drafter the full depth of a block he could not have been
   told apart measures the tiebreak. Averaging is symmetric, applied to the
   **observed and the simulated series alike**, discards nothing, and is a no-op
   the moment values separate. Under the corrected snapshot it moves the means
   by < 0.1 slots — **3 of 45 Lakeview picks and 2 of 28 MFL picks land inside a
   tied block, down from a 4-wide floor block in W2b.** The exclusion-based
   alternative the brief also allowed was not chosen: it would have dropped
   real picks to fix an artifact that the corrected values had already mostly
   removed.
2. **Picks the consensus cannot price are excluded and COUNTED.** A prospect
   with no blended value has no opinion to reach past — his rank inside the
   unvalued block is alphabetical. `reach_report` returns `skipped`:
   **3 of 48 Lakeview picks** (`Ted Hurst`, whose DP row is `ted hurst iii` and
   so misses the shipped name join, plus the veterans `Jake Tonges` and
   `Rashod Bateman`, who are not rookies at all) and **1 of 29 MFL picks**
   (`Ted Hurst` again). W2b's snapshot excluded 5 and 1.

## 3. Corpora — unchanged

Shape is still checked **before** use (T-W2-17). `lakeview-complete` is a 4×12
rookie draft (45 of 48 picks retained, up from 43); `mfl-complete` is a 3-round
single-unit rookie draft (28 of 29 retained); `mfl-multi-unit` is still excluded
because it is a two-unit conference-split draft. Formats are unchanged —
Lakeview `sf_tep`, MFL `1qb_ppr`. (Pricing MFL as `sf_tep` was *tested as a
hypothesis* — three of its four deepest picks are TEs — and **rejected**: it
moves MFL's observed mean the wrong way, 5.54 → 5.93. It is recorded here so
nobody re-runs it hoping.)

Observed distributions under the corrected snapshot:

| `d` | 0 | 0.5 | 1 | 2 | 3 | 3.5 | 4 | 5 | 6 | 7 | 8 | 10 | 13 | 15 | 29.5 | 33.5 | 51.5 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `lakeview-complete` (n=45) | 15 | 1 | 6 | 8 | 1 | 1 | 4 | 2 | 2 | 2 | 1 | 1 | — | — | 1 | — | — |
| `mfl-complete` (n=28) | 11 | — | 4 | 1 | 3 | — | 1 | 2 | 1 | 1 | — | — | 1 | 1 | — | 1 | 1 |

## 4. The procedure and its numbers

### 4.1 Split — unchanged

Fit on Lakeview rounds 1–2 (picks 1–24 → **23** retained); validate on rounds
3–4 (picks 25–48 → **22** retained). The hold-out block is never fitted. Then
`mfl-complete` (**28**) with **no refit**.

### 4.2 Fit — the same 2-D grid, 1000 seeded simulations per point

Same natural-domain grids as W2b (`bpa_prob` ∈ {0.00 … 0.90}, `reach_decay` ∈
{0.1 … 0.9, 0.95, 0.99}), same 110 points, same objective: the 1-D Wasserstein
distance W₁ between the simulated and the observed `|d|` on the fit block.

**Fitted: `mock_bpa_prob = 0.20`, `mock_reach_decay = 0.70`. W₁ = 0.323.**

| `reach_decay` at `bpa_prob = 0.20` | 0.1 | 0.3 | 0.5 | 0.6 | **0.7** | 0.8 | 0.9 | 0.95 | 0.99 |
|---|---|---|---|---|---|---|---|---|---|
| W₁ | 1.776 | 1.524 | 1.071 | 0.720 | **0.323** | 0.626 | 1.513 | 1.994 | 2.369 |

| `bpa_prob` at `reach_decay = 0.70` | 0.0 | 0.1 | **0.2** | 0.3 | 0.4 | 0.5 | 0.7 | 0.9 |
|---|---|---|---|---|---|---|---|---|
| W₁ | 0.508 | 0.383 | **0.323** | 0.460 | 0.638 | 0.842 | 1.254 | 1.654 |

Interior in both parameters, and a better fit than W2b's on the same objective
(0.323 vs 0.444) with more leverage across the grid (10.8× spread, vs 6.7×).
**One honest caveat:** at 300 sims/point the optimum moves to (0.40, 0.80), so
the objective is flatter than W2b's around its minimum; every number in the
verdict table is at the shipped 1000.

### 4.3 Hold-out validation (Lakeview rounds 3–4, n = 22)

| Bar | Threshold | Result | |
|---|---|---|---|
| Two-sample KS | not rejected at α = 0.05 | D = **0.253**, p = **0.101** | **not rejected — PASS** |
| Paired mean | \|Δ mean\|d\|\| ≤ 1.0 | observed **3.886** vs simulated **1.719** ⇒ Δ = **2.167** | **FAIL** |

### 4.4 Independent validation — `mfl-complete`, NO refit (n = 28)

| Bar | Threshold | Result | |
|---|---|---|---|
| Two-sample KS | not rejected at α = 0.05 | D = **0.164**, p = **0.408** | **not rejected — PASS** |
| Paired mean | ≤ 1.0 | observed **5.536** vs simulated **1.715** ⇒ Δ = **3.821** | **FAIL** |

A second league, a different platform, a different scoring format, no refit —
and the *shape* survives more comfortably than it did in W2b.

## 5. The corpora's own observed means, before and after

This is the number that decides whether the W2b disagreement was an artifact.

| Block | n (W2b → W2c) | W2b snapshot | **W2c snapshot** | move |
|---|---|---|---|---|
| `lakeview-complete` fit block (r1–2) | 23 → 23 | 2.348 | **1.870** | −0.478 |
| `lakeview-complete` hold-out (r3–4) | 20 → 22 | 2.650 | **3.886** | +1.236 |
| `lakeview-complete` whole draft | 43 → 45 | 2.488 | **2.856** | +0.368 |
| `mfl-complete` | 28 → 28 | 5.357 | **5.536** | +0.179 |
| **spread — the two VALIDATION blocks** (`mfl` − Lakeview hold-out) | | **2.707** | **1.649** | **−1.058** |
| spread — whole-corpus means | | 2.869 | 2.680 | −0.189 |

**The corrected snapshot moved the two corpora's means substantially closer on
the comparison the bars actually make: 2.707 → 1.649 slots.** That is the
decisive change, and it is why the verdict's *reason* has changed even though
its value has not.

## 6. Why it still fails — the diagnosis moved, and it is no longer W2b's

**W2b's argument is dissolved.** W2b said the mean bars were *jointly
unsatisfiable*: with the blocks 2.707 apart, passing Lakeview's needed a
simulated mean in [1.65, 3.65] and passing MFL's needed [4.36, 6.36] —
disjoint. At 1.649 apart the windows **overlap**: any corpus-invariant model
whose simulated mean lands in **[4.536, 4.886]** satisfies both. Such a point
exists inside the frozen model family and inside the frozen grid — e.g.
`bpa_prob = 0.1, reach_decay = 0.99` simulates a mean of **4.83** on the same
replay. Pinned by
`test_w2_16_the_mean_bars_became_jointly_satisfiable_under_the_corrected_snapshot`.

**What fails instead: the FIT BLOCK disagrees with the blocks it is validated
against.** Under the corrected snapshot the observable drifts

```
mean|d|(Lakeview r3–4) − mean|d|(Lakeview r1–2) = 3.886 − 1.870 = 2.017 slots
```

— twice the ±1.0 bar, *inside a single corpus*, before any model is involved.
The procedure fits on rounds 1–2 (mean 1.870), so W₁ selects a short-tailed
`decay = 0.70`, which simulates 1.72 — and then both validation blocks, at
3.886 and 5.536, are out of reach. The model is not wrong about the shape (both
KS bars pass); it is calibrated to the shallowest two rounds of the only corpus
the split lets it see.

**Why the observable drifts with depth, structurally.** `d` is a *rank*
distance, not a value distance. The consensus value curve is steep at the top
and almost flat in the tail, so an identical disagreement — "I like this guy a
bit more than the market" — costs 1–2 slots in round 1 and 20+ slots in round
4, where dozens of prospects sit within a couple of DP points of each other.
Rounds 1–2 sit on the steep part. **W2b could not see this**: its 50-player
universe ran out of players before round 4 could express a deep reach, so every
Lakeview reach was censored at ≤ 9 slots and the same split measured a drift of
only ~0.3. Uncensoring the tail is what exposed it. Pinned by
`test_w2_16_the_observable_drifts_with_draft_depth`, which also keeps W2a's
comparison alive: the rejected static-rank reading of `d_i` drifts harder still
(3.56).

**And the bar is tighter than the statistic it tests.** `|d|` under the
corrected snapshot is heavy-tailed, so at these n the mean is barely estimable:

| Block | n | mean | sd | **SE of the mean** | median | max |
|---|---|---|---|---|---|---|
| Lakeview fit r1–2 | 23 | 1.870 | 2.546 | 0.531 | 1.0 | 8.0 |
| Lakeview hold-out r3–4 | 22 | 3.886 | 6.258 | **1.334** | 2.0 | 29.5 |
| `mfl-complete` | 28 | 5.536 | 11.380 | **2.151** | 1.0 | 51.5 |

**Both validation blocks estimate their own mean to worse than ±1.0**, so even
a perfectly-specified model would fail the paired-mean bar a large share of the
time on sampling noise alone — one pick moves it: drop the single 29.5 from the
hold-out and its mean falls to 2.67, which *passes*. Pinned by
`test_w2_16_the_mean_bar_is_tighter_than_the_statistic_it_tests`. This is
evidence for the operator, **not** an argument for widening the bar; no bar was
widened.

## 7. Robustness — the verdict does not hinge on the snapshot choices

Refitting from scratch under each variant (300 sims/point for tractability, so
read the columns comparatively, not against §4's absolutes):

| Variant | fitted | W₁ | hold KS p | hold Δ | hold | `mfl` KS p | `mfl` Δ | `mfl` |
|---|---|---|---|---|---|---|---|---|
| **shipped** — complete valued class, KTC-blended | (0.40, 0.80) | 0.342 | 0.031 | 2.071 | FAIL | 0.532 | 3.716 | FAIL |
| complete valued class, **blend OFF** (DP-only) | (0.50, 0.95) | 0.513 | 0.048 | 1.657 | FAIL | 0.145 | 3.483 | FAIL |
| **W2b's 56-row cut**, live blended values | (0.40, 0.80) | 0.342 | 0.075 | **0.799** | **PASS** | 0.532 | 2.984 | FAIL |
| *(W2b, for reference: 56-row cut, trimmed values, 1000 sims)* | (0.50, 0.95) | 0.444 | 0.324 | 0.222 | PASS | 0.127 | 2.935 | FAIL |

Three conclusions:

1. **No variant passes.** The verdict is FAILED under every snapshot tried.
2. **The KTC blend is a genuine improvement, not decoration** — it lowers the
   fit W₁ (0.513 → 0.342) and raises both KS p-values. The live-shaped
   consensus is the better consensus even though it does not rescue the gate.
3. **The 56-row cut looks better on the verdict (3 of 4 rather than 2 of 4) and
   was still NOT chosen.** Picking a universe by its effect on the verdict is
   exactly the move amendment 2 exists to prevent. It is the seeder's rule, not
   the product's, and it is the one that censors the tail; the row is published
   so the operator can see the sensitivity rather than have it hidden.

## 8. Consequences and options (plan §5's abort criterion, applied)

**Applied now:**

1. **The CPU-bot mock stays CUT.** `CPU_MODEL_VALIDATED = False`;
   `advance_cpu` raises `CalibrationGateClosed` unless a caller explicitly opts
   in (the harness and the engine tests do; the routes never do).
2. **`draft.mock` stays OFF**, and with the flag ON `POST /api/mock-draft`
   still returns `200 {"empty": true, "reason": "cpu_model_unvalidated"}`.
3. **The corrected snapshot ships anyway**, as W2a's and W2b's models did, so
   the verdict is reproducible and the next attempt starts from the better
   consensus rather than the trimmed one.

**For the operator to choose between — none of these is decided here:**

| Option | What it costs | What it would settle |
|---|---|---|
| **A. Re-balance the SPLIT for draft depth** — fit and hold out on interleaved picks (e.g. odd/even) or on whole rounds sampled from both ends, instead of r1–2 vs r3–4 | one gate re-run; **it is a change to the GATE, which is why this wave did not make it** | This is now the highest-value next step and the direct consequence of §6: the mean bars are jointly satisfiable, the shape passes on both corpora, and the only thing standing between the two is that the fit block is the shallowest 2 rounds of the corpus. A depth-balanced split tests the model instead of the depth profile. It must be decided *before* it is run, and recorded, or it is fitting on the validation set. |
| **B. Add corpora.** `mfl-partial` is already shape-checked and unused; more recorded rookie drafts beyond that | corpus collection | §6's SE table makes this a precondition, not a nice-to-have: at n = 22 and n = 28 with this tail, the ±1.0 bar is inside the noise of its own statistic. More corpora shrink the SE *and* let a between-league spread be distinguished from an n = 28 accident. |
| **C. Accept a documented residual** — ship bots against the KS bar alone, with the paired-mean result published as a known, quantified deviation | a deliberate, recorded lowering of the ship bar — **not** a quiet one | The shape bar passes on both corpora, on two platforms and two scoring formats, with no refit. Whether "the depth distribution is right but the mean depth is off" is shippable for a *mock draft opponent* is a product judgement, and it is the operator's, not this wave's. If taken, it should be taken explicitly in the plan, not by editing this artifact. |
| **D. Re-spec the model a third time** | another wave | **Not recommended, and now less so than in W2b.** Both KS bars pass, the fit is interior with a better W₁ than W2b's, and §6 locates the failure in the split rather than the family. A third form would be fitting the fit-block/hold-out disagreement. |

**Practice/replay (W2b's option C) is deliberately absent — the operator has
rejected it.**

**Recommended order: A, then re-run the gate; B alongside it if more corpora
can be recorded; C only as an explicit product decision. Do not do D.**

---

*Prepared under [build-w2c.md](build-w2c.md). The engine, the harness and every
number above are reproducible with
`python3 -m pytest backend/tests/test_mock_draft.py -k w2_16`.*
