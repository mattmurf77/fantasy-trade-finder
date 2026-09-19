# FB-262 — status

- **Item:** #262 (bug) — "Can't actually rank rookies from the page"
- **Reported screen:** `RookieRanks` · **App version:** 1.11.0 (TestFlight build 82)
- **Branch:** `teardown-remediation` (worktree agent) · **Date:** 2026-08-08
- **Outcome:** **NOT REPRODUCIBLE on current code — no code shipped.**
  Fixed upstream by commit `be56567` (2026-08-06), which post-dates the tester's build.

---

## What shipped

**No production code.** Documentation only:

| File | Change |
|---|---|
| `docs/feedback/items/262-rookie-ranking-broken/prd.md` | new — surface identification (grep evidence), repro, root cause, why no fix is needed, Maestro regression flow |
| `docs/feedback/items/262-rookie-ranking-broken/status.md` | new — this file |

Files **read and verified unmodified**: `mobile/src/screens/RookieRanksScreen.tsx`,
`mobile/src/api/rankings.ts`, `mobile/src/screens/ManualRanksScreen.tsx`,
`mobile/src/navigation/TabNav.tsx`, `mobile/src/state/rookieScope.ts`,
`mobile/src/components/RookieScopeControl.tsx`, `backend/server.py`,
`backend/ranking_service.py`, `backend/tests/test_rookie_ranks_editable.py`.

`RookieDraftBoardSheet.tsx` was not the reported surface and was not touched.

## Why nothing was built

The tester is right about build 82: `RookieRanksScreen` shipped read-only at
rookie-draft M2 (`6da3dad`) while its own entry copy — the Draft Room's **"Rank
the rookies"** row — promised an action it could not perform.

The operator already fixed this on 2026-08-06 in `be56567` ("draft: editable
rookie ranks + seasonal Draft tab as a simple flag"), recorded in
`docs/plans/draft-extensions/build-tab-and-rookie-edit.md` §"Change 1". That
commit is on this branch; build 82 was cut before it. So on current
`teardown-remediation` the page **can** rank rookies.

Adding a second fix would mean re-editing a surface whose write path carries a
hard constraint (the reorder lane only — it may never reach
`/api/tiers/save` / `apply_tiers` / the merged-band path, the one construction
in this codebase that has destroyed a user's board). Per
`docs/coding-guidelines.md` §3 (surgical changes) the correct action is to
verify, document, and hand runtime confirmation to the QA round.

## Verification (static only — no simulator, no Maestro, no Flask)

### 1. Surface identification

```
$ grep -rn "activeScreen=" mobile/src
mobile/src/navigation/RootNav.tsx:416:  <FeedbackFAB activeScreen={activeScreen} />
mobile/src/screens/PickAssignmentScreen.tsx:858,1072,1151: activeScreen="PickAssignment"
mobile/src/screens/MockDraftScreen.tsx:507:                    activeScreen="MockDraft"
mobile/src/screens/DraftRoomScreen.tsx:763:                    activeScreen="DraftRoom"
mobile/src/screens/FreeAgentsScreen.tsx:275:                   activeScreen="FreeAgents"
mobile/src/screens/LeagueSummaryScreen.tsx:981:                  activeScreen="LeagueSummary"
```

No literal `"RookieRanks"` in a FAB prop ⇒ it came from RootNav's global mount,
i.e. the focused **route name**. That route is registered at
`mobile/src/navigation/TabNav.tsx:374-375` → `RookieRanksScreen`.

### 2. The screen is a functioning drag board on current code

`mobile/src/screens/RookieRanksScreen.tsx` — the full reorder chain is present
and matches the shipped `ManualRanksScreen` construction line for line:

| Link in the chain | RookieRanks | ManualRanks (shipped reference) |
|---|---|---|
| Drag list component | `:534` `DraggableFlatList` | `:648` |
| Pickup gesture | `:352` `onLongPress={drag}` / `delayLongPress` 220ms | `:441-442` |
| Activation distance | `:544` `DRAG_ACTIVATION_DISTANCE` | `:660` |
| Drag-end → local splice | `:269-283` `onDragEnd` → `spliceBack` | `:309-333` |
| Debounced save | `:212-235` 600ms, ref-held payload, `<2` ids skipped | `:256-288` |
| Mutation | `:183-202` `reorderRankings(pos, ids, 'rookie_ranks')` | `:230-251` |
| A11y move actions | `:103-106`, `:287-310`, `:340-343` | `:344-376`, `:418-432` |
| Server resync | `:150-153` sort by Elo desc on `ranksQuery.data` | `:157-161` |

### 3. Entry points resolve

```
$ grep -rn "CONSOLIDATED_VIEW\|rank-home.rookie-ranks" mobile/src
mobile/src/state/rookieScope.ts:51:            route: 'RookieRanks'
mobile/src/components/RookieScopeControl.tsx:115: navigation.navigate(CONSOLIDATED_VIEW.route)
mobile/src/screens/RankHomeScreen.tsx:222:       navigation.navigate(CONSOLIDATED_VIEW.route)
mobile/src/screens/DraftRoomScreen.tsx:351:      screen: 'RookieRanks'
```

Flag `ranks.rookie_subset` is `true` (`config/features.json:144`), so the control
and both in-app entries render.

### 4. The write lane is intact end to end

- Client: `reorderRankings` (`mobile/src/api/rankings.ts`) → `POST /api/rankings/reorder`
  with `X-Scoring-Format`.
- Route: `backend/server.py:7577` — accepts `position: null` (overall) and a
  position slice; requires `>= 2` ids (the client skips below that,
  `RookieRanksScreen.tsx:227-230`).
- Service: `RankingService.apply_reorder` (`backend/ranking_service.py:1489`) —
  permutes the sorted multiset of exactly the posted ids' own Elos, writes
  overrides for exactly those pids. Subset-safe; no veteran moves.

### 5. Commands run

```
$ cd mobile && npx tsc --noEmit
(no output, exit 0)

$ python3 -m pytest backend/tests/test_rookie_ranks_editable.py -q
................                                                   [100%]
16 passed in 0.14s
```

(`mobile/node_modules` is symlinked into the worktree from the main checkout so
`tsc` resolves; the symlink is gitignored and not committed.)

The 16 passing tests include `test_the_rookie_board_uses_the_shipped_drag_list`,
which is #262's standing regression guard — it fails the moment the board
reverts to read-only.

## QA checklist (batch QA round owns runtime)

Confirm on the **next TestFlight build** (build 83+, i.e. the first build cut
after `be56567`). If the tester is still on build 82, the report will still
reproduce there and that is expected — ask them to update before re-testing.

- [ ] Rank tab → any rank surface → **Rookies** scope → "See all rookies in one
      list" lands on `rookie-ranks.list`.
- [ ] Long-press a row for ~250ms → row lifts, pickup haptic fires.
- [ ] Drag it above the row before it, release → order changes on screen and
      the left-column rookie ranks renumber immediately.
- [ ] `rookie-ranks.save-status` shows "saving…" then "saved" within ~2s.
- [ ] Leave the screen and return → the new order persisted.
- [ ] Repeat under a position filter (`rookie-ranks.filter.rb`) → only that
      position's slice reorders; switching back to ALL shows the same relative
      order and **no non-rookie moved**.
- [ ] Overall Ranks (`ManualRanks`) shows the same values for those rookies and
      no veteran changed position.
- [ ] VoiceOver: focus a row → "Move up" / "Move down" custom actions present
      and functional; announcement "<name> moved to rank N".
- [ ] Draft Room → `draft-room.rank-rookies` → lands here **with**
      `rookie-ranks.back-to-draft`, and the board is draggable from that entry.
- [ ] Negative: nothing on this screen ever calls `/api/tiers/save` (watch the
      request log during the whole pass).
- [ ] Empty-class path unchanged: with a thin/unloaded rookie class the screen
      renders `RookieScopeEmpty` with the "Show all players" escape — a designed
      state, not this bug.

## Follow-up

If QA on build 83+ finds the page still cannot rank, that is a **new** defect
(gesture/library-level, not the read-only screen) and should be filed against
`RookieRanksScreen`'s drag stack with a video — the code path documented above
would then be present but non-firing, which is a different investigation.
