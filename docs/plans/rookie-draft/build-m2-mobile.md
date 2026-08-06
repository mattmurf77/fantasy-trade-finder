# M2 mobile — rookie scope on the ranking surfaces

**Status: BUILT (mobile half), flag `ranks.rookie_subset` OFF** · 2026-08-06
Sources: [plan.md](plan.md) §M2 + operator decisions O1-expanded / O4 / O10 · [lld.md](lld.md) §4.2/§4.3 "Client half"
Backend half: commit `a3152d4` (`rookie-draft M2-BE: scope seam + merged-band saves + snapshot`).

## What shipped

One shared control, six surfaces, one consolidated view. No backend change (this
wave consumes the M2-BE seam exactly as delivered).

### The shared model — `mobile/src/state/rookieScope.ts`

Session-only zustand store plus the control's content and copy, in ONE file:
`SCOPE_OPTIONS` (the two segments), `CONSOLIDATED_VIEW` (the entry copy),
`scopeEmptyCopy()` (the typed-empty lines), `useRookieScope()` and the non-hook
`rookieScopeParam()`.

This is the `navigation/rankChooserModel.ts` pattern applied to a control
instead of a chooser: the six surfaces render the same component over the same
state, so they cannot diverge in labels, behaviour, testIDs or what "rookies"
means on any one page.

Session-only by design (#133 scope-pill precedent). Not persisted, not a
preference: a board filter that outlived its session would read as data loss on
the next cold start.

`rookieScopeParam()` returns `undefined` whenever the flag is off, so a scope
value left in memory can never put `?scope=` on the wire.

### The control — `mobile/src/components/RookieScopeControl.tsx`

`All players | Rookies`, #133 PositionTabs construction (hairline group, ink-3
fill, 2px underline: ice for All players — an action; flare for Rookies — the
informational-highlight accent, ADR-005, which is exactly what "you are looking
at a subset" is).

- Renders `null` with the flag off. That is the client-side kill switch, and it
  simultaneously removes the only in-app entry to the consolidated view.
- With Rookies active it carries the **"See all rookies in one list"** link —
  the operator's "reachable from any rank page as a new section" (O1-expanded),
  satisfied structurally rather than by six copies of a link.
- Exports `RookieScopeEmpty` — the shared rendering of the server's typed
  `{empty:true, reason}` response, with an always-works "Show all players"
  escape. A thin or unloaded class is a designed state, never an error state.
- `flush` drops the built-in gutter for hosts whose container already pads.

testIDs: `<surface>.scope`, `<surface>.scope-all`, `<surface>.scope-rookie`,
`<surface>.scope-consolidated`, `<surface>.scope-empty`,
`<surface>.scope-empty.all`. Surfaces: `anchors` · `tiers` · `quick-set` ·
`quick-rank` · `manual-ranks` · `trios` · `rookie-ranks`.

### API plumbing — `mobile/src/api/rankings.ts`

`getRankings` / `getNextTrio` / `getAnchorPool` take `{scope:'rookie'}` and
return `T | ScopedEmpty`. The union is deliberate: it makes every call site
handle the typed-empty branch at compile time. `splitRankings()` /
`isScopedEmpty()` do the narrowing once per screen.

`saveTiers` takes `{scope, via}`. **`reorderRankings` and `saveAnchor`
deliberately take no scope** — `apply_reorder` and `apply_anchor` are already
subset-safe (write-identity I-2), so posting the rookie subsequence is
byte-identical to the unscoped equivalent. Adding a scope there would be
inventing a second write path for no behavioural difference.

### Rollout, in plan order

| # | Surface | What scope does | Save path |
|---|---|---|---|
| 1 | **Pick Anchors** | queue narrows to rookies; composes with the #133 position pills | unchanged (`/api/anchor/save`, subset-safe) |
| 2 | **Tiers board** | board narrows; scope joins the bucket identity so a flip can't strand the other scope's unsaved layout | `{scope:'rookie', via:'rookie_tiers'}` on both save and "Reset to suggested" (a scoped clear) |
| 3 | **Quick Set** | pool narrows; **the ladder starts at the first rookie-bearing rung** | `{scope:'rookie', via:'rookie_quickset'}`; **never writes `quicksetCompletedPositions`, never fires `quickset_completed`** |
| 4 | **Overall ranks · Quick Rank** | inherit — board/step list narrow | unchanged (reorder is subset-safe) |
| 5 | **Trios** | constrains CANDIDATE SELECTION only; picks still produce full-board Elo updates | unchanged |

Trios shipped last per the plan, gated on M0's measurement
([measurement.md](measurement.md)): 85 valued rookies in the thinner format with
TE=21, so every format/position can still field a 3-candidate matchup.

### The consolidated rookie view — `mobile/src/screens/RookieRanksScreen.tsx`

Rank-stack route `RookieRanks`, deep link `app/rank/rookies`.

Reads `GET /api/rankings?scope=rookie` with **no position** — the cross-position
board through the same post-Elo view filter. That is the whole point: the values
here and the values on the position boards are synced *by construction*, not by
a sync step. It is a new SECTION over the one Elo space, not a new Elo space —
the thing the plan rejected on the merits.

Rows: cross-position rookie rank · name · position badge · team/age ·
`<POS><n> rookie` positional rookie rank · tier badge · 0–10k value. ALL/QB/RB/
WR/TE pills filter the one list client-side (no second fetch, so the
cross-position ranks stay stable while filtering).

**Read-only, deliberately.** Every editing gesture already exists on a rank
surface and all six now carry the scope, so a seventh drag board here would just
be Overall ranks under scope with a different name.

Two entry points, both flag-gated: the scope control's link (from any rank page)
and a "Rookies" section on RankHome (`rank-home.rookie-ranks`, which also flips
the shared scope so the next mode the user picks is already scoped — two doors
into one state).

## The two rules that could silently damage a board

Both are client mirrors of server invariants, and both are load-bearing.

**1. A scoped Quick Set walk must not mark the position complete (I-4).**
`quicksetCompletedPositions` feeds `state/quicksetProgress.ts`, which drives
**#244 launch routing** — a "complete" QB would route a no-pref user to Trios —
plus the Trades provenance chip and LeagueScreen's ranked count. A rookies-only
pass has not completed a position. The client-side `quickset_completed` event is
skipped for the same reason; the forensic trail for a scoped walk is the `via`
tag on each save (KD-10), which is what the board-restore procedure keys off.

**2. #161 demotion under scope (O4).** No scope branch was added, and that is
the correct answer, not an omission: the demotion set derives from
`gridPlayers`, which under scope IS the rookie subset. A scoped save therefore
demotes only rookies that were **visible and unselected**, and an unshown vet is
never touched — the rule was already bounded by what the user could see.

## Flag-off identity

With `ranks.rookie_subset` off: `useRookieScope()` reports `'all'`, `param` is
`undefined`, the control renders `null`, the RankHome section is absent, and
every query key is the pre-M2 key exactly (scope is a `'rookie'` **suffix**,
appended only under scope — which also means every existing prefix invalidation
already covers the scoped cache, with no invalidation changes anywhere).
Request URLs and `POST /api/tiers/save` bodies are byte-identical to pre-M2.

## Gates

- `cd mobile && npx tsc --noEmit` — **clean** (exit 0; the three new files are in
  the compiled set).
- Chalkline: no new colors, no emoji, no gradients; radii ≤ 8; accents limited to
  ice (actions) and flare (the informational Rookies underline).
- FeedbackFAB (#188): `RookieRanks` is a Rank-**tab**-stack screen, so it is
  covered by the RootNav global mount — no local FAB (the rule's exception list
  is modals/onboarding; a duplicate mount is the #196/#197 bug).
- Deep-link table updated (`utils/deepLinks.ts`) — URL-addressability is
  definition-of-done for a new screen.

## Not in this wave

- **Web parity** for rookie scope — plan §M7, deferred.
- **Draft Room** (M3/M4) — owned by another agent; this wave touched no
  `backend/`, no `TradesScreen`, no `TopBar`, no DraftRoom files.
- **Maestro matrix** — the 6-mode QA matrix is the batch's QA step, not this
  build's.

## QA notes for the matrix

1. Flag OFF: every rank surface renders exactly as before; no scope pills
   anywhere; `app/rank/rookies` shows the unavailable state.
2. Flag ON, scope Rookies on each of the six surfaces: only rookies appear;
   values match what the same player shows on the unscoped board (D2 by eye).
3. Quick Set under scope: walk opens at the first rung that holds a rookie;
   completing all rungs must NOT flip the position complete on LeagueScreen's
   ranked count, and a no-pref relaunch must still route to Quick Set.
4. Quick Set under scope, save a rung with picks: an unshown veteran's tier is
   unchanged after the save.
5. Trios under scope on TE (the thinnest position): a trio draws; if it ever
   can't, the typed-empty notice renders — never a spinner and never an error.
6. Consolidated view: cross-position order matches Elo order; a rookie's tier
   badge equals the badge on its position board; the position pills re-filter
   without changing the ranks.
7. Scope flip mid-edit on Tiers: unsaved placements from the other scope must
   not carry across.
