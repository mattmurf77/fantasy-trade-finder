# #242 — "Pick a manager" sheet too short for a 12-team league

**Status: fixed (worktree branch `teardown-remediation`, pending merge) — 2026-08-02**

Operator (build 68, bug): "The pick a manager hover over window when
selecting trade with a team should have enough room to display all users
without scrolling."

## Root cause

Both manager-picker sheets (they are separate implementations of the same
pattern) hard-capped their row list at `maxHeight: 360`:

- `TradesScreen` in-screen sheet (`trades.team-picker.<user_id>`,
  `styles.teamPickerScroll`)
- `TradeFinderHubScreen` Specific-Team sheet (`finder-hub.team-picker.*`,
  `styles.pickerScroll`)

11 opponent rows at ~47pt each ≈ 517pt, so a 12-team league always scrolled
even though the sheet itself was allowed 80% of the screen.

## Fix (applied to both sheets)

- List cap removed: the ScrollView now sizes to content (`flexGrow: 0`) and
  compresses into the sheet (`flexShrink: 1`) only when content exceeds it.
- Sheet `maxHeight` 80% → 85%. Sheet+header ≈ 630pt for 11 rows, under 85%
  on modern iPhones (812pt+ → ≥690pt usable) — no scrolling; scrolling
  remains as overflow for very large leagues (14+) and small/SE screens.
- Row height untouched (~47pt, inside the 44–48pt target — no compaction
  needed).

The hub's `sheet` style is shared with the untouchables sheet, which also
just sizes to content up to the same bound — benign.

## Files

- `mobile/src/screens/TradesScreen.tsx`
- `mobile/src/screens/TradeFinderHubScreen.tsx`

testIDs unchanged.

## Verification

- `cd mobile && npx tsc --noEmit` — clean
