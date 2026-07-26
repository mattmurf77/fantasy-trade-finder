# PRD F9 — First-Session Win Engineering

**Priority:** 10 · **Effort:** ~2d · **Flag:** `deck.first_session` · **Depends:** none (better with F5)
**Source:** gap-analysis #11; presentment-research §3 + principle 4 (session one is the 260-video
window; the felt "it gets me" moment IS the activation event)

## Problem

Cold-start *inputs* are strong (DP+KTC consensus seeding, shrinkage, provenance chips, outlook
inference) but nothing *engineers the first-session experience*: no guarantee a clearly-good trade
appears early, and adaptation isn't visible in session one. TikTok's cold start works because the
popularity-seeded feed makes the first minutes reliably good AND the user *feels* the feed change.
FTF's activation equivalent: first deck contains an obviously sensible trade in the first ~5 cards,
and by mid-deck the user sees evidence the deck noticed their swipes.

## Solution

1. **Confidence-weighted first-5:** for a user's first-ever deck (and first deck per league), the
   top 5 positions are drawn preferring **high-consensus-confidence** candidates — strong surplus
   margin, high-n Elo/consensus players, simple 1-for-1 or 2-for-1 shapes (parseable in ~2s per the
   presentment 3-second-hook finding). Complex 3-for-2s and thin-data players serve later.
   (TikTok's mainstream-first seeding: don't lead with the weird stuff.)
2. **Visible adaptation moment:** after the first 5+ dispositions of session one, if a clear signal
   exists (e.g. ≥3 likes sharing an attribute), surface a one-line inline card between deck cards:
   "Noticed you're liking pick-heavy deals — more of those ahead." Requires F4/F5 when available;
   without them, the moment triggers off the session tally alone and simply *describes* what was
   already generated later in the deck (honest — never claims adaptation that didn't happen).
   **Board-sourced variant (amended 2026-07-26):** when the deck was generated from a board updated
   since the user's last deck (cache invalidation already tracks this), the deck header cites it —
   "Built from your updated board" (+ count of ranked players when personal basis). Ranks are the
   user's loudest explicit input; the deck visibly honoring them is the same anti-control-theater
   rule applied to ranking. Applies beyond session one (every board-refreshed deck), still flag-gated.
3. **First-deck size guard:** first deck targets the smaller end (8–10 cards) so completion — and
   F10's completion moment — happens in session one.
4. Instrument activation explicitly: log `first_session_like_position` (position of first like) and
   session-one completion to F1.

## Acceptance criteria
- [ ] Fresh user's first deck: positions 1–5 all pass the confidence bar (margin + data-n + shape
      simplicity thresholds, config-served).
- [ ] Adaptation card renders at most once per first session, only when its trigger condition is
      literally true, and never claims un-had personalization.
- [ ] Existing users (any prior deck) see zero behavior change.
- [ ] Flag OFF: byte-identical.

## Metrics
First-session activation (≥1 like + deck completion), first-like position (expect ↓), D7 return rate
of activated vs not.

## Risks
"Simple trades first" could bore sharp users — bounded: applies to first deck only, and simple ≠
low-value (still gate-passing mutual-gain trades).
