# Tester protocol — the weekly measurement cadence (M5)

**Date:** 2026-08-20 · **Status:** committed protocol — this is the input-supply half of
the measurement rail.
**Sources (binding):** [PLAN.md](PLAN.md) Phase 2 (the cadence and power math) ·
[../fit-challenger/PLAN-v2.md](../fit-challenger/PLAN-v2.md) §5 (the rollout schedule this
protocol feeds) · draft B §2.2 (metric definitions the Friday readout uses).

## Why this exists, in plain words

The bake-off can only pick a winner if testers generate enough *decided* cards each week —
a card viewed but never liked/passed tells us nothing. At our base like-rate, seeing a
10-point improvement needs about 300 decided cards per arm; the tester base produces about
400 decided cards a week total when everyone follows this protocol. That is exactly one
clean two-arm comparison per week. Every requirement below is downstream of that number.

## The weekly loop

| Day | What happens |
|---|---|
| **Monday** | At most ONE engine-affecting change ships (knob flip, roster change, serve-bit move — each IS an engine-affecting change). It goes through `scripts/set_knob.py` so it lands in the knob log (`model_config_changes`) with a timestamp and a source. Nothing else engine-affecting moves that week. |
| **All week** | Testers churn decks per the tester asks below. During any transition week the daily tripwires run (deck-median, p95 ms — `scripts/bakeoff_readout.sql` §4/§7), not just the Friday pass. |
| **Friday** | The readout ritual (below). ~30 minutes of execution, zero authoring. |

## Tester asks (the brief, verbatim)

1. **Decide ≥ 40 cards this week** — decide, not just view. Likes and passes both count;
   an undecided card is a wasted serve.
2. **Always pick a decline reason** when passing. The decline-reason mix is a co-primary
   metric (`value_giving` share is the complaint the fit arm exists to fix); a pass
   without a reason is half a data point.
3. **Attempt ≥ 1 real send per week** when a card is genuinely close. The propose funnel
   has fired zero times ever and it is launch gate G1 — it must be exercised, not admired.

## Tester onboarding requirements (input supply, not busywork)

A tester is *measurement-ready* when all of the following hold:

- **A real board: ≥ 100 matchup votes** before their first deck. Unboarded testers only
  exercise the consensus path.
- **A declared outlook** via Team Review — inferred outlooks are a known wrong-input
  source, and the outlook machinery fires against nearly everyone under inference.
- (Program-level, not per-tester) **≥ 2 leagues with 3+ boarded members** is the standing
  goal — divergence currently has one league of supply and every replay conclusion is
  captive to it. gen_v2 re-enters serving only when this is met.

## Friday readout ritual

1. Run `scripts/bakeoff_readout.sql` under the read-only prod posture
   (`backend/tools/prod_analytics.py` idiom), `:window_start` = Monday 00:00 UTC.
2. Check the header first: decided-cards-per-arm n, knob changes in the window, config
   snapshot diff. A mid-window engine-affecting change → censor at the logged timestamp;
   an *unlogged* change or re-ranker contamination → discard the window and say so.
3. File the readout to `docs/plans/fit-challenger/readouts/2026-Wnn.md`, pointer in
   `living-memory/TEST_LEDGER.md`.
4. Honesty rules: Wilson intervals on every rate; deltas < 3pp read "did not move";
   nothing is called before its pre-registered n. Pooled like-rate is a guardrail, never
   the verdict.
5. Supply tripwire: < 250 total decided cards in the week → extend the round one week
   (once) and tell the operator; do not call results at partial n.

## What this protocol is not

It does not authorize any knob change (Monday's slot is the operator's, through
`set_knob.py`), does not replace the per-stage soak bars in PLAN-v2 §5, and does not
change any tester-facing product surface — it is a brief plus a calendar.
