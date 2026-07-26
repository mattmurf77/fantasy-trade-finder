# PRD F1 — Signal Foundation (impression_id spine)

**Priority:** 1 (prerequisite for F2–F8) · **Effort:** ~3d · **Flag:** `deck.signal_v2`
**Source:** gap-analysis #2, #3; models-research blueprint stage 1 (Monolith online-joiner pattern)

## Problem

Today's logging cannot answer "what did the user see, in what order, and what did they do about it":

- `trade_impressions` rows are written at **generation time** (server.py:2436–2439) — a row exists for
  cards the user never reached. Served ≠ viewed ≠ decided are indistinguishable.
- `trade_decisions` and `trade_card_viewed` have **no shared key** with impressions; the only join is
  fragile asset-set equality (server.py:1986–1989).
- The Thompson multiplier drawn for each card (server.py:2106) is discarded — no propensity, so no
  off-policy evaluation (F8) and no debiased learning (F6) is ever possible on this data.
- Zero dwell capture: a 1-second pass and a 30-second inspect-then-pass produce identical rows.

This is the classic impossible-to-retrofit-later gap: every week without it is training data lost.

## Solution

Monolith's online-joiner pattern, miniaturized to SQL:

### Backend
1. **New table `deck_impressions`** — one row per card *in the served deck order*:
   `impression_id (uuid pk), user_id, league_id, deck_job_id, card_index (position), trade_hash,
   features_json (frozen at serve time), propensity (the Thompson multiplier actually drawn),
   base_score, final_score, archetype, shape_bucket, served_at`.
   Features are **frozen at serve time** — never recomputed at label time (training/serving skew).
2. **New table `deck_outcomes`** — joined by `impression_id`:
   `impression_id (fk), action (viewed|like|pass|not_interested|propose|undo), dwell_ms,
   detail_expanded (bool), calc_opened (bool), acted_at`. Late labels are fine (append-only).
3. `/api/trades/generate` response includes `impression_id` per card (behind flag).
4. Decision endpoints accept and persist `impression_id` when present; fall back to today's asset-set
   path when absent (old clients).

### Client
5. Card advance/decision events send `impression_id` + `dwell_ms` (mount→disposition timer, capped
   at 120s, paused on app-background) + `detail_expanded`/`calc_opened` booleans.
6. A `viewed` outcome fires when a card is front-of-deck ≥500ms (distinguishes served-vs-seen).

### Explicitly out of scope
Any *consumer* of this data (F2–F8). This PRD only writes it down. Existing `trade_impressions` /
Elo pipelines untouched — additive tables only.

## Acceptance criteria
- [ ] With flag ON: every served deck writes N `deck_impressions` rows with non-null propensity + position.
- [ ] Every swipe/decision writes a `deck_outcomes` row joined by `impression_id`, with dwell_ms > 0.
- [ ] Cards generated but never fronted have impressions and **no** viewed outcome (the served/viewed split).
- [ ] Undo produces an `undo` outcome; the original outcome row is retained (append-only history).
- [ ] Flag OFF: zero new rows, zero payload changes (byte-identical responses).
- [ ] Backfill/migration is additive; no changes to existing tables.

## Metrics
Row-count sanity (impressions ≥ outcomes ≥ decisions), dwell distribution by disposition (expect
pass-dwell < like-dwell), join-rate ≥ 99% on flag-ON clients.

## Risks
Dwell timer inflation from backgrounding (mitigated: pause + cap); payload size (+~40B/card, fine);
old-client mixed traffic (fallback path preserves today's behavior).
