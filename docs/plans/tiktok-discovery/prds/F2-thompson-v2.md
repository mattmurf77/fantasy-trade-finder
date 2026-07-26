# PRD F2 — Thompson v2 (bandit hygiene)

**Priority:** 2 · **Effort:** ~2d · **Flag:** `deck.thompson_v2` · **Depends:** F1
**Source:** gap-analysis #7; models-research §5 (Deezer arXiv 2009.06546, DoorDash warm-start)

## Problem

The existing Thompson deck sampler (server.py:2095–2110) has four known-correctness defects:

1. **Priors ≈ uniform:** `Beta(1+likes, 2+passes)` starts near Beta(1,2) — wildly optimistic vs the
   observed like base rate. New arms flood decks with junk exploration. Deezer's production A/B was
   won by pessimistic priors at the base rate.
2. **No decay:** posteriors ossify. A shape the user liked in March outranks their July taste forever.
3. **No cascade handling:** cards after the session's last engagement are counted as passes when
   decks are abandoned mid-way. *Unseen ≠ negative* — the single biggest correctness bug in naive
   deck bandits.
4. **Arms too coarse:** 5 package-shape buckets only. No archetype dimension, no warm-starting.

Also: draws aren't persisted (fixed by F1's `propensity` column — this PRD consumes it).

## Solution

1. **Pessimistic priors:** `Beta(1, 1/p̂)` where p̂ = trailing-30-day global like rate (recomputed
   nightly, config knob with today's value as fallback).
2. **Posterior decay:** effective counts decay `× γ^days_since` with γ = 0.995/day (config), applied
   lazily at read time from stored (count, last_updated) — no cron mutation needed.
3. **Cascade updates:** only outcomes with a `viewed` event (from F1) update posteriors. Cards served
   but never fronted update **nothing**.
4. **Arm hierarchy:** arms become `archetype × shape_bucket`, warm-started from the parent
   shape-bucket posterior (DoorDash pattern). Arm state lazily created, TTL-expired after 120d
   inactivity (Monolith admission/expiry, in SQL).
5. Draws logged to F1's `propensity` field (already plumbed).

Multiplier stays bounded (0.5, 1.5) — this PRD changes *what feeds the draw*, not its authority.

## Acceptance criteria
- [ ] New arm's expected multiplier at zero data ≈ 1.0 with pessimistic spread (not optimistic).
- [ ] A 90-day-old strong posterior with no fresh data has measurably wider CI than a fresh one.
- [ ] Abandoned-deck tail cards produce zero posterior updates (verified via F1 join).
- [ ] Child arm with <5 observations samples near its parent's posterior.
- [ ] Flag OFF: v1 sampler byte-identical behavior.

## Metrics
Like-rate on cards ranked by v2 vs v1 (interleaved once F8 lands; until then, trailing cohort
comparison), junk-exploration rate (like-rate of bottom-quartile-propensity cards).

## Risks
γ too aggressive forgets stable tastes — start conservative (0.995); config-tunable without deploy.
