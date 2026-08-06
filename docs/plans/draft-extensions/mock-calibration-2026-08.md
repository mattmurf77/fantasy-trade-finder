# Mock-draft CPU noise model — calibration report (interface I-10)

**Date:** 2026-08-06 · **Wave:** draft-extensions W2a (engine + calibration)
**Normative:** [plan.md](plan.md) §5 (amendment 2 + the W2 abort criterion) · [lld.md](lld.md) §4.2.3
**Reproduced by:** `python3 -m pytest backend/tests/test_mock_draft.py -k w2_16`
**Harness:** `backend/mock_draft_service.reach_series` / `simulate_reaches` (the simulator drives the **shipped** `cpu_pick`) + the statistics in `backend/tests/test_mock_draft.py`.

> **This document is a GATE, not a report.** `mock_draft_service.CPU_MODEL_VALIDATED`
> mirrors the verdict below, and `test_w2_16_calibration_gate` fails if the two
> ever disagree — in either direction.

---

## VERDICT: **FAILED** — the W2 abort criterion fires

The specified noise model does not reproduce the reach distribution of a real
dynasty rookie draft at **any** value in the specified grid. It fails **both**
bars on the Lakeview hold-out **and** both bars on the independent `mfl-complete`
corpus. Per plan §5 the **CPU-bot mock is CUT**: practice/replay remains the
QA-only surface, `draft.mock` stays OFF, and the create route answers the
typed-empty `200 {"empty": true, "reason": "cpu_model_unvalidated"}`.

**Do not retune.** The failure is a *model-form* failure, not a tuning miss
(§5 below). Widening the grid is exactly the "fit on the validation set" move
amendment 2 exists to prevent.

---

## 1. The model under test

```
score(c)   = rank(c) − need_bonus(t, pos(c)) − jitter(c)
pick       = argmin score                       (ties → better consensus rank)
need_bonus = need_weight(t) × severity(t, pos) × MOCK_MAX_REACH
jitter(c)  ~ Uniform(0, MOCK_JITTER_SLOTS)      ← THE fitted parameter
need_weight(t) = trade_service.outlook_alpha(persona_outlook(t))
```

`MOCK_MAX_REACH` is held at the product-specified **3.0**: it is a product cap,
not a fitted parameter, and fitting both at n = 23 is unidentifiable
(lld §4.2.3 step 2).

## 2. The observable — and a correction to the LLD

`d_i` = **how many better-valued *available* players the pick passed over**,
i.e. the player's 1-based consensus rank in the pool *as it stood at that pick*,
minus 1. `d_i > 0` is a reach; `d_i == 0` is best-player-available.

The LLD writes `d_i = consensus_rank_at_pick − i` *and* says the rank is taken
"over the pool as it stood at that pick (drafted players removed)". **Those two
clauses contradict each other** and the ambiguity is load-bearing, so it is
resolved here explicitly:

| Reading | BPA pick scores | mean \|d\| r1–2 | mean \|d\| r3–4 | Drift across the split |
|---|---|---|---|---|
| **Remaining-pool rank − 1** (adopted) | `0` | **2.35** | **2.65** | **0.30** |
| Static pre-draft rank − pick index | `0` | 2.65 | 5.55 | **2.90** |

The static reading is **non-stationary**: it drifts 2.9 slots between the fit
block and the hold-out block, which exceeds the ±1.0 hold-out bar *before any
model is involved*. Under it the gate would test the split rather than the
model, and no single-parameter model could ever pass. The remaining-pool
reading is stationary (0.30) and is therefore the only one that can falsify a
noise model — which is the point. Pinned by
`test_w2_16_the_observable_is_stationary_across_the_split`.

Consequence worth stating: under the adopted reading `d ≥ 0` always, so a
"fall" (`d < 0`, per the LLD's prose) is not expressible. `|d| = d`, and every
bar below is unchanged.

## 3. Corpora and their shape check (T-W2-17)

Shape is checked **before** use — a startup corpus has a different reach
distribution by construction and would silently poison the fit.

| Corpus | Rounds | Picks used | Role | Verdict |
|---|---|---|---|---|
| `lakeview-complete` | 4 × 12 | 43 of 48 | **fit (r1–2) + hold-out (r3–4)** | rookie-shaped ✓ |
| `mfl-complete` | 3, single unit | 28 of 30 | **independent validation, NO refit** | rookie-shaped ✓ |
| `mfl-partial` | 3 made, single unit | 29 of 36 | reference only | rookie-shaped ✓ |
| `mfl-multi-unit` | 5, **two** units | — | **EXCLUDED** | see below |

**`mfl-multi-unit` exclusion — the LLD's stated reason is wrong.** The LLD calls
it "startup-shaped"; by the shipped discriminator (`draft_status.ROOKIE_MAX_ROUNDS = 8`
/ `STARTUP_MIN_ROUNDS = 15`) it is not — it runs 5 rounds. The real disqualifier
is that it is a **two-unit conference-split draft** (`CONFERENCE00`/`CONFERENCE01`,
96 picks each, 16 franchises each): two drafts interleave in one grid, so "the
pool as it stood at that pick" is not well defined across units. Excluded for
that reason instead.

**Hermetic-consensus limitation (stated, not hidden).** The calibration ranks
players from the committed `backend/tests/fixtures/player_pool_2026.json`
snapshot through the shipped `data_loader.seed_elo_for_value` and the shipped
`draft_board_service._undrafted` — the same functions the product uses — but
that snapshot is trimmed (top-N per position) and carries no live KTC blend.
The resulting rookie universe is 50 players (Lakeview, `sf_tep` values — the
league is superflex) and 56 (MFL, `1qb_ppr`). Five Lakeview picks and two
`mfl-complete` picks fall outside it and are dropped; the ranking **and** the
sequence are then restricted to the same sub-universe, which leaves `d`
self-consistent. A richer universe would, if anything, *widen* the observed
tail, so it cannot rescue the verdict.

**Personas.** Neither corpus carries `league_preferences`, so every CPU team
runs the default `not_sure` persona (`need_weight = 0.5`). §5 shows the verdict
is persona-independent: the persona weight moves the simulated mean by < 0.05
slots because a *uniform* need bonus cancels out of an argmin — only
**per-position** severity differences differentiate at all, and those are capped
at `MOCK_MAX_REACH` by construction.

## 4. The procedure and its numbers

### 4.1 Split

Fit on Lakeview rounds 1–2 (picks 1–24 → **23** retained), validate on rounds
3–4 (picks 25–48 → **20** retained). The hold-out block is never fitted.

### 4.2 Fit — grid search, 1000 seeded simulations per point

`MOCK_JITTER_SLOTS` over `[0.25, 3.00]` step `0.25`, minimising the 1-D
Wasserstein distance between simulated and observed `|d|` on the fit block.

| jitter | 0.25 | 0.50 | 0.75 | 1.00 | 1.25 | 1.50 | 1.75 | 2.00 | 2.25 | 2.50 | 2.75 | **3.00** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W₁ | 2.348 | 2.348 | 2.347 | 2.340 | 2.318 | 2.286 | 2.249 | 2.214 | 2.176 | 2.137 | 2.100 | **2.059** |

**Fitted value: `mock_jitter_slots = 3.00`.**

Two things about this fit are already disqualifying on their own:

1. **The optimum is pinned at the grid boundary** — the objective is monotone
   decreasing across the whole grid, so the grid does not contain the minimum.
2. **The objective barely moves** (2.348 → 2.059 across a 12× change in the
   parameter). The fitted parameter has almost no leverage on the observable it
   is supposed to explain.

Observed fit-block mean `|d|` = **2.35**.

### 4.3 Hold-out validation (Lakeview rounds 3–4, n = 20) — **BOTH BARS FAIL**

| Bar | Threshold | Result | |
|---|---|---|---|
| Two-sample KS | not rejected at α = 0.05 | D = **0.567**, p = **2.3 × 10⁻⁶** | **REJECTED — FAIL** |
| Paired mean | \|Δ mean\|d\|\| ≤ 1.0 | observed **2.65** vs simulated **0.280** ⇒ Δ = **2.37** | **FAIL** |

*The paired mean bar is not redundant with KS.* KS at n = 20 is underpowered —
a model can survive it on sample size alone. Here both fail, but the mean bar
is the one that states the magnitude: the simulator reaches an eighth as far as
real drafters do. Never drop it as duplicative.

### 4.4 Independent validation — `mfl-complete`, NO refit (n = 28) — **BOTH BARS FAIL**

| Bar | Threshold | Result | |
|---|---|---|---|
| Two-sample KS | not rejected at α = 0.05 | D = **0.570**, p = **9.4 × 10⁻⁹** | **REJECTED — FAIL** |
| Paired mean | ≤ 1.0 | observed **5.36** vs simulated **0.295** ⇒ Δ = **5.06** | **FAIL** |

A second, unrelated league, a different platform, a different scoring format —
and the gap is more than twice as large. The failure is not a Lakeview artifact.

## 5. Why it fails — structural, not a tuning miss

A candidate at rank *r* can only win the argmin when

```
r − need_bonus − jitter  <  1 − need_bonus₁ − jitter₁
```

with `need_bonus ≤ MOCK_MAX_REACH = 3` and `jitter ≤ MOCK_JITTER_SLOTS`. The
model's reachable support is therefore bounded by roughly **`max_reach + jitter`
≈ 6 slots**, and it is additionally hard-capped by the candidate window
`K = ceil(max_reach) + 5 = 8`.

The observed distributions are **bimodal with a fat tail well past that bound**:

| `d` | 0 | 1 | 2 | 3 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| Lakeview (n=43) | 19 | 4 | 5 | 4 | 2 | 1 | 2 | 3 | 3 |

44 % of real picks are exact BPA, and **21 % reach 6–9 slots** — beyond
anything the model can express. `mfl-complete` is worse still, with observed
reaches of 11, 17, 26 and 33 slots. Uniform jitter around an argmin produces a
smooth, thin-tailed decay; it cannot produce "usually exactly BPA, occasionally
nine slots off the board". Human rookie drafting is *mixture-shaped* — mostly
consensus, sometimes a private conviction — and a single additive uniform noise
term is the wrong family.

For scale: reproducing the observed **mean** alone would need
`mock_jitter_slots ≈ 28` (measured), nine times the product's own 3-slot reach
cap and an order of magnitude outside the specified grid — and the *shape*
would still be wrong. That is the definition of a model-form failure.

Pinned by `test_w2_16_the_failure_is_structural_not_a_tuning_miss`.

## 6. Consequences (plan §5's abort criterion, applied)

1. **The CPU-bot mock is CUT.** `mock_draft_service.CPU_MODEL_VALIDATED = False`;
   `advance_cpu` raises `CalibrationGateClosed` unless a caller explicitly opts
   in (the harness and the engine tests do; the routes never do).
2. **`draft.mock` lands OFF and stays OFF.** With the flag ON, `POST /api/mock-draft`
   returns `200 {"empty": true, "reason": "cpu_model_unvalidated"}` — M2's
   existing typed-empty contract, so no closed client enum gains a member (D10).
3. **Practice/replay is the surviving surface** and is QA-only (plan O5:
   tester allowlist). It needs no noise model: the non-user picks come from a
   recorded corpus. W2b/W2c should be re-scoped to it, or deferred.
4. **The engine, its tests and this harness all ship anyway.** Everything except
   the noise model validated cleanly (T-W2-01..15, T-W2-17), so a re-specced
   model can be re-gated by re-running one test rather than rebuilding a wave.

## 7. What a passing model would need (for whoever re-specs it)

Not a recommendation to build now — a record of what the evidence says, so the
next attempt is not the same attempt.

- **A mixture, not a single noise term.** Something like: with probability
  `1 − p` take BPA-with-small-noise; with probability `p` draw the pick from a
  heavy-tailed reach distribution. Two parameters, and n ≈ 43 + 28 can identify
  two.
- **Remove the `K` cap from the fit** — it truncates the very tail being
  measured. Keep it in the product for cost if wanted, but not in the model.
- **Re-derive the consensus universe from a full, live-shaped DP snapshot**
  before drawing conclusions about tail magnitude; the trimmed fixture pool
  bounds `d` at ~50, and `mfl-complete` already shows a `d = 33`.
- **Keep the split and both bars exactly as they are.** They worked: they
  rejected a wrong model on the first corpus and confirmed it on a second.
