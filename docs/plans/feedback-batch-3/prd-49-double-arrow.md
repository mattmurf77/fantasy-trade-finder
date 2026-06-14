# PRD — #49 Double ▾ cue on the Rank tab

**Severity:** bug (cosmetic) · **Screen:** bottom nav · **Effort:** trivial (~5 min)

## Problem
The Rank tab shows a down-arrow in **both** the icon (`🏈▾`) and the label (`Rank ▾`). Only one is needed. Reported on v1.2.0.

## Root cause (regression)
FB-28 (commit 21bd403, this morning) added `tabBarLabel: 'Rank ▾'` to strengthen the menu affordance — but the icon already rendered a `▾` chevron via `rankTabIcon` (added in PR #79). The two cues now stack.

`mobile/src/navigation/TabNav.tsx`:
- icon chevron: `rankTabIcon` + `styles.rankIconChevron` (~line 89–96, 298)
- label: `tabBarLabel: 'Rank ▾'` (~line 124)

## Decision
Keep **one** cue. The icon chevron is the more conventional "this fans out" signal and sits tight to the glyph; the label arrow is the redundant one. **Remove the `▾` from the label** (back to `Rank`, or omit `tabBarLabel` to use the route name). Keep the icon chevron at its FB-28 size (14).

## Acceptance criteria
- Rank tab label reads `Rank` (no arrow).
- Icon still shows the `🏈▾` chevron.
- Other tab labels unchanged.
- `tsc --noEmit` clean.

## Files
- `mobile/src/navigation/TabNav.tsx` (label only).

## Out of scope
The icon chevron itself, the menu behavior.
