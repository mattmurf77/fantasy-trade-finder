# Build status — editable rookie ranks + the seasonal Draft tab

**Date:** 2026-08-06 · **Branch:** `teardown-remediation` (worktree agent)
**Source:** two operator-directed changes from live TestFlight testing of
build 82. Not a plan wave — direct operator decisions, recorded here.

Supersedes the tab half of
[`../rookie-draft/build-placement.md`](../rookie-draft/build-placement.md)
(option A′). That document stays as history; the predicate it describes no
longer exists.

---

## Change 1 — the consolidated rookie screen is EDITABLE

### Why

`RookieRanksScreen` shipped deliberately read-only: *"a seventh drag board
would just be Overall ranks under scope."* Live testing killed that argument.
The Draft Room's bridge row is labeled **"Rank the rookies"**, it lands on
this screen, and the screen could not rank. A label that promises an action
must deliver it on the surface it lands on.

**Operator decision: make it editable.**

### What shipped

The **shipped** drag board, reused rather than reinvented — `DraggableFlatList`
with `ManualRanksScreen`'s exact interaction:

| Behaviour | Value |
|---|---|
| Pickup | `onLongPress={drag}`, `delayLongPress={220}` |
| Activation distance | `DRAG_ACTIVATION_DISTANCE` (18 — the value Tiers and Overall ranks landed on) |
| Haptics | `haptics.pickup()` on drag begin, `haptics.swipe()` on drag end (routine, not `success()` — the save hasn't happened yet) |
| Save | 600 ms debounce, one network call for a rapid-fire series of drags |
| Filtered edit | drag on the position-filtered view, splice the sub-order back into the full list |
| A11y | `moveUp` / `moveDown` custom actions on every row, wired to the same move handler — a drag-only board is unusable under VoiceOver |
| Status | `SaveIndicator` pill (`rookie-ranks.save-status`): saving… / saved / error |

The left column keeps showing the **cross-position** rookie rank even under a
position filter — that is this screen's whole point, and it updates live
during a drag from local state.

### The lane

Writes go through `POST /api/rankings/reorder` → `RankingService.apply_reorder`.

**Verified, not assumed** (`backend/ranking_service.py:1489`): `apply_reorder`
computes `valid_ids` = the posted ids that are in the pool, takes the sorted
multiset of **exactly those players' own current Elos**, and writes
`_elo_overrides` for **exactly those pids**. Nothing else is read or written.

Consequences, each pinned by a test in
`backend/tests/test_rookie_ranks_editable.py`:

- a rookie-only reorder moves nobody outside the posted subset (no vet ever
  moves, even when the vet is in the same position pool);
- the subset's Elo multiset is invariant, so tier occupancy is preserved (the
  FB #60/#69 "44 elite QBs" property);
- a scoped subset reorder lands **byte-identically** to the equivalent
  unscoped full-board reorder with only those slots permuted.

Payloads: `position: null` + every rookie id under **ALL**; `position: <POS>`
+ that position's rookie slice under a filter. `reorderRankings` still takes
no `scope` — subset-safety is why it never needed one.

### HARD CONSTRAINT — reorder lane only

This screen may **never** reach `/api/tiers/save`, `save_tiers_position`,
`apply_tiers` or the merged-band `apply_tiers_subset` path. That is the one
construction in this codebase that can destroy a user's board, and it has
done so once. Pinned by a source test following the
`backend/tests/test_draft_extensions_w1.py` pattern (comment-stripped, so the
prohibition can be explained in prose without tripping its own rule).

### Tagging

Writes carry `via: 'rookie_ranks'` (`reorderRankings`'s `via` union widened
from `'quickrank'` to `'quickrank' | 'rookie_ranks'`).

⚠️ **Request-only.** `/api/rankings/reorder` branches on `via == 'quickrank'`
and ignores every other value, so the tag reaches the request log but **not**
the `ranking_reorder` event props. Making it a real event tag needs a
`server.py` change this build deliberately did not make. The `via:'rookie_*'`
vocabulary the brief refers to belongs to the **tiers-save** lane (the
`("tiers", "quickset", "rookie_tiers", "rookie_quickset", "rookie_anchors")`
whitelist in `save_tiers_route`), which this surface is forbidden from
touching.

### testIDs

Kept: `rookie-ranks.list`, `rookie-ranks.row.<pid>`, `rookie-ranks.filter.<pos>`,
`rookie-ranks.back-to-draft` (the W1 two-way Draft Room bridge).
New: `rookie-ranks.drag-handle.<pid>`, `rookie-ranks.save-status`.

Flag: `ranks.rookie_subset` (already ON). No new flag.

---

## Change 2 — the Draft tab is a SIMPLE FLAG

### Why

Operator, verbatim:

> On the Draft tab - it should literally just be set to seasonal. So a flag we
> turn on and off to display the tab. Right now it should be on for all.

The tab shipped gated on a per-league predicate (`draft_status ===
'not_drafted' && draft_status_confidence === 'high'` **and** a bound platform
adapter) fed by an AsyncStorage snapshot that hydrated at the App.tsx boot
gate and refreshed only for the **next** launch. Two of the operator's
leagues genuinely qualified — verified server-side — and the tab still did not
appear, because the snapshot was empty on that build's first run (its storage
key had just been bumped). The launch lag is exactly what this change removes.

### New flag `draft.tab` — 4-touch, ships TRUE

| Touch | File |
|---|---|
| Registry | `backend/feature_flags.py` (`FLAG_KEYS`, default `False`) |
| Runtime | `config/features.json` → `true` |
| Mirror | `backend/tests/fixtures/flags/release.json` → `true` (test-enforced) |
| Docs | `docs/config-reference.md` |

Documented as **the seasonal on/off switch the operator flips by hand each
year**. It is never computed. No backend route reads it — client-only.

### TabNav

```ts
const [showDraftTab] = useState(
  () => !!useFeatureFlags.getState().flags['draft.tab'],
);
```

That is the entire predicate. No league qualification, no snapshot, no
confidence check, no platform check. First-mount discipline is unchanged: the
flag is read **imperatively** inside a `useState` initializer, never via
`useFlag`, so a mid-session flag revalidation cannot rewrite the navigator's
route array. A flip takes effect on the next launch.

Unchanged whether the tab is present or absent: `initialRouteName` (resolves
by NAME), #244's completion-aware Rank launch routing, #245/#246's Acquire
semantics.

### Destination

The **active league's** Draft Room. `DraftStackNav` registers one screen with
`initialParams {inTabs: true}` — no `leagueId` override, no chooser. With the
tab always on there is nothing to choose between, and `DraftRoomScreen`
renders every state honestly (drafted ⇒ recap, not-drafted ⇒ upcoming, ESPN ⇒
unsupported, no league ⇒ its no-league state), so a non-drafting league lands
somewhere truthful rather than somewhere empty.

`inTabs: true` still suppresses the screen's own `FeedbackFAB` (RootNav's
global mount covers tab screens; two FABs is the #196/#197 bug).

### Deleted

- `mobile/src/state/draftLeagues.ts` — the whole module: the predicate
  (`leagueQualifiesForDraftTab`), `hydrateDraftLeagues()`,
  `refreshDraftLeagues()`, `qualifyingDraftLeagues()`,
  `_setDraftLeaguesForTest()`, the `QualifyingDraftLeague` type and the
  `ftf_draft_leagues_v2` AsyncStorage key.
- Its two `mobile/App.tsx` call sites (the boot-gate `Promise.all` leg and the
  post-`revalidateSession` detached refresh).
- `DraftLeagueChooserScreen` + the `DraftLeaguePicker` route + the
  `draft-chooser.league.<id>` rows + their four chooser styles in `TabNav.tsx`.

**Checked before deleting:** no other consumer. The League tile and the
Acquire mode strip's Draft chip both push the root-stack `DraftRoom` directly
and never touched this module.

### Survives untouched

`DraftRoom` is still **dual-registered** — root stack (unconditional, since
M4) and the tab's stack — with ONE canonical deep-link path
(`app/league/draft-room`) pointed at the root-stack copy, so a link resolves
identically with the tab present or hidden and can never 404 on a hidden tab.

`LeagueSummary.draft_status` / `draft_status_confidence` (server-stamped
behind `draft.room`, `GET /api/sleeper/leagues/<user_id>`) still ship and are
still tested — they now have **no client consumer**. Left in place because
`backend/server.py` was out of scope; delete the field, its mapping in
`mobile/src/api/sleeper.ts`, its `LeagueSummary` keys and the four
`test_draft_board.py` placement tests together if nothing adopts it.

---

## Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **1866 passed, 1 skipped**, exit 0 (baseline 1850/1 + 16 new) |
| `cd mobile && npx tsc --noEmit` | **clean**, exit 0 |

New tests: `backend/tests/test_rookie_ranks_editable.py` (16).

## Docs updated

`docs/config-reference.md` (new `draft.tab` row) ·
`mobile/src/state/CLAUDE.md` (the `draftLeagues.ts` row rewritten as a
deletion record) · `mobile/src/navigation/CLAUDE.md` (the seasonal-tab row
rewritten) · `mobile/src/screens/CLAUDE.md` (the `RookieRanksScreen` row's
"deliberately READ-ONLY" claim replaced) · `mobile/src/shared/types.ts` +
`mobile/src/api/sleeper.ts` (dangling references to the deleted module) ·
`backend/tests/test_draft_board.py` (placement-block comments).

## What proved stale

1. **`via:'rookie_*'` on the reorder lane never existed.** The brief says
   "keep" it; `mobile/src/api/CLAUDE.md` is explicit that `reorderRankings`
   takes no scope and no rookie tag. It is added here as a request-only field
   — see the ⚠️ under Change 1.
2. **`ux.touch_polish` branching was not carried over.** The flag is ON in
   `config/features.json`; a brand-new editable surface has no legacy
   behaviour to preserve, so it uses the polished values unconditionally.
3. **No test pinned the deleted predicate.** The brief expects some; the only
   references were the `test_draft_board.py` comments (updated) and the two
   registry docs (rewritten). `leagueQualifiesForDraftTab` had no test at all.
