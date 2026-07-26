# PRD F7 — Exploration Slots & Archetype Audition

**Priority:** 6 · **Effort:** ~2d · **Flag:** `deck.exploration` · **Depends:** F1, F2
**Source:** gap-analysis #8; presentment-research §5 + principle 5–6; models-research §4
(staged pools; TikTok's own ~7% off-interest figure)

## Problem

Exploration today is incidental (bounded Thompson noise). Nothing guarantees off-taste variety, so
decks can collapse onto early likes — the WSJ rabbit hole in miniature, made worse once F4/F5 land.
New trade *archetypes* the generator could produce have no audition path: they compete against
proven shapes on equal footing and die unseen. And without a randomization slot, F1's propensity
logs cover only the neighborhood Thompson already likes — off-policy eval (F8) stays half-blind.

## Solution

1. **Wildcard slot:** 1 card per deck (≈1-in-8 to 1-in-12 given deck sizes; config `exploration_rate`)
   is drawn from *outside* the user's current taste neighborhood (low prefMatch / low-data arms),
   uniformly at random from gate-passing candidates. Slot position fixed mid-deck (position 4–6),
   immune to F4 re-rank displacement.
2. **Labeled honestly** (presentment principle 5 + heating lesson): card badge "Wildcard — outside
   your usual" in the existing provenance-chip style. Hand-boosts get labels; so does exploration.
3. **Archetype audition (follower-blind staged pools):** a new/low-data archetype enters a test
   pool — served only via wildcard slots across users until it accrues n≥30 viewed impressions;
   graduates to the general pool if its like-rate clears 0.5× the global base rate, else retired for
   30d. Successive-elimination bandit, TikTok's new-item pipeline in miniature.
4. **Propensity honesty:** wildcard draws log `propensity = exploration_rate × 1/|candidates|` to
   F1 — this is the randomization traffic that makes F8's IPS estimates trustworthy.
5. Quality gates NEVER relax for exploration — wildcards are gate-passing trades that are merely
   off-taste, not lower-quality (guardrail 4).

## Acceptance criteria
- [ ] Every deck of ≥8 cards contains exactly one labeled wildcard in positions 4–6.
- [ ] Wildcard candidates come from the bottom prefMatch tercile or sub-n arms (logged provenance).
- [ ] Auditioning archetypes appear only in wildcard slots until graduation; graduation/retirement
      transitions logged.
- [ ] Wildcard impressions carry the exploration propensity formula's value.
- [ ] F4 re-rank never moves the wildcard; F3 fatigue applies normally after it's seen.
- [ ] Flag OFF: no wildcard, byte-identical decks.

## Metrics
Wildcard like-rate vs deck average (healthy: 30–70% of average — 0% means junk, ≈100% means taste
model is too narrow to matter), archetype graduation rate, taste-vector entropy over time (expect
exploration to hold it up).

## Risks
Wildcards read as "bad recs" — mitigated by the honest label and by gate-passing quality; rate is
config-served for instant tuning.
