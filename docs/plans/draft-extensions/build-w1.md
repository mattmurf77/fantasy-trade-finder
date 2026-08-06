# Build status — W1: draft-room per-player actions + instrumentation

**Date:** 2026-08-06 · **Status:** built, gates green, flag OFF, not merged
**Spec:** [plan.md](plan.md) §4 (+ the binding design-pass corrections carried in [hld.md](hld.md) §6 RB-11/RB-12) · [lld.md](lld.md) §2.1, §2.2, §4.1
**Flag:** `draft.rank_inline` — 4-touch, **lands OFF**
**Branch:** `worktree-agent-afa6d1c4926e46d77` (worktree; merged `origin/main` clean before starting)

---

## What W1 actually was

Not a new feature. `draft.room` is **already TRUE in prod**, and the room it
gates shipped with three defects that made its stated job impossible:

1. **Undrafted rows were inert `View`s.** The one thing a user needs on the
   clock — "this guy isn't priced and I have 90 seconds" — had no gesture.
2. **Three testIDs were shared and non-unique** across every row
   (`draft-room.undrafted-row`, `.order-row`, `.pick-row`), so the flow was
   untestable, which is why (1) went unnoticed.
3. **Zero `track()` calls.** Including `draft-room.rank-rookies`, the one link
   between rookie ranking and rookie drafting, which has never reported a tap.

W1 fixes all three. (1) is behind the flag; (2) and (3) ship **unflagged** —
inert ids and telemetry are what make the flag testable and measurable at all.

---

## Delivered

### Unflagged

| Change | Where |
|---|---|
| `draft-room.undrafted-row.<player_id>` — per-player testID (D0) | `DraftRoomScreen.tsx` |
| `draft-room.order-row.<round>-<slot\|r>` · `draft-room.pick-row.<pick_no>` — same defect, same commit | `DraftRoomScreen.tsx` |
| `draft_room_rank_rookies_tapped{state, from}` on the bridge row — **this room's first-ever analytics event** | `DraftRoomScreen.tsx` |
| The bridge is **two-way**: it passes `returnTo:'DraftRoom'` + `returnLeagueId`, and `RookieRanksScreen` renders `rookie-ranks.back-to-draft` when it sees them | `DraftRoomScreen.tsx`, `RookieRanksScreen.tsx` |
| `ANCHOR_ROWS` extracted from `PickAnchorScreen` → `utils/anchorRows.ts` | both |
| `saveAnchor(pid, anchor, via?)` — third arg optional; omitting it sends today's exact body | `api/rankings.ts` |
| `POST /api/anchor/save` accepts optional `via`/`surface`, whitelist `{anchors, draft_room}`, fallback `anchors`, request-only | `server.py` |
| Four client events registered in **both** taxonomy registries | `analytics_taxonomy.py` |

### Behind `draft.rank_inline`

| Change | Where |
|---|---|
| Long-press + `accessibilityActions [{name:'menu'}]` on an undrafted row → the shipped `PlayerContextMenu` | `DraftRoomScreen.tsx` |
| **Set my value** → the new `AnchorSheet` on the shipped anchor lane, `via:'draft_room'` | `components/AnchorSheet.tsx` |
| **Rank the rookies** → the two-way bridge · **Add to targets** → the shipped asset-pref write + toast | `DraftRoomScreen.tsx` |
| Coverage nudge `draft-room.coverage-nudge` off the payload's own `undrafted[].valued` | `DraftRoomScreen.tsx` |
| Cache re-price + rank-cache invalidation on a successful anchor | `DraftRoomScreen.tsx` |

**Flag OFF ⇒ the rows are the plain `View`s they shipped as.** No handler is
even constructed (`rowActionsOn ? onRowMenu : undefined`), so both sheets are
unreachable: their targets are only ever set by the gated row handler.

---

## The binding corrections, and how each was honored

| Correction | What was done |
|---|---|
| **There is NO existing anchor sheet — BUILD one** (HLD RB-11) | Built `mobile/src/components/AnchorSheet.tsx`. Reuses the shipped **lane** (`saveAnchor`, unchanged) and the shipped **rung grid** (extracted, not copied), so no second anchor vocabulary exists. |
| **Do NOT invent a "⋯" glyph** (HLD RB-12) | Long-press **plus** the `accessibilityActions` custom action — the `TradeCard` precedent verbatim. No visible affordance was added. A glyph would need a `docs/design/components.md` spec under ADR-004/005. |
| **Anchor lane ONLY — AST + runtime test required** | Three tests, not one: AST over `save_anchor_route`'s own body; a runtime save with `save_tiers_position` booby-trapped to raise (still 200) plus a `get_tiers_saved` never-called assert; and a source scan of the W1 client files with comments stripped. See below. |
| **Taxonomy is default-deny with import-time asserts** | All four events are in `ALLOWED_CLIENT_EVENTS` **and** `CLIENT_EVENT_PROPS`, and in **neither** server registry (parametrized tests assert both directions). |
| **Per-player testIDs required** | Done, plus the two sibling ids with the same defect. |
| **Do NOT touch the tiers-save `via` whitelist** | Untouched. `_ANCHOR_VIA` is a separate module constant, and a test asserts the tiers-save members (`rookie_tiers`, `rookie_quickset`) are not in it. |

### The containment proof, in three parts

`save_tiers_position` / the merged-band `apply_tiers*` path is the one
construction in this codebase that can destroy a board, so "we didn't call it"
is pinned rather than asserted:

- **AST** — `save_anchor_route`'s `ast.FunctionDef` body names no forbidden
  symbol (`ast.Name` + `ast.Attribute` walk). Copies the shipped `test_m3_07`
  containment pattern.
- **Runtime** — `save_tiers_position` patched to raise; a real
  `POST /api/anchor/save {via: draft_room}` still returns 200, and
  `get_tiers_saved` is asserted never-called (D1's "`tiers_saved`/`all_done`
  untouched").
- **Source** — the three W1 client files, **comments stripped** (the
  `test_m3_08` docstring-exclusion precedent — a rule that fires on its own
  explanation only teaches builders to delete the explanation), contain none
  of `/api/tiers/save`, `saveTiers`, `resetTiers`, `save_tiers_position`,
  `apply_tiers`.

---

## Deliberate deviations from the LLD (with reasons)

1. **§4.1.4 "optimistic update, roll back on failure" → confirmed update.**
   A truly optimistic write needs the anchor→value mapping client-side, and
   that mapping depends on the user's stored pick-value scale (#111) and lives
   in exactly one place: the backend. Duplicating it in the app to shave a
   round-trip would fork a cross-client invariant — the precise failure class
   `docs/cross-client-invariants.md` exists to prevent. The sheet therefore
   writes the **server's returned value** into the `['draft-board', …]` cache
   on success and invalidates the rank caches; on failure nothing was written,
   so there is nothing to roll back and the sheet shows an inline error.

2. **§4.1.4 "provide undo" → correction, not undo.** An undo would have to
   restore the player's *prior* Elo, and the anchor lane has no such call —
   `saveAnchor` only takes a rung. Inventing a restore path is exactly the
   kind of new write surface W1 forbids, and guessing the prior rung from the
   displayed value is lossy. Instead the sheet **stays open after a save with
   every rung still live** and says "Tap another rung to change it", so a
   mis-tap costs one tap. The no-confirm-step requirement (D1's 3-gesture
   budget) is met exactly as specified.

3. **Files the LLD's §4.1 ownership list omitted but §4.1.4/§4.1.6 require.**
   `PickAnchorScreen.tsx` (the `ANCHOR_ROWS` extraction §4.1.4 asks for) and
   `RookieRanksScreen.tsx` (the return leg §4.1.6 asks for) are not in the
   §4.1 file list. Both changes are additive and small (an import swap; a
   param-gated row). Neither file is touched by W2 or W3. Flagged here so a
   later merge is not surprised.

---

## Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **exit 0** — 1792 passed, 1 skipped (baseline 1765 collected → 1793 with the 28 new W1 tests) |
| `cd mobile && npx tsc --noEmit` | **exit 0**, no output |

*(`mobile/node_modules` is not checked out in a fresh worktree — it was
symlinked from the main checkout to run `tsc`. Nothing tracked changed.)*

## Files changed

**Backend** — `server.py` (`_ANCHOR_VIA` + a 2-line parse + one event prop),
`analytics_taxonomy.py`, `feature_flags.py`, `tests/test_draft_extensions_w1.py` (new),
`tests/fixtures/flags/release.json`
**Config** — `config/features.json`
**Mobile** — `screens/DraftRoomScreen.tsx`, `screens/RookieRanksScreen.tsx`,
`screens/PickAnchorScreen.tsx`, `components/AnchorSheet.tsx` (new),
`utils/anchorRows.ts` (new), `api/rankings.ts`,
`.maestro/flows/rookie/d1-…`, `d2-…` (the renamed ids)
**Docs** — `api-reference.md`, `config-reference.md`, `cross-client-invariants.md`,
`glossary.md`, `business/analytics/2026-08-06-draft-room-w1-addendum.md` (new),
`mobile/src/{screens,components,utils}/CLAUDE.md`, this file

**Untouched, as instructed:** `database.py`, `ranking_service.py`,
`trade_service.py`, the tiers-save `via` whitelist, every W2/W3 file.

## Follow-ons (not W1)

- **A flag-ON Maestro flow** for the long-press → *Set my value* → rung path.
  The two existing rookie flows were updated for the renamed ids and both
  declare `draft.rank_inline OFF`; a flag-on flow needs a profile that flips
  it, which is a QA-harness change rather than a W1 build change.
- **Flip gate for `draft.rank_inline`:** that Maestro flow green, plus
  `draft_room_rank_rookies_tapped` confirming the bridge row is used at all
  (it ships unflagged, so this data starts accruing immediately).
