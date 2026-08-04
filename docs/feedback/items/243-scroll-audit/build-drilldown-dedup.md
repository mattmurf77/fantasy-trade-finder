# #243 — Drill-in filter dedup, V1 (build)

Built 2026-08-03 from the operator-approved **V1 frame** of
`mockups/polish-lab-2026-08/drilldown-filter-dedup.html`, implementing the
LeagueSummaryScreen drill-in reductions from
`docs/feedback/items/243-scroll-audit/league-misc-surfaces.md` §1b
(fixes #1 chart-card control collapse, #3 hint density, #4 home-row hide).

File touched: `mobile/src/screens/LeagueSummaryScreen.tsx` only (plus this doc
and the `mobile/src/screens/CLAUDE.md` registry row).

## Change

All of the following applies **only while a team is focused** (`selected` set —
the drill-in roster panel is open). The unfocused state renders exactly as
before.

1. **Chart card → slim strip.** The card's own `SubsetControl`
   (`league-summary.subset.*`) and `PosFilterPills`
   (`league-summary.posfilter.*`) do not mount while focused. In their place a
   passive one-line caption (new testID `league-summary.filter-caption`)
   reports the active filter — "Filtered by: **All**", "Filtered by:
   **Starters · WR**", "Filtered by: **All · WR + TE + Picks**" (positions in
   canonical QB→RB→WR→TE order, Picks last) — with "— change filters below"
   pointing at the drill panel's copy, which becomes the single visible,
   interactive control set. The focused team name, "League rank: N/M" caption
   (`league-summary.focus-caption`), updated-at line, grayscale mini bar chart,
   rank pills and legend all stay.
2. **Back affordance.** The X close control is restyled as "‹ All teams"
   (chevron-left + ice label). It KEEPS testID `league-summary.roster-close`
   (identical function — clears focus — so any existing flow keeps working);
   the inner label carries the new testID `league-summary.back-all-teams`.
   `accessibilityLabel` is now "Back to all teams".
3. **Hint density (audit fix #3, focused only).** `hintTight`
   (`marginTop: xs, marginBottom: sm`) layers over the hint's normal
   `sm`/`md` margins — −8pt, focused state only.
4. **"League home" row hides (audit fix #4).** The tab-root-only `homeRow`
   renders on `isTabRoot && !selected`; it returns the moment focus clears.

## Points recovered (658pt tab-screen viewport, audit arithmetic)

| Block (focused, pre-roster) | Before | After |
|---|---|---|
| Screen top padding | 16 | 16 |
| "League home" row | 79 | 0 (hidden) |
| Basis chip row | 44 | 44 |
| Chart card — SubsetControl | 48 | 0 (not mounted) |
| Chart card — PosFilterPills | 40 | 0 (not mounted) |
| Chart card — filter caption | — | ~40 |
| Chart card — hint | 38 | 30 |
| Chart card — everything else (head, updated-at, chart, rank pills, legend, padding) | 321 | 321 |
| Drill sub-line + drill SubsetControl + PosFilterPills + list margin | 106 | 106 |
| **Total before first roster row** | **692** | **~557** |

**~135pt recovered; pre-roster content ~557pt vs the 658pt budget (~100pt
spare)** — the first roster group header (~38pt, ends ~595) **and** the first
dense PlayerCard row (~50pt, ends ~645) clear the fold, vs zero roster pixels
before. Note: the mock's headline figure (521pt / 171pt) budgeted the passive
caption at ~4pt; the real caption row (hairline well + one bodySm line +
margin) costs ~40pt, hence the honest ~557. The acceptance target — roster
rows clear the 658pt fold without scrolling — is met with margin.

## #237 preservation statement

#237's operator requirement — "both sections have the buttons and always
match" — is preserved:

- The shared state model is untouched: one `subset` + one `posFilter`,
  `togglePos`/`switchSubset` unchanged, no second/drill-local filter state was
  (re)introduced. Every change above is **visibility-only** (which mount
  points render), never state.
- **Unfocused (the state #237's requirement addresses as rendered today):**
  byte-identical rendering — chart card carries its `SubsetControl` +
  `PosFilterPills`, the home row shows, the refresh control shows. Nothing in
  the unfocused tree is behind a new condition that can be false while
  unfocused (`!selected` is always true there).
- **Focused:** the drill panel's mirrored controls
  (`league-summary.roster-subset.*` / `league-summary.roster-posfilter.*`)
  render exactly as #237 shipped them and drive the same shared state — the
  grayscale chart above still re-values/re-sorts live on every change; the
  slim strip's caption re-renders from the same state, so the two sections
  still can never disagree.
- Unfocusing (back affordance) restores today's layout exactly — the only
  mutation is `setSelectedId(null)`, same as the old X.

## testIDs

- Kept (all pre-existing IDs unchanged): `league-summary.roster-close` (now on
  the back affordance — same close-focus function), `league-summary.subset.*`,
  `league-summary.posfilter.*`, `league-summary.roster-subset.*`,
  `league-summary.roster-posfilter.*`, `league-summary.league-home`,
  `league-summary.focus-caption`, `league-summary.refresh`,
  `league-summary.updated-at`, `league-summary.bar.*`, `league-summary.team.*`,
  `league-summary.avg-line`, `league-summary.roster-picks`, basis chips.
- New: `league-summary.filter-caption` (slim-strip passive caption),
  `league-summary.back-all-teams` (back-affordance label, inside the
  roster-close Pressable).

## Verification

- `cd mobile && npx tsc --noEmit` — passes (0 errors), 2026-08-03.
- Code-level checks: home row / card controls / caption / hintTight all
  conditioned solely on `selected`; unfocused branch renders the exact
  pre-change JSX; no state, query, or handler logic touched; Chalkline only
  (existing tokens, no new hues, radius ≤ 8, ice = action on the back
  affordance).
- Not run here: on-device screenshot pass (worktree build agent, no simulator
  session) — QA should confirm the focused fold on an iPhone 15/16-class
  device: tap any bar/row → first roster group header + ≥1 player row visible
  without scrolling; tap "‹ All teams" → exact pre-#243 layout.
