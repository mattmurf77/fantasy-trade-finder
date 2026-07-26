# PRD F8 — Offline Eval Harness (replay/IPS + interleaving)

**Priority:** 7 · **Effort:** ~3d · **Flag:** none (operator tooling) · **Depends:** F1, F7
**Source:** gap-analysis #15; models-research blueprint stage 5 (Monolith's offline-then-online
discipline; interleaving over parallel-cohort A/B at small traffic)

## Problem

Every ranking change so far ships on judgment. The experiments engine (experiments.py) exists but
nothing deck-related uses it, and without propensities there was nothing to evaluate against. Once
F1/F7 log propensities, FTF can grade candidate rankers on **logged data before any user sees
them** — the discipline that let ByteDance iterate daily. Without this, F5's η-tuning and F6's
model are guesswork; with it, every future ranking idea gets a cheap, safe first gate.

## Solution

Operator-facing tooling (no user surface, no client changes):

1. **Replay/IPS evaluator** (`backend/eval/replay.py` + CLI): given a candidate scorer (a Python
   callable over F1's frozen `features_json`), replay logged impressions and compute
   IPS/SNIPS-weighted expected like-rate and propose-rate, with confidence intervals and an
   effective-sample-size report (small ESS ⇒ verdict labeled unreliable — no silent caps).
2. **Calibration checks:** for any scorer emitting probabilities (F6), reliability tables by decile.
3. **Time-ordered protocol:** train/tune on days ≤ T, evaluate on days > T only (no shuffled CV on
   sequential data); the harness enforces the split.
4. **Within-user interleaving** (the small-traffic alternative to cohort A/B): behind the existing
   experiments engine, blend cards from ranker A and B into one deck (team-draft interleaving),
   credit dispositions to the source ranker. Positions + source logged via F1.
5. **Nightly job** (existing cron stack): re-run registered candidate scorers on the trailing
   window, append to `eval_runs` table; simple operator report (markdown to `docs/feedback/` style
   or stdout) ranking candidates vs the production scorer.
6. **The gate (process, recorded here):** no ranking-affecting flag (F5 η's, F6, future tweaks)
   graduates without (a) a replay win with adequate ESS, then (b) an interleaving or experiment win.

## Acceptance criteria
- [ ] Replaying the *production* scorer on its own logs reproduces observed like-rate within CI
      (the self-consistency sanity check).
- [ ] A deliberately broken scorer (random order) grades measurably worse.
- [ ] ESS and CI reported on every run; unreliable verdicts labeled.
- [ ] Interleaving mode serves blended decks only to experiment-bucketed users and credits
      dispositions correctly by source.
- [ ] Nightly job idempotent; failures logged to runbook conventions.

## Metrics
This IS the metrics feature. Success = F5/F6 tuning decisions cite replay numbers, not vibes.

## Risks
IPS variance at FTF's volume — mitigated by SNIPS, ESS reporting, and leaning on interleaving (which
needs far less traffic) for final calls.
