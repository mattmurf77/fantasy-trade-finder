# PRD F5 — Trade-Taste Vectors (long/short interest profile)

**Priority:** 5 · **Effort:** ~4d · **Flag:** `deck.taste_vectors` · **Depends:** F1
**Source:** gap-analysis #5; models-research §8 + blueprint stages 2–3

## Problem

Personalization today learns **player values** (Elo) and **package-shape appetite** (5-bucket
Thompson) — nothing else. Consolidation-vs-spread taste beyond 5 buckets, value-band appetite,
age/pick appetite, partner affinity, win-now-vs-rebuild lean: all unlearned. Declared prefs
(outlook, untouchables) are hard filters, not graded appetite. Elo learns *who* the user values;
nothing learns *what kinds of trades* they take.

## Solution

Per-user **decayed attribute-preference vectors** over engineered attributes — the Monolith
long/short interest split without embeddings.

1. **Attribute space** (~30–50 keys, from F1's frozen `features_json`): shape bucket, archetype,
   centerpiece position, give/receive value bands, age bands, pick involvement (none/mid/premium),
   partner (manager id), competitive-window alignment.
2. **Two vectors per user**, short τ=21d and long τ=180d:
   `w[a] ← w[a]·exp(−Δt/τ) + r(action)` updated synchronously on every F1 outcome (minute-level
   sync at FTF QPS = a SQL write). Rewards mirror Elo K-ratios: like +1, propose-sent +6, accept +4,
   long-dwell +0.3, pass −0.5, decline −2, not-interested −4.
3. **Storage:** `user_taste(user_id, attr, w_short, w_long, updated_at)` — lazily created rows,
   GC'd when both weights decay below ε (Monolith admission/expiry in SQL).
4. **Serving — multiplicative re-rank at generation:**
   `final = base_score × (1 + η_l·prefMatch_long) × (1 + η_s·prefMatch_short)` with prefMatch =
   normalized cosine over the card's attributes; η's config-served, start 0.2/0.3. Multiplicative =
   surplus/fairness gates stay authoritative — taste reorders good trades, never rescues bad ones.
5. **Blend with declared prefs:** vectors *modulate within* the declared-pref envelope (outlook,
   untouchables, #168-style intents when they land) — declared always wins conflicts. This is the
   learned complement to the operator's intents PRD, not a replacement.
6. **Board-derived prior (the ranks input — amended 2026-07-26):** the user's board is taste signal
   available *before a single swipe*. Initialize the long-τ vector from systematic board-vs-consensus
   deltas, aggregated per attribute: for each ranked player, `delta = user_value − consensus_value`,
   averaged over the player's attributes (position, age band, value tier, pick proxies), shrunk by
   ranked-count `w = n/(n+20)`, and scaled so a strong board prior ≈ the weight of ~10 swipes. Refresh
   the prior on board saves (the deck-cache invalidation path already fires there). Swipe-learned
   weights accumulate on top and dominate with volume — the prior is a warm start, not a ceiling.
7. **Cold vector = neutral:** a user with no board AND no swipes has an all-ε vector yielding
   multiplier 1.0 everywhere (consensus-quality deck), preserving today's cold-start behavior exactly.

## Acceptance criteria
- [ ] 20 simulated likes on pick-heavy rebuilds measurably raise pick-heavy candidates' final scores
      for that user only.
- [ ] Zero-history user (no board, no swipes): all multipliers = 1.0 (bitwise-comparable to flag-off).
- [ ] A user whose board systematically values rookie picks above consensus gets a positive pick-
      involvement prior before their first swipe; the prior refreshes after a board save.
- [ ] A March-strong signal with no reinforcement is near-neutral in short-τ by May, retained in long-τ.
- [ ] Vector never overrides untouchables/not-interested/outlook filters (test each).
- [ ] Rows GC'd below ε; table size bounded per user.
- [ ] Flag OFF: generation scoring byte-identical.

## Metrics
Like-rate and propose-rate on taste-boosted vs neutral cards (F8 replay once available), taste-vector
coverage (% of active users with ≥5 non-ε attrs).

## Risks
Feedback loop narrowing the deck onto early taste — countered by F7's exploration quota and the
partner/archetype dispersion rules already in generation; η's kept small until F8 can measure.
