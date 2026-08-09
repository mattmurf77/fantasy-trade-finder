# #273/#274/#275 — PickAssignmentScreen: future-year order fiction, sheet height, close-on-select

**Covered feedback IDs:** #273 (bug), #274 (polish), #275 (polish) —
multi-ID fix, filed under the lowest id per the folder convention.
**Branch:** worktree-agent-a20618766530621df (from `origin/main` @ ef9bbaa)
**Date:** 2026-08-09
**Status:** built; backend suite + mobile typecheck green.

## #273 (bug) — "Future years should not have draft order (27,28,29). Just picks to reassign for each round."

### The problem

Every season tab — including the three future ones (operator decision 3:
current + 3) — rendered its rounds sorted by, and labeled with, a
`round.position` slot number (`draftPosition()` / `slotLabel()`, e.g.
`"3.05"`). That number is derived from the league's ROUND-1 ORDER
(`settings.order` / `order_type`), which is real for the current season
(it is either what the league actually drafted to, or what the league has
decided it will draft to) but fictional for a future season — nobody has
drafted, or decided how they will draft, three years out. Showing a slot
number there asserts an order that doesn't exist.

### What I chose, and why

**No backend change.** `POST /api/league/pick-assignments/order`
(`backend/server.py:10790`) has no `season` parameter at all — `rounds` /
`order_type` / `order` are ONE setting for the whole board
(`backend/database.py`'s `seed_pick_grid` applies the same `order` to
`current_season .. current_season + seasons_ahead` in one loop, and
`_assignment_slots` derives every season's `slot` number off that same
single `settings.order`). There is therefore no way for a request to
"target" a future season specifically — every order-changing write already
touches the whole board, current season included — so there is nothing for
the server to validate or reject that isn't already true of an ordinary
current-season order edit. Adding a season-scoped rejection would be
inventing a distinction the data model doesn't have, which the brief
explicitly warned against ("do NOT rewrite the seeded data model").

**Client-side, in `mobile/src/screens/PickAssignmentScreen.tsx`:**

1. The order/rounds-editing entry point (the "N rounds · order — change"
   inline link that opens `SetupView`) now only renders when the active
   season tab IS the current season (`!isFutureSeasonTab`). Since editing
   order is a whole-board action with no season targeting to speak of,
   restricting where the ENTRY POINT appears is the surgical fix: a user
   looking at a future tab can no longer reach the order editor from a
   context that implies "set this year's order," because there is no such
   thing to set. The already-current-season-only unseeded-board setup flow
   is untouched.
2. A new `slotDisplayLabel()` helper is now the ONE place a slot's on-screen
   label is computed. For a slot whose `season` is past the payload's first
   (ascending) season — which the payload's own contract guarantees is the
   current season, see `pickAssignment.ts`'s `PickAssignments.seasons` doc
   comment — it renders a round ordinal (`"2nd"`) instead of a position
   (`"2.07"`), and never calls `draftPosition()`/the order at all. Wired
   into every place a slot label was rendered: the per-round grid rows, the
   owner-picker sheet's heading, the CAS-conflict sheet's row, and the
   cross-season "Traded picks" summary (which gets the season-prefixed form,
   e.g. `"2027 2nd"`, since it spans seasons).
3. Within a future-season tab, round rows are no longer sorted by
   `draftPosition()` (meaningless without a real order) — they sort by the
   opaque `original_roster_id` label instead, purely for a stable render
   order that implies nothing about draft position. The "Round N" grouping
   itself, and the "K traded / All original" round header, are unchanged —
   the brief asked for "each round as an unordered set of picks," not for
   collapsing rounds away.

Reassigning a future-season pick (`PUT
/api/league/pick-assignments/<pick_id>`) already worked before this
change and needed no fix — the bug was purely that the DISPLAY implied an
order that isn't real. Ownership assignment on a future slot is exactly
the feature; only its presentation was dishonest.

## #274 (polish) — "Half sheet should open taller to fit more of the team names"

`styles.sheetScroll` was a fixed `maxHeight: 320`, well short of a 12-team
league's picker rows (`pickerRow.minHeight` 48 × 12 = 576). Replaced the
fixed cap with a computed one: `useWindowDimensions()` reads the device's
current height, and the sheet's `ScrollView` gets
`Math.max(PICKER_ROW_HEIGHT * 3, Math.min(teams.length * PICKER_ROW_HEIGHT, windowHeight - PICKER_SHEET_CHROME))`
— i.e. it grows to fit every team's row up to what the window can actually
hold (window height minus `PICKER_SHEET_CHROME`, a fixed 260pt reserved for
the grabber, heading, subline, sheet padding, and bottom safe area), floored
so a near-empty league's sheet never reads as broken-short. A 12-team league
on a standard phone (e.g. an iPhone-class ~844pt window) now fits all 12
rows (576pt list vs. ~584pt budget); a larger league or a smaller device
still scrolls rather than overflowing off-screen. Stays a Chalkline sheet
(`styles.sheet`/`styles.grabber`/`shadowSheet` untouched) — only the list's
own height cap changed.

## #275 (polish) — "The half sheet closing after selecting a team is just a little too slow"

The owner-picker's row `onPress` previously only closed the sheet inside
`assignMutation`'s `onSuccess` (and, for the CAS-conflict branch, `onError`)
— i.e. after the round trip resolved. Now it calls `setPicking(null)`
FIRST, synchronously on tap, then fires `commitOwner(picking, t.user_id)`
against the still-valid closure. #267's existing optimistic `onMutate`
already paints the grid before the response lands, so the sheet was never
actually waiting on anything the user could see — it just looked like it
was.

`disabled={assignMutation.isPending}` was dropped from the picker rows: it
existed to stop a second tap from firing a second PUT while the sheet was
still open and waiting, which can no longer happen once the sheet closes on
the first tap.

**CAS-conflict interaction, verified by reading the flow (existing coverage
`backend/tests/test_pick_assignment.py::test_w3_09_cas_stale_token_409s_with_the_current_row`
et al. — untouched, since #275 is mobile-only):** `assignMutation`'s
`onError` still runs on a 409 exactly as before; its
`staleAssignment(err)` branch still calls `setPicking(null)` (now a
harmless no-op — the sheet closed at tap time) and then `setConflict({...})`,
which opens the SEPARATE CAS-conflict `Modal` (`visible={!!conflict}`).
Because that modal is keyed off its own `conflict` state, not `picking`,
closing the owner sheet immediately does not race or suppress it — the
conflict prompt still opens right after the (now already-gone) sheet,
carrying the other person's row exactly as before.

## Verification

- `python3 -m pytest backend/tests -q` — 2053 passed, 1 skipped, exit 0.
  Unchanged from baseline (no backend behavior touched by this fix, per the
  "no backend change" decision above — no new test was needed for a
  server route that gained no new branch).
- `cd mobile && npx tsc --noEmit` — clean, exit 0 (via the shared
  `agent-a16b8c9e20f110454/mobile/node_modules` symlink, removed after).
- Read-through of the CAS-conflict flow (see #275 above) in lieu of a live
  Maestro run — this is an express-adjacent polish batch on an already-off
  flag (`picks.assign` ships OFF); no new user-visible surface was added,
  only display/timing changes to an existing flagged screen.
