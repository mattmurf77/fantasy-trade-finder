# ADR-014 — Bake-off serving runs as screen-then-confirm rounds, arm B always seated, plain draft

**Date:** 2026-08-20
**Status:** Accepted
**Author:** worktree session `claude/trade-suggestions-review-69c9eb`
(plan: [`../plans/fit-challenger/PLAN-v2.md`](../plans/fit-challenger/PLAN-v2.md) §1 rulings;
reasoning record: the two adversarial drafts + cross-critiques in the same directory)

## Context

Interleaved serving was lit once (2026-08-18) and reverted in a day: lane quotas plus
leave-short shrank a 40-card pool to a 10-card deck. Since then every arm but `current`
has generated dark — zero user decisions ever (prod-verified 2026-08-20). Meanwhile the
tester base supplies ~400 decided cards/week, which no serving design can wish away: with
k simultaneously-served arms and the bucketed co-primary counting roughly half of fit's
cards, a 10pp like-rate read at k=4 needs ~4–5 weeks — past the point where this repo's
own change velocity historically contaminates a window.

## Decision

1. **`bakeoff_group_size = 0` is the serving posture** — the composition/lane-quota layer
   is off; the plain per-arm team draft has no quotas to under-fill, so a zero-card arm
   costs nothing and the deck fills from the rest (regression-tested:
   `test_zero_card_arm_deck_still_fills`). Lane-quota telemetry is knob-restorable; 79
   dark runs of it are already banked.
2. **Screen-then-confirm rounds, arm B always seated.** Screening windows may serve 3
   arms (variety is an operator goal) and read at **15pp / non-inferiority**; a
   **10pp verdict** requires a k=2 confirmatory round (B vs the candidate). Pre-registered
   promote/iterate/kill rules are written before a round serves; pooled like-rate is a
   guardrail, never the verdict (a two-sided arm loses a pooled comparison by
   construction).
3. **Windows are censored, not discarded, at a logged knob change** — the knob log gives
   the timestamp; split the window and keep both segments. Whole-window discard is
   reserved for re-ranker contamination and *unlogged* changes (the cases with nothing to
   split on). The control arm is frozen for the duration of any round.

## Consequences

- Arms accrue decisions only inside rounds; a built arm waits for its round (fit's is
  gated on a 3-day dark soak behind `bakeoff_serve_fit`).
- `gen_v2` serves again only when ≥2 leagues have 3+ boards — its decided sample is
  otherwise league-captive and unreadable.
- Every roster/serve-bit move is that week's one engine-affecting change and lands on a
  Monday boundary; the Friday readout (`scripts/bakeoff_readout.sql`) diffs every run's
  `config_json` against round start.
- The 3-week window mark is a review trigger (audit the snapshot diffs before trusting
  the verdict), not a hard ceiling.
