# PRD — #53 Show positional rank (QB1, RB4) as the prominent value

**Severity:** polish · **Screen:** Overall Ranks (ManualRanksScreen); extends to Tiers/Trends rows · **Effort:** small–medium (presentation; no engine change)

## Problem
On the manual-rank board the prominent number is **raw Elo** (e.g. 1547). The user: "Elo shouldn't be the prominent value displayed — it should be positional rank (QB1, RB4, etc.)." Raw Elo is meaningless to a fantasy manager and doesn't encode scarcity.

## Why (research)
Universal competitor precedent: positional rank is shown prominently and almost always **paired with** a value, not instead of it. DynastyGM rows read `Name — RB5, #22 — 6,261`; KTC rows carry rank + positional rank + tier + value together; FantasyPros centers positional rank + tiers. Positional rank is the right *prominent* value because FTF's decisions are position-relative (start/flex/target within a position encodes replacement level that overall rank hides). [research-synthesis.md #53]

## Goal
Make **positional rank** (QB1, RB4, `NR` for unranked) the prominent label on player rows. Keep a numeric value as **secondary** context — but on the **0–10,000 `elo_to_value` scale, not raw Elo** (ties into #54). Don't delete the number; the engine trades on it and every competitor shows both.

## Scope / decisions
1. **Compute positional rank client-side** from the already-loaded ranking set: within each position, sort by Elo desc, assign 1..N. Unranked / below-threshold → `NR`. (Backend already can serialize `pos_rank` per top20 #14 if we prefer server-side later; client-side is the cheaper first cut and needs no API change.)
2. **Row layout:** prominent = `RB4` (position-colored to match existing PositionChip palette); secondary = value on the 0–10k scale (small, de-emphasized). Overall rank (`#22`) optional as tertiary.
3. Apply first on **ManualRanksScreen** (the filed screen). Reuse the same display helper on Tiers chips and Trends rows for consistency (those can follow in the same PR or a fast-follow).
4. Add a tiny shared util `positionalRank(players, pid)` + a value-format helper (`eloToDisplayValue`) in `mobile/src/utils/` so all three screens render identically (avoids drift; mirrors the cross-client-invariants discipline).

## Acceptance criteria
- ManualRanks rows show positional rank (QB1/RB4/…/NR) as the prominent value; raw Elo is no longer the headline number.
- Secondary value renders on the 0–10k scale.
- Position color matches the existing tier/position palette (cross-client-invariant).
- `tsc --noEmit` clean; verify on device that ranks are correct per position and update live after a reorder.

## Files (anticipated)
- `mobile/src/screens/ManualRanksScreen.tsx` (row render)
- `mobile/src/utils/` new helper(s)
- possibly `mobile/src/components/PlayerCard.tsx` if the row is shared
- `docs/cross-client-invariants.md` if the value-scale display becomes a shared convention

## Dependencies / sequencing
Pairs naturally with **#54** (the 0–10k value scale) and **#58** (row density). Recommend building #53 + #54 display layer together as one "player value display" change, then #58 reflows the row. PRD kept separate so they can ship independently if needed.

## Out of scope
Changing the ranking math; server-side pos_rank (optional later).
