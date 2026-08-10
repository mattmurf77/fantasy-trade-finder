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

**Bye weeks are being pulled NOW** (operator directive, 2026-08-09) as a "middle path"
ahead of full projections: keep phase 1's validated μ, apply a per-week multiplier for
starting-lineup value on bye, on **both** sides of each matchup. Evaluated on the phase-1
backtest before it ships — see `bye-week-multiplier-2026-08-09.md`. This also delivers the
bye dataset step 4 needs, accelerating phase 2.

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

| # | Hypothesis | Predicted effect on μ/σ |
|---|---|---|
| 1a | Heavy pick capital → in-season buying → team gets stronger | μ rises through season |
| 1b | Heavy pick capital → rebuilding → sheds producers | μ falls through season |
| 1c | Positional bench depth → injury resilience | σ falls (fragility, not scoring power) |

1a and 1b predict **opposite signs from the same signal** — the net, and any moderator that
separates them (record at midseason, contender vs rebuilder), is the real finding. A clean
null on any of these keeps a bogus term out of the model.

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
