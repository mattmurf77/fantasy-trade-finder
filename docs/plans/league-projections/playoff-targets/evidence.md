# Playoff targets: evidence

> D-056: no Maestro, no simulator, no `screens/` capture. This file holds the code walk, the
> measured job time, and the manual TestFlight checklist. Test counts and sabotages are in
> `living-memory/TEST_LEDGER.md` (2026-11-14). Every `file:line` was read on
> `feat/playoff-targets`. Scope: [scope.md](scope.md). Contract: [contract.md](contract.md).

- [1. Code walk](#1-code-walk)
- [2. Measured job time](#2-measured-job-time)
- [3. Manual TestFlight checklist](#3-manual-testflight-checklist)

## 1. Code walk

### 1.1 The eligibility rule has one definition and two call sites

| Step | Where |
|---|---|
| The cut and the two outlooks are constants | `backend/league_projections/playoff_targets.py:28-29` |
| The rule: `playoff_probability < 0.5 or saved_outlook in {rebuilder, jets}` | `playoff_targets.py:62-65` (`is_seller`) |
| Job: every other team gets `eligible = is_seller(its probability in this run, its saved outlook)` | `playoff_targets.py:216` |
| Job: candidates are drawn only from the teams with `eligible` | `playoff_targets.py:218` (`selling`), `:232-240` (the loop over `selling`) |
| Read: the rule again, over the saved teams with the outlooks saved now | `playoff_targets.py:68-72` (`sellers_now`), called at `:333` |
| Read: a row whose team is not selling now is not served | `playoff_targets.py:339-342` |
| Read: no team selling now → `no_sellers` | `playoff_targets.py:336-337` |

No other code path builds a row: `compute` appends to `rows` only inside the loop over `chosen`
(`:248-267`), and `chosen` comes from `gains`, which is filled only inside the loop over
`selling` (`:232-240`).

### 1.2 Where the saved outlooks come from

| Step | Where |
|---|---|
| Capture records each roster's owner and co-owner ids in the side channel, outside the snapshot | `backend/league_projections/provider.py:668` |
| Job: one bulk read of `league_preferences` for those ids; the first saved outlook among a roster's owners, primary owner first | `backend/league_projections/service.py:98-107` (`_seller_outlooks`) |
| Job: passed to `compute` with the owner ids, which are saved per team | `service.py:120-121`, `:135-137`; saved at `playoff_targets.py:217` |
| Read: one bulk read for the saved owner ids, same order of precedence | `backend/league_projections/api.py:128-134` |
| Read: passed to `compose` as `live_outlooks` | `api.py:135-137` |
| Only a saved outlook is read: both use `db.load_league_preferences_bulk`, which returns `team_outlook` from `league_preferences` and nothing inferred | `backend/database.py:13416` |

`partner_outlook` (the inferred reads) is not imported by any of these files.

### 1.3 The weekly job

| Step | Where |
|---|---|
| The step runs only for a fresh baseline capture with the flag on | `service.py:175-178` |
| A side channel is passed to capture when either flag is on | `service.py:179`, `:192-196` |
| Order: Max PF moves first, then playoff targets | `service.py:212-219` |
| Flag off: a reused result's block is dropped | `service.py:220-221` |
| Budget: the earlier of `time_budget_seconds` and 480 s after the job started; checked by every simulation and every 8 players in step one | `service.py:127-134`; `playoff_targets.py:234-235` |
| Any exception or a budget hit: the forecast is saved without the block | `service.py:139-142` |
| A reused prior result is recomputed when the block is missing, its settings changed, or the selling teams changed | `service.py:122-126` |

### 1.4 The calculation

| Step | Where |
|---|---|
| The viewer's lineups for every unplayed week (Max PF moves' builder) | `playoff_targets.py:120-129` (`_base`) → `maxpf_moves.py:135-171` |
| The builder's one change: `add` joins ids as active players; default empty, so Max PF moves is unchanged | `maxpf_moves.py:135`, `:141` |
| Step one: lineup-lane gain per player, a bye or an "out" week a known 0, an unprojected week leaves him out | `playoff_targets.py:96-117` (`lineup_gains`) |
| The skip that cannot change the answer (full lineup of rostered players, he projects no higher than its lowest starter) | `playoff_targets.py:79-88` (`_floor`), used at `:110-113` |
| Nothing to compute (season over, deadline, clinched, eliminated, near certain, no sellers): no simulation | `playoff_targets.py:222-230` |
| The largest gains only | `playoff_targets.py:242` |
| Step two: both lanes for the viewer with him added; who leaves the lineup | `playoff_targets.py:132-157` (`joined`) |
| His own team without him (Max PF moves' removal re-solve) | `playoff_targets.py:160-168` (`departed`) |
| One shared "before" run; the snapshot shifted for both teams; one "after" run | `playoff_targets.py:246`, `:253-255` |
| "After" = the saved 250,000-run figure plus the paired difference (Max PF moves' anchoring) | `playoff_targets.py:256` → `maxpf_moves.py:317-335` |
| A row only when the chance rises; ranked by the rise | `playoff_targets.py:257-258`, `:268-271` |
| `simulation.py` is not modified | — |

### 1.5 The read

| Step | Where |
|---|---|
| The raw saved block is stripped from every served result, in every flag state | `api.py:56-57` |
| The composed block is added only while the flag is on | `api.py:215-216` |
| Never raises: an unreadable block is `unavailable` / `read_failed` | `api.py:138-140` |
| State precedence | `playoff_targets.py:299-350` |
| A served row is the saved row minus `seller_roster_id`, plus `seller` (name, chance, proof): no outlook, no owner id | `playoff_targets.py:280-281` (`_ROW_KEYS`), `:344-348` |

### 1.6 The app

| Step | Where |
|---|---|
| The screen reads the flag and passes the block and its own roster query; no new query | `mobile/src/screens/StandingsScreen.tsx:81`, `:274-277` |
| Mount rule: flag, block, Sleeper, own card, version 1, a known state | `mobile/src/utils/playoffTargets.ts:52-55`; called at `mobile/src/components/LeagueProjectionDetail.tsx:56-59` |
| Placement: after the Max PF moves disclosure | `LeagueProjectionDetail.tsx:91-93` |
| Default open: the complement of Max PF moves' rule, from its constant | `playoffTargets.ts:62-66` |
| A row whose player has left his team's live roster is dropped | `playoffTargets.ts:70-82` |
| Every line and number is formatted from the block; the playoff chance goes through the D-262 rule | `playoffTargets.ts:91`, `:133-143` |
| The impression fires once per opening of the card | `mobile/src/components/PlayoffTargetsSection.tsx:40-45` |
| The hand-off: receive pin, give cleared, event, `popTo('Main', …)` with the canvas prefill and the partner | `playoffTargets.ts:269-276`, `:250-259`; `PlayoffTargetsSection.tsx:47-56` |
| The button renders only with a resolved partner | `playoffTargets.ts:185`, `:211` |
| TradesScreen consumes `canvasPrefill` (unchanged code) | `mobile/src/screens/TradesScreen.tsx:1362-1368` |

## 2. Measured job time

The 12-team, 14-week synthetic fixture league (`backend/tests/test_season_points.py`
`sleeper_world`: 24-player rosters, 9 starting slots, real `provider.capture`, the production
best-available scoring contract), on a laptop, shipped settings (5,000 runs, 8 candidates).

| What | Result |
|---|---|
| The step inside the real worker (`service._run`, `test_playoff_targets_job.py::test_flag_on_adds_only_the_block`, three runs) | **7.7 s, 7.9 s, 7.9 s**; 144 players checked (6 selling teams), 81 candidates, 8 rows; saved block 6.8 KB |
| Max PF moves' step in the same session, for scale (`test_maxpf_moves_job.py`, three runs) | 8.7 s, 9.0 s, 9.1 s; saved block 38.4 KB |
| One 5,000-run simulation | 0.77 s. The step runs 9 (one "before", 8 "after"), about 6.9 s of the total |
| Step one, every player on the selling teams | 0.5 s (1.0 s without the skip of §1.4) |
| Every other team selling (11 teams, 264 players) | 7.9 s for the whole step |

So with both flags on the weekly job spends about 17 s on the two steps for this league, against
budgets of 60 s each and the shared 480 s line. The cost is nearly all simulation and is set by
`candidates`, not by how many teams are selling: each extra re-simulated player costs about one
simulation (0.8 s here). It grows with weeks remaining and league size the way Max PF moves'
does.

**Not measured:** the job on Render (a slower, shared CPU), a superflex or IDP league with
larger rosters and more slots, or a league with more than 12 teams. The saved block's
`elapsed_ms` records the real figure for every run once the flag is on.

## 3. Manual TestFlight checklist

For the operator, on a TestFlight build that contains this branch, with
`league.playoff_targets` on for the test environment and a weekly forecast saved **after** the
flag was turned on (before that the section reads "appear after the next update"). Use a
Sleeper league in season, before its trade deadline.

| # | Do | Expect |
|---|---|---|
| 1 | Open Standings and tap your own team | Under "Max PF moves" there is a "Playoff targets" row. If your playoff chance is above 45% and your saved outlook is not Rebuilding or Tanking it is already open and Max PF moves is closed; otherwise the reverse |
| 2 | Tap any other team | No "Playoff targets" row on that card |
| 3 | Read the first line of the open section | "Your playoff chance today: N%." and N matches the Playoffs column for your team in the table (same rounding) |
| 4 | Read the rows | At most 5, then "Show all". Each has a name and position, a number with a leading + on the right, "Playoff chance N% → M%" with M above or equal to N, and a team name with its playoff chance |
| 5 | **The rule.** For every row, find the row's team in the Standings table | Its Playoffs figure is under 50%, **or** you know that manager has Rebuilding or Tanking saved. No row belongs to a team at 50% or above whose manager has not saved one of those. Your own players never appear |
| 6 | Open the top row | "Starts for you in K of the remaining N weeks.", a "Starts over …" sentence naming a player on **your** roster (or "Fills an open lineup spot"), and "Find trades for [player]" |
| 7 | Open Weekly projections for a week the row affects and find the player it says he starts over | That player is in your projected lineup for that week |
| 8 | Tap "Find trades for [player]" | The app goes to Trades. The trade canvas shows that player on the side you **receive**, the partner is his team, and your give side is empty. Nothing has been searched yet |
| 9 | Go back to Standings and open your card again | The section is as you left the page; reopening the card does not break anything |
| 10 | With a second account in the same league, on a team at or above 50%, save a Rebuilding outlook. Reload Standings on the first account | The next weekly forecast lists that team's players if they help you. Before it runs, the section shows "A team's outlook changed after this forecast…" |
| 11 | After step 10's team has rows: change that manager's outlook to Contender and reload Standings on the first account | That team's rows are gone at once, without waiting for a forecast |
| 12 | Read the two sentences under the list | One says the number assumes you give up only picks or players who would not start and that the true gain is usually smaller; the other states the under-50% / Rebuilding / Tanking rule |
| 13 | Open the section in a league where your team is at 99% or above, or has clinched | One line ("…so no trade raises that by a visible amount." or "You have clinched a playoff spot."), no list |
| 14 | Open Standings in an ESPN or MFL league | No "Playoff targets" row |
| 15 | Turn the flag off and reload | The row is gone; everything else on the card is unchanged |
| 16 | Set the phone's text size to its largest and open the section | No row is cut off; the team name truncates with an ellipsis, numbers do not |

A regression this checklist is built to catch: a row from a team that is not selling (step 5),
the player landing on the give side (step 8), and the section appearing on someone else's
card (step 2).
