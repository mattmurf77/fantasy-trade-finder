# Feature Scope — Standings: stat rows, SoS column, Remaining schedule, likely pick range

**Date:** 2026-11-25 (scope block written while the build ran; updated after the code was verified, with [evidence.md](evidence.md))
**Entry point:** direct ask. The operator (Matt) compared our season projections with dynastyhound.com and asked for a cleaner Standings tile and a few of the competitor's numbers; design review ran 2026-11-24/25 over nine mockup revisions. All decisions below are final.
**Builder:** two builder subagents on `feat/standings-display-rows` (cut from origin/main `30ee823c`): Builder A, the Standings table and tile; Builder B, the open-team detail, pick range and Home card. Main session reviews, commits and opens the PR. Decision entry: [D-285](../../../living-memory/DECISIONS.md). The branch carries the change as one commit on `origin/main` `c9091e5a`.
**Operator sign-off on waivers:** GIVEN 2026-11-25, relayed by the main session: full gates; (a) no feature flag and no deploy-free rollback lever, (b) no new analytics events.

Design reference (made-up layout, real data from three of the operator's leagues, forecast of 2026-11-24): the operator's local mockup `data/review/dynastyhound-comparison-2026-11-24/display-mockups/` (`build.py` holds the copy tables and design notes; `index.html` is its rendered page). Gitignored, not in the repo; see "Mockup" at the end. This doc carries every string and rule it needs, so it stands without the mockup.

---

## What changes

Mobile only: `StandingsScreen` (route `Standings`), `LeagueProjectionDetail` (the open team's detail on Standings) and `HomePlayoffBanner` (the playoff card on Home, and on League rankings, which mounts the same component at `mobile/src/screens/LeagueSummaryScreen.tsx:1916`). No schema, API, server, flag or analytics change. Every number shown is read from fields the app already receives on `GET /api/leagues/<id>/projection-runs/latest`.

1. **Open team tile, stat rows.** The two dot-separated summary lines (`StandingsScreen.tsx:278-281`, built by `openTeamLines`, `utils/standingsTable.ts:216-237`) become one label/value row per stat (new `components/StatRow.tsx`). Same stats, same values, no sentences.
2. **SoS, a fourth Record-view column.** Strength of remaining schedule, ranked across the league, computed on the client from the saved forecast's `weeks[]`. The Playoffs heading stacks as "Play" / "offs" and the Record view's numeric columns are tightened so the team column keeps (gains 3 pt of) its width.
3. **Sort caret on the left** of a numeric heading's text, so heading text shares its right edge with the cells in every sort state (today the sorted heading sits 12 pt left of the others: `StandingsScreen.tsx:385`, `:394-396`).
4. **Under the table:** only the caption ("Weekly estimate" / "Last saved: {date}" with "Incomplete" / "Provisional") and the tiebreakers line remain.
5. **Remaining schedule** replaces "Weekly projections" in the open team: a matchup table, each row opening to that week's projected lineup.
6. **Draft pick odds** become rows and, for a team that misses the playoffs in at least 25% of simulations, add the likely pick range and the chance of the 1.01.
7. **Home playoff card:** a "likely 1.01–1.02" note under the Projected pick figure (same 25% rule) and one sentence in the card's info text.

Not touched: `web/js/league-projections.js` (mirrors this UI; deliberately unchanged), `components/DirectionPage.tsx` (the Improve Draft Pick page's projected-pick figure: the mockup offered the same note there, not built), Final record odds, Max PF moves, Playoff targets and their link rows, the no-forecast state, the non-Sleeper card, the Points view's columns.

## Spec (final strings and rules)

`{…}` are fills. En dash `–` (U+2013) in records and ranges. Strings are from the mockup's copy tables (`build.py` `COPY`, section copy rows and design notes), corrected below where the built code settled them differently; source lines are in [evidence.md](evidence.md).

### Standings table

| Item | Rule / string |
|---|---|
| Record view columns | Team · W–L · Proj. W–L · Playoffs · SoS. Default sort unchanged: W–L, best first |
| Points view columns | Unchanged: Team · PF · Max PF · Proj. Max PF |
| Headings | "W–L"; "Proj." over "W–L"; **"Play" over "offs"** (stacked, both lines right-aligned, caps `label` style); **"SoS"** drawn exactly so (lowercase o, the one exception to the caps transform) |
| Record view widths | **As built:** W–L 40 · Proj. W–L 51 · Playoffs 46 · SoS 37 pt (today 48 · 56 · 76, no SoS), each its widest real cell or its heading plus the 12 pt caret, from the bundled fonts' metrics (the mockup had 40 / 50 / 47 / 36). Gaps (4 pt), the 16 pt chevron column, type sizes and 44 pt rows unchanged. Team column at 375 pt: 375 − 32 page padding − 8 row padding − 16 chevron − 5 × 4 gaps − 174 = **125 pt** (today 123) |
| Fit target | A 16-character name (the longest in Lakeview League) shows whole at 375 pt, the narrowest current iPhone, with the caret on any column. **Known limit:** the viewer's row (name + "You" badge) fits only when the name is about 76 pt wide or less ("mattmurf77" fits; a wide 11-character name needs about 130 pt and truncates, as it already does at today's 123 pt). At 320 pt (first-gen SE, still installable on iOS 15.1) names truncate, as they already do today |
| Sort caret | 10 pt chevron, ice, to the **left** of a numeric heading's text inside the column's reserved width; Team keeps its caret on the right. Widths do not change (they already included the caret) |
| SoS value | For each team, the mean over its remaining weeks (`actual_score_observed !== true`) of the opponent's projected score **that week** (the opponent's own `weeks[].modeled_score_mean` for the same `week`, found via `opponent_roster_id`); none if any opponent or week is missing. Rank across teams with a value by the unrounded mean, highest = 1 = toughest; an exact tie goes to the lower roster id |
| SoS cell | Ordinal rank ("1st", "2nd", "3rd", "5th", "11th", "12th"), with a second line **"hard"** for ranks ≤ n/3 and **"easy"** for ranks > 2n/3 (12 teams: 1–4 hard, 9–12 easy, 5–8 no word). Thirds are of the league's team count. Dash with no forecast for the team, no remaining weeks or a missing opponent |
| SoS sort | First tap: toughest first (rank 1 at top); second tap reverses. Dashes last in both directions (existing `sortRows` rule) |
| SoS spoken | **As built:** heading "Sort by strength of schedule, toughest first" / "easiest first" / "not sorted"; a row reads "strength of schedule 5th" plus ", hard" / ", easy" |
| Under the table (with a forecast) | One caption line: "Weekly estimate" or "Last saved: {date}", then " · Incomplete" when `coverage.estimate_status` is `incomplete`, then " · Provisional" when `provisional`. Then "Your league’s own tiebreakers and divisions may order tied records differently." Nothing else |
| Under the table (no forecast) | Unchanged: "Projections aren’t available for this league yet." + its status sentence + Check for update |

### Open team tile rows

Label left, value right in Plex Mono aligned to the table's number columns, 28 pt rows on the tile's ink-3 hairline (the Status row construction, `docs/design/components.md`). A row whose value is unknown is left out, as today's line leaves the item out.

| View | Rows, in order (value format) |
|---|---|
| Record | Points for ("1612.5", one decimal) · Max PF ("1,888", whole, commas; omitted when unknown) · Projected Max PF ("2,321") · Average final record ("8.8–5.2", a tie part when ≥ 0.05) · Bye odds ("7.8%", only when the league has byes) |
| Points | Record ("7–4") · Projected ("9–5", most likely record) · Playoff odds (`playoffOddsText`, whole percent, D-262 ">99%" / "<1%") · Average final record · Bye odds |
| No forecast | Record view: Points for, Max PF. Points view: Record. (Forecast rows absent, as today) |

### Remaining schedule (open team, replaces Weekly projections)

| Item | Rule / string |
|---|---|
| Section title | "Remaining schedule" (sentence case, between "Final record odds" and "Draft pick odds") |
| Rows | The team's remaining weeks only (`actual_score_observed !== true`; completed weeks are not listed). One week open at a time; the section is closed by default |
| Header | Wk · Opponent · Proj. · Opp. · Win % (blank 16 pt chevron cell at the end, so numbers never move) |
| Row | "12 · Team B · 137.4 · 111.0 · 77%": week, opponent name (ellipsis), this team's projected score, the opponent's projected score that week (one decimal each), win chance as a whole percent, never 100% or 0% (">99%" / "<1%"). Row ≥ 44 pt, chevron-down; open row ink-3 fill + ice chevron-up, week detail below |
| Fallback (a week has no win chance) | **As built, per section:** if any remaining week lacks a finite win chance, the whole last column becomes "Edge": "W" / "L" by which projection is higher, "Even" when they differ by less than 3.0 points (exactly 3.0 reads W or L); "—" if a projection is missing |
| Season over | Section body: "No regular-season games left." (the section stays) |
| Opened week | The projected lineup as aligned rows: slot (caps label) · player · points to one decimal ("RB · Jahmyr Gibbs · 23.1"). Slot keys as sent except SUPER_FLEX "SF", IDP_FLEX "IDP", REC_FLEX "W/T", WRRB_FLEX "W/R" (the forecast admits exactly 13 slots, `backend/league_projections/core.py:11`). A free-agent fill: name followed by "(free agent)". Other slots keep today's words: "Empty slot", "Hypothetical bye replacement", "Locked starter {name}" (points "—"). Then one row per player with no estimate: "{name}" · "no estimate" (the reason is dropped). Nothing else |
| Median-game league | Rows are the head-to-head game; the median-game chance is not shown (not in the mobile type) |
| VoiceOver row | "Week 12, against Team B. Projected 137.4 to 111.0. 77% chance to win." (fallback: "… Edge W.") |

### Draft pick odds (open team)

| Item | Rule / string |
|---|---|
| Kept sentence | "Estimates assume regular-season Max PF draft order." |
| Rows | Miss playoffs (`missOddsText`, one decimal, D-262) · Pick owner (team name) · Pick ("2027 round 1") |
| Range rows, only when `nonplayoff_probability` ≥ 0.25 (exactly 25% shows) and `config.draft_round` is present | Likely pick if this team misses ("1.01–1.02") · Chance of the {round}.01 ("83.7%", one decimal) |
| Likely pick | Renormalise `pick_probabilities` (index 0 = pick 1) to the seasons where the team misses; low end = first slot whose cumulative share reaches 10%, high end = first reaching 90%. Label `{round}.{slot, two digits}`; one label when both ends match ("1.06"). No range when the probabilities sum to 0 |
| Chance of the 1.01 | `pick_probabilities[0]` (unconditional: equals the nested list's "Pick 1") |
| Nested "Pick odds and range" | Kept: "Current Max PF: … · … per week", "Projected Max PF, middle 80%: …–…", "Pick odds include the chance of making playoffs.", then the Pick n list |

### Home playoff card (Home and League rankings)

| Item | Rule / string |
|---|---|
| Note under the Projected pick value | "likely {range}" (e.g. "likely 1.01–1.02"), styled as the "owned by" note: after a "last saved" note if any, and above "owned by …" when the pick is owned elsewhere (both show) |
| VoiceOver | The pick figure's label gains ", likely {range}" before the owner |
| Shown when | The card draws the Projected pick figure (a `team_direction` block with a projected pick) and the viewer's own team misses in ≥ 25% of simulations |
| Info text sentence (with the note) | "Likely range: where your pick lands in 8 of 10 simulated seasons where you miss the playoffs." |

## Text removed that ships today

Verified against `origin/main` `30ee823c` (this branch's base; none of these files changed on `origin/main` since, checked at `c9091e5a`). Paths under `mobile/src/`.

| Removed | Where | What users stop being told |
|---|---|---|
| The two dot-separated tile lines ("Points for … · Max PF … · Projected Max PF …", "Average final record: … · Bye odds: …"; Points view "Record … · Projected … · Playoff odds …") | `screens/StandingsScreen.tsx:278-281`, `utils/standingsTable.ts:216-237` | Nothing: replaced by rows with the same values |
| "Partial Sleeper data" caption tag | `StandingsScreen.tsx:299` (`result.coverage?.estimated`) | That some players or scoring rules had no usable projection and totals were built from the contributions available. Nothing on Standings says a forecast is partial |
| The forecast status sentence after the caption ("Weekly update due.", "Latest update failed.", "Weekly update queued.", "Weekly update in progress.", "Missing player or scoring data.", "This league’s rules aren’t supported yet.", "Weekly update failed.", "Couldn’t check for an update.") | `StandingsScreen.tsx:300` (words at `utils/standingsTable.ts:240-257`) | Why a saved forecast is "Last saved" rather than current. The words stay in the no-forecast line (`:305-312`) |
| The incomplete-scores sentence ("{n} lineup slots had a starter whose score is not recorded yet, so these odds are incomplete."), testID `league-projections.incomplete` | `StandingsScreen.tsx:301` (text `utils/projectionCoverage.ts:6-9`) | What "Incomplete" means on Standings. Home's info text keeps its own explanation (`components/home/HomePlayoffBanner.tsx:175`) |
| "Projected W–L is the most likely final record from the weekly forecast. Odds don’t confirm a playoff spot." | `StandingsScreen.tsx:68`, rendered `:302` | What Proj. W–L means, and **the only line on the page saying a playoff percentage is not a confirmed spot** |
| "Max PF is the season so far. Projected Max PF is the forecast for the full regular season." | `StandingsScreen.tsx:69`, rendered `:302` | The two Max PF columns' definitions |
| "Weekly projections" and its "Week {n} · {p}% win" rows (every week, completed ones included) | `components/LeagueProjectionDetail.tsx:80-81` | Completed weeks' detail, including "Recorded completed lineup score" (`:125`), "Locked starter …: actual score unavailable" (`utils/projectionCoverage.ts:21`) and the win chance to one decimal |
| "vs {opponent}: win …, tie …, loss …. Projected lineup score …; standard deviation …." | `LeagueProjectionDetail.tsx:125` | **Tie and loss odds and the score's standard deviation, now shown nowhere in the app** (the win chance stays, whole percent) |
| "Max PF target …; simulated mean …. Simulation averages vary; predictive uncertainty is not calibrated." / "Historical model: input Max PF …; simulated mean …." | `LeagueProjectionDetail.tsx:126` | **The only in-app warning that simulation uncertainty is not calibrated** |
| "Show model diagnostics" / "Hide model diagnostics" (testID `league-projections.diagnostics`) and the diagnostics paragraph | `LeagueProjectionDetail.tsx:127`, `:128` | **Model diagnostics, no longer reachable from the app** |
| "An already completed eligible lineup establishes at least … Max PF. …" | `LeagueProjectionDetail.tsx:129` | The known Max PF floor from completed weeks |
| "Available projections: … players for the actual lineup, … for Max PF. The lineup uses available contributions; unknown players and rules are not confirmed zeros." | `LeagueProjectionDetail.tsx:130` | Pool counts, and that a missing estimate is not a zero |
| "Score not recorded yet at: …." | `LeagueProjectionDetail.tsx:131` | Which slots still lack a recorded score (completed-week only) |
| "{name}: no usable estimate ({reason})." | `LeagueProjectionDetail.tsx:132` | The reason; reshaped to "{name}" · "no estimate" |
| "{name}: partial contributions; missing …." per player | `LeagueProjectionDetail.tsx:133` | **Per-player partial-scoring detail, now shown nowhere** |
| "No hypothetical IDP bye replacement was added because its historical scoring average is unavailable." | `LeagueProjectionDetail.tsx:134` | Why an IDP bye slot has no replacement |
| Raw lineup rows "{slot}: {name} · {points}" | `LeagueProjectionDetail.tsx:135` (`utils/projectionCoverage.ts:14-23`) | Nothing: reshaped to aligned rows, points to one decimal |
| "Available lineup contributions …; Max PF eligible contributions …." (+ "Recorded team total …") | `LeagueProjectionDetail.tsx:136` | The week's lineup total and Max PF total (the row's Proj. is the modeled mean) |
| "{player_id}: {reason}" per exclusion | `LeagueProjectionDetail.tsx:137` | Which players were excluded (reserve, unknown team) |
| "Miss playoffs: …", "Pick owner: … · {season} round {n}" | `LeagueProjectionDetail.tsx:87-88` | Nothing: reshaped to rows |
| "Expected pick if this team misses: …" | `LeagueProjectionDetail.tsx:89` | The conditional expected pick (replaced, only at a ≥ 25% miss chance, by the likely range) |
| "Missed-playoff simulations: {n}. This franchise is projected to own … non-playoff picks, with a …% chance of at least one." | `LeagueProjectionDetail.tsx:95` | The sample count and the owner's expected number of non-playoff picks |

## Consequences the operator accepted

- Tie and loss odds, the score standard deviation, model diagnostics, per-player partial-scoring detail and the "predictive uncertainty is not calibrated" warning are no longer visible anywhere in the app.
- Nothing on the Standings page says a forecast is built from partial data, or that playoff odds do not confirm a spot.
- A team under the 25% bar shows no pick position at the top level of Draft pick odds; only the nested Pick n list does.
- Completed weeks are no longer listed in the open team (Remaining schedule lists unplayed weeks only).
- The web client (`web/js/league-projections.js`) is deliberately left unchanged, so web and mobile differ: web keeps "Weekly projections" with the long week detail, the dot-separated lines, "Expected pick …", the "Partial Sleeper data" tag, no SoS and no pick range. Since the 2026-11-25 launch cut no web page loads that script (`web/CLAUDE.md`), so no user sees the web version today; the divergence matters if that cut is reversed.
- `docs/cross-client-invariants.md` § "Stored weekly projection results" says both clients disclose modeled scoring omissions, show the weekly target-vs-simulated text and the advanced diagnostics, and show the conditional expected pick. After this change only web does; the section now says so (see its D-285 table).

## Deferred (designed, not built)

| Item | Why |
|---|---|
| **Luck** view on the Standings pill (Exp. wins · Luck · SoS) | Needs completed weekly scores for every team, which the saved forecast does not carry (a new result field, or the app reading Sleeper's public matchups). Design rule to keep: in a median league, luck uses head-to-head games only |
| **Median what-if** view (W–L · With median · New place, flipped in a median league) | Same data gap |
| **Web** version of all of the above | Operator chose mobile only (round 9); web pages are cut since 2026-11-25 |
| Likely-pick note on the Improve Draft Pick page | Offered in the mockup as optional; not in this change |

The mockup's `build.py` keeps the deferred sections behind `SHOW_DEFERRED = False`.

---

## 1. Analytics scope

Lines are on the branch (one commit on `origin/main` `c9091e5a`); the emitters are byte-identical to `30ee823c`.

- [x] **(b) Existing events cover what is measured today, unchanged:**
  - `screen_viewed {screen: 'Standings', prev_screen}`: auto-emitted on navigation (`mobile/src/navigation/RootNav.tsx:585`, `:609-610`); counts Standings visits.
  - `standings_segment_changed {segment: record | points}`: the Record | Points pill, on a changing tap only (`mobile/src/screens/StandingsScreen.tsx:151`, the screen's only `track`; taxonomy `backend/analytics_taxonomy.py:758-764`, props `:2161`; NON_INTENT `backend/analytics_queries.py:416`). No new value: the pill keeps two segments. `check-standings-table.js` B9 pins it as the one emitter.
  - `home_tile_tapped {tile: 'standings'}` from the playoff card's percentage and "View" (`mobile/src/components/home/HomeHub.tsx:192`, `:198`; props `analytics_taxonomy.py:2155`).
  - `direction_card_shown {band, primary, shown, sheet, pick_shown}`, once per card mount (`components/home/HomePlayoffBanner.tsx:84`; props `analytics_taxonomy.py:2205`; NON_INTENT `analytics_queries.py:430`; pinned in `check-home-playoff-banner.js`). `pick_shown` says the Projected pick figure was drawn; it does not say whether the new range note was.
  - Inside the viewer's own open card, `maxpf_moves_viewed` / `maxpf_move_expanded` (`components/MaxPfMovesSection.tsx:65`, `:125`, `:131`) and `playoff_targets_viewed` / `playoff_target_expanded` (`components/PlayoffTargetsSection.tsx:46`, `:65`) keep firing: neither file changed, and `LeagueProjectionDetail.tsx:104-113` still mounts both bodies and link rows.
- [x] **(c) WAIVED, operator sign-off 2026-11-25: no new events.** Not tracked before and still not tracked after: column sort taps (the SoS sort joins them), opening a team row, every section and week opened in `LeagueProjectionDetail` (before: Weekly projections and its week rows; the old diagnostics toggle emitted nothing either), and the Home card's info toggle (state only). New untracked surfaces: the SoS column and sort, Remaining schedule week opens, the range rows and the Home note. So whether anyone uses SoS or the Remaining schedule cannot be measured. The `standings_sorted` / `standings_team_opened` events proposed in `docs/plans/home-engagement/scope-standings-table.md` §1 remain unregistered.

## 2. Schema & flag scope

- New/changed tables or columns: none. Nothing new is saved; the weekly job is unchanged.
- New/changed feature flags: **none. WAIVED (a), operator sign-off 2026-11-25.** The forecast parts already ride `league.projections` (off: the no-forecast state, no tile detail, no Home card). There is **no deploy-free rollback lever**: rollback is reverting the PR and cutting a new TestFlight build; installed builds keep the new display until updated.
- New env vars / `model_config` keys: none. `config/league_projections.json` unchanged. The two client constants: `PICK_RANGE_MIN_MISS = 0.25` (`mobile/src/utils/pickRange.ts:8`) and `EVEN_POINTS = 3.0` (`mobile/src/utils/projectionCoverage.ts:16`).

## 3. Evidence scope

D-056: no simulator, no Maestro, no `screens/` captures. Run and counts: [evidence.md](evidence.md) §2 and `living-memory/TEST_LEDGER.md` (2026-11-25).

- [x] **Structural guards:** `check-standings-table.js` **147 passed** (107 at base): SoS rank / tie / band / dash / sort from synthetic `weeks[]`, the four Record widths against measured font metrics, the 375 / 390 / 393pt team-column arithmetic, a 16-character name at 375pt, the left-hand caret, stat rows per view, the removed strings absent, caption + tiebreak note only. `check-league-projections.js` passes (executes `projectionCoverage` and `pickRange`: rows, Win % ends, Edge at the 3.0 edge, season over, lineup parts and slot labels, the 25% bar, the range; removed week-detail and pick strings absent). `check-home-playoff-banner.js` passes (the note and sentence at exactly 25% and not below, a zero sum, no draft round, both notes and their order, the VoiceOver label, `direction_card_shown` unchanged). Moved to the new truth: `check-playoff-odds-display.js` (21 passed; two pins now read the row form) and `direction-card-harness.js` (loads `pickRange`; `check-direction-card.js` 94 passed). All 210 suites pass; `tsc --noEmit` clean; testid-lint OK.
- [x] **Unit tests:** none. No backend behaviour changes; `pytest backend/tests` runs in CI as a guard only.
- [x] **Code-walk proof:** [evidence.md](evidence.md) §1, file:line per feature and state.
- [x] **Manual TestFlight checklist:** [testflight-checklist.md](testflight-checklist.md). The only runtime evidence; **not run yet**.
- `testID`s added: `standings.open.stats`, `standings.schedule.week.<n>`, `standings.pick.range`, `home.playoff.pick.range`, `home.playoff.pick.range.explanation`. Removed: `standings.open.left-out`, `standings.open.average`, `league-projections.incomplete`, `league-projections.diagnostics` (no Maestro flow references any of them). testid-lint passes.
- Helpers removed: `openTeamLines` (now `openTeamStats`), `lineupRowText` and `incompleteSentence` (no mobile caller left; web keeps its own copies).

## 4. Docs scope

Every row of `docs/CLAUDE.md`'s trigger table plus the template's mandatory rows.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed or changed in contract. Standings and Home read the same `GET /api/leagues/<id>/projection-runs/latest`; the new numbers come from fields already served (`teams[].weeks[].opponent_roster_id`, `modeled_score_mean`, `win_probability`, `actual_score_observed`, `teams[].pick_probabilities`, `nonplayoff_probability`, `config.draft_round`) |
| `docs/data-dictionary.md` | n/a | No table, column or saved key changes |
| `docs/config-reference.md` | n/a | No env var, flag or `model_config` key; the two constants are client code |
| `docs/architecture.md` | n/a | No module wiring or data flow change; the paragraph naming `StandingsScreen` → `LeagueProjectionDetail` and the shared key stays true |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifts |
| `living-memory/HLD.md` | n/a | No new module, client or flow |
| `docs/cross-client-invariants.md` | updated | § "Stored weekly projection results": what both clients still share, and a table of what deliberately differs since D-285 (web keeps the omissions disclosure, diagnostics, tie/loss/SD and the conditional expected pick; mobile has the matchup table, SoS, stat rows and the likely range) |
| `docs/glossary.md` | updated | New: **Likely pick (range)**, **SoS (strength of schedule)**, **Remaining schedule**; **Projected pick** points at the note |
| `docs/design/components.md` | updated | **Standings table** row (four columns, widths, stacked heading, SoS casing, caret left, stat rows, only caption + tiebreak under the table); new **Stat row** and **Matchup table** rows; the stale `LeagueProjectionSection` section rewritten as `LeagueProjectionDetail`; one sentence on the Home banner's note |
| `docs/design/design-system.md` | n/a | No token added or changed |
| `docs/runbook.md` | n/a | No operational issue |
| `docs/coding-guidelines.md` | n/a | No new rule |
| `docs/adr/` | n/a | Display choice, not architecture; DECISIONS.md carries it |
| `docs/feedback/items/` | n/a | Direct ask, not a feedback item |
| `docs/integrations/` | n/a | No external call changes |
| `docs/recovery/` | n/a here | The main session ledgers the branch / worktree when it removes them |
| `docs/business/` (incl. `analytics/` addenda) | n/a | No event or property change |
| `docs/plans/README.md` | updated | New row for `standings-display-rows/` (built, PR open) |
| `docs/plans/home-engagement/scope-standings-table.md` | updated | "Superseded in part" note at the top |
| ADR or `DECISIONS.md` | updated | D-285 |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `NEXT.md` | updated | Dated entry (not merged); the test run; a dated NEXT section (merge, build, checklist) outside the seven active items |
| `living-memory/OPEN_QUESTIONS.md` | updated | Q-041: the mockups embed rule vs the D-056 capture freeze (operator call; see "Mockup" below) |
| `living-memory/GOTCHAS.md`, `MISTAKES.md` | n/a | Nothing cost time past those files' bar; no approach was abandoned |
| `living-memory/HANDOFF.md` | n/a | Not touched by recent PRs; the in-flight state is in NEXT and the PR |
| `mobile/src/components/CLAUDE.md`, `mobile/src/utils/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`, `mobile/tests/README.md` | updated | `StatRow` row; `LeagueProjectionDetail` row; `standingsTable`, `projectionCoverage`, new `pickRange` lines; `StandingsScreen` row; the three suites' descriptions |

## 5. Ship gate declaration

- **CI green** on the pushed sha: `backend-tests`, `mobile-typecheck` (with the `check-*.js` suites), testid-lint.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-25 entry (suites, counts, code-walk proof).
- **TestFlight verification:** the checklist, run by the operator on the first build carrying this branch; outcome logged in TEST_LEDGER.
- `FTF_SKIP_SIM_GATE=1` for the pre-push hook (standing D-056 posture).
- Express lane declared by the operator? **no** (full gates).

## Mockup

The design lives outside the repo (`data/` is gitignored, `.gitignore:8`) and embeds the operator's real league and opponent usernames. `mockups/CLAUDE.md` asks for one directory per lab with an index row; no `screens/` capture exists for Standings or Home (both shipped after the 2026-08-11 freeze), so every "before" frame is a labelled reconstruction, as the interim posture there requires. Whether to register it is an open call for the operator, logged as Q-041 in `living-memory/OPEN_QUESTIONS.md`.
