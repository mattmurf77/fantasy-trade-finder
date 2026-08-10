# Outlook odds — phase 2 plan (projection-driven strength)

**Status:** planning, 2026-08-09. Phase 1 (team-level, trailing-scores/roster-value μ) is
built, calibrated, and dark — see [`calibration-report-2026-08-09.md`](calibration-report-2026-08-09.md).
Nothing here ships until phase 1 is lit and its bugs are fixed.

> Phase 1 asks "how many points does this *team* score in a week?" and answers it from
> team-level history. Phase 2 asks the same question **bottom-up from players**, which is
> the only way μ becomes *week-specific*. Everything below feeds the existing
> `StrengthProvider` seam — the simulator, playoff format, and serializer are unchanged.

---

## Table of Contents
- [Operator's target pipeline](#operators-target-pipeline)
- [Candidate strength providers](#candidate-strength-providers)
- [Roster-signal hypotheses under test](#roster-signal-hypotheses-under-test)
- [Sequencing and gates](#sequencing-and-gates)

---

## Operator's target pipeline

Sketched by the operator 2026-08-09; this is the phase-2 north star:

1. Extract team rosters
2. Run player projections for the season
3. Calculate per-week average per player
4. Ingest player bye weeks → zero out that player's week
5. Generate starting lineups per team, per week
6. Calculate projected points per team, per week (**week-specific μ**)
7. Apply weekly team projections against the league schedule
8. Calculate win/loss projections per team
9. Calculate playoff odds

Steps 7–9 are **already built** (phases 3–5 of the shipped pipeline). Phase 2 is steps 1–6
replacing the flat μ.

**Bye weeks: data landed, multiplier rejected** (2026-08-09) — see
[`bye-week-multiplier-2026-08-09.md`](bye-week-multiplier-2026-08-09.md). The nflverse
ingestion (`backend/outlook/bye_weeks.py`, CC-BY, cached, tested) is **kept** as reusable
infrastructure for step 4. The naive multiplier is **NOT shipped**: playoff Brier got
*worse* (0.1113 → 0.1212) at every scale tested.

> **This is the single most important finding for phase 2.** The mechanism is real — scores
> in bye-heavy weeks do fall (CI [−0.305, −0.138], excludes 0) — but only ~22% as much as a
> fixed-lineup model assumes (empirical slope −0.222 vs the model's −1.000). **Managers
> absorb most of a bye by starting someone else.** Step 4 of the pipeline below ("zero out
> the bye player") therefore CANNOT be implemented naively: a projection model must
> re-optimize the lineup from available players for that week, not zero a starter and keep
> the rest. A model that skips the re-optimization will systematically over-penalize byes
> and score worse than today's flat μ — which is exactly what just happened.

## Candidate strength providers

| Provider | Source | Status | Notes |
|---|---|---|---|
| `RosterValueStrength` | dynasty starting-lineup value | **shipped** (preseason default) | Excludes bench and draft picks by design — picks don't score this season |
| `TrailingScoresStrength` | team weekly scoring history | **shipped** (in-season default) | Memoryless mean/stdev; validated +55% playoff skill |
| Bye-adjusted μ | above × per-week bye multiplier | **in evaluation** | Middle path; both-sides |
| Projection-driven μ | per-player projections → optimal weekly lineup | **phase 2 target** | Operator's pipeline; only free per-player feed is Sleeper's undocumented projections endpoint (ToS-gray; operator accepts the posture — DynastyDaddy scrapes KTC, a more aggressive stance) |
| **MOV-scaled Elo** | compounding rating off real results | **phase 2 candidate** | See below |

### MOV-scaled Elo — memorialized from DynastyDaddy (operator directive, 2026-08-09)

Byte-verified against `Leondoff/dynasty-daddy@6efac02` (MIT) — full analysis in
[`dynastydaddy-sim-reference.md`](dynastydaddy-sim-reference.md). The one idea the
dual-lens review ranked worth adopting:

- **Seed** each team's rating from a preseason value estimate (they use redraft ADP
  consensus; ours would be `RosterValueStrength`) rather than a flat 1500 baseline.
- **Update** weekly with textbook logistic Elo (400 scale) where **K is scaled by margin
  of victory and clamped to [10, 40]** — a blowout moves the rating more than a squeaker.
- **Adopt as a new `StrengthProvider`** emitting into our existing μ/σ Gaussian machinery.
  Do **not** adopt DynastyDaddy's simulation mechanic itself: they never simulate a score
  (each matchup is one weighted coin flip), which costs them consistent points-for
  tiebreaks and determinism. Our design is ahead there and stays.
- **Why it may beat `TrailingScoresStrength`:** trailing scores are memoryless and
  schedule-blind; Elo compounds evidence and accounts for opponent quality. Worth testing
  as a blend, not an automatic replacement.

**No code is copied from DynastyDaddy regardless of license** until the operator clears it;
this is a method reference.

## Roster-signal hypotheses under test

Operator-raised 2026-08-09; validation agents running. Results land in
`hypothesis-pick-capital-2026-08-09.md` and `hypothesis-bench-depth-2026-08-09.md`, and
whichever survive get specced into a provider adjustment here.

Operator-raised 2026-08-09; **all three validated 2026-08-09 — no term ships.** Reports:
[`hypothesis-pick-capital-2026-08-09.md`](hypothesis-pick-capital-2026-08-09.md),
[`hypothesis-bench-depth-2026-08-09.md`](hypothesis-bench-depth-2026-08-09.md).

| # | Hypothesis | Verdict | Key evidence |
|---|---|---|---|
| 1a | Pick capital → in-season buying → stronger | **NOT SUPPORTED** (ran backwards) | buy:sell ratio *falls* as capital rises |
| 1b | Pick capital → rebuilding → sheds producers | ~~**SUPPORTED but underpowered**~~ → **WEAKENED (re-tested 2026-08-09 with dated boards)** | buy:sell 2.4:1 → 0.7:1 → 0.6:1 by capital tercile (monotonic, mechanism-level, confound-resistant); outcome correlations r ≈ −0.20 to −0.25 but confounded by pick-rich teams already being weaker (r ≈ −0.3) |
| 1c | Positional bench depth → injury resilience | **NOT SUPPORTED** | next-man-up survives controlling at r = +0.17 (raw bench total collapses +0.27 → +0.02), but variance ≈ 0 and the absence interaction fails — no injury mechanism |

**Standing decision (2026-08-09): no coefficient specced from any of the three.** 1b is the
only live candidate; revisit when the sample exceeds ~72 team-seasons. ~~Both agents
independently hit the same blocker — **no dated historical dynasty-value board exists**, so
retroactive roster pricing uses today's values. Building/finding one is the prerequisite for
re-testing 1b honestly, and would also sharpen `RosterValueStrength`'s own backtest.~~

**PREREQUISITE MET AND CLOSED — 2026-08-09.** The "no dated board exists" premise was
**wrong**: the DynastyProcess repo keeps the full git history of `values-players.csv`, so any
past season can be priced with a period-correct board. 24 dated boards (2022–2025 × weeks
0/3/6/9/12/14) are committed under `backend/tests/fixtures/dp-values-history/`, served offline
by `backend/dp_values_history.py`. Both follow-ups it gated are now done —
[`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md):

- **1b re-tested honestly.** Sub-test (i) flips from r = −0.11 (CI excluding 0) to **+0.076
  (CI spanning 0)**; the confound strengthens (−0.35 → **−0.41**); (ii), (iii) and the buy:sell
  gradient are bit-identical. **1b is WEAKENED** — see the verdict row above, now read as
  "supported on outcomes and behaviour, NOT on roster composition". Δ dynasty value is a
  structurally poor instrument for 1b; do not re-run that sub-test on more seasons.
- **`RosterValueStrength` backtested.** Preseason playoff Brier **0.1959** vs climatology
  0.2500 (**+21.6 %**, 90 % CI [+4.1 %, +38.3 %]); preseason **title odds show no skill**.
  Over-confident at the extremes (95 % → 75 % realized) and beaten by climatology in 2 of 6
  league-seasons. **Statistically indistinguishable from the week-3 `trailing_scores` model**,
  which means the `completed_weeks >= 3` gate in §Sequencing buys no measured accuracy at
  week 3 — its honest justification is weeks 6+.

## Sequencing and gates

1. **Phase 1 lighting first** — fix BUG-1 (median-match ingestion, G-024), then light
   playoff odds only, gated `completed_weeks >= 3`. Title odds stay dark (unvalidated,
   6 champion events).
2. **Bye multiplier** — ships only if the backtest shows improvement; behind a
   `model_config` knob, default off.
3. **Hypothesis terms** — only those that survive validation, specced as μ or σ
   adjustments, each re-backtested.
4. **Projection-driven μ (the operator's pipeline)** — needs its own calibration gate
   against the same 6 league-seasons before it displaces the validated provider.
5. **MOV-scaled Elo** — prototype as a provider, backtest as a blend candidate.

**Standing rule for every item above:** no strength change reaches users without beating
the phase-1 baseline on the existing backtest harness. The harness, not intuition, decides.
