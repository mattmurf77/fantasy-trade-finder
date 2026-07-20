# #169 — League Summary redesign (bar chart + position filter + drill-in)

**Covered feedback IDs:** 169
**Scope shipped:** dynasty near-term slice only. The mockup's odds/projection
("Outlook odds") layer is **DEFERRED/parked** — FTF has no redraft or
win-probability value source today, so this delivers the buildable dynasty
valuation view against existing `/api/league/power-rankings` data.
**Status:** built + typecheck-clean on branch `teardown-remediation`.
**Approved mockup:** `mockups/outlook-odds/league-summary.html`.

## What was built

Redesigned `mobile/src/screens/LeagueSummaryScreen.tsx` from a plain ranked
list into the mockup's stacked bar chart:

1. **Vertical stacked bar chart** — each team is a bar row (rank numeral, name +
   You badge, a position-stacked value track, active value + chevron). The
   track is a 16px `--ink-2` well; the fill is a flex row of QB/RB/WR/TE
   segments in the position hexes (data encodings), each sized to its share so
   segments fill the track exactly. Bars scale to the league max; teams sorted
   most→least. Position legend below.
2. **Position filter** — pill row (All + QB/RB/WR/TE), single OR multi select.
   On change the chart re-values to the selected position(s) only and re-sorts
   teams live. Pure client-side transform over the per-team
   `positions[pos].value` the payload already carries — **no refetch, no
   backend change**. Zero-value-under-filter teams show an empty track + "—"
   (honest, never a fabricated bar).
3. **Basis toggle** — Consensus | My board (existing `basis` param) + a disabled
   "Redraft (soon)" chip. The client never requests `basis=redraft` (backend
   501s it).
4. **Team drill-in** — tapping a bar opens the roster overlay grouped
   QB→RB→WR→TE→Other, value-desc within group, reusing the per-team `roster`
   already returned. The overlay has its own position filter that limits the
   shown groups.

## Backend

**No backend change.** `GET /api/league/power-rankings` already returns, per
team, `positions[pos].value` (the position stack) and the value-sorted
`roster`, which is everything the filter/re-sort/drill-in need.
`basis=redraft` stays 501 (`backend/power_rankings.py` unchanged).

## Files

- `mobile/src/screens/LeagueSummaryScreen.tsx` — redesigned (bar chart,
  position filter, drill-in filter; reuses existing `BasisChip`, `groupRoster`,
  PlayerCard overlay)
- `docs/design/components.md` — added "League rankings — stacked bar chart" spec
- `mobile/src/components/CLAUDE.md` — new testID tranche (#169)
- `docs/feedback/items/169-outlook-league-summary/status.md` — this file

## New testIDs

- `league-summary.posfilter.<all|qb|rb|wr|te>` — chart position filter
- `league-summary.roster-posfilter.<all|qb|rb|wr|te>` — drill-in position filter

(existing `league-summary.basis.*`, `league-summary.team.<user_id>`,
`league-summary.roster-close` unchanged.)

## Verification

- `cd mobile && npx tsc --noEmit` → exit 0, clean.
- No backend touched → no pytest run needed.

## Deferred / parked

The odds/projection layer (redraft bars, win-probability, the "Outlook odds"
framing in the mockup title) needs a current-season projection/redraft value
model that does not exist. Redraft remains a disabled placeholder chip.
