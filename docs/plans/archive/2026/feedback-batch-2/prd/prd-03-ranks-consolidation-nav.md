# PRD FB-03 — Ranks consolidation + Rank-tab nav affordance

**Feedback:** #40, #28 (←#18) · **Surface:** mobile · **Priority:** P1

## Part A — Remove OverallRanks, rename ManualRanks → "Overall Ranks"

### Requirement
OverallRanks and ManualRanks look identical to users (#40). **Remove the
OverallRanks screen entirely** and **rename ManualRanks to "Overall Ranks"** so
the single surviving screen is the editable drag/tap board, labeled "Overall
Ranks" everywhere (rank menu, headers, nav).

### User story
As a manager, I see **one** "Overall Ranks" screen — the one where I can drag/tap
to reorder — instead of two confusingly-similar screens.

### Acceptance criteria
- [ ] `OverallRanksScreen.tsx` is deleted and removed from navigation
      (`TabNav.tsx` RankMenu + any stack registration, `RootNav.tsx`).
- [ ] The ManualRanks screen survives and is labeled **"Overall Ranks"** in: the
      Rank action-sheet menu row, the screen header/title, and any nav route
      label shown to the user.
- [ ] Any prefetch / query keys that referenced the removed screen are cleaned up
      (the Wave-1 prefetch warmed `['rankings','all']` for both — keep it for the
      surviving screen).
- [ ] No dead imports/routes remain; `cd mobile && npx tsc --noEmit` clean.
- [ ] `mobile/src/screens/CLAUDE.md` screen table updated (remove OverallRanks
      row; note ManualRanks is now "Overall Ranks").

## Part B — Rank-tab menu affordance (#28 ← #18)

### Requirement
The far-left bottom-tab ("Rank", which opens an action sheet of rank modes) gives
no visual hint that it's a menu. Add an icon/indicator making it obvious there
are multiple rank options behind it (the earlier text hint in #18 wasn't enough).

### User story
As a manager, I can tell at a glance that the far-left tab opens a menu of rank
modes (Trios, Tiers, Overall Ranks, Trends) — without having to tap it to
discover them.

### Acceptance criteria
- [ ] The Rank tab shows a clear affordance that it's a menu (e.g. a small
      chevron/▾ or a "menu/grid" glyph on/under the icon, or a distinct label),
      consistent with the app's tab-bar styling.
- [ ] Tapping still opens the existing RankMenu action sheet (unchanged behavior).
- [ ] Looks correct on the bottom tab bar (no clipping/overlap); tsc clean.

## Implementation notes
- **Owns:** `mobile/src/navigation/TabNav.tsx`, `mobile/src/navigation/RootNav.tsx`,
  `mobile/src/screens/OverallRanksScreen.tsx` (delete),
  `mobile/src/screens/ManualRanksScreen.tsx` (rename labels/title ONLY — do NOT
  change its drag logic; another feature reads its drag engine). Also
  `mobile/src/screens/CLAUDE.md`.
- The RankMenu lives in `TabNav.tsx` (items list ~`:170`). Update the labels and
  remove the OverallRanks row; ensure the ManualRanks row reads "Overall Ranks".
- Coordinate: the Wave-1 prefetch in TabNav warms `['rankings','all']` for both
  Overall+Manual — collapse to the single surviving screen.
