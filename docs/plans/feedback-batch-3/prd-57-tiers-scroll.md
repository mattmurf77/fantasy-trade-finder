# PRD — #57 Tiers scrolling fights the drag gesture

**Severity:** bug (UX) · **Screen:** Tiers · **Effort:** small but HIGH-RISK

## Problem
Reported on v1.2.0: "Scrolling the page is a little difficult — pushing up and down has to be very light. We should explore click sensitivity/timing to allow for seamless scrolling."

The vertical scroll and the drag-to-reorder compete: a normal scroll swipe too easily lifts a row into a drag, so the user must swipe unnaturally lightly to scroll.

## Root cause
`mobile/src/screens/TiersScreen.tsx` uses `DraggableFlatList` with **`activationDistance={5}`** (~line 577). Drag activates after only 5px of finger travel, so an ordinary scroll gesture crosses that threshold and the list grabs the row instead of scrolling. Drag is intended to start from a **long-press** (`onLongPress={drag}`, ~line 399), so distance-based activation at 5px is the wrong lever — it makes any short drag steal the touch.

## Goal
Scrolling should feel native; dragging should start deliberately (long-press) and still be easy once started. Do **not** regress the drag the operator just confirmed working (ids 16/27/29/32/43).

## Decision (conservative, tune on device)
1. **Raise `activationDistance`** substantially (e.g. 12–20px) so a scroll swipe no longer trips the drag, OR rely on the long-press to gate activation and keep distance high. The library starts the drag from `onLongPress`; a higher `activationDistance` only affects how far the finger can move before the press is treated as a drag vs a scroll — higher = scroll wins more often.
2. Confirm `autoscrollThreshold`/`autoscrollSpeed` defaults still allow edge auto-scroll while dragging.
3. If raising `activationDistance` alone doesn't separate the two cleanly, consider the long-press delay so drag only begins after a clear hold; keep it ≤ the value used elsewhere so dragging doesn't feel sluggish.

This is a **one-or-two-number tuning change**, not a gesture rewrite. Resist re-architecting the gesture handler.

## Acceptance criteria
- A normal-speed vertical swipe scrolls the list without lifting a row.
- Long-press still reliably starts a drag, and an in-progress drag still reorders + auto-scrolls at the edges.
- Multiselect tap-to-select still works (no drag interference in select mode).
- `tsc --noEmit` clean.
- **On-device verification is mandatory** (this is gesture feel): scroll up/down repeatedly, then long-press-drag a row top→bottom, in both normal and multiselect modes. Record before/after behavior in the PR notes.

## Files
- `mobile/src/screens/TiersScreen.tsx` (DraggableFlatList props; possibly the row's long-press config).

## Risk / guardrails
- This is the **same gesture layer** as the recently-fixed tiers drag. If a clean separation isn't achievable with conservative tuning, STOP and report rather than risk regressing drag — flag for a follow-up with the reference-app screenshots (#58) in hand.
