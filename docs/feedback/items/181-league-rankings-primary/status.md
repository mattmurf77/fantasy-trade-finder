# #181 — League rankings becomes the League tab's primary page — status

**Status: built** · 2026-07-25 · branch `teardown-remediation` worktree

Operator: the league rankings view should be the primary page when clicking the League tab, with the current default league page reachable from it.

## Approach: League tab becomes a small stack (mirrors the Trades-tab pattern)

`TabNav.tsx` gains a `LeagueStack` (same construction as `TradesStack`):

- **`LeagueRankings`** (stack root) — `LeagueSummaryScreen`, the view the tab now lands on (stacked bar chart + basis toggle + position filter + drill-in + the dark odds section). Gets a Chalkline stack header titled "League rankings"; being the stack root it has no headerLeft, so there is **no back button to nowhere**.
- **`LeagueHome`** (pushed) — `LeagueScreen`, the classic league page (hero/switcher, Matches tiles, Explore rows, activity, contrarian, coverage, leaderboards). Uses the shared always-on `HeaderBack` (#51/#52 pattern) with fallback `LeagueRankings`, covering the cold-start deep-link case.

Chosen over swapping the tab's component alone because the classic page needs to stay one tap away with sane back behavior, and the app already has two tab stacks establishing exactly this pattern — least new machinery, no RootNav changes needed.

### Entry points between the two views

- `LeagueSummaryScreen` (tab-root variant only) renders a **"League home"** row at the top (LeagueRow construction, testID **`league-summary.league-home`**) → pushes `LeagueHome`.
- `LeagueScreen`'s existing "League rankings" Explore row (testID `league.rankings-row`, unchanged) now navigates to `LeagueRankings` (returns to the stack root) instead of pushing the root-stack `LeagueSummary` on top.

### Legacy route kept functional

The ROOT-stack `LeagueSummary` route (RootNav) is untouched and still serves old entry points: deep link `app/league/summary`, stored whats-new routes, any `navigate('LeagueSummary')`. `LeagueSummaryScreen` detects its variant via `useRoute().name === 'LeagueRankings'`; the root-stack variant renders no home row and registers no re-tap handler (its RootNav `HeaderBack`, testID `league-summary.back-btn`, is unchanged).

### Deep links (v2 table, `utils/deepLinks.ts`)

`League` tab is now nested: `app/league` → `LeagueRankings` (tab root), `app/league/home` → `LeagueHome`. `app/league/summary` still resolves to the root-stack screen. Notification taps to the League tab (`league_member_joined` etc.) land on the rankings root.

### Re-tap / scroll-to-top (flag `ux.retap_active_tab`)

League tab listener now uses the Trades pattern: focused re-tap pops `LeagueHome` → `LeagueRankings`; at root it requests scroll-to-top. The `registerScrollToTop('League', …)` registration **moved from `LeagueScreen` to `LeagueSummaryScreen`'s tab-root variant** (the old registration would have clobbered the root's handler while both were mounted).

## testIDs

- All existing testIDs preserved (`league.*`, `league-summary.*`, `tab.league`).
- New: `league-summary.league-home`.
- None renamed; note the *route names* around them changed (`League` tab root screen is now `LeagueRankings`; classic page is `LeagueHome`) — Maestro flows that asserted on screen names, and analytics `screen_viewed` values, see `LeagueRankings`/`LeagueHome` instead of `League`.

## Known follow-ups (not in scope — other agents own the files)

- `RankScreen.tsx:361` streak chip navigates to the League tab expecting the leaderboards (which live on `LeagueScreen`); it now lands on the rankings root, one tap short. Fix is a one-liner: `navigate('League', { screen: 'LeagueHome' })`.
- League-kind notification taps (member joined/unlocked) also now land on rankings rather than the members surface; acceptable per "rankings is primary", revisit if testers object.

## Verification

- `cd mobile && npx tsc --noEmit` — clean (exit 0).
- Backend untouched by this item; suite green via #183's run (1047 passed, 1 skipped).
- Docs updated: `docs/design/components.md` (League rankings spec: tab root + League home row), `mobile/src/navigation/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`.

---

# 2026-07-26 — League Analyzer replication (DynastyGM teardown)

**Status: built** · branch `teardown-remediation` worktree · spec
`docs/business/product/2026-07-26-dynastygm-app-teardown.md` ("Replication
scope"), plus two operator amendments applied mid-build: (1) starters/bench
are DERIVED, not ingested; (2) tercile-colored positional-rank chips.

## What changed

### 1. Vertical stacked bar chart (replaces the horizontal track rows)

`LeagueSummaryScreen` rebuilt around a chart card: VERTICAL position-stacked
columns, x-axis = rank 1..N (numerals under each bar, the caller's numeral in
an ice pill), bars scaled to the league max, rounded tops (`--r-sm`). Card
header carries league name + "Dynasty · <format>" caption (from
`scoring_format`: `1qb_ppr` → "1QB PPR", `sf_tep` → "SF TEP"), the
"Updated <relative>" line (testID unchanged), and a refresh icon (pull-to-
refresh stays). Position filter pills restyled to colored outline pills
(selected = solid fill in the position hex, ink-0 text). Below the chart:
ranked team list rows (rank numeral · name + You badge · value · chevron;
caller's row surface-highlighted) keeping testID `league-summary.team.<user_id>`.
Basis toggle, League-home row, odds section (dark), deep links: untouched.

### 2. All · Starters · Bench — DERIVED value-optimal lineup (amendment 1)

Per the operator amendment, NO lineup-array ingestion and NO new storage
(an earlier in-progress `league_members.starters_data` column + Sleeper
`rosters[].starters` ingestion was built and then fully reverted). Instead:

- `backend/power_rankings.py` — `optimal_starters(roster, lineup_slots)`:
  fills the league's starting-slot template with each team's highest-value
  eligible players. Dedicated QB/RB/WR/TE slots first (top-N by value), then
  flex slots narrowest-eligibility-first (`WRRB_FLEX`/`REC_FLEX` → `FLEX` →
  `SUPER_FLEX`); eligibility map `LINEUP_SLOT_ELIGIBILITY`; K/DEF/IDP/BN/IR/
  TAXI slots ignored (out of the value pool); deterministic (value desc,
  player_id asc); unfillable slots left empty, never padded. Preseason-
  correct (no per-week data) and **basis-aware**: computed from the same
  values being ranked, so a personal board reshapes the split.
- `compute_power_rankings(..., lineup_slots=None)` — each team gains
  `starters: [pid,...] | None` (None when no template). Additive.
- `backend/server.py` — `_sleeper_lineup_slots(league_id)`: Sleeper
  `roster_positions` filtered to pool-fillable slots, via the existing #179
  15-min league-meta cache (`_FA_LEAGUE_META_CACHE`) — **no schema change,
  no new fetch in steady state**; None for non-Sleeper ids (ESPN/MFL/
  Fleaflicker/demo) or meta failure. `/api/league/power-rankings` passes it
  through and adds top-level `starters_available` (all teams have a list AND
  ≥1 non-empty).
- Client: segmented control `league-summary.subset.<all|starters|bench>` on
  the chart card, rendered ONLY when `starters_available` — hidden = today's
  All-only behavior (honest degradation). Selecting Starters/Bench recomputes
  every team's per-position values from that subset client-side and re-ranks
  the whole chart; the caller's highlight follows; the drill-in filters to
  the same subset and its group totals/ranks recompute. Picks are neither
  starters nor bench: the Picks pill/segment/section exist only in All (a
  stale PICKS selection is stripped on subset switch).
- **Naming note (operator rule):** the control says "Starters" — Starters IS
  the value-optimal lineup by construction, so a separate "Optimal" mode is
  deliberately not built.
- **MFL/ESPN/Fleaflicker degradation:** platform imports have no Sleeper
  meta → no slot template → `starters:null`, `starters_available:false`,
  control hidden. (MFL's link bundle carries rosters but not a cheap,
  reliable lineup template — not wired; degrade instead, per spec.)

### 3. Drill-in focus treatment

Tapping a team (bar `league-summary.bar.<user_id>` or list row): its bar
keeps full position colors, every other bar switches to muted-gray segments
(existing tokens only — QB `chalk.dim`, RB `ink.lineStrong`, WR
`chalk.faint`, TE `ink.line`, Picks `ink.ink3` — one distinct step per
position). Card caption swaps to team name + "League rank: N/M" (rank under
the ACTIVE subset/filter ordering); X restores (testID
`league-summary.roster-close`, unchanged). The roster panel now renders
**inline below the chart** instead of a Modal — required so the grayscale
chart stays visible above it (the DynastyGM presentation); open/close
behavior and all drill-in testIDs are preserved. Group headers show
"(count) · positional total · rank/M" with the rank chip **tercile-colored**
(amendment 2: top third `semantic.pos`, middle `semantic.warn`, bottom
`semantic.neg`; a11y label "POS ranked N of M"; position hex stays on the
position label only). Player rows show league-wide positional value ranks
("RB2" via PlayerCard's existing `posRank` prop; zero value → "NR"),
computed client-side from the payload's per-player roster values under the
active subset.

## Payload shape chosen

Per-team `starters: [player_id] | null` + top-level `starters_available`
(vs server-computed per-position splits): keeps the payload small and the
client math trivial (bench = roster rows ∉ starters set; per-position sums
from roster rows the payload already carries), and one list serves the
chart re-rank, the drill-in subset, and the positional-rank computations.

## Files

- `backend/power_rankings.py` — `LINEUP_SLOT_ELIGIBILITY`, `optimal_starters`,
  `lineup_slots` param + per-team `starters`
- `backend/server.py` — `_sleeper_lineup_slots` + route passthrough +
  `starters_available`
- `mobile/src/api/league.ts` — `PowerRankedTeam.starters`,
  `PowerRankingsResponse.starters_available`
- `mobile/src/screens/LeagueSummaryScreen.tsx` — full chart/list/drill-in
  rebuild (odds section, basis toggle, home row, FAB logic untouched)
- `backend/tests/test_power_rankings.py` — 12 new tests
- Docs: `docs/api-reference.md` (payload additions),
  `docs/design/components.md` (League rankings spec rewritten),
  `mobile/src/components/CLAUDE.md` (new testID tranche). `docs/data-dictionary.md`
  intentionally untouched — the amendment removed the storage change.

## testIDs

- New: `league-summary.bar.<user_id>` (the task sheet said
  `league-summary.bar.<roster_id>` — the power-rankings payload keys teams
  by `user_id`, not roster_id, so the team identifier is user_id),
  `league-summary.subset.<all|starters|bench>`, `league-summary.refresh`,
  `league-summary.focus-caption`.
- All pre-existing ids preserved (see the components/CLAUDE.md tranche);
  `league-summary.roster-close` now closes the inline focus instead of a
  Modal — flows that tap team → assert roster → tap close still pass.

## Verification

- Backend: `python3 -m pytest backend/tests -q` → **1198 passed, 1 skipped**
  (baseline before this change: 1186 passed, 1 skipped; +12 new tests in
  `test_power_rankings.py`: optimal-lineup fill/flex/degradation, derived
  starters per basis, bench re-ranking flip, route `starters_available`
  true/false, `_sleeper_lineup_slots` filtering).
- Mobile: `cd mobile && npx tsc --noEmit` → exit 0 (typechecked via the main
  repo's `mobile/node_modules` symlink; the worktree has no local install).

## Trimmed / deferred (honest)

- "Optimal" as a fourth segment — per spec, later (and redundant today:
  Starters = optimal by construction).
- MFL lineup wiring — degrades (control hidden) rather than wiring the MFL
  starting-lineup export; revisit if MFL leagues need the split.
- Per-player positional ranks are league-wide within the active subset
  (bench view ranks bench players against bench players) — documented
  choice; DynastyGM's exact semantics unverifiable from the recording.
