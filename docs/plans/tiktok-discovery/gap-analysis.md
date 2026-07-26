# TikTok ↔ Find-a-Trade — Gap Analysis

*Compares the consolidated TikTok research (`research/tiktok-presentment.md`,
`research/tiktok-models-layer.md`) against the file:line-cited current state
(`current-state.md`, mapped at HEAD 786f63d). Verdicts: ✅ have it · 🟡 partial · ❌ missing ·
🚫 deliberately not wanted. 2026-07-26.*

## Framing

TikTok's engine is three disciplines: **(1) presentment that makes preference legible** (one item,
forced verdict, every affordance a sensor), **(2) logging discipline** (every impression joined to
its outcome, with position and propensity), and **(3) a fast learning loop** (interactions become
servable ranking changes in minutes, exploration keeps the estimator honest). FTF already has the
*rarest* piece — a per-user value model updated online (player Elo) — and, as of #156, the
intent-splitting entry point (Trade Finder Hub ≈ TikTok's multiple feeds). What's missing is almost
entirely **discipline 2** (the logging substrate) and the **taste layer** of discipline 3: nothing
learns trade-shape/partner/value-band appetite from behavior, and nothing adapts within a session.

## Mechanism-by-mechanism

| # | TikTok mechanism (evidence) | FTF today (evidence) | Verdict → gap |
|---|---|---|---|
| 1 | **One-item forced-verdict presentment** — the crown jewel (Wei) | One card + peek, swipe/buttons, optimistic advance (TradesScreen.tsx:1353–3547) | ✅ **Keep.** The format is already right; never regress to a list-first surface |
| 2 | **Impression↔outcome join with position + propensity** (Monolith online joiner; features frozen at serve time) | `trade_impressions` are *generation-time* (rows for never-seen cards), **no shared key** with `trade_decisions`/`trade_card_viewed` (join by fragile asset-set equality, server.py:1986–1989); Thompson draws not persisted (server.py:2106) | ❌ **The foundational gap.** No served-vs-viewed distinction, no clean labels, no counterfactual eval possible. Everything downstream depends on this |
| 3 | **Dwell/watch-time as the dominant implicit signal** (WSJ: watch time alone profiles a user in 36 min; D2Q duration-debiasing) | Zero dwell capture; `trade_card_viewed` logs only card-index; keep-side taps + calculator edits tracked as events but **feed nothing** (current-state §3, §7) | ❌ A 1-second pass and a 30-second inspect-then-pass are identical today — the richest untapped signal on the deck |
| 4 | **Value model: score = Σ P(action)·V(action)**, calibrated heads, hand-set V's (Algo 101) | Hand-tuned composite (harmonic mean + ~90 config knobs) + bounded multipliers; impressions/decisions tables built as "training data for the future acceptance model" that **does not exist** (server.py:2436–2439) | ❌ No learned P(like)/P(propose); ranking quality is pure hand-tuning. The V-vector discipline (V(proposal) ≫ V(like)) is also the place to encode utility-not-time-spent |
| 5 | **Per-user interest vectors, short/long decay** (attribute prefs; DIN-lite) | Player-level Elo (pairwise flat K) + a 5-bucket package-shape Beta posterior — nothing learns consolidation taste, value-band appetite, age/pick appetite, partner affinity, window taste (current-state §4) | ❌ The taste layer. Declared prefs (outlook/untouchables) are hard filters, not learned appetite |
| 6 | **Minute-level freshness → session adaptation** ("bends to you in 3 swipes" = fresh sparse state + re-rank of remaining pool) | Deck is static per job; 30-min cache; re-rank only on explicit regenerate (server.py:5699–5714) | ❌ Sessions don't bend. The remaining deck never reorders on a like/pass |
| 7 | **Bandit hygiene** (pessimistic priors at base rate, posterior decay, cascade updates, semi-personalized arms — Deezer) | Thompson exists ✅ but: Beta(1+likes, 2+passes) ≈ uniform prior; **no decay** (posterior ossifies); **no cascade handling** (never-reached cards indistinguishable from passed); arms = package shape only; draws unlogged (server.py:2095–2110) | 🟡 Right idea, four known-correctness upgrades available |
| 8 | **Exploration quota + follower-blind audition of new items** (staged pools; ~5–10% off-interest injection; exploration doubles as logging randomization) | Thompson multiplier bounded (0.5–1.5) gives incidental exploration; no explicit quota, no labeled wildcards, no archetype audition, no randomization slot (current-state §2, §7) | ❌ Deck can collapse onto early likes (WSJ rabbit hole in miniature); estimator has no exploration traffic |
| 9 | **Fatigue + impression discounting** (score × exp-decay on impCount/lastSeen; category-level cooldowns; graduated suppression windows) | 7-day league-wide saturation cap + intra-deck max-3-per-target (server.py:2044–2127) — league-level, not per-user; no per-user impression fatigue; declined concepts can restack | 🟡 Partial at league level; the per-user layer is missing |
| 10 | **Durable, visible negative steering** (Northeastern: −84% but relapses in minutes = control theater; Mozilla: gradient-only negatives fail) | Not-interested (#163) + untouchables exist as pool filters ✅ — genuinely hard, better than TikTok's | 🟡 Have the hard filter; missing the *graded* middle (decline ⇒ 30-day near-duplicate suppression; pass ⇒ fatigue) and the visible "we heard you" moment |
| 11 | **Cold start: seeded pool + fast visible adaptation + engineered early win** | Strong: DP+KTC consensus seeding, shrinkage w=n/(n+4), consensus-basis cards, provenance chip, outlook inference (current-state §6) | ✅/🟡 Foundation excellent; nothing *engineers* a great trade into the first 5 cards, and adaptation isn't visible (no "your board changed this deck" beyond the quickset diff banner) |
| 12 | **Multiple feeds frame intent** (FYP/Following/topic; tab = intent signal) | **Trade Finder Hub #156 ships exactly this** (guided/team/player/calculator + Trade DNA), ON since 2026-07-25 | ✅ Operator already there. Remaining piece = #168/#172 "looking-for intents" (operator's own acknowledged next lever — generate API exposes no intent knobs) |
| 13 | **Completion + scheduled replenishment** (deliberate divergence: a finite deck should END; honest scarcity as habit loop) | Deck-exhausted state + rank-more CTA ✅; but cadence is pull-only — no scheduled deck build, no "fresh trades" push (reengagement default-off by design), 7-day card expiry unused as a hook | 🟡 The end-state exists; the *replenishment ritual* doesn't |
| 14 | **Instant next item** (preload, <100ms advance) | Next-card peek + optimistic advance ✅; generation latency masked by progress strip | ✅ Adequate; keep under watch |
| 15 | **Offline eval before online A/B** (replay/IPS on propensity logs; interleaving at small traffic) | Experiments engine live but unused for the deck; no propensities → no replay; no holdout (current-state §7) | ❌ Blocked on #2/#7's logging; the eval muscle exists (experiments.py) but has nothing to chew |
| 16 | **Compulsion mechanics** (infinite feed, habit thresholds, time-spent objective) | Absent | 🚫 **Correctly absent — keep it that way.** North star = trades proposed/accepted per week, never session minutes |

## What FTF already does that TikTok would recognize as best-practice
Mutual-gain two-sided gating (a quality bar TikTok can't have) · likes-you injection (a true
collaborative signal) · undo-with-delayed-POST keeping the Elo stream clean · consensus fallback
that never fabricates personalization · hub intent modes · hard untouchable filters (more durable
than TikTok's own controls).

## The dependency spine

```
F1 Signal Foundation (impression_id join + viewed + position + propensity + dwell)
 ├─► F2 Bandit hygiene (priors/decay/cascade/arms)      [needs propensity+position]
 ├─► F3 Fatigue & durable suppression                    [needs per-user impression history]
 ├─► F4 Session re-rank (bends-in-one-session)           [needs dwell/disposition stream]
 ├─► F5 Taste vectors (short/long decay)                 [needs labeled outcomes]
 │     └─► F6 Learned acceptance heads × V-vector        [needs F5 features + F1 labels]
 ├─► F7 Exploration slots & archetype audition           [needs F2's propensity logging]
 └─► F8 Offline eval harness (replay/IPS, interleaving)  [needs F1+F7 logs]
F9 First-session win engineering                          [independent-ish; uses F5 later]
F10 Deck replenishment ritual                             [independent; uses notif stack]
```

Everything routes through F1. It is deliberately first in the backlog.
