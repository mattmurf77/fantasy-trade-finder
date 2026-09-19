# FB-262 — "Can't actually rank rookies from the page"

- **Screen (as reported):** `RookieRanks` · **App version:** 1.11.0
- **Type:** bug · **Status:** **NOT REPRODUCIBLE on current `teardown-remediation`** —
  already fixed by commit `be56567` (2026-08-06), which post-dates the tester's build.
  See status.md.

---

## 1. Which surface this actually is

`RookieRanks` is a real React Navigation **route name**, not a missing file. The
feedback FAB reports `activeScreen` from the focused route, and for tab-stack
screens that value comes from RootNav's global mount
(`mobile/src/navigation/RootNav.tsx:416`, `<FeedbackFAB activeScreen={activeScreen} />`),
so the reported string is the route name verbatim.

Grep evidence (from the worktree root):

```
$ grep -rn "RookieRanks" mobile/src backend
mobile/src/navigation/TabNav.tsx:33:  import RookieRanksScreen from '../screens/RookieRanksScreen';
mobile/src/navigation/TabNav.tsx:73:    | 'RookieRanks'
mobile/src/navigation/TabNav.tsx:374:        name="RookieRanks"
mobile/src/navigation/TabNav.tsx:375:        component={RookieRanksScreen}
mobile/src/utils/deepLinks.ts:141:          RookieRanks: 'rookies',
mobile/src/state/rookieScope.ts:52:  route: 'RookieRanks' as const,
mobile/src/screens/RookieRanksScreen.tsx:108:  export default function RookieRanksScreen({ route, navigation }: any = {})
```

```
$ grep -rn "activeScreen=" mobile/src
mobile/src/navigation/RootNav.tsx:416:  <FeedbackFAB activeScreen={activeScreen} />
... (only root-stack pushes hard-code a literal: DraftRoom, MockDraft,
    PickAssignment, FreeAgents, LeagueSummary — none of them is RookieRanks)
```

So the surface is unambiguously **`mobile/src/screens/RookieRanksScreen.tsx`**,
the consolidated cross-position rookie board — the Rank-stack route `RookieRanks`,
deep link `app/rank/rookies`, flag `ranks.rookie_subset` (currently `true` in
`config/features.json:144`). It is **not** `RookieDraftBoardSheet` (the League
tile's read-only rookie board sheet) and **not** a rookie mode of `RankScreen`
(Trios); those surfaces report different `activeScreen` values.

Entry points, all present and wired to the same route constant
(`CONSOLIDATED_VIEW.route` in `mobile/src/state/rookieScope.ts:52`):

| Entry | Site |
|---|---|
| "See all rookies in one list" on every rank surface | `mobile/src/components/RookieScopeControl.tsx:115` |
| RankHome "Rookies" row (`rank-home.rookie-ranks`) | `mobile/src/screens/RankHomeScreen.tsx:222` |
| Draft Room "Rank the rookies" bridge | `mobile/src/screens/DraftRoomScreen.tsx:345-352` |

## 2. Repro (on the tester's build)

1. Sign in, open the **Rank** tab → any rank surface → scope control → **Rookies**
   → "See all rookies in one list" (or Draft Room → "Rank the rookies").
2. `RookieRanks` renders the cross-position rookie list.
3. Attempt to reorder any row — long-press, drag, tap the rank number, VoiceOver
   Move up / Move down. **Nothing happens.** There is no reorder gesture, no
   handler and no write path on the screen.

## 3. Root cause

`RookieRanksScreen` **shipped deliberately read-only** at rookie-draft M2
(commit `6da3dad`), on the design argument recorded in the build doc: *"a seventh
drag board would just be Overall ranks under scope."* The screen rendered rows,
filters, tier badges and values, and nothing else.

That decision collided with its own entry copy: the Draft Room's bridge row is
labeled **"Rank the rookies"** and lands here, and the RankHome row sells the
screen as a rookie board. A label promising an action on a surface that cannot
perform it reads to a tester exactly as reported — "can't actually rank rookies
from the page."

The tester's build is **v1.11.0 / TestFlight build 82**, which carries the
read-only screen. The report is accurate for that binary.

## 4. Fix approach — already landed, nothing to build

The operator made the screen editable on 2026-08-06 in commit **`be56567`**
("draft: editable rookie ranks + seasonal Draft tab as a simple flag"), which is
on this branch and **after** build 82. The change reused the shipped drag board
rather than inventing a seventh one — `ManualRanksScreen`'s exact interaction:

| Behaviour | Current code |
|---|---|
| Drag list | `DraggableFlatList` (`RookieRanksScreen.tsx:534`, testID `rookie-ranks.list`) |
| Pickup | `onLongPress={drag}` + `delayLongPress={DRAG_ACTIVATION_MS}` (220ms), `:352-353` |
| Activation | `activationDistance={DRAG_ACTIVATION_DISTANCE}` (18), `:544` |
| Haptics | `haptics.pickup()` on begin `:256`, `haptics.swipe()` on end `:276` |
| Save | 600ms debounce → one `POST /api/rankings/reorder`, `:212-235` |
| Filtered edit | splice the visible sub-order back into the full list, `:258-267` |
| A11y | `moveUp` / `moveDown` custom actions → `applyRankMove`, `:103-106`, `:287-310`, `:340-343` |
| Status | `SaveIndicator` pill, testID `rookie-ranks.save-status`, `:563` |
| Handles | `rookie-ranks.drag-handle.<pid>`, `:393` |

Lane: `reorderRankings(position, orderedIds, 'rookie_ranks')` →
`/api/rankings/reorder` → `RankingService.apply_reorder`
(`backend/ranking_service.py:1489`), which permutes the sorted multiset of
exactly the posted ids' own Elos and writes overrides for exactly those pids —
subset-safe, so no veteran moves. The screen may never touch the tiers-save /
merged-band path; that prohibition is pinned by
`backend/tests/test_rookie_ranks_editable.py` (16 tests, all passing).

**Verified against current code, not assumed** (see status.md §Verification):
the screen is byte-for-byte the same drag construction as the shipped
`ManualRanksScreen` (query → local `rows` → `visible` filter → `onDragEnd` →
`spliceBack` → debounced `scheduleSave` → invalidate), the route registration is
intact (`TabNav.tsx:373-380`), all three entry points resolve, `tsc --noEmit` is
clean and the regression suite is green.

**Therefore: no code change is shipped for #262.** Writing a second fix on top of
a landed one would violate the surgical-changes guideline and risk regressing a
lane whose safety story is a hard constraint. The item is closed as *fixed by
`be56567`, pending confirmation on the next TestFlight build*.

## 5. Regression coverage

Already pinned statically in `backend/tests/test_rookie_ranks_editable.py`:

- `test_the_rookie_board_uses_the_shipped_drag_list` — asserts the source
  contains `react-native-draggable-flatlist`, `DraggableFlatList`,
  `activationDistance={DRAG_ACTIVATION_DISTANCE}` and the `moveUp`/`moveDown`
  no-drag power path. **This test is exactly #262's regression guard**: if the
  board ever reverts to read-only, it fails.
- `test_the_rookie_board_writes_on_the_shipped_reorder_lane` — the screen calls
  `reorderRankings(`.
- `test_the_rookie_board_never_references_the_tiers_lane` — the hard constraint.
- `test_the_rookie_board_keeps_its_shipped_entry_points_and_testids`.

No new test is added; duplicating an existing pin adds maintenance cost without
coverage.

## 6. Maestro regression flow (for the batch QA round)

`mobile/.maestro/rookie-ranks-reorder.yaml` — runtime verification is owned by
the batch QA round, not by this agent.

```yaml
appId: com.ftf.app
---
- launchApp
# Entry: Rank tab → scope control → Rookies → consolidated view
- tapOn: { id: "tab.rank" }
- tapOn: { id: "manual-ranks.scope-rookie" }          # any rank surface's control
- tapOn: { text: "See all rookies in one list" }
- assertVisible: { id: "rookie-ranks.list" }

# The board must be non-empty (a thin/unloaded class renders RookieScopeEmpty,
# which is a designed state, not this bug — abort the run if it appears).
- assertNotVisible: { text: "Not enough valued" }

# Capture the top two rows, drag row 2 above row 1 with the shipped gesture:
# long-press (>=220ms) then drag past the 18pt activation distance.
- longPressOn: { id: "rookie-ranks.list", index: 1 }
- swipe:
    from: { id: "rookie-ranks.list", index: 1 }
    to:   { id: "rookie-ranks.list", index: 0 }
    duration: 800

# The save fires 600ms after the drag ends.
- assertVisible: { id: "rookie-ranks.save-status" }
- extendedWaitUntil:
    visible: { id: "rookie-ranks.save-status", text: "saved" }
    timeout: 8000

# Persistence: leave and return, the new order survives a refetch.
- back
- tapOn: { text: "See all rookies in one list" }
- assertVisible: { id: "rookie-ranks.list" }

# Position filter path — the same drag under a filter posts that slice only.
- tapOn: { id: "rookie-ranks.filter.rb" }
- longPressOn: { id: "rookie-ranks.list", index: 1 }
- swipe:
    from: { id: "rookie-ranks.list", index: 1 }
    to:   { id: "rookie-ranks.list", index: 0 }
    duration: 800
- extendedWaitUntil:
    visible: { id: "rookie-ranks.save-status", text: "saved" }
    timeout: 8000

# The two-way Draft Room bridge still lands on an editable board.
- tapOn: { id: "tab.draft" }
- tapOn: { id: "draft-room.rank-rookies" }
- assertVisible: { id: "rookie-ranks.back-to-draft" }
- assertVisible: { id: "rookie-ranks.list" }
```

Manual companion checks (no testID exists for cross-board sync):
1. Note a rookie's value on `RookieRanks`, open Overall Ranks → the same value.
2. Re-rank that rookie on `RookieRanks`, return to Overall Ranks → the rookie
   moved and **no veteran moved**.

## 7. Out of scope

`RookieDraftBoardSheet` (the League tile's read-only rookie board), `RankScreen`
(Trios), the tiers-save lane, and any change to `apply_reorder`.
