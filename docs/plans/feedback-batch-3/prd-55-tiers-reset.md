# PRD — #55 Tiers "Reset" button does nothing / unclear intent

**Severity:** bug · **Screen:** Tiers · **Effort:** small

## Problem
Reported on v1.2.0: "Reset button does nothing. Unclear whether it's more of an 'undo' action or a full rank reset. Either way it's a broken click."

Two issues: (a) it appears inert, and (b) its meaning is ambiguous.

## Root cause
`mobile/src/screens/TiersScreen.tsx` (~line 485–502): Reset re-runs `autoBucket(players, position, fmt)` from the current `rankingsQuery.data` (sorted by Elo) and `setBuckets(...)`.

Why it looks like "nothing happens":
- The screen typically **loads already auto-bucketed** (or from saved tier overrides that mirror the auto-bucketing), so re-bucketing from the same Elo order produces a near-identical arrangement → no visible change.
- It only mutates local `buckets` state — it neither clears the user's manual placements in an obvious way nor persists, and there's no confirmation/haptic feedback beyond `haptics.selection()`, so a no-op-looking result reads as broken.

## Goal / intended behavior
Make Reset do something **visible and well-labeled**. Define it as: **"Reset to suggested tiers" — discard my manual tier placements for this position and re-apply the app's auto-bucketing.** (Not an undo stack; a clean revert to the consensus-suggested layout for the current position.)

## Decision
1. **Rename/relabel** the control so intent is unambiguous: `Reset to suggested` (or an icon + "Reset tiers"). A short confirm is optional but recommended since it discards manual work — a lightweight `Alert.alert` confirm ("Reset {position} tiers to suggested? Your manual placements for {position} will be cleared.") is the safest.
2. **Make it actually revert:** clear any in-memory manual placement state AND mark the affected pids as cleared so a subsequent save persists the revert (mirror the existing `clearedPids` path used elsewhere in this screen). Re-auto-bucket and `setBuckets`.
3. **Feedback:** on apply, show the existing Toast (or a brief inline note) "Tiers reset to suggested" so the click visibly registers even when the layout barely changes.
4. If `rankingsQuery.data` is missing, the button should be disabled (greyed) rather than a silent no-op.

## Acceptance criteria
- Tapping Reset visibly changes state (or shows confirm → applies) and surfaces feedback every time it's pressed with data present.
- After Reset + Save, reloading the position shows the suggested tiers (manual placements gone), proving persistence.
- Disabled state when no rankings are loaded.
- Label communicates "revert to suggested," not an ambiguous "Reset."
- `tsc --noEmit` clean; verify on device: make a manual move, Reset, confirm it reverts and persists.

## Files
- `mobile/src/screens/TiersScreen.tsx` only.

## Out of scope
Multiselect, scroll/drag tuning (#56/#57), drag mechanics.
