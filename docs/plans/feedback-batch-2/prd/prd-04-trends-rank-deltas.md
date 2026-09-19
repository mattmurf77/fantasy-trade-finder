# PRD FB-04 — Trends as rank deltas

**Feedback:** #31 · **Surface:** mobile + backend · **Priority:** P2 (idea/feature)

## Requirement
The Trends screen currently expresses movement and "easiest sells/buys" as ELO
deltas. Represent them instead (or additionally) as **rank changes** — the +/-
movement of a player's position in both the **overall** rank set and the
**positional** rank set — which is more intuitive than raw ELO.

## User story
As a manager checking Trends, I see that a player moved e.g. "▲3 overall, ▲1 at
RB" rather than an opaque ELO number, so I immediately understand how my ranking
of them shifted and which are the easiest buys/sells by rank.

## Acceptance criteria
- [ ] Risers/fallers rows show a **rank delta** (overall and positional), with a
      clear up/down direction, instead of (or alongside, clearly labeled) the ELO
      delta.
- [ ] "Easiest sells/buys" (contrarian gap) rows express the gap as a **rank
      difference** (your rank vs the comparison rank) where meaningful.
- [ ] Positional rank is shown per the player's position (RB rank, WR rank, …).
- [ ] If historical rank can't be derived for a player (insufficient history),
      the row degrades gracefully (no crash, sensible "—").
- [ ] Backend (if changed) keeps existing Trends endpoints backward-compatible;
      `python3 -m pytest backend/tests/ -q` green; mobile tsc clean.

## Implementation notes
- Today `trends_service.py` computes ELO deltas (current_elo vs previous_elo) and
  the contrarian gap. Converting to rank requires deriving each player's rank
  (overall + within-position) at the current and previous points. Prefer
  computing ranks from the ranking the backend already has (sort by ELO →
  position index); "previous rank" needs the prior snapshot (`elo_history` may
  provide previous ELOs → derive previous rank by sorting that snapshot).
- **Owns:** `mobile/src/screens/TrendsScreen.tsx`, `backend/trends_service.py`,
  and the Trends route in `backend/server.py` ONLY IF the response shape must
  change (keep it additive/back-compatible). Add fields like `overall_rank`,
  `overall_rank_delta`, `pos_rank`, `pos_rank_delta` to the row shapes
  (`mobile/src/shared/types.ts` `TrendRow` / `ContrarianGapEntry`).
- Do not alter ELO math; rank is a derived presentation of existing ELOs.
- NOTE (orchestration): this is the one feature that may touch `backend/server.py`
  alongside FB-01. Each runs in its own worktree; the regions are disjoint
  (Trends route vs disposition route) and merge cleanly — but keep the route
  change minimal/additive.
