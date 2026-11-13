# Max PF moves: which players to trade away to improve your draft pick — exploration

> Feature exploration, **not built**. No product code changed. Written 2026-11-12 (NFL week 10)
> against `origin/main` `53711036`. Operator ask, verbatim: "a feature on the non-playoff picks
> tab of projected standings ... to help these users identify the biggest opportunities to
> reduce max PF by trading away players. The feature should present those players, the
> calculated change to max PF, updated draft pick projection by trading the player. This
> feature must be able to understand which player on the users' roster will replace the traded
> player to ensure the reduction in max pf is accurate."
>
> Everything marked **measured** was run in a scratch script on an invented 12-team league (the
> repo's synthetic test league, with made-up results for weeks 1 to 9). No real league, manager
> or user appears anywhere in this document. Everything else was read from the code and is
> cited as `file:line`.

- [1. Recommendation](#1-recommendation)
- [2. Terms](#2-terms)
- [3. Where the feature belongs](#3-where-the-feature-belongs)
- [4. What the user sees](#4-what-the-user-sees)
- [5. Who it is for, when it shows, paywall, tone](#5-who-it-is-for-when-it-shows-paywall-tone)
- [6. Worked example](#6-worked-example)
- [7. The calculation, in three tiers](#7-the-calculation-in-three-tiers)
- [8. What the forecast does today](#8-what-the-forecast-does-today)
- [9. Effects the ask did not mention](#9-effects-the-ask-did-not-mention)
- [10. Measurements](#10-measurements)
- [11. How to validate before shipping](#11-how-to-validate-before-shipping)
- [12. Analytics, flag and docs if built](#12-analytics-flag-and-docs-if-built)
- [13. Effort](#13-effort)
- [14. Decisions for the operator](#14-decisions-for-the-operator)
- [15. What the code could not tell us](#15-what-the-code-could-not-tell-us)

## 1. Recommendation

Build it, as a section called **Max PF moves** inside the user's own team card on the Standings
page, behind a new flag. The first version (v1) should do four things.

1. **Use the exact calculation, not the "next best bench player" shortcut.** For every player
   on the user's roster and every remaining regular-season week, rebuild the best lineup
   without that player and take the difference. The function that does this already exists
   and takes about 0.14 milliseconds per team-week (measured), so the exact answer costs
   nothing extra. The shortcut is wrong by more than 5 points for about half of all starters
   on the invented league, and it puts a different player at the top of the list for 4 of 12
   teams.
2. **Re-run the forecast for the top 8 candidates, on a small paired sample.** The saved
   forecast keeps no per-simulation data, so pick odds cannot be looked up after a roster
   change. A paired re-run (same random numbers with and without the player) of 5,000
   simulations takes about a third of a second per player (measured, laptop) and is accurate
   to about 0.01 of a draft slot. Do this once a week inside the existing forecast job, and
   save the answers with the forecast. Nothing new runs when the page opens.
3. **Show three "after" numbers, not one.** The ranked pick label from D-257 (for example
   "1.02") is a league ranking, so it often does not move even when the pick clearly improves:
   on the invented league one team stayed "1.02" for all eight of its candidates while its
   chance of a top-3 pick went from 46% to 77%. Show the label, and beside it the pick if you
   miss the playoffs (one decimal), the chance of a top-3 pick, and the change in the pick's
   trade value.
4. **Say plainly what the number assumes.** The drop shown is the most the trade can do: it
   assumes the user gets back picks or players who would not start. It also lowers the
   team's playoff chance, and for a team still in the race that is where most of the "better
   pick" comes from. Show the playoff change on every row.

The three findings that shape this most:

| Finding | Where | Consequence |
|---|---|---|
| The lineup solver is a pure function that takes a list of players and returns the best lineup. Removing one player and calling it again is the exact "who replaces him" answer, week by week | `backend/league_projections/core.py:145-194`; per-player weekly points are recoverable from the saved run by `season_points.player_points` (`season_points.py:82-88`) | No new lineup logic is needed. The operator's rule becomes the wording ("Mercer starts instead"), not the maths |
| The saved forecast keeps each team's average projected max PF, three percentiles and the final pick odds, but not the individual simulations | `simulation.py:285`, `:301-305` | Pick odds after a roster change need a re-simulation. The simulation is deterministic for a given seed, so a paired re-run is cheap and low-noise |
| In the model, a future week's projected max PF is the projected best lineup, the same number as the projected score unless a taxi-squad player would start | `provider.py:488-493`, `simulation.py:137-138`, `joint.py:73-78` | Trading a starter lowers projected scoring and max PF together. Playoff odds fall too. The feature must show both, and cannot pretend the max PF change is free |

## 2. Terms

| Term | Meaning in this document |
|---|---|
| **Max PF** | "Maximum points for": the points a team would have scored each week had it started its best possible lineup. Sleeper keeps a season total for each team. Many dynasty leagues order the rookie draft for non-playoff teams by lowest max PF, so that benching good players does not improve a pick |
| **Rest of season (ROS)** | The remaining regular-season weeks. The forecast stops at the last week before the league's playoffs start (`provider.py:254-259`) |
| **Forecast** | The weekly league forecast in `backend/league_projections/`: 250,000 simulated finishes of the regular season, giving each team's playoff chance and, for teams that miss, the odds of each draft slot. Flag `league.projections`, on in production, Sleeper leagues only |
| **Lineup lane / max PF lane** | The forecast builds two best lineups per team per week. The lineup lane uses the active roster and sets the projected score. The max PF lane also lets taxi-squad players start, and sets projected max PF |
| **Replacement** | The player or players who enter the best lineup once the traded player is gone. It can be a different player in different weeks |
| **Paired re-run** | Running the simulation twice with identical random numbers, once with and once without the player, and reading the difference. Random noise cancels |
| **Pick if you miss** | The average draft slot in the simulations where the team misses the playoffs. The app already shows it as "Expected pick if this team misses" |
| **Ranked label** | The D-257 rule (in flight on `feat/projected-pick-rank`, not on main): teams are ordered by expected slot and labelled 1.01 to 1.N, each label used once |
| **Pick value** | The engine's trade value for the pick, from the existing pricing (`pick_values.priced_pool_value`, `pick_values.py:810-889`) |

## 3. Where the feature belongs

**The "non-playoff picks tab" no longer exists in the app code on main.** It was a toggle
("Playoffs | Non-playoff picks") on the old projected standings section. That section was
removed today by the single-table Standings rebuild (D-254, commit `1791beba`), which needs
the next app build, so an installed build may still show the old tab. On main today its
content lives in two places:

| Old tab content | Where it is on main |
|---|---|
| Team list sorted by projected max PF, with "Miss playoffs" | Standings page, **Points** view: columns PF, Max PF, Proj. Max PF (`mobile/src/screens/StandingsScreen.tsx:66-69`) |
| Per-team pick detail (pick owner, expected pick if the team misses, odds of each pick) | The **Draft pick odds** section inside a team's open card (`mobile/src/components/LeagueProjectionDetail.tsx:40-52`) |
| The tab itself | Still on the website only (`web/js/league-projections.js:32`) |

**Recommended home:** a fourth section, **Max PF moves**, directly under Draft pick odds, shown
only inside the user's own team card. Reasons:

- It is where the numbers it changes are already shown (max PF, pick odds), in either view.
- The card already reads the saved forecast once and starts no simulation (D-254). A list
  saved with the forecast keeps that rule.
- It needs no new screen, no navigation entry and no new feedback button mount.

Secondary entry points, later and optional: a line in Team Review's plan step for users whose
saved outlook is Rebuilding or Tanking, and the Home playoff tile's low band. Neither is
needed for v1.

## 4. What the user sees

### 4.1 Layout

A text sketch of the user's own open card on Standings. Names are invented.

```
 Harbor Herons   You                      3–6    Proj. 5–9    Playoffs 3%
 ┌───────────────────────────────────────────────────────────────────────┐
 │ PF 1,012 · Max PF 1,140 · Proj. Max PF 1,612                          │
 │ > Final record odds                                                   │
 │ > Weekly projections                                                  │
 │ > Draft pick odds                                                     │
 │ v Max PF moves                                                        │
 │   Your 2027 1st today: 1.02 projected. If you miss the playoffs,      │
 │   pick 3.7 on average. 46% chance of a top-3 pick. Value 2,480.       │
 │                                                                       │
 │   Player        Max PF,   Pick if     Top-3     Pick     Playoff      │
 │                 5 weeks   you miss    chance    value    chance       │
 │   R. Sato  RB    −31      3.7 → 3.4   46 → 62%  +169     3% → 1%      │
 │     Mercer starts instead (4 weeks), Quill (1 week)                   │
 │   D. Okafor WR   −28      3.7 → 3.4   46 → 61%  +153     3% → 1%      │
 │     Lund moves to WR and Mercer takes the flex (4 weeks). Bye wk 12   │
 │   ... up to 5 rows, "Show all" for the rest                           │
 │                                                                       │
 │   Largest possible change: assumes you get back picks or players      │
 │   who would not start for you. Assumes your league orders the draft   │
 │   by lowest max PF.  Change                                           │
 │   [ Find trades for Sato ]                                            │
 └───────────────────────────────────────────────────────────────────────┘
```

On a phone the six columns do not fit one row. Each player is a two-line row: name, position
and the max PF change on the first line; "pick if you miss" and pick value on the second.
Tapping a row opens the rest (top-3 chance, playoff chance, ranked label, the week-by-week
replacement). All UI follows the Chalkline design system; ice for the action, no new colours.

### 4.2 Columns

| Column | Source | Notes |
|---|---|---|
| Player, position | The user's roster in the saved forecast | Tag a player the user has marked Keep / untouchable (D-241). Show the row, hide its trade button |
| Max PF change, rest of season | Exact weekly re-solve, max PF lane (§7.1) | Whole points. Header states the number of weeks left |
| Replacement, by name | Players who enter the best lineup, with the number of weeks each | One line. More than one name is normal: on the invented league 87 of 108 starters were covered by more than one player across five weeks (measured) |
| Pick if you miss: now → after | Paired re-run | One decimal |
| Top-3 chance: now → after | Paired re-run | "Top 3" is a display choice. An alternative is the single most likely slot |
| Pick value change | Existing pricing applied to the before and after slot odds | Engine value units, the same number the trade finder prices the pick at |
| Playoff chance: now → after | Paired re-run | Always shown. It is the cost side |
| Ranked label: now → after | D-257 rule on the after odds | In the opened row. Shown in the main row only when it changes |

### 4.3 Which players are listed

| Rule | Proposed value | Why |
|---|---|---|
| Candidates | Every player on the user's roster with a non-zero max PF change | On the invented league 10 to 13 of 24 players per team |
| Re-simulated | The 8 largest by max PF change | Each costs one paired re-run. The rest would show a max PF change but no pick numbers, so they are not listed |
| Shown by default | Up to 5 that pass the threshold, "Show all" for the rest of the 8 | Keeps the card short |
| Threshold | Max PF change of at least 5 points over the rest of the season **and** a pick-if-you-miss change of at least 0.1, or a top-3 change of at least 2 points | Below this the change is inside what a week of injury news moves anyway |
| Order | Largest max PF change first | The operator's ask. A second sort, "pick value gained per point of trade value given up", is worth testing later: it surfaces older high scorers, which is also what the D-244 sell bonus favours |
| Excluded | Players on injured reserve (they are not in the max PF pool under the production setting `ir_maxpf: exclude`), and players with no projection (unknown is not counted as zero) | `provider.py:404-406`, `:458-460` |

### 4.4 States

| State | What shows |
|---|---|
| Forecast current, user owns their own next-year 1st, playoff chance at or below 45% | The full list |
| Playoff chance above 45% | Section collapsed, one line: "Your team makes the playoffs in 62% of simulations. Moving these players lowers that." The list opens on tap |
| Team almost never misses the playoffs (the forecast gives no "pick if you miss" when fewer than 100 simulations miss, `simulation.py:302-303`) | No list: "Your team is not projected to miss the playoffs." |
| User does not own their own next-year 1st (`pick_owner_roster_id`, `simulation.py:191-196`, `:307`) | One line naming the team that owns it: lowering max PF improves their pick. List behind "Show anyway" |
| No forecast, forecast being prepared, last update failed, stale, older model, incomplete | The existing sentences for those states (`recommendation.py:34-46`, `:83-103`). No list |
| Roster has changed since the forecast was saved | Notice: "Your roster changed after this forecast. The list updates with the next weekly forecast." Rows for players no longer on the roster are dropped |
| League does not order the draft by max PF (user answered, §5.3) | No list, one line with a link to change the answer |
| After the league's trade deadline | No list: "Your league's trade deadline has passed." The forecast does not read the deadline today (only Win Now does, `win_now_service.py:193`), so capture would need to keep it |
| Regular season over | No list. The forecast has no weeks left to change (§8.5) |
| No player passes the threshold | "No single player moves your projected pick by a visible amount." |
| ESPN or MFL league | The Standings page's existing unavailable card. There is no forecast (§8.6) |

### 4.5 The next action

One button per opened row: **Find trades for [player]**. It puts the player on the "give" side
of the trade finder using the pin list that already exists (`mobile/src/state/useFinderTargets.ts:72-88`,
event `finder_target_pinned`). League rankings already has the same hand-off for "Offer"
(flag `league.player_trade_handoff`).

Preferring returns that do not push max PF back up is a tier 2 item (§7.2). The engine has a
related, dormant piece: for users whose saved outlook is Tanking or Rebuilding, trade
generator revision 5 scores cards on lineup points given up (D-238, knobs
`season_shed_weight_tanking` and `season_shed_weight_rebuilding`; revision 5 is switched off).
Until that is on, v1 can only pin the player. The card the user then sees is not guaranteed
to be max PF neutral, which is one more reason the list must say "largest possible change".

## 5. Who it is for, when it shows, paywall, tone

### 5.1 Audience and visibility

| Question | Recommendation |
|---|---|
| Whose team | The user's own team only. The forecast is saved per user and per league and marks the viewer's team (`viewer_roster_id`). Other teams' lists are possible from the same data but are a different product ("who in my league should be selling") |
| When open by default | Playoff chance at or below 45%, the line the outlook suggestion already uses between Rebuilding and Contender (`recommendation.py:25`), or a saved outlook of Rebuilding or Tanking |
| When collapsed | Playoff chance above 45% |
| When hidden | No usable forecast, league not on max PF order, after the deadline, regular season over, non-Sleeper league |

### 5.2 Paywall

`monetize.*` flags exist, and the paywall flag is on in production through the Render
override (`docs/config-reference.md:283`). Options only:

| Option | Trade-off |
|---|---|
| Free | It leads straight into the trade finder, the core loop. Simplest |
| Free list, paid detail | The list of players is free; pick value and odds changes are Pro. More to build, and the free half is less useful |
| Pro only | Clean, but the audience (teams out of the race) is where late-season engagement is weakest |

### 5.3 Tone and league integrity

Moving a productive older player for future value when a season is lost is ordinary dynasty
strategy, and max PF draft order exists so that lineup choices cannot improve a pick. Some
leagues still police roster moves made for draft position.

- **Wording.** "Max PF moves", "lowers your max PF", "improves your projected pick". Never
  "tank" in this section's copy, and never anything about who to start or bench.
- **No hard guard.** The app already has a Tanking outlook and already suggests "prioritizing
  future value and draft position" (`recommendation.py:28`). A block here would be
  inconsistent.
- **Two light guards.** The draft-order question below, and one sentence the first time the
  section opens: "Check your league's rules on trades made for draft position."
- **Draft-order question, asked once per league.** "How does your league set next year's
  draft order for non-playoff teams?" Answers: lowest max PF; reverse standings; lottery or
  other; not sure. Until answered, show the list with the existing line "Estimates assume
  regular-season Max PF draft order." Reverse standings, lottery or other: hide the list. An
  unbuilt design for ESPN and MFL forecasts already proposes a per-league setting for this
  (`leagues.draft_order_rule`, `docs/plans/forecasts-espn-mfl/design.md` §5.2, operator-set
  only). If that is built, this question should write to it, and the same answer should then
  stop the projected-slot pick pricing (D-240) from assuming max PF for a league that does
  not use it.

## 6. Worked example

Invented league: 12 teams, 6 make the playoffs. Lineup: QB, 2 RB, 2 WR, TE, 1 flex
(RB/WR/TE). Five regular-season weeks left (weeks 10 to 14). The Harbor Herons are 3–6.

| Player | Position | Projected points a week | Role today |
|---|---|---|---|
| Nico Varga | QB | 19 | Starts |
| Rhett Sato | RB | 15 | Starts |
| Jonah Pike | RB | 12 | Starts |
| Cal Mercer | RB | 10 | Bench |
| Dale Okafor | WR | 17, bye in week 12 | Starts |
| Milo Brandt | WR | 13 | Starts |
| Tavi Lund | WR | 11 | Starts in the flex |
| Ezra Quill | WR | 4 | Bench |
| Bo Halvorsen | TE | 9 | Starts |

**The simple rule** (the traded player's rest-of-season points minus those of the best player
at his position who is not starting):

| Traded player | His points, 5 weeks | Best non-starter at the position | Simple-rule drop |
|---|---|---|---|
| Okafor (WR) | 68 (four games) | Quill, 20 | **48** |
| Sato (RB) | 75 | Mercer, 50 | **25** |

**The exact re-solve** (rebuild the best lineup each week without the player; checked with
the forecast's own lineup solver):

| Traded player | Normal week | Week 12 (Okafor's bye) | Exact drop |
|---|---|---|---|
| Okafor | Lund moves from the flex to WR and Mercer (RB, 10) takes the flex. 96 → 89, a drop of 7, in four weeks | He was not playing. Drop 0 | **28** |
| Sato | Mercer starts at RB. 96 → 91, a drop of 5, in four weeks | Mercer was already in the flex covering the bye, so Quill (4) has to start. 89 → 78, a drop of 11 | **31** |

The two methods disagree in both directions. For Okafor the simple rule replaces him with the
weak bench receiver; in fact a running back takes the open flex spot, and one of his five
weeks was a bye anyway. For Sato the simple rule misses that his replacement was already
needed in the bye week. **The order flips**: the simple rule says Okafor is the much bigger
move (48 against 25); the exact answer says Sato is slightly bigger (31 against 28).

What that does to the pick. These numbers come from running the forecast engine on the
invented league with those week-by-week drops applied to a team in the Herons' position
(20,000 paired simulations; pick values use the per-slot curve documented in
`docs/plans/pick-value-projected-slot/design.md` §5 with the generic first at 1,860):

| | Playoff chance | Pick if you miss | Top-3 chance | Pick value | Ranked label |
|---|---|---|---|---|---|
| Today | 2.7% | 3.69 | 46% | 2,480 | 1.02 |
| Without Sato, exact (−31) | 1.2% | 3.36 | 62% | 2,650 (+169) | 1.02 |
| Without Okafor, exact (−28) | 1.3% | 3.39 | 61% | 2,633 (+153) | 1.02 |
| Without Okafor, simple rule (−48) | 0.7% | 3.19 | 71% | 2,736 (+256) | 1.02 |
| Without Sato, simple rule (−25) | 1.4% | 3.42 | 59% | 2,617 (+136) | 1.02 |

The simple rule would overstate what trading Okafor is worth to the pick by about two thirds
(+256 against +153). The ranked label does not move in any row.

## 7. The calculation, in three tiers

### 7.1 Tier 1, the recommended v1: exact lineup, paired re-run, nothing coming back

**Inputs.** All from the saved weekly run, `league_projection_runs.snapshot_json` and
`result_json`. No new reads from Sleeper.

| Input | Where it is |
|---|---|
| Each rostered player's projected points for each remaining week | `snapshot.player_week_inputs`, re-scored by `season_points.player_points` (`season_points.py:82-88`). The win-now season signal already reads the snapshot this way (`season_value.py:85-125`) |
| Lineup slots, and each team's active, taxi and reserve lists | `snapshot.slots`, `snapshot.teams[].roster` (`provider.py:343`, `:641`) |
| The baseline forecast: slot odds, playoff chance, pick owner | `result.teams[]` (`simulation.py:293-309`) |
| The simulation settings and seed | `result.config` |

**Formula.** For a player *p* on the user's roster *R*, and each remaining week *w* that has no
game already played in the snapshot:

```
A_w(R)  = best lineup total from the active roster           (lineup lane)
M_w(R)  = best lineup total from active + taxi players       (max PF lane; reserve excluded)
          each then fills any open slot with the best projected free agent, else 0

dA_w(p) = A_w(R) − A_w(R without p)
dM_w(p) = M_w(R) − M_w(R without p)

Max PF change, rest of season  = − Σ_w dM_w(p)
Replacement                    = the players in the lineup for M_w(R without p)
                                 who were not in the lineup for M_w(R), with week counts
```

`best lineup total` is `core.optimize` (`core.py:145-194`), an exact assignment of players to
slots that already handles flex, superflex and the other combined slots (`core.py:11-18`).
Points already banked this season are not touched: the simulation starts every world from the
team's official season max PF and adds only the remaining weeks (`simulation.py:160`, `:203`,
`:252`).

**From max PF change to pick projection.**

1. Copy the snapshot. For the user's team, lower each remaining week's projected score by
   `dA_w(p)` and projected max PF by `dM_w(p)`.
2. Run the existing `simulate` (`simulation.py:80`) twice with the saved seed at 5,000
   simulations: once on the saved snapshot, once on the copy. Take the difference in the
   user's slot odds, playoff chance and pick-if-you-miss. With no change to the roster the
   two runs are identical, so the difference is exactly zero. The older playoff-odds
   "trade impact" feature uses the same technique at 2,000 simulations
   (`backend/outlook/trade_delta.py:63`).
3. "After" = the saved 250,000-simulation figure plus that difference.
4. Ranked label: apply the D-257 ordering to every team's "after" expected slot. Other
   teams' odds shift a little when one team falls, and those shifts come out of the same
   re-run.
5. Pick value change: `G × w × (ratio_after − ratio_before)`, the existing formula
   (`pick_projection.py:203-211`, `pick_values.py:770-792`), computed when the page is read,
   because prices depend on live settings and the market curve.

**Where it runs.** In the weekly forecast job, straight after the main simulation
(`service.py:109`), for the viewer's team only. The answers are saved inside the run's result
and travel to the app with the forecast it already downloads (`api.py:41-45`). Pick values are
added at read time, the way the outlook suggestion is (`api.py:112-116`).

**Cost** (measured on a laptop, Python 3.12, 12 teams, five weeks left; production will be
slower):

| Step | Cost |
|---|---|
| Lineup re-solve, one team-week | 0.14 ms |
| Whole roster (24 players), five weeks, one lane | 17 ms |
| One simulation run of 5,000 | 0.33 s |
| Eight candidates, paired, including copying the snapshot | 3.5 s |
| For scale: the weekly 250,000 run | about 16 s (extrapolated from 100,000) |

Cost grows with weeks remaining: roughly three times this in week 1. The job has a 540-second
budget per run (`service.py:83`).

**Accuracy risks, to be stated in the product, not hidden.**

| # | Approximation | Direction of error |
|---|---|---|
| 1 | Nothing that starts comes back in the trade | The drop shown is a maximum |
| 2 | Projected max PF is the projected best lineup. Real max PF is the best lineup in hindsight, which is higher, and higher still for a deep bench. The forecast's own warning says so (`simulation.py:340`) | A bench player who would sometimes outscore a starter shows a change of 0 when the true change is small but real. Starters' drops are slightly understated |
| 3 | One projection per player per week from Sleeper's feed. An injury label alone does not remove a player (`provider.py:663-664`); a player with no projection is unknown, not zero | A hurt player whose projection the feed has not cut shows too large a drop |
| 4 | The same weekly spread, 25 points, for every team, marked provisional (`config/league_projections.json`, `simulation.py:333`) | Pick odds are probably too uncertain or too certain by an unknown amount. The change is less affected than the level |
| 5 | The buyer's roster does not change | See §9, item d |
| 6 | The league orders the draft by regular-season max PF | §5.3 |
| 7 | The list is as of the weekly forecast (Tuesday 09:30 Eastern). Trades and injuries after that are not in it | Stale until the next run. The roster-changed notice covers trades |
| 8 | A newly opened slot nobody on the roster can fill | Today the saved run keeps only the free agents that were actually used (`provider.py:581-587`), so the re-solve would count the slot as 0 and overstate the drop. On the invented league this affected 12 of 288 removals, mostly a team's only quarterback or tight end. Fix: have capture keep the top few free agents per position per week (a small change in `provider.py`), or flag those rows |
| 9 | Playoff teams' draft positions are not projected; their share is spread evenly over the late slots (`pick_projection.py:123`) | Matters for the ranked label and the pick value of teams still in the race, as it does today |
| 10 | "After" mixes a 250,000-run baseline with a 5,000-run difference | Negligible: about ±0.01 of a slot (measured, §10) |

### 7.2 Tier 2: the whole trade

Adds what comes back, the other team, and returns that keep max PF down.

| Item | What it adds |
|---|---|
| Inputs | The same snapshot. It holds weekly projections for every rostered player in the league, so any trade between two teams in the league can be evaluated: roster − give + receive, re-solved each week, for both teams |
| Formula | As tier 1, with both teams' weeks changed in the copy before the paired re-run. The buyer's max PF and score go up; the result includes the effect on the lottery order if the buyer is also likely to miss the playoffs |
| Where | On a trade card or in the calculator: "This trade: max PF −22, pick value +120, playoff chance −1 point". Either as an on-demand queued run (the forecast API already accepts a scenario run that reuses a saved snapshot, `api.py:54-93`, limited to four runs per ten minutes per user, `store.py:81-84`), or computed for each card in the deck job for users with a Rebuilding or Tanking outlook |
| Hand-off | "Find trades" prefers returns that do not start for the user: picks, taxi-eligible players, players below the user's starters. This is the lineup-points-shed scoring revision 5 already contains (D-238) |
| Cost | One paired re-run per card (about 0.3 to 0.7 s each on a laptop). A 30-card deck is too slow to do inline; it needs the saved-baseline pattern the older trade-impact feature uses (`server.py:1441-1464`), or to run only for the card the user opens |
| Accuracy risks | Tier 1's, minus items 1 and 5. New: the trade finder's per-card season figure is a points-per-game average (`trade_gen_bilateral_season.py:383-398`), not a weekly re-solve, so the two numbers on one card could disagree unless the card uses the exact one |

### 7.3 Tier 3: a better model

| Item | What it adds |
|---|---|
| Hindsight max PF | Model the gap between the projected best lineup and the hindsight best lineup, so bench depth counts. Needs per-player weekly variance. Removes risk 2 |
| League draft-order rules | Reverse standings and lottery as rules inside the simulation (the ESPN and MFL design already specifies reverse standings). Lets the feature say something for those leagues, though for reverse standings the honest advice is about wins, not max PF |
| Playoff weeks | If a league's max PF keeps counting after the regular season, model those weeks for non-playoff teams |
| Calibration | Score this season's saved forecasts against the final draft order (weekly baselines are kept 90 days for this, D-240) and tune the spread |
| All candidates in one run | A simulation loop that carries every candidate's version of the user's team through the same random draws, instead of one run per candidate. Cuts tier 1's cost several times; only worth it if lists grow |

### 7.4 Considered and not recommended: the simple rule as the calculation

The operator's rule, taken literally, is one subtraction per player. It is not cheaper in any
way that matters (the exact answer for a whole roster takes 17 ms), it is wrong by a visible
amount for about half of starters (§10), and it cannot say anything about the pick without the
same re-run. Keep the rule as the explanation the user reads ("Mercer starts instead").

## 8. What the forecast does today

### 8.1 Player projections and lineups

| Question | Answer | Where |
|---|---|---|
| Which projections | Sleeper's weekly projection feed, one row per player per remaining week, scored with the league's own scoring settings. Only the stat lines the feed supplies are counted ("best available") | `provider.py:109`, `:171-173`, `:471-477`; production setting `scoring_contract: sleeper_best_available_v1` in `config/league_projections.json` |
| Horizon | From the current week to the last regular-season week. Playoff weeks are not forecast | `provider.py:254-259`, `:645` (`postseason_rounds_simulated: false`) |
| Slots | The league's starting slots, bench, IR and taxi removed. Flex, superflex, WR/TE and WR/RB flex, kicker and the defensive-player slots are supported | `provider.py:260`, `core.py:11-18` |
| How a lineup is filled | An exact best assignment of players to slots, not a greedy fill, so flex chains come out right | `core.py:107-194` |
| Bye weeks | A player on a verified bye is left out of that week | `provider.py:451-457` |
| Injuries | Not applied directly. A player is in if the feed projects him. His injury label is stored for display only | `provider.py:463-468`, `:484`, `:664` |
| Taxi squad | Not in the lineup lane. **In** the max PF lane | `provider.py:488-493` |
| Injured reserve | In neither lane under the production setting `ir_maxpf: exclude` | `provider.py:404-406`, `:492` |
| Open slots | After the roster is used, each open slot takes the best projected free agent (not on any roster in the league), or 0 if there is none. Both lanes. This is the "open lineup slots use the best available free agent" rule, D-234 | `provider.py:506-508`, `:530-531`, `core.py:197-237` |
| Defensive-player bye fill | A league-average stand-in for a defensive player on bye, where the rule applies | `core.py:240-280` |
| Whose lineup | The best projected lineup, not the lineup the manager has set, for every future week | `provider.py:507`, `simulation.py:131-134` |

### 8.2 What is simulated and what is fixed

| Fixed (no randomness) | Simulated |
|---|---|
| Results, points and max PF of completed weeks (official totals) | Each team's score in each remaining week: projected lineup total plus a random amount with a 25-point spread, the same for every team |
| Each team's projected lineup total and projected max PF for each remaining week | Each team's max PF in each remaining week: never below its simulated score; equal to it when the two projections are equal, which is the case whenever no taxi player would start |
| The schedule | Wins and losses, playoff seeding (record, then points for, points against, then a random draw), and the order of non-playoff teams by season max PF, lowest first |

Sources: `simulation.py:95-96`, `:158-160`, `:199-285`; `joint.py:73-78`; settings in
`config/league_projections.json` (250,000 simulations, spread 25, correlation 0, seed 42).

### 8.3 What the saved run keeps

| Kept | Not kept |
|---|---|
| Per team: record, points and max PF to date; expected and most likely final record; playoff and bye chance; odds of each non-playoff pick; pick if you miss; average projected max PF and its 10th, 50th and 90th percentiles; the pick's owner (`simulation.py:293-309`) | The individual simulations. Each team's simulated max PF totals are held in memory only long enough to take the average and percentiles (`simulation.py:285`, `:289`, `:304-305`) |
| Per team per week: both best lineups with player names and points, the players left out and why, coverage notes, win, loss and tie chances, the opponent (`provider.py:599-613`, `simulation.py:310-325`) | Bench players' points in the result. They are in the snapshot's `player_week_inputs` and can be re-scored exactly |
| The full capture (`snapshot_json`) for the latest successful run of each user and league | Snapshots of older runs. Runs older than 7 days are deleted; weekly baselines are kept 90 days with the snapshot removed (`store.py:23-45`) |

**Is there a lineup function that can be re-run with one player removed?** Yes:
`core.optimize(slots, players, empty_policy=...)` (`core.py:145`). `season_points.lineup_parity`
already rebuilds each team-week from the saved inputs and proves it reproduces the saved
lineup total (`season_points.py:101-130`), for weeks with no free-agent fill and no game
played. The feature would extend that check to the max PF lane and to filled weeks.

### 8.4 Can pick odds be recomputed cheaply?

Not by lookup. Nothing saved describes how one team's max PF relates to the others' in each
simulated season, and whether a team misses the playoffs is tied to its own scoring in the
same simulation. An approximation from the saved averages and percentiles would need its own
validation and would still miss the playoff effect. A re-simulation is needed, but a small
paired one is enough (§7.1, §10). The full run happens in a background worker started by the
15-minute scheduled tick, never in a page request (`batch.py:146`, `service.py:15-23`,
`server.py:46418`).

### 8.5 Playoff weeks

The forecast's max PF is regular season only. Once the regular season is over there are no
weeks left to simulate and the order in the forecast is fixed. Whether a league keeps counting
max PF during its playoff weeks is not known to the code (§15).

### 8.6 ESPN and MFL

There is no forecast for them: the routes answer "Sleeper only" (`api.py:73-74`, `:102-103`)
and only Sleeper leagues are scheduled (`batch.py:141`). So the feature cannot show for those
leagues. A design to extend the forecast to both exists and is not built
(`docs/plans/forecasts-espn-mfl/`). Under that design ESPN leagues default to reverse
standings, where max PF does not set the order, so this feature would apply to MFL leagues
and to Sleeper leagues only.

## 9. Effects the ask did not mention

| | Effect | How v1 handles it | Size on the invented league (measured) |
|---|---|---|---|
| a | Trading a starter lowers real scoring, so win chances and playoff odds fall, which itself moves the expected pick | Included automatically: both lanes are lowered before the re-run. Shown as its own column | For a team at 3% playoff chance, a 42-point drop improved the expected slot by 0.54, of which 0.44 came from lottery position. For a team at 26%, a 57-point drop improved it by 1.22, of which **1.00 came from giving up the playoffs** (26% → 12%) and only 0.23 from lottery position |
| b | What comes back. Picks and non-starters leave the drop intact; a returning starter cancels some or all of it | v1 states the assumption. Tier 2 computes the actual trade | Not measured |
| c | Max PF already banked is fixed | Built into the simulation: only remaining weeks change | A player's drop shrinks every week. With five weeks left the largest single-player drops were about 60 to 100 points on season totals of about 1,500 to 2,100 |
| d | The buyer's max PF rises | Ignored in v1. The buyer is usually a contender, whose pick is not in the lottery. It matters when the buyer is also likely to miss the playoffs: then the buyer can move behind the seller, which helps the seller a little more than v1 shows. The other direction to watch is when the user owns the buyer's first: raising that team's max PF hurts a pick the user holds. Tier 2 covers both | In the re-runs, other teams' pick-if-you-miss moved by up to 0.2 of a slot when one team dropped 40 points |
| e | The league may not use max PF order at all | Ask once per league; hide for other rules (§5.3) | n/a |
| f | The user may not own their own first | State it, list behind a tap (§4.4) | n/a |
| g | The pick's price in the trade finder already follows the forecast (D-240) | After a real trade the pick reprices at the next weekly forecast. The list shows that change ahead of time, with the same pricing, so the two agree | n/a |

## 10. Measurements

All on the invented league: 12 teams, 24 players each, lineup QB, 2 RB, 3 WR, TE, 2 flex;
weeks 1 to 9 given made-up scores; five weeks left. Scratch scripts, not in the repo.

**Simple rule against the exact re-solve, 108 starters.** "Same position" is the operator's
rule read literally. "Slot-eligible" lets the replacement be any bench player who could fill
the starter's slot.

| | Same-position rule | Slot-eligible rule |
|---|---|---|
| Median gap from exact, rest of season | 5.4 points | 5.0 points |
| Gap above 5 points | 53% of starters | 50% |
| Gap above 10 points | 29% | 25% |
| Largest gap | 36.8 points | 31.6 points |
| Overstates the drop by more than 2 | 41% | 31% |
| Understates the drop by more than 2 | 31% | 43% |
| Same top player as exact | 8 of 12 teams | not run |
| Overlap of the top five per team with exact | 49 of 60 | not run |

For scale, the median starter's exact drop was 22 points over the five weeks. Also: 87 of 108
starters were covered by more than one replacement across the weeks; 35 of 180 bench players
had a non-zero exact drop, which the simple rule shows as zero.

**What a point of max PF is worth.** For a team at 3% playoff chance in the middle of the
non-playoff group:

| Drop, rest of season | Expected slot | Top-3 chance | Playoff chance |
|---|---|---|---|
| 10 points | −0.14 | +5 points | −0.6 points |
| 30 points | −0.40 | +16 points | −1.5 points |
| 50 points | −0.63 | +25 points | −2.1 points |
| 100 points | −1.09 | +42 points | −2.6 points |

So a 10-point error in the max PF change, which the simple rule makes for a quarter of
starters, is about 0.14 of a slot and 5 points of top-3 chance.

**A real list.** For that team, the eight largest candidates moved the expected slot by
between 0.06 and 0.76 and the pick value by between +24 and +329 on a pick valued 2,480. The
ranked label stayed 1.02 for all eight.

**Noise of the paired re-run**, for a change of −0.40 slots and +15.8 points of top-3 chance
(reference: 100,000 paired), across 12 seeds:

| Simulations | Spread of the slot change | Spread of the top-3 change | Time per run |
|---|---|---|---|
| 2,000 paired | 0.013 | 1.1 points | 0.15 s |
| 5,000 paired | 0.010 | 0.7 points | 0.33 s |
| 10,000 paired | 0.007 | 0.4 points | 0.64 s |
| 5,000 not paired | 0.018 | 0.9 points | 0.33 s |

**Read, not measured:** everything in §8; production run times; how many leagues have a
current forecast.

## 11. How to validate before shipping

| Check | What it proves | When |
|---|---|---|
| Unit: re-solving with nobody removed reproduces the saved projected score and projected max PF for every team-week, including weeks with a free-agent fill | The re-solve is the forecast's own lineup, not a look-alike | Build |
| Unit: hand-built rosters for a flex chain, a bye week, superflex, a two-for-one position chain, a taxi player as the max PF replacement, a team's only tight end, a player on reserve | The cases in §6 and §7.1 | Build |
| Unit: removing a player never raises the lineup total; the drop is never more than the player's own points that week; a player who never starts gives 0 | Basic sanity | Build |
| Unit: an unchanged roster gives a pick change of exactly 0; the same input gives the same output | The paired re-run is honest | Build |
| Unit: the 5,000-run change is within a set tolerance of a 100,000-run change on a fixture | The sample size is enough | Build |
| Leave-one-out backtest on past weeks: at each past week, for each starter, compare the predicted rest-of-season drop (projections) with the realised drop (rebuild the hindsight-best lineup from actual points with and without him). Needs no real trade | How good "max PF change" is, and how big the bench-depth bias (risk 2) is | Before turning the flag on. Uses the historical projection and actual-points data the calibration research already uses (`docs/plans/league-projections/calibration-check/`) |
| Real trades: for trades the app has captured this season, compare the predicted drop for the selling team with what its roster actually posted afterwards | The same, on real moves, including what came back | After a few weeks of saved lists. Needs the per-player inputs, which are deleted after 7 days today; either keep them for a sample or run it weekly |
| Pick odds against the final draft order | Whether the forecast's pick odds are right at all. Not established today (`simulation.py:337`) | After the season; weekly baselines are already kept for it |
| Structural app check (`mobile/tests/check-*.js`): the section mounts only on the user's own card, every state in §4.4 has copy, the button pins the give side | App wiring, in place of a simulator run (D-056) | Build |
| Manual TestFlight checklist: own team in a league with a current forecast shows the list; another team's card does not; the top row's replacement names match the Weekly projections lineup for that week; "pick if you miss: now" equals the Draft pick odds line; Find trades lands in the finder with the player pinned; a non-Sleeper league shows the unavailable card; a league answered "reverse standings" hides the list | Runtime proof on a device | Before release |

## 12. Analytics, flag and docs if built

**Flag:** `league.max_pf_moves`, default false, read by backend and app; requires
`league.projections`. **Settings** in `config/league_projections.json`: simulations per
candidate (5,000), candidates re-run (8), minimum drop (5).

**Events**, named in the existing style (`backend/analytics_taxonomy.py`), registered and
classified in the same commit as the code that sends them. No player ids or names in
properties, following `shop_opened`.

| Event | When | Properties | Class |
|---|---|---|---|
| `maxpf_moves_viewed` | The section opens | `state`, `n_moves`, `band` (the playoff band `home_tile_tapped` already carries) | Impression: add to `NON_INTENT_EVENTS` |
| `maxpf_move_expanded` | A row is opened | `position`, `rank` | Intent |
| `finder_target_pinned` (exists) | Find trades is tapped | `side: give`, new `source` value `maxpf_moves` | Intent, already registered (`analytics_taxonomy.py:428`, `:1809`) |
| `draft_order_rule_answered` | The once-per-league question is answered | `answer`, `source` | Intent |

**Docs to update if built** (list only; no scope block is filled here):

- `docs/api-reference.md`: the new block on the forecast read
- `docs/data-dictionary.md`: the result block; where the draft-order answer is stored
- `docs/config-reference.md`: the flag and the three settings
- `docs/cross-client-invariants.md`: wording, rounding and the "largest possible change" rule
- `docs/glossary.md`: max PF, replacement, pick if you miss, max PF moves
- `docs/plans/league-projections/implementation.md`: the weekly job's extra step
- `living-memory/LLD.md`; `living-memory/HLD.md` and `docs/architecture.md` only if the
  worker's flow is judged an architecture change
- `mobile/src/components/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`
- `living-memory/DECISIONS.md`, `CHANGELOG.md`, `TEST_LEDGER.md`
- A scope block from `docs/templates/feature-scope.md` in this folder, before any build

## 13. Effort

Estimates for tier 1, in builder working days. They assume D-257 has merged.

| Part | Work | Days |
|---|---|---|
| Backend | A pure module for the re-solve and the paired re-run; the hook in the weekly job; capture keeping the top free agents per position; the read-time pick values; the draft-order answer; the flag; unit tests | 4 to 5 |
| App | The section in the open card, its states and copy, the hand-off, the once-per-league question, events, the structural check | 2 to 3 |
| Validation | The leave-one-out backtest and write-up | 1 to 2 |
| Website | Not in v1 | 0 |

Tier 2 is roughly the same again, most of it in the trade finder.

## 14. Decisions for the operator

| # | Decision | Recommendation |
|---|---|---|
| 1 | Where it lives | A "Max PF moves" section in the user's own team card on Standings, under Draft pick odds. The old tab is gone |
| 2 | Simple rule or exact re-solve | Exact. Same cost, and the simple rule is off by more than 5 points for half of starters. Keep the simple rule as the sentence the user reads |
| 3 | What "updated pick projection" shows | Pick if you miss, top-3 chance and pick value change in the row; the D-257 ranked label in the opened row, because it often does not move |
| 4 | Always show the playoff-chance change | Yes, on every row. For a team still in the race it is most of the effect |
| 5 | Leagues that do not draft by max PF | Ask once per league; hide the list for reverse standings and lottery; until answered, show with the existing "assumes max PF" line. Reuse the unbuilt `leagues.draft_order_rule` design if it is built first |
| 6 | When the numbers are computed | Weekly, with the forecast, saved with it. Show a notice when the roster has changed since. A per-trade check on demand is tier 2 |
| 7 | Who sees it | Own team only. Open when playoff chance is at or below 45% or the saved outlook is Rebuilding or Tanking; collapsed otherwise; behind a tap when the user does not own their own first |
| 8 | A slot nobody on the roster can fill after the trade | Have capture keep the top few free agents per position, so the forecast's own free-agent rule applies. The alternative is to flag those rows as overstated |
| 9 | Paywall | Free in v1 |
| 10 | Tone | Neutral wording, no hard guard, one first-time sentence about league rules |
| 11 | Backtest before or after turning it on | Before: run the leave-one-out backtest, then decide whether risk 2 needs a caveat line or a tier 3 fix |

## 15. What the code could not tell us

- **Whether a league's draft order really is lowest max PF.** Nothing in the code reads a
  league rule. The forecast assumes it (`provider.py:645`, `:663`).
- **Whether max PF keeps counting in playoff weeks** for non-playoff teams, on Sleeper or in a
  league's own rules. The forecast stops at the regular season.
- **How accurate the pick odds are.** The forecast's own warning says model accuracy has not
  been established, and the weekly spread is marked provisional.
- **Production run times.** All timings here are from a laptop.
- **How many users this reaches**: leagues with a current forecast, and within them teams
  likely to miss the playoffs who still own their first. That is a production read.
- **What the trade deadline field means in every league setup.** Win Now reads
  `settings.trade_deadline`; the forecast does not.
- **How large the bench-depth bias is** (risk 2). The backtest in §11 answers it.
