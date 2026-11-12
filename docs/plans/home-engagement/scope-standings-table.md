# Feature Scope — Standings as one sortable table

**Date:** 2026-11-12
**Entry point:** direct ask (operator, 2026-11-12): "explore a version of the standings page that doesn't need the current and projected tabs … include a Max PF column … make the columns sortable"; after the mockups: "one row. W-L, Projected W-L, Playoff Odds %. A pill in the top right of the table to toggle to Points summary. That changes the columns to 'PF', 'Max PF', 'Proj Max PF'"; on the open team: "a stronger, higher contrast border … to focus on the expanded card" (outlined card, treatment B, not objected to).
**Builder:** builder agent on `feat/standings-single-table` (stacked on `feat/league-rankings-playoff-tile` + `fix/projection-drop-fa-fill-line`)
**Operator sign-off on waivers:** not needed (no waivers beyond the template's dead Maestro / simulator sections, per `docs/CLAUDE.md`)

Design references (made-up data, not code): `standings-final.html` (Record view, Points view, no-forecast state) and `index.html` treatment B (the outlined open team), handed to the builder by the coordinating session.

---

## What changes

`mobile/src/screens/StandingsScreen.tsx` (route `Standings`, root-stack push under `LeagueTopBarHeader`) drops its Current | Projected segments and becomes ONE table:

| | Record (default) | Points |
|---|---|---|
| Columns | W–L · Proj. W–L · Playoffs | PF · Max PF · Proj. Max PF |
| Opens sorted by | W–L, best first (PF breaks ties) | PF, most first |
| Source | W–L, PF, Max PF: Sleeper rosters (`settings.wins/losses/ties/fpts/ppts`); Proj. W–L (`modal_record`), Playoffs (`playoff_probability`), Proj. Max PF (`maxpf_mean`): the saved weekly forecast | |

- Every heading sorts, Team included; the active heading reverses on a second tap; the active heading is ice with an arrow; each view keeps its own sort while the screen is mounted. Ties keep standings order; dashes sort last in both directions (`utils/standingsTable.sortRows`).
- Playoffs is a whole percent: "<1%" under 0.5%, "100%" from 99.95%, else 1–99%. Points are whole with thousands commas.
- The open team (one at a time; closes on a view or league switch) is an outlined card: 1pt ice border, radius 8, `ink2`, 8pt gap above and below, name semi-bold, chevron ice. Inside: what the view leaves out, the average final record (`expected_record`) with bye odds where the league has byes, then Final record odds, Weekly projections and Draft pick odds (moved from `LeagueProjectionSection`, text unchanged; indented with `ink3` separators).
- No forecast (Sleeper league without a saved run, flag `league.projections` off, or a read failure): the table still shows and sorts W–L, PF and Max PF (Sleeper's `ppts`; a dash where Sleeper sent none); Proj. W–L, Playoffs and Proj. Max PF are dashes; one line under the table: "Projections aren’t available for this league yet." plus the existing status sentence where a state applies (waiting for the first weekly forecast, update due, rules not supported, couldn’t check), with Check for update (a re-read).
- With a forecast, the old Projected status line (Weekly estimate / Last saved: date · Incomplete · Partial Sleeper data · Provisional, the status sentence and the incomplete sentence) sits directly under the table.
- Non-Sleeper leagues keep the "can’t read this league’s standings yet" card. Before week 1 with no forecast, the page says no games have been played instead of ranking a league-wide tie.
- `LeagueProjectionSection` is retired (nothing else mounted it); its detail moved to `components/LeagueProjectionDetail.tsx`, its status words to `utils/standingsTable.ts`.

**No simulation from this page.** The page reads the saved forecast on `['league-projection-batch', userId, leagueId]` (shared with Home's and League rankings' playoff tiles), a GET of a stored weekly result. The old path that ran `/api/league/outlook` (10,000 sims) while Projected was selected and `league.projections` was off is **removed from Standings**: with batch projections off the page shows the no-forecast state, and the Season outlook bands stay on League rankings (where they render today with that flag off). Nothing on the page starts a simulation, on open or on any tap.

**Route param.** `Standings: { segment?: 'projected' } | undefined` is kept so installed builds and deep links that send it land without error; the screen never reads it, and the app no longer sends it (Home's playoff tile, League rankings' tile).

## 1. Analytics scope

- [ ] (a) New events specced — **not taken.** Two taps would need a new name, which this change does not mint (operator brief). Proposed for a later decision, untracked until then:

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `standings_sorted` (proposed, NOT registered) | `view` (record\|points), `column` (team\|wl\|proj_wl\|playoffs\|pf\|max_pf\|proj_max_pf), `dir` (asc\|desc) | a heading tap | mobile |
  | `standings_team_opened` (proposed, NOT registered) | `view`, `has_forecast` | a row tap that opens a team | mobile |
- [x] **(b) Existing events cover the pill:** `standings_segment_changed` (NON_INTENT, a lens switch on a read-only page) keeps its name, meaning and its one prop `segment`; the pill emits `segment: record | points` on a changing tap only (never mount, never a re-tap). The new values are registered in the same commit: `backend/analytics_taxonomy.py` (comment rows for the event and its prop) and `docs/business/analytics/2026-10-10-home-hub-addendum.md` (2026-11-12 note, value list, the "what did Projected cost" question rewritten). `screen_viewed {screen: Standings}` is unchanged. No existing event fits a sort or an open-team tap (`league_team_opened` is League rankings' drill-in with rank/basis/subset props; `usage_trends_view_changed` is Usage Trends'), so those taps are untracked.
- [ ] (c) WAIVED — n/a.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: **none.** The table is the page; the forecast columns already ride `league.projections` (off ⇒ the no-forecast state), and `nav.home_hub` still gates the Home entry. A new flag would keep the retired segment UI alive as a second renderer for no rollback value the existing flags do not already give.
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-standings-table.js` (`npm run test:standings-table`). Part A **executes** `utils/standingsTable.ts` and `utils/standings.ts`: every column sorted both directions with ties and dashes, `nextSort`, the default sorts and column sets, "<1%"/"100%"/rounding edges, "1,498", records, cells and dash rules (forecast missing for one team and for the whole league), Max PF from `ppts` and the forecast fallback, the open team's lines per view with/without forecast and byes, the no-forecast line per state, and the 375pt layout arithmetic. Part B pins: no segments / no route read; the pill on the caption line; one table; every heading a sort button through `nextSort`/`sortRows`; headings fixed-width, number cells min-width; the outlined open card; one open team remembered with its league; view switch closes it; the status line under the table; the shared forecast key and its gate; no outlook/simulation/mutation; no effect, no keyed remount (view + sort survive a league switch); one FeedbackFAB; the RootNav header; the one analytics emitter; no caller sending params; `LeagueProjectionSection` deleted and unimported; the moved detail and its quieter separators; Chalkline (no hex, no shadow, radii md/pill only); testIDs.
- Existing suites moved to the new truth (no assertion deleted without a replacement): `check-home-destinations.js` §6/§7/§9/§11, `check-home-hub.js` 13a/13b + comments, `check-league-header-pages.js` 4a/4b2, `check-league-projections.js` (section → screen/detail/util), `check-league-rankings-playoff-tile.js` T1d/T1e/T3a/T3d.
- [x] **Unit tests:** backend: none added (no backend behaviour changed; the taxonomy edit is comments). `backend/tests/test_analytics_taxonomy_home_hub.py` still pins the event name, prop row and NON_INTENT class.
- [x] **Code-walk proof:** in the builder report (file:line trace of open → forecast read → table → sort → open team → league switch).
- [x] **Manual TestFlight checklist:** in the builder report; to be copied into `living-memory/TEST_LEDGER.md` by the coordinating session.
- `testID`s added: `standings.view-pill`, `standings.view.record`, `standings.view.points`, `standings.table`, `standings.sort.<column>`, `standings.row.<rosterId>`, `standings.open`, `standings.open.left-out`, `standings.open.average`, `standings.open.detail`, `standings.forecast-status`, `standings.no-forecast`. Removed: `standings.segment.current`, `standings.segment.projected`, `standings.current.table`, `league-projections.section`, `league-projections.grid`. Kept: `standings.screen`, `standings.current.unavailable`, `standings.back-btn`, `league-projections.check`, `league-projections.incomplete`, `league-projections.diagnostics`. No Maestro flow references any of them; `testid-lint.sh` passes.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed or changed. Standings now calls `GET /api/leagues/<id>/projection-runs/latest` on open instead of only inside Projected, and no longer calls `GET /api/league/outlook`; the reference documents routes, not their mobile callers |
| `living-memory/LLD.md` | n/a here | No schema/route convention shifted; living-memory is written by the coordinating session |
| `docs/architecture.md` | updated | "Home weekly playoff forecast consumer": the shared key is now held by the Standings table |
| `living-memory/HLD.md` | n/a | No architecture shift |
| `docs/cross-client-invariants.md` | n/a | No shared constant; the odds/points formats are mobile-only (web standings out of scope) |
| `docs/glossary.md` | updated | "Current vs projected standings" |
| ADR or `DECISIONS.md` entry | for the coordinating session | Non-obvious choices to record: removing the outlook (simulation) path from Standings; reusing `standings_segment_changed` for the pill; Proj. W–L = `modal_record` |

Also updated: `docs/design/components.md` (Standings table row), `docs/plans/README.md` (home-engagement row), `docs/business/analytics/2026-10-10-home-hub-addendum.md`, `mobile/src/{screens,components,utils,navigation}/CLAUDE.md`, `mobile/tests/README.md`.

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests`, `tsc --noEmit` + the `check-*.js` suites, `testid-lint` — run locally by the builder (results in the report); CI on push is the coordinating session's.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` — by the coordinating session.
- **TestFlight verification:** operator, from the report's checklist.
- Express lane declared by the operator? no.
