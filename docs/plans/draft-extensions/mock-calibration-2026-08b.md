# Mock-draft CPU noise model — calibration report, re-spec #2 (interface I-10)

**Date:** 2026-08-06 · **Wave:** draft-extensions **W2b** (mixture re-spec + re-fit)
**Supersedes:** [mock-calibration-2026-08.md](mock-calibration-2026-08.md) (W2a, the single-parameter model — kept as history)
**Normative:** [plan.md](plan.md) §5 (amendment 2 + the W2 abort criterion) · [lld.md](lld.md) §4.2.3
**Reproduced by:** `python3 -m pytest backend/tests/test_mock_draft.py -k w2_16`
**Harness:** `backend/mock_draft_service.reach_series` / `simulate_reaches` (the simulator drives the **shipped** `cpu_pick`) + the statistics in `backend/tests/test_mock_draft.py`.

> **This document is a GATE, not a report.** `mock_draft_service.CPU_MODEL_VALIDATED`
> mirrors the verdict below, and `test_w2_16_calibration_gate` fails if the two
> ever disagree — in either direction.

---

## VERDICT: **FAILED** — the W2 abort criterion stays fired

The re-specced **two-parameter mixture** passes **three of the four bars**: both
bars on the Lakeview hold-out, and the KS bar on the independent `mfl-complete`
corpus with no refit. It fails `mfl-complete`'s **paired-mean** bar by 2.94
slots.

| Stage | Corpus | n | Bar | Result | |
|---|---|---|---|---|---|
| Fit | `lakeview-complete` r1–2 | 23 | min W₁ over the 110-point grid | `bpa_prob` **0.50**, `reach_decay` **0.95** — **interior in both parameters**, W₁ 0.444 (worst point 2.997) | ✓ well-posed |
| Hold-out | `lakeview-complete` r3–4 | 20 | KS not rejected at α = 0.05 | D = **0.207**, p = **0.324** | **PASS** |
| Hold-out | " | 20 | \|Δ mean\|d\|\| ≤ 1.0 | observed **2.650** vs simulated **2.428** ⇒ Δ = **0.222** | **PASS** |
| Independent (no refit) | `mfl-complete` | 28 | KS at α = 0.05 | D = **0.216**, p = **0.127** | **PASS** |
| Independent (no refit) | " | 28 | \|Δ mean\|d\|\| ≤ 1.0 | observed **5.357** vs simulated **2.422** ⇒ Δ = **2.935** | **FAIL** |

Both bars must hold on both corpora, so the verdict is FAILED:
`CPU_MODEL_VALIDATED` stays `False`, `draft.mock` stays OFF, and
`POST /api/mock-draft` still answers the typed-empty
`200 {"empty": true, "reason": "cpu_model_unvalidated"}`.

**The residual is not the same kind of failure as W2a's.** W2a failed because
the model *could not express the data* at any parameter value. W2b fails
because the two corpora **disagree with each other** by 2.71 slots in the
observable itself — 2.7× the ±1.0 bar — so no corpus-invariant noise model can
land inside ±1.0 of both. §6 derives that and quantifies what drives it.
Read §6 and §7 before either re-specing again or cutting.

---

## 1. The model under test (the W2b re-spec)

```
score(c)  = rank(c) − need_bonus(t, pos(c)) − reach_noise(c)
pick      = argmin score                        (ties → better consensus rank)
need_bonus= need_weight(t) × severity(t, pos) × MOCK_MAX_REACH     (unchanged)

reach_noise(c) = 0                        with probability  MOCK_BPA_PROB   ← fitted
               = Gumbel(0, β) i.i.d.      otherwise
β              = −1 / ln(MOCK_REACH_DECAY)                                  ← fitted
```

**Why a mixture.** W2a's artifact §7 recorded what the evidence demanded and
this is it: the Lakeview corpus is 44 % *exactly* best-available yet puts 21 %
of picks 6–9 slots deep. That is a point mass plus a heavy tail — a mixture —
and a single additive uniform term is the wrong family for it (W2a §5).

**Why Gumbel, over log-normal or negative-binomial.** Structural, not fit
convenience. By the Gumbel-max identity, an argmin over `rank − G` with
`G ~ Gumbel(0, β)` is *exactly* a softmax over `−rank`, so the reach depth is
**geometric** with per-slot survival ratio `exp(−1/β) = reach_decay`:

```
P(reach = d)  ∝  reach_decay ᵈ ,      d = 0 … K−1
```

That buys three things at once. It is the heavy-tailed discrete law the
evidence asks for; it keeps the **shipped per-candidate additive-noise code
shape**, so the need term stays in the same rank-slot units and no second
ordering of the pool is introduced (amendment 1 — the module still contains no
`sorted`/`.sort` call at all, pinned by `test_w2_14_...`); and it makes the
fitted parameter *interpretable to an operator* — "reaching one slot further is
95 % as likely" — rather than a nuisance scale. A log-normal reach would have
needed the pool re-sorted by a need-adjusted key to apply, which amendment 1
forbids. The geometric law is verified rather than asserted, by
`test_w2_04b_the_reach_branch_is_geometric_in_reach_decay`.

**The two fitted parameters** are `mock_bpa_prob` and `mock_reach_decay`.
**Not fitted:** `mock_max_reach_slots` (3.0 — a product cap on the *need*
reach, unchanged from W2a) and the candidate window `K`.

**`K` is out of the fit, by construction.** W2a treated `K = ceil(max_reach)+5
= 8` as a side-effect of the need cap. W2b makes it an explicit product cap,
`MOCK_CANDIDATE_WINDOW = 12`, chosen once **from the fit block alone**
(Lakeview rounds 1–2 reach at most 9 slots, so a window under 10 could not
represent the fit data at all) and never re-touched. The geometric tail is
truncated **by** it, never fitted **to** it. §5 shows the verdict is invariant
to K across `8 … 20`, including at W2a's own K = 8 — so the window is not
doing the work.

**Persona.** The need term is persona-scaled exactly as before; the *reach*
branch is deliberately persona-**independent**, because neither corpus carries
persona labels and there is no evidence to condition it on. Stated in code and
pinned by `test_w2_04b_the_reach_branch_is_persona_independent`, so nobody
later reads persona-scaled idiosyncrasy into a model that never had it. The
product consequence, stated plainly: under the mixture a `jets` bot is a pure
best-player-available drafter *with respect to need*, but every bot occasionally
reaches. The old prose "a `jets` team is pure BPA" is no longer true of the
whole model.

## 2. The observable — unchanged from W2a

`d_i` = **how many better-valued *available* players the pick passed over**:
the player's 1-based consensus rank in the pool *as it stood at that pick*,
minus 1. `d_i > 0` is a reach; `d_i == 0` is best-player-available.

This is W2a's adopted remaining-pool reading, carried over **verbatim and
deliberately** — the whole point of holding it fixed is that W2b's numbers are
comparable to W2a's on the same scale. The rejected alternative (a rank frozen
over the pre-draft pool, minus the pick index) drifts 2.90 slots across the
fit/hold-out split, which exceeds the ±1.0 bar before any model is involved;
the adopted reading drifts 0.30. Both facts are still pinned by
`test_w2_16_the_observable_is_stationary_across_the_split`.

Consequence, restated: `d ≥ 0` always, so a "fall" is not expressible and
`|d| = d`.

## 3. Corpora — unchanged from W2a

Shape is checked **before** use (T-W2-17). `lakeview-complete` is a 4×12 rookie
draft, 43 of 48 picks retained; `mfl-complete` is a 3-round single-unit rookie
draft, 28 of 30 retained; `mfl-multi-unit` is excluded because it is a two-unit
conference-split draft, so "the pool as it stood at that pick" is undefined
across units (**not** because it is startup-shaped, which the LLD claims and
the shipped discriminator refutes). The hermetic-consensus limitation — the
trimmed committed `player_pool_2026.json` snapshot, no live KTC blend, a rookie
universe of 50 (Lakeview, `sf_tep`) and 56 (MFL, `1qb_ppr`) — is unchanged and
is re-examined in §6, where it turns out to matter.

Observed distributions, for reference:

| `d` | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 11 | 17 | 26 | 33 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `lakeview-complete` (n=43) | 19 | 4 | 5 | 4 | — | 2 | 1 | 2 | 3 | 3 | — | — | — | — |
| `mfl-complete` (n=28) | 10 | 1 | 4 | 1 | 1 | 3 | — | 1 | 2 | 1 | 1 | 1 | 1 | 1 |

Mean |d|: Lakeview fit block **2.348**, Lakeview hold-out **2.650**,
`mfl-complete` **5.357**.

## 4. The procedure and its numbers

### 4.1 Split — unchanged

Fit on Lakeview rounds 1–2 (picks 1–24 → **23** retained); validate on rounds
3–4 (picks 25–48 → **20** retained). The hold-out block is never fitted.
Then `mfl-complete` (**28**) with **no refit**.

### 4.2 Fit — 2-D grid search, 1000 seeded simulations per point

Each parameter is gridded over its **natural domain**, not a hand-picked
interval — which is what makes "the optimum is interior" mean anything:

* `mock_bpa_prob` ∈ `{0.00, 0.10, … 0.90}` (a probability)
* `mock_reach_decay` ∈ `{0.1 … 0.9 step 0.1, 0.95, 0.99}` (a survival ratio in
  (0,1); the interesting region of a geometric ratio compresses against 1, so
  the last two points are appended)

110 points × 1000 seeded simulations of the fit block, minimising the 1-D
Wasserstein distance W₁ between simulated and observed `|d|`.

**Fitted: `mock_bpa_prob = 0.50`, `mock_reach_decay = 0.95`. W₁ = 0.444.**

The two 1-D slices through the optimum, which are what W2a's fit failed to
produce:

| `reach_decay` at `bpa_prob = 0.50` | 0.1 | 0.3 | 0.5 | 0.7 | 0.8 | 0.9 | **0.95** | 0.99 |
|---|---|---|---|---|---|---|---|---|
| W₁ | 2.289 | 2.132 | 1.850 | 1.292 | 0.870 | 0.491 | **0.444** | 0.506 |

| `bpa_prob` at `reach_decay = 0.95` | 0.0 | 0.1 | 0.2 | 0.3 | 0.4 | **0.5** | 0.6 | 0.7 | 0.8 | 0.9 |
|---|---|---|---|---|---|---|---|---|---|---|
| W₁ | 2.528 | 2.014 | 1.532 | 1.105 | 0.701 | **0.444** | 0.579 | 1.006 | 1.446 | 1.895 |

Three things W2a's fit could not say, and this one can:

1. **The optimum is interior in both parameters** — it turns over on both sides
   in both directions. W2a's pinned at the top of its grid.
2. **The objective has leverage:** W₁ ranges 0.444 → 2.997 across the grid, a
   6.7× spread. W2a's moved 2.348 → 2.059 across a 12× parameter change.
3. **It is a 4.6× better fit on the same objective, the same fit block and the
   same observable** — 0.444 against W2a's best of 2.059.

### 4.3 Hold-out validation (Lakeview rounds 3–4, n = 20) — **BOTH BARS PASS**

| Bar | Threshold | Result | |
|---|---|---|---|
| Two-sample KS | not rejected at α = 0.05 | D = **0.207**, p = **0.324** | **not rejected — PASS** |
| Paired mean | \|Δ mean\|d\|\| ≤ 1.0 | observed **2.650** vs simulated **2.428** ⇒ Δ = **0.222** | **PASS** |

*The paired mean bar is still not redundant with KS.* KS at n = 20 is
underpowered — a model can survive it on sample size alone — which is exactly
why the mean bar exists and exactly why it is the bar that decides the verdict
below. Never drop it as duplicative.

### 4.4 Independent validation — `mfl-complete`, NO refit (n = 28) — **ONE BAR FAILS**

| Bar | Threshold | Result | |
|---|---|---|---|
| Two-sample KS | not rejected at α = 0.05 | D = **0.216**, p = **0.127** | **not rejected — PASS** |
| Paired mean | ≤ 1.0 | observed **5.357** vs simulated **2.422** ⇒ Δ = **2.935** | **FAIL** |

A second league, a different platform, a different scoring format, no refit —
and the *shape* now survives (W2a was rejected here at p = 9.4 × 10⁻⁹). Only
the mean is off, and §6 is about why.

## 5. Robustness — the verdict does not depend on `K`

`K` is the one number W2b chose that W2a did not, so it gets its own check.
Refitting from scratch at each window (300 sims/point for tractability; the
fitted point at K = 12 is identical at 300 and 1000 sims):

| `K` | fitted (`bpa_prob`, `decay`) | W₁ | hold-out Δ mean | hold-out KS p | hold-out | `mfl` Δ mean | `mfl` KS p | `mfl` |
|---|---|---|---|---|---|---|---|---|
| 8 *(= W2a's window)* | (0.50, 0.99) | 0.771 | 0.91 | 0.241 | **PASS** | 3.63 | 0.051 | FAIL |
| 10 | (0.50, 0.99) | 0.470 | 0.42 | 0.377 | **PASS** | 3.16 | 0.148 | FAIL |
| **12** *(shipped)* | **(0.50, 0.95)** | **0.447** | **0.18** | **0.372** | **PASS** | **2.91** | **0.145** | FAIL |
| 16 | (0.50, 0.90) | 0.652 | 0.05 | 0.307 | **PASS** | 2.71 | 0.105 | FAIL |
| 20 | (0.40, 0.80) | 0.710 | 0.42 | 0.248 | **PASS** | 3.13 | 0.090 | FAIL |

Two conclusions, both load-bearing:

1. **The window is not doing the work.** The mixture passes the hold-out even
   at W2a's own `K = 8` — where the *entire* model change is the noise family.
   The improvement is the model form, not a widened cap.
2. **`K = 12` is nevertheless the right cap**, and for a fit-block reason
   rather than a hold-out one: at `K ≤ 10` the fit pins `reach_decay` at the
   top of its grid (0.99) — the same degeneracy signature that disqualified
   W2a's fit — while `K = 12` gives an interior optimum and the lowest W₁.

## 6. Why the one bar fails — the corpora disagree, not the model

The two corpora's **own** observed means differ by

```
mean|d|(mfl-complete) − mean|d|(lakeview hold-out)  =  5.357 − 2.650  =  2.707 slots
```

which is **2.7× the ±1.0 bar itself**, before any model is involved. A noise
model's simulated mean is very nearly corpus-invariant — here 2.428 on Lakeview
against 2.422 on MFL, a 0.006-slot difference — because the reach law does not
know which league it is in. Formally: passing bar 1 needs a simulated mean in
`[1.65, 3.65]`; passing bar 2 needs it in `[4.36, 6.36]`. **Those intervals are
disjoint.** No single parameter set of any corpus-invariant model can satisfy
both. That is the whole of the residual failure, and it is pinned by
`test_w2_16_the_residual_failure_is_a_corpus_disagreement_not_a_model_form`.

*Why doesn't the simulated mean move between corpora?* Because the one thing
that could move it — positional need — is inert on `mfl-complete`: that corpus
carries no roster snapshot, so every team enters with zero viable players at
every position, severity is 1.0 everywhere, and a *uniform* need bonus cancels
out of an argmin exactly. The MFL replay is therefore pure noise model.

*What drives MFL's observed mean?* Four picks: reaches of 11, 17, 26 and 33.
They contribute 87 of the 150 total slots — drop them and the corpus reads mean
2.6, i.e. Lakeview. And those four sit inside a block of players the consensus
**cannot tell apart**: `Jack Endries` (`d = 33`) and `Michael Trigg`
(`d = 26`) carry the *identical* seeded Elo of 1205.107, as do `Zachariah
Branch` (`d = 11`) and `Malachi Fields` (`d = 7`) at 1271.860. The trimmed
`player_pool_2026.json` snapshot floors a long deep tail at a handful of
repeated DP values; inside such a block the pool order is a `search_rank`
tiebreak, so `d` is measuring **which arbitrary tiebreak a human happened to
pick**, not how far he reached. Lakeview shows this far less because it is a
superflex league priced on `sf_tep` with 43 of 50 rookies taken — its tail is
consumed rather than sampled.

**This is diagnosis, not a fix.** No bar was loosened, no grid widened, no
corpus edited, and the tie artefact was *not* engineered out of the observable
— identifying the thing that fails the gate and then redefining it is the exact
move amendment 2 exists to prevent. It is recorded here so the operator can
decide whether the bar is testing the model or the corpus. §7 lists what a
clean answer would take.

## 7. Consequences and options (plan §5's abort criterion, applied)

**Applied now:**

1. **The CPU-bot mock stays CUT.** `CPU_MODEL_VALIDATED = False`;
   `advance_cpu` raises `CalibrationGateClosed` unless a caller explicitly opts
   in (the harness and the engine tests do; the routes never do).
2. **`draft.mock` stays OFF**, and with the flag ON `POST /api/mock-draft`
   still returns `200 {"empty": true, "reason": "cpu_model_unvalidated"}` —
   M2's existing typed-empty contract, so no closed client enum gains a member.
3. **The mixture ships anyway**, as W2a's model did, so the verdict is
   reproducible and the next attempt starts from a better model rather than
   from the uniform one.

**For the operator to choose between — none of these is decided here:**

| Option | What it costs | What it would settle |
|---|---|---|
| **A. Re-derive the consensus universe from a full, live-shaped snapshot** (KTC-blended, untrimmed) and re-run the gate unchanged | a fixture refresh; no code change | This is the highest-value next step. It attacks the *measured* cause directly: a universe with no floored tie-block makes `d` a real reach everywhere, and if the corpora then agree the mixture likely passes outright. It also cannot be accused of tuning — the model and both bars stay frozen. |
| **B. Add corpora** (`mfl-partial` is already shape-checked and unused; more recorded rookie drafts) | corpus collection | Whether Lakeview-vs-MFL is a real between-league spread or an n = 28 artefact of four picks. Two corpora cannot distinguish "the bar is wrong" from "one corpus is odd". |
| **C. Cut CPU bots; ship practice/replay** (plan O5, tester allowlist) | W2b/W2c re-scope | Needs no noise model at all — the non-user picks come from a recorded corpus. Still the right fallback, and still the recommendation if A and B are not worth the time. |
| **D. Re-spec the model again** | another wave | **Not recommended.** The evidence does not point at the model any more: the shape passes on both corpora and the hold-out passes on both bars. A third model form would be fitting the corpus disagreement, which is exactly what the gate is designed to catch. |

**Recommended order: A, then re-run the gate; if it still fails, B; if that
still fails, C.** Do not do D.

---

*Prepared under `docs/plans/draft-extensions/build-w2b.md`. The engine, the
harness and every number above are reproducible with
`python3 -m pytest backend/tests/test_mock_draft.py -k w2_16`.*
