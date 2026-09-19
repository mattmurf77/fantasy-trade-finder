# #203 — Add-player suggestions in the picker (v1)

**Operator:** "When making a trade offer, I'm adding a player to my side as
I'm gaining more… the UI when I hit 'add player' should suggest players that
ideally: 1. Fill a need for the team I'm trading with 2. Are closest value to
make the trade even. Interview me… if you need more clarity when only one of
these conditions can be met."
**Status:** BUILT v1 2026-07-27 (branch `teardown-remediation`, isolated
worktree). Client-only, no backend change, no flag.

## What shipped

- `mobile/src/components/PlayerPickerModal.tsx`: optional `suggested` prop —
  when present, a "Suggested" section (≤4 rows, then an "All players" label)
  renders at the top of the list. Suggested rows are the standard picker row
  plus a flare `NEED` badge (informational highlight per the design system)
  and testID `calc.picker.suggested.<player_id>`. The section hides as soon
  as a search query or position filter is active (the user is looking for
  someone specific). The rest of the picker is unchanged.
- `mobile/src/components/InLeagueCalculator.tsx` computes the list: only when
  the current trade is UNEVEN and the opened picker adds to the side
  `gap.add_to` points at. Candidates are that side's real pool (roster +
  owned picks) minus assets already in the trade.

## v1 ranking rule (documented, awaiting the offered interview)

- Primary: value-closeness to `gap.value` (|asset value − gap|).
- NEED badge: the asset's position is a roster need of the team that would
  RECEIVE it (opponent when adding to "you send", the caller when adding to
  "you receive").
- Need-fillers whose value falls inside the evener window (0.4–1.5 × gap —
  mirrors backend `_EVENER_WINDOW`) sort FIRST; outside that window,
  value-closeness wins the order and the badge stays visible.
- **Open question:** the operator explicitly offered an interview on the
  conflict rule (need vs closeness when only one condition can be met). The
  v1 rule above is a placeholder judgment — window-qualified need beats raw
  closeness, otherwise closeness wins. Revisit after that conversation.

## Need-signal source (the cheapest honest one)

- `position_needs` from `analyze_roster_strengths` is only served for the
  CALLER (`GET /api/league/preferences` profiles the session roster); no
  endpoint exposes the OPPONENT's needs. Chosen proxy: league-relative
  positional weakness from `GET /api/league/power-rankings` (consensus) —
  a position is a "need" for a team when its positional value ranks in the
  league's bottom third. The calculator already fetches that payload for the
  partner-chip summaries (same react-query key as LeagueSummaryScreen), so
  the signal costs zero extra requests and works symmetrically for both
  receiving teams. No power-rankings data (error / old server) → no badges,
  suggestions still rank by value-closeness (silent degradation).

## Verification

- `cd mobile && npx tsc --noEmit` → clean.
- Backend untouched: `python3 -m pytest backend/tests -q` → 1346 passed,
  1 skipped (branch baseline).
