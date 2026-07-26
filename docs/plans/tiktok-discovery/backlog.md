# TikTok-Discovery Feature Backlog — Prioritized

*Derived from `gap-analysis.md`. Scoring: **Impact** (1–5, on the north star: trades proposed/accepted
per weekly-active user — never session minutes) × **Confidence** (0–1, evidence strength that the
mechanism transfers) ÷ **Effort** (person-days). Sequencing respects the dependency spine — F1 is
deliberately first regardless of raw score. Each item has a PRD in `prds/`. 2026-07-26.*

## The one-sentence strategy

Keep the deck format (already right), build TikTok's **logging discipline** first, then layer the
**taste-learning loop** (fatigue → session re-rank → taste vectors → learned heads) on top of the
existing generator — which becomes the *retrieval stage* of a two-stage system — while deliberately
rejecting the compulsion mechanics.

## Prioritized backlog

| P | ID | Feature | Impact | Conf | Effort | Score | Depends on | Flag |
|---|---|---|---|---|---|---|---|---|
| 1 | **F1** | Signal Foundation — impression_id spine: served/viewed/position/propensity/dwell logging, features frozen at serve time | 5 (enables everything) | 0.95 | 3d | ★★★★★ | — | `deck.signal_v2` (logging inert; can ship near-unflagged) |
| 2 | **F2** | Thompson v2 — pessimistic base-rate priors, posterior decay, cascade updates, archetype-level arms, logged draws | 4 | 0.9 | 2d | ★★★★★ | F1 | `deck.thompson_v2` |
| 3 | **F3** | Fatigue & durable suppression — per-user impression discounting, decline ⇒ 30-day near-duplicate suppression, graduated pass penalties, visible "we heard you" | 4 | 0.85 | 3d | ★★★★ | F1 | `deck.fatigue` |
| 4 | **F4** | Session re-rank — remaining deck re-scores after every disposition via last-k session boost vector ("bends to you in one session") | 5 | 0.8 | 3d | ★★★★ | F1 | `deck.session_rerank` |
| 5 | **F5** | Trade-taste vectors — per-user decayed attribute-preference vectors (shape, value band, age, picks, partner, window), short+long τ, multiplicative re-rank | 4 | 0.8 | 4d | ★★★★ | F1 | `deck.taste_vectors` |
| 6 | **F7** | Exploration slots & archetype audition — labeled Wildcard quota (~1 in 8), follower-blind new-shape audition, randomization slot feeding propensity logs | 3 | 0.85 | 2d | ★★★ | F1, F2 | `deck.exploration` |
| 7 | **F8** | Offline eval harness — replay/IPS scoring of candidate rankers on propensity logs, within-user interleaving, nightly job; gate all future ranking changes | 4 (compounding) | 0.75 | 3d | ★★★ | F1, F7 | operator tooling (unflagged) |
| 8 | **F6** | Learned acceptance heads × V-vector — calibrated P(like)/P(propose) (LR/GBT) blended as Σ P·V with hand-set V(propose) ≫ V(like); replaces hand-tuned composite *ordering* only | 5 | 0.6 | 5d | ★★★ | F1, F5, F8 | `deck.value_model` |
| 9 | **F10** | Deck replenishment ritual — completion celebration + scheduled replenishment ("new trades after waivers") + fresh-deck push via existing typed dispatcher, honest scarcity | 3 | 0.8 | 2d | ★★★ | — | `deck.replenishment` |
| 10 | **F9** | First-session win engineering — confidence-weighted first-5 cards + a visible adaptation moment in session one | 3 | 0.7 | 2d | ★★ | (better w/ F5) | `deck.first_session` |
| — | F11 | Intent knobs on generate ("looking-for" intents) | — | — | — | — | **Operator's own #168/#172 PRD** — this backlog deliberately defers to it; F5's taste vectors are the learned complement to those declared intents |

## Sequencing rationale

- **F1 first, non-negotiable.** Every TikTok lesson routes through the logging substrate (gap-analysis
  spine). It's also the cheapest-to-retrofit-now / impossible-to-retrofit-later item: Thompson already
  randomizes — we're just not writing down the propensities.
- **F2/F3 before F4/F5:** correctness fixes to the existing loop (bandit hygiene, fatigue) de-risk the
  new learning layers and are independently shippable wins.
- **F8 before F6:** the learned model only earns trust through replay evaluation — ship the harness
  before the model, per TikTok's offline-then-online discipline (and Monolith's day-by-day eval).
- **F6 is the crown but lowest confidence** (0.6): small data, and the hand-tuned composite is already
  decent. It re-*orders* only — the surplus/fairness gates stay authoritative (a bad trade can never
  be boosted into a deck, mirroring the multiplicative re-rank guardrail).
- **F9/F10 are parallel-anytime** UX wins that don't touch the ranking spine.

## Wave plan (if built via flag-gated-remediation-build)

- **Wave 1:** F1 (backend+client logging) · F10 (replenishment) — disjoint.
- **Wave 2:** F2+F7 (bandit+exploration, one owner) · F3 (fatigue) · F9 (first session) — disjoint.
- **Wave 3:** F4 (session re-rank) · F5 (taste vectors) — F4 client-heavy, F5 backend-heavy.
- **Wave 4:** F8 (eval harness) → then F6 (value model) gated on an F8 replay win.

## Guardrails (standing, from the research's failure-mode catalog)

1. **North star:** proposals-sent + matches-accepted per weekly-active user. Session minutes are a
   *cost* metric. Never optimize time-spent.
2. **No control theater:** every steering affordance (not-interested, untouchables, refresh) must
   visibly and durably change the next deck — measured, not assumed (Northeastern relapse finding).
3. **No fake-infinite inventory:** never pad decks with junk to avoid the end-state; the completion
   state is a feature (F10).
4. **Quality gates never relax for engagement:** surplus/fairness/junk-filler gates stay authoritative
   under every re-ranking layer.
5. **Label hand-boosts** (likes-you pins are labeled today — keep that bar for anything F6 boosts).
