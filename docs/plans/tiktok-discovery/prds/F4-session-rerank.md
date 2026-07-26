# PRD F4 — Session Re-rank ("bends to you in one session")

**Priority:** 4 · **Effort:** ~3d · **Flag:** `deck.session_rerank` · **Depends:** F1
**Source:** gap-analysis #6; models-research §7 (session adaptation = fresh state + re-rank of the
remaining pool, NOT mid-session retraining)

## Problem

The deck is static once generated (30-min cache; re-rank only on explicit regenerate,
server.py:5699–5714). Like three consolidation trades in a row and the deck keeps serving the
pre-computed order. TikTok's "it responds in 3 swipes" feeling — the felt personalization that IS
the activation event — never happens. This is the highest-leverage *perceptible* gap.

## Solution

TikTok's mechanism miniaturized: the deck's **remaining cards re-score after every disposition**
against a short-term session vector. No retraining, no server round-trip per swipe.

1. **Session boost vector (client-side):** over engineered attributes (shape bucket, archetype,
   centerpiece position, value band, pick involvement, partner) maintain a recency-weighted last-k
   (k≈10) vector: like +1, long-dwell-pass (>75th percentile for complexity bin) +0.3, fast pass
   −0.5, not-interested −2; weights decay ×0.8 per subsequent card.
2. **Re-rank remaining cards** after each disposition: `served_score × (1 + η·cos(attrs, boost))`,
   η≈0.3 config-served. Client-side sort of already-served candidates — instant, offline-safe.
3. **Stability guards:** the next card (peeked) never swaps under the user's thumb — re-rank applies
   from position +2 onward; likes-you pins and the F7 wildcard slot keep their positions; max 1
   reorder per disposition.
4. **Session reset:** vector dies with the deck session (hard reset on deck completion/regenerate).
   Persistent taste belongs to F5's long-τ vectors, not this.
5. Server echo: attributes per card ride the F1 `features_json` already in the generate payload —
   no new endpoint. Re-rank events log to F1 outcomes (`reranked_from`/`to` positions) so F8 can
   later measure whether bending helped.

## Acceptance criteria
- [ ] After 3 same-archetype likes, remaining same-archetype cards move measurably earlier (visible
      in logged positions), without touching the peeked next card.
- [ ] Fast-passing an archetype twice pushes its remaining cards later.
- [ ] Pinned likes-you cards and the wildcard slot never move.
- [ ] Vector state absent after deck completion or app relaunch.
- [ ] Flag OFF: deck order = served order, byte-identical.

## Metrics
Like-rate in back half of deck (expect ↑ vs static-order cohort), session completion rate,
deck-abandonment position (expect later).

## Risks
Rabbit-holing within a deck (the WSJ failure in miniature) — bounded by η, by the finite deck, and by
F7's fixed exploration slot which re-rank cannot displace.
