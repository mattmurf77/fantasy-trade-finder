# PRD — #50 Trends page needs a "what am I looking at" explainer

**Severity:** polish · **Screen:** Trends (TrendsScreen) · **Effort:** small

## Problem
User: "It's not clear whether these are user trends or not. Best practices should have a sentence or two max explaining what's being presented on the page."

The Trends screen shows movers + a consensus-gap view, but never states **whose** data (the user's own rankings) or **what** each section measures.

## Why (research)
- Competitors carry "yours-ness" with **possessive titles** ("Your Leagues/Picks" — DynastyGM) plus a personal anchor, and hard-separate personal vs market (DynastyDealer Portfolio vs Market Hub). [research-synthesis.md #50]
- Best practice: a one-line **subtitle/dek under the title naming subject + metric + timeframe**; self-describing section headers so a user landing mid-scroll still knows whose data; empty states = **copy + visual + CTA** (not a blank chart). [NN/g, Pencil&Paper, Justinmind]
- top20 #14 has a directly reusable **"By Market / By You" basis toggle**; #09 supplies per-row "You: WR12 · Market: WR24" badges.

## Goal
Make it unmistakable, in ≤2 sentences of chrome, that Trends shows **the user's own ranking movement and where they diverge from market** — without redesigning the page.

## Decisions
1. **Title + one-line subhead.** Title → "Your Trends" (possessive). Subhead names subject + metric + timeframe, e.g. *"How your rankings have moved, and where you differ from the market."* Keep it to one or two sentences as the user asked.
2. **Self-describing section headers.** Label the two halves explicitly: e.g. "Your biggest movers" and "You vs market (consensus gap)". Each gets a ≤1-line caption if the numbers are ambiguous (e.g. "Players where your rank is higher/lower than consensus").
3. **Per-row clarity (cheap win).** On the consensus-gap rows, show the comparison in rank terms ("You: WR12 · Market: WR24") per #09, so each line self-explains.
4. **Empty state.** If there's not enough ranking history yet, show copy + a CTA ("Rank a few more players to see your trends") instead of an empty chart.
5. *(Optional, larger)* a "By You / By Market" basis toggle (#14) if we later want to show market movement too — out of scope for the explainer fix.

## Acceptance criteria
- Trends opens with a possessive title + a ≤2-sentence subhead naming whose data + what metric + timeframe.
- Both sections have self-describing headers; consensus-gap rows read in rank terms.
- A non-empty, instructive empty state when history is thin.
- No data/logic change to what's computed; `tsc --noEmit` clean; on-device read-through confirms a first-time user understands the page.

## Files (anticipated)
- `mobile/src/screens/TrendsScreen.tsx` (titles, subhead, section captions, empty state)
- possibly `mobile/src/api/` only if a row needs the market rank it doesn't already receive (check first; likely already present).

## Out of scope
The basis toggle, new trend computations, the movers data source (backlog #33 scoping is separate).
