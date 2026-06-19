# PRD FB4-61 — Stats on Tiers tiles + consensus/user toggle

**Feedback #61 (Tiers, polish):** "Explore adding stats to the tiles: consensus rank, 30d trend.
Maybe a setting on the top of the tiers page to toggle between consensus stats and user stats.
Same two stats for both."

## Requirement
Each player tile on Tiers shows **two stats**: a **rank** and a **30-day trend**. A toggle at the top
of the Tiers page switches both stats between **Consensus** and **You (user)**:
- **Consensus mode:** consensus rank + consensus 30d trend.
- **You mode:** the user's own rank (their position in their tiers/overall) + the user's 30d trend.

## User story
On a tile I can see "Consensus #4 ▲5 (30d)"; flipping the toggle to "You" shows my own rank + my 30d
movement for the same player — so I can compare my board to the field at a glance.

## Acceptance criteria
- [ ] A compact segmented toggle (Consensus | You) sits at the top of the Tiers page (near the
      position tabs / Select-Reset row). Default: Consensus.
- [ ] Each player tile shows the two stats (rank + 30d trend) for the selected mode, in a small,
      non-crowding treatment (the tiles are already flagged as too big in #58 — keep it tight).
- [ ] Trend renders with direction + magnitude (e.g. ▲5 / ▼3 / – ) and a green/red/neutral color.
- [ ] If a stat is unavailable for a player/mode, render a graceful placeholder ("—"), never crash.
- [ ] Toggle state is local screen state (no persistence required); both modes use the SAME two stats.
- [ ] tsc clean.

## Implementation notes — DATA FIRST
- **Before building UI, find the data source.** Check `mobile/src/shared/types.ts` (`RankedPlayer`)
  and `mobile/src/api/rankings.ts` for fields already returned: consensus rank, user rank, and any
  30-day trend/delta. The Trends screen (`mobile/src/screens/TrendsScreen.tsx`) and
  `mobile/src/api/` already compute rank deltas (FB-04 shipped "Trends as rank deltas") — reuse that
  source/shape; do NOT invent a new backend endpoint.
- If consensus-rank and/or 30d-trend fields are NOT already on the rankings payload, scope this to
  what IS available (e.g. show the available stat + a "—" for the missing one) and leave a clear
  `// FB4-61: <field> not in payload — needs backend` note. Do NOT add backend routes in this task
  (backend has uncommitted operator WIP — stay mobile-only).
- Files: `mobile/src/screens/TiersScreen.tsx` (toggle + wiring); the per-tile stats can live inline
  in the player-row render or a tiny `mobile/src/components/TileStats.tsx`. Reuse `colors` from theme
  for trend up/down/neutral. Mirror any existing trend-pill styling from TrendsScreen for consistency.
