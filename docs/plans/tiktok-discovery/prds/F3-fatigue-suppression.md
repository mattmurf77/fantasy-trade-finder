# PRD F3 — Fatigue & Durable Suppression

**Priority:** 3 · **Effort:** ~3d · **Flag:** `deck.fatigue` · **Depends:** F1
**Source:** gap-analysis #9, #10; models-research §6 (LinkedIn impression discounting, WWW 2016);
presentment-research §4 (Northeastern control-theater finding — the anti-pattern to avoid)

## Problem

- Saturation caps are **league-level** (7-day cap, server.py:2044–2127) — nothing tracks what *this
  user* has repeatedly seen and ignored. The same near-duplicate concept can restack deck after deck.
- Negative steering is binary: untouchables/not-interested are hard filters (good), but there's no
  graded middle. A **decline** (strongest negative — the other manager said no, or the user killed a
  proposal) doesn't durably suppress near-duplicates. A **pass** costs the concept nothing next deck.
- Nothing in the UI ever shows the user their feedback *worked*. Northeastern's TikTok audit is the
  cautionary tale: suppression that relapses reads as control theater and erodes trust — the research
  pair's strongest convergent UX finding is "if you ship a control, make it stick, visibly."

## Solution

### Scoring layer (backend, generation-time)
1. **Impression discounting multiplier** per candidate, LinkedIn form:
   `fatigue = w₁·exp(−a·impCount) + w₂·exp(−b·daysSinceLastSeen)` — computed per user from F1's
   `deck_impressions` (viewed rows only), keyed by `trade_hash` AND by centerpiece-player, applied
   multiplicatively to final score. Items decay out gracefully and can return after cooldown.
2. **Graduated negative response:**
   - single pass → mild fatigue (above);
   - 2+ passes on same centerpiece within a session → strong session-level demotion;
   - **decline / proposal-killed → 30-day hard suppression of near-duplicates** (same centerpiece +
     same shape bucket + value band within ±10%), then ONE low-exposure retest card, then re-suppress
     if passed again;
   - not-interested / untouchable → unchanged (already hard).
3. Category-level accrual: fatigue also keyed on `archetype` so a whole shape the user keeps passing
   cools down, not just individual trades.

### Visible honoring (client)
4. When a deck was shaped by suppression, the deck header shows a one-line, dismissible note:
   "Hiding trades like the one you declined Tue — undo". Undo lifts the 30-day suppression.
5. "Refresh my deck" action in deck overflow (the FYP-reset analog): clears fatigue state (NOT
   untouchables/not-interested) and regenerates — staleness insurance, resets only the soft layer.

## Acceptance criteria
- [ ] A viewed-and-passed trade concept scores measurably lower in the next generation for that user.
- [ ] Post-decline, near-duplicates absent from decks for 30d except exactly one labeled retest.
- [ ] Suppression note renders when ≥1 candidate was suppressed; undo restores within one regenerate.
- [ ] Deck refresh clears fatigue rows for the user; hard filters unaffected.
- [ ] League-level saturation caps unchanged and still applied (this layers on top).
- [ ] Flag OFF: scoring byte-identical.

## Metrics
Repeat-near-duplicate rate per user-week (expect ↓), pass-rate trend across a session (expect flatter
— less deja-vu fatigue), suppression-undo rate (high undo = too aggressive).

## Risks
Over-suppression in small leagues can starve inventory — floor: suppression never drops candidate
pool below deck size; log when the floor engages (no silent caps).
