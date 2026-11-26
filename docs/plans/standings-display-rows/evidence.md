# Standings display rows: evidence (D-285)

> D-056: no Maestro, no simulator, no `screens/` capture. This file holds the code walk and the
> test run; the device checks are in [testflight-checklist.md](testflight-checklist.md). Every
> `file:line` was read on `feat/standings-display-rows` as one commit on
> `origin/main` `c9091e5a` (the branch was cut at `30ee823c` and main merged in before the checks). Paths are under `mobile/src/`
> unless they start with `mobile/` or `backend/`. Scope: [scope.md](scope.md).

- [1. Code walk](#1-code-walk)
- [2. Test evidence](#2-test-evidence)
- [3. Not verified](#3-not-verified)

## 1. Code walk

### 1.1 Data: one read, nothing new

| Step | Where |
|---|---|
| Standings reads the saved forecast on the shared key, gated on `league.projections` + Sleeper | `screens/StandingsScreen.tsx:115-121` |
| The rows join standings to forecast teams; SoS is computed here, from `result.teams` only | `StandingsScreen.tsx:137-142` → `utils/standingsTable.ts:116-155` |
| Home's card reads the same key; the viewer's team's `nonplayoff_probability`, `pick_probabilities` and `config.draft_round` are passed through | `components/home/HomePlayoffBanner.tsx:60-61`, `utils/homePlayoffBanner.ts:63-69` |
| No other request, no simulation: no `track`, query or mutation was added (`git diff c9091e5a..feat/standings-display-rows` adds none; `check-standings-table.js` pins one emitter) | `StandingsScreen.tsx:151` (the only `track`) |

### 1.2 SoS column

| Step | Where |
|---|---|
| Remaining weeks = `actual_score_observed !== true` | `utils/standingsTable.ts:97` |
| Opponent's projected score the same week (its own `weeks[]` entry); **null if no remaining weeks, or any opponent / week / finite mean is missing** | `standingsTable.ts:96-106` |
| Rank by the unrounded mean, highest first; exact tie → lower roster id | `standingsTable.ts:124-130` |
| Band: rank ≤ team count / 3 "hard", > 2 × team count / 3 "easy" (team count = all standings rows, including any without a value) | `standingsTable.ts:132-136` |
| Cell: `ordinal(rank)` or a dash | `standingsTable.ts:109-113`, `:239` |
| Rendered as two lines (rank, then band) only when there is a value; a dash otherwise | `StandingsScreen.tsx:258-264`, styles `:471-472` |
| Sort: `[-rank]`, so the first tap (`desc`) puts rank 1 first; dashes last both ways | `standingsTable.ts:174`, `:183-199`, `:203-206` |
| Column order and default sort (Record still opens on W–L) | `standingsTable.ts:21-30` |
| Spoken: heading "Sort by strength of schedule, toughest first / easiest first / not sorted"; row adds ", hard" / ", easy" | `standingsTable.ts:266`; `StandingsScreen.tsx:376-380`, `:388`; `:232-234` |

States: no forecast for the team → dash (`:239`); no remaining weeks (season over) → dash; an opponent missing from the forecast → that team's mean is null → dash, and the other teams rank without it.

### 1.3 Headings, widths and the caret

| Step | Where |
|---|---|
| Widths: W–L 40, Proj. W–L 51, Playoffs 46, SoS 37; Points 48 / 60 / 60 unchanged; the arithmetic (team column 125pt at 375pt) in the comment | `StandingsScreen.tsx:56-68` |
| Labels: "Play\noffs" stacked, "SoS" as written | `standingsTable.ts:249-258`; `StandingsScreen.tsx:397`, `:443` (`textTransform: 'none'`) |
| Caret left of a numeric heading's text, right of "Team" | `StandingsScreen.tsx:381-383`, `:393`, `:401` |
| Heading cell right-justified, two lines max | `StandingsScreen.tsx:391`, `:394-397` |

### 1.4 Open team stat rows

| Step | Where |
|---|---|
| Rows per view; a row without a value is left out; average record and bye odds (byes only) | `utils/standingsTable.ts:277-295` |
| Rendered as `StatRow`s in `standings.open.stats`, ending under the last number column | `StandingsScreen.tsx:235`, `:280-284`, style `:475` |
| `StatRow`: label truncates, value never wraps, one accessible element "label, value" | `components/StatRow.tsx:12-26` |
| Detail sections follow, only with a forecast for the team | `StandingsScreen.tsx:285-290` |

### 1.5 Under the table

| Step | Where |
|---|---|
| With a forecast: one caption ("Last saved: {date}" when the read failed, the state is not current or `model_current` is false; else "Weekly estimate"; then Incomplete / Provisional) | `StandingsScreen.tsx:199-202`, `:298-302` |
| Without one: unchanged `noForecastLine` + Check for update | `StandingsScreen.tsx:303-313`, `utils/standingsTable.ts:322-327` |
| Tiebreak note whenever the table shows | `StandingsScreen.tsx:314-318` |
| Gone: the status sentence, the incomplete sentence, "Partial Sleeper data", `VIEW_FOOT` | absent from `StandingsScreen.tsx` (pinned absent in `check-standings-table.js`); `incompleteSentence` deleted from `utils/projectionCoverage.ts` |

### 1.6 Remaining schedule

| Step | Where |
|---|---|
| Section title "Remaining schedule", between Final record odds and Draft pick odds (closed by default, like every section) | `components/LeagueProjectionDetail.tsx:83-85` |
| Rows: remaining weeks only; opponent name from `result.teams` (else "Team {id}"); Proj. / Opp. to one decimal (else "—") | `utils/projectionCoverage.ts:23`, `:43-56` |
| Win %: whole percent, ">99%" / "<1%" at the ends | `projectionCoverage.ts:26-29` |
| Fallback: **any** remaining week without a finite win chance turns the whole column into "Edge"; W / L, or "Even" when `|own − opp| < 3.0` (a gap of exactly 3.0 reads W or L); "—" if a mean is missing | `projectionCoverage.ts:15-16`, `:32-35`, `:45`, `:50-51`; heading `LeagueProjectionDetail.tsx:134`, `:141` |
| No remaining weeks: "No regular-season games left." | `LeagueProjectionDetail.tsx:133`, copy `projectionCoverage.ts:10` |
| One week open at a time; tapping the open week closes it | `LeagueProjectionDetail.tsx:131`, `:145-149` |
| Row: ≥44pt button, `standings.schedule.week.<n>`, expanded state, ice chevron when open | `LeagueProjectionDetail.tsx:155-165`, styles `:207-208` |
| Spoken row: "Week {n}, against {opponent}. Projected {own} to {opp}. {p} chance to win." (fallback: "… Edge {W/L/Even}.") | `LeagueProjectionDetail.tsx:157` |
| Opened week: lineup rows, then one "no estimate" row per `unpriced_players` entry (the reason is dropped) | `LeagueProjectionDetail.tsx:169-189` |
| Lineup row parts: slot label (SUPER_FLEX SF, IDP_FLEX IDP, REC_FLEX W/T, WRRB_FLEX W/R, else as sent), "Hypothetical bye replacement", "Locked starter {name}" / "Empty slot" with "—", "(free agent)" from `free_agent_fills`, points to one decimal | `projectionCoverage.ts:18-20`, `:63-75` |
| The forecast admits exactly the 13 slots the shortening map has to cover | `backend/league_projections/core.py:11` `SLOTS` |

Removed (all of the old `WeekDetail`: score SD, tie/loss odds, Max PF target and "not calibrated" sentence, diagnostics toggle `league-projections.diagnostics`, known floor, pool counts, "Score not recorded yet", partial contributions, IDP sentence, contribution totals, exclusions): none of them is in `LeagueProjectionDetail.tsx`; `lineupRowText` deleted. `check-league-projections.js` pins each absent.

### 1.7 Draft pick odds and the likely range

| Step | Where |
|---|---|
| Kept sentence, then `StatRow`s Miss playoffs (`missOddsText`, D-262), Pick owner (name, body face), Pick ("{season} round {round}") | `LeagueProjectionDetail.tsx:86-92` |
| Range text, null under the bar | `LeagueProjectionDetail.tsx:78` → `utils/pickRange.ts:40-45` |
| Bar: `nonplayoff_probability >= 0.25` (exactly 25% shows) | `pickRange.ts:8`, `:42` |
| Range: renormalise `pick_probabilities` by their sum; first slot reaching 10% / 90% cumulative; null if the sum is not positive | `pickRange.ts:19-31` |
| Label "{round}.{two-digit slot}", one label when both ends match | `pickRange.ts:11-13`, `:34-36` |
| Rows "Likely pick if this team misses" and "Chance of the {round}.01" (`pick_probabilities[0]`, one decimal) under `standings.pick.range` | `LeagueProjectionDetail.tsx:93-96` |
| Nested "Pick odds and range": its three lines kept, Pick n as `StatRow`s | `LeagueProjectionDetail.tsx:97-102` |
| Gone: "Expected pick if this team misses", "Missed-playoff simulations" | absent; pinned in `check-league-projections.js` |

States: under 25% (including a clinched team) → Miss playoffs / Pick owner / Pick only; no `draft_round` in `config` → no range rows.

### 1.8 Home playoff card

| Step | Where |
|---|---|
| `likely` only when the pick figure shows (`pickFigure`: a `team_direction` block with a projected pick) **and** the range rule passes | `components/home/HomePlayoffBanner.tsx:77-79` |
| Note "likely {range}" under the value, after a "last saved" note and **before** "owned by …"; both show when the pick is owned elsewhere | `HomePlayoffBanner.tsx:133-142` (`home.playoff.pick.range` at `:140`, owner at `:141`) |
| VoiceOver: the figure's label gains ", likely {range}" before the owner | `HomePlayoffBanner.tsx:134` |
| Info text: "Likely range: where your pick lands in 8 of 10 simulated seasons where you miss the playoffs." only with the note, after the Projected pick sentence | `HomePlayoffBanner.tsx:181-182` |
| Same component on League rankings | `screens/LeagueSummaryScreen.tsx:1916` |
| `direction_card_shown` unchanged | `HomePlayoffBanner.tsx:84` (pinned in `check-home-playoff-banner.js`) |

### 1.9 Unchanged on purpose

- Max PF moves and Playoff targets: bodies, link rows and their events untouched (`git diff c9091e5a..feat/standings-display-rows -- mobile/src/components/MaxPfMovesSection.tsx mobile/src/components/PlayoffTargetsSection.tsx` is empty; mounts at `LeagueProjectionDetail.tsx:104-113`).
- Web, backend, config: no file changed (`git diff --stat c9091e5a..feat/standings-display-rows`).
- testIDs added: `standings.open.stats`, `standings.schedule.week.<n>`, `standings.pick.range`, `home.playoff.pick.range`, `home.playoff.pick.range.explanation`. Removed: `standings.open.left-out`, `standings.open.average`, `league-projections.incomplete`, `league-projections.diagnostics` (`git grep` finds none in `mobile/src` code; the last survives only in the pre-update `components/CLAUDE.md` text, corrected in this change).

## 2. Test evidence

Run by the main session on the merged branch, re-run here for the six suites named.

| Check | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | clean |
| `mobile/tests/check-*.js`, all 210 files (207 on the branch + 3 from main) | all exit 0 |
| `check-standings-table.js` | **147 passed** (107 at `30ee823c`) |
| `check-league-projections.js` | passes; prints no count (101 assertion call sites by static grep, 43 at base) |
| `check-home-playoff-banner.js` | passes; prints no count (197 call sites, 180 at base) |
| `check-playoff-odds-display.js` | **21 passed** (two pins moved to the row form) |
| `check-direction-card.js` | **94 passed** (its harness loads `utils/pickRange`) |
| `check-league-projections-web.js` | passes, untouched (web unchanged) |
| `bash mobile/scripts/testid-lint.sh` | OK |
| `pytest backend/tests`, web checks | not run locally (no backend or web file changed); CI on the PR |

What the suites pin (beyond the counts): SoS mean / rank / tie / band / dash / sort from synthetic `weeks[]`; the 375 / 390 / 393pt column arithmetic (team 125 / 140 / 143pt) and each Record width = widest cell or heading + caret within 1pt; a 16-character name fits at 375pt; the caret placement; the stat rows; every removed string absent; Remaining schedule rows, Win % ends, the Edge fallback at 3.0, season over, lineup parts and slot labels; the 25% bar at exactly 0.25, a zero sum and no draft round; both Home notes and their order; the VoiceOver label; the analytics emitters unchanged.

## 3. Not verified

Nothing ran on a device or simulator. The TestFlight checklist is the only runtime evidence. Specifically:

- Real text metrics and truncation at 375pt. The widths come from the bundled fonts' measured metrics, not a render. The builders' measurement: the viewer's row fits only when the name is about 76pt wide or less (team column 125pt minus the "You" badge and gap). "mattmurf77" fits. A wide 11-character name needs about 130pt with the badge and truncates at 375pt, as it already did with 123pt. That is a known limit, not a regression, and no test pins it.
- Heading wrap and cell fit at large Dynamic Type; the two-line SoS cell inside the 44pt row; the FLEX slot labels at the largest dense text scale.
- The Home card with "last saved", "likely" and "owned by" all showing at once.
- VoiceOver reading order on device.
- Values against a real forecast. The suites use synthetic payloads plus one fixture shaped like La Resistance; the operator's leagues are checked by hand in the checklist.
