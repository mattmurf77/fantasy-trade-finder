# PRD F6 — Learned Acceptance Heads × V-Vector

**Priority:** 8 (build LAST of the ranking spine; gated on an F8 replay win) · **Effort:** ~5d ·
**Flag:** `deck.value_model` · **Depends:** F1, F5, F8
**Source:** gap-analysis #4; models-research §2 (Algo 101 value function), §1 (log-odds calibration)

## Problem

Deck ordering is a hand-tuned composite (~90 knobs) — the impressions/decisions tables were built
as "training data for the future acceptance model" (server.py:2436–2439) and that model was never
built. TikTok's ranking core is the opposite: **learned calibrated P(action) heads, hand-set
V(action) values** — ML predicts, the business chooses what to want. FTF has the labels (soon clean,
via F1), the features (F5's vectors + Elo + card attributes), and the eval harness (F8). This is
the crown of the spine — and deliberately last, because the hand-tuned composite is already decent
and small-data models earn trust only through replay.

## Solution

1. **Two calibrated heads** (LR or small GBT — explicitly no neural rankers at this scale):
   - `P(like | user, card)` — trained on F1 viewed→like/pass outcomes;
   - `P(propose | user, card, liked)` — the scarcer, higher-value head.
   Features: card attributes (frozen features_json), F5 short+long taste-match scores, Elo-derived
   value deltas, surplus/fairness margins, partner history, session position. Calibration via Platt
   /isotonic, checked by F8's reliability tables; if negatives are downsampled, apply the Monolith
   log-odds correction so probabilities stay honest.
2. **The V-vector — the strategy layer, hand-set and documented:**
   `rank_score = P(like)·V_like + P(like)·P(propose|like)·V_propose` with `V_propose ≫ V_like`
   (start 6:1, mirroring Elo K-ratios). This is where *utility-not-time-spent* is encoded — the
   deliberate objective divergence from TikTok. V's live in model_config, changeable without
   retraining (rules outside the model).
3. **Scope of authority — ordering only:** the learned score replaces the hand-tuned composite as
   the *base ordering* input; surplus/fairness/junk gates, F3 fatigue, F5 multipliers, F7 wildcard,
   dispersion rules all stay authoritative on top. A bad trade can never be boosted into a deck.
4. **Training cadence:** nightly batch refit (cron) — freshness matters less than F2–F5's online
   layers because taste drift is already absorbed there; the model learns slower structure.
5. **Rollout:** F8 replay win (adequate ESS) → interleaving win → flag ON. Fallback to composite on
   any scoring error (never a failed deck).

## Acceptance criteria
- [ ] Heads beat the composite on F8 replay (both targets) with reported ESS before any live traffic.
- [ ] Reliability tables: predicted deciles within ±20% relative of observed.
- [ ] Zero-history users fall back to composite ordering exactly (cold-start unchanged).
- [ ] Gates/pins/wildcard behavior unchanged under the new ordering (test each).
- [ ] Kill-switch: flag OFF or scorer exception ⇒ composite path, no user-visible failure.

## Metrics
Propose-rate per deck (north star) via interleaving; like-rate secondary; calibration drift monitored
nightly.

## Risks
Small data (propose events are scarce) — mitigated: propose head conditions on like, nightly refit
on all history, and the gate means we simply don't ship until replay says it wins. Feedback loops —
mitigated by F7's permanent exploration traffic.
