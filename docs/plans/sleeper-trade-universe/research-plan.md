# Research and test plan — a wider universe of completed Sleeper trades

**Date:** 2026-11-12 · **Status:** plan approved, decisions in §11; build starting · **Entry point:** direct ask (operator)

> "The goal of this is to expand the universe of completed trades so that we can use it to train our trade card generation models, identify additional details or inputs (or maybe prioritize league specific context on valuations)."
> "We should store rosters and trades tied to those rosters to better understand outlook's role in our model."

This is a plan. A plan is not evidence anything shipped (see [`../CLAUDE.md`](../CLAUDE.md)).

## Contents

1. [What we are trying to learn](#1-what-we-are-trying-to-learn)
2. [What we hold today](#2-what-we-hold-today)
3. [What Sleeper's public API gives](#3-what-sleepers-public-api-gives)
4. [Recommended approach: one program pulls, agents analyse](#4-recommended-approach-one-program-pulls-agents-analyse)
5. [Data plan](#5-data-plan)
6. [Hypotheses](#6-hypotheses)
7. [How the data trains the card models](#7-how-the-data-trains-the-card-models)
8. [Test plan and gates](#8-test-plan-and-gates)
9. [Team](#9-team)
10. [Risks and limits](#10-risks-and-limits)
11. [Decisions](#11-decisions)

---

## 1. What we are trying to learn

Three questions, in priority order:

1. **Outlook.** How much does a team's situation (contending, rebuilding) at the moment of a trade explain what it buys, what it sells and what it pays?
2. **League context.** Do leagues price players and picks differently enough, by format or by their own history, that a league-specific value beats one market value?
3. **Card generation.** Can real trades teach the generator which trades happen, so the first 30 cards look more like trades people make?

Everything else in §6 is a secondary hypothesis the same data can answer at little extra cost.

## 2. What we hold today

Read-only counts from production on 2026-11-12:

| Data | Size | Note |
|---|---|---|
| Completed Sleeper trades | 629 trades, 27 leagues, June 2022 to now | Captured for linked leagues and one hop of league-mates' leagues |
| Waiver and free-agent moves | 850 moves, 3 leagues | Manager profiles (36 profiles) |
| In-app decisions | 684 likes, 1,281 passes | The only true "no" answers we have, with the private Sleeper offers read |
| Dated player values | 110 daily snapshots, from 2026-07-10 | Nothing earlier |
| Weekly roster history | 28 snapshot dates, from 2026-08-14 | Linked leagues only |

Two gaps follow from this table and shape the plan:

- 629 trades is too few to split by format, outlook pair and time of year at once.
- **We cannot value a 2024 or 2025 trade as the market saw it then.** Our value history starts in July 2026. Section 5.6 covers the options.

## 3. What Sleeper's public API gives

No login is needed for any of this. Source: Sleeper's published docs and the shapes recorded in [`../../integrations/sleeper.md`](../../integrations/sleeper.md).

| Call | Returns | Used for |
|---|---|---|
| `/user/<id>/leagues/nfl/<season>` | Every league a user is in, with settings | Discovery |
| `/league/<id>` | Format: teams, roster slots, scoring, league type, `previous_league_id` | Format features; history chain |
| `/league/<id>/rosters` | Current roster, owner and co-owners per team, record | Roster state; next discovery hop |
| `/league/<id>/transactions/<week>` | Completed trades, waivers and free-agent moves for the week | Trades; roster reconstruction |
| `/league/<id>/matchups/<week>` | Each team's players, starters and points that week | Weekly roster snapshot; standings at any week |
| `/league/<id>/drafts`, `/draft/<id>/picks` | Rookie and startup draft results | Resolve a traded pick to its slot and player |
| `/league/<id>/traded_picks` | Who owns each future pick | Pick capital |
| `/league/<id>/winners_bracket` | Playoff results | Outcomes |

Not available: offers that are pending, declined, cancelled or countered; league chat. The data is **what happened, never what was turned down**. Section 7 says how the plan works around that.

Sleeper asks callers to stay under 1,000 requests a minute.

## 4. Recommended approach: one program pulls, agents analyse

The operator asked whether to use 5 to 10 subagents each assigned a set of user ids, or subagents split by role (user to league mapping, league to transactions, league to teams).

**Recommendation: neither does the pull. One deterministic, resumable program pulls the data; agents build it, review it, and then analyse the frozen result in parallel by question.**

Why not agents for the pull:

- **Splitting by user id duplicates work.** Leagues overlap heavily between users, so shards reach the same league from many directions. Without one shared "seen" list they repeat requests; with one, they are no longer independent.
- **Splitting by endpoint is a pipeline, not a team.** "Users to leagues", "leagues to transactions" and "leagues to rosters" are stages of one program that pass ids to each other. Code does that exactly and for free; agents do it slowly, at token cost, and differently each run.
- **One process must own the rate limit.** Several agents calling Sleeper at once cannot guarantee we stay under its ceiling. One throttled process can.
- **It has to be repeatable.** We will want to refresh this weekly. A program re-runs; an agent session does not.

Where agents do help is the thinking: building and reviewing the program, and analysing the data from different angles at once. That is role-split, as the operator's second option suggests, but the roles are analytical. The team is in §9.

## 5. Data plan

### 5.1 Discovery

- **Seeds:** the usernames the operator shares, plus the owners already in our linked leagues.
- **Walk:** user → their leagues for each season in scope → those leagues' owners → their leagues. Stop at the hop limit or the league cap, whichever comes first.
- **Keep only:** dynasty leagues (`settings.type == 2`), not best ball, 8 to 16 teams, started or complete. Everything else is recorded as skipped with the reason, so the filter can be audited.
- **History:** follow `previous_league_id` back so one league's seasons form a single lineage. A lineage is the unit for every train and test split (§8.4).

### 5.2 Per league-season pull

About 44 requests per league-season: league, rosters, users (owner ids only), 18 weeks of transactions, 17 weeks of matchups, drafts and picks, traded picks, two brackets.

| Scope | League-seasons | Requests | Time at 4 requests a second |
|---|---|---|---|
| Pilot | 150 | about 6,600 | under 30 minutes |
| Full (recommended cap) | up to 9,000 (3,000 leagues, seasons 2024 to 2026) | about 400,000 | about 28 hours |

- **Throttle:** one process, 4 requests a second (a quarter of Sleeper's stated ceiling), back-off on 429 and 5xx, and a hard stop after repeated 429s.
- **Resumable:** every league-season is a checkpoint; a restart skips what is done.
- **Expected yield:** our 27 leagues hold 629 trades. The pilot measures the real rate; the working guess is tens of thousands of trades from the full pull.

### 5.3 What is stored, and what is not

Stored: league id and format, lineage, roster ids, weekly rosters and starters, every transaction, draft results, pick ownership, playoff results.

**Not stored: usernames, display names, team names, avatars.** They are dropped in memory before anything is written.

To study whether the *same manager* behaves the same way across leagues, an owner needs a stable key. The store holds a keyed hash of the Sleeper owner id (the key is kept outside the repo), never the id itself (decision 2). Rosters and trades stay tied together.

### 5.4 Where it lives

- A local research store in `data/sleeper-universe/`: compressed raw responses per league-season, and one SQLite file of normalised tables. `/data/` is already git-ignored; nothing in it is ever committed or uploaded.
- **Not the production database.** This is research data. If a finding becomes a product feature that needs some of it in production, that is a separate change with its own schema and gates.

Tables: `leagues`, `rosters`, `roster_weeks` (players, starters, points), `transactions` (raw), `trades` and `trade_assets` (one row per player, pick or FAAB amount moved, with from and to roster), `drafts`, `draft_picks`, `standings_weeks` (derived), `outcomes`.

### 5.5 The roster at the moment of a trade

The operator's main question needs each team's roster and standing *when the trade happened*, and the API only gives the current roster.

- **In season:** the matchups call gives every team's players for each week. Start from that week's snapshot and replay the week's transactions up to the trade's timestamp.
- **Offseason:** start from the last snapshot of the season before (same lineage) and replay transactions forward, including the rookie draft.
- **Check:** replaying a full week must land on the next week's snapshot. Target: at least 98% of roster-weeks match exactly in the pilot. League-seasons that fail are flagged and excluded from outlook work, with the count reported.

From that roster we derive, per team, at the trade's date: record and points so far, roster strength (best lineup by market value), age profile, pick capital, and the app's own outlook label computed offline with the existing classifier, so findings map straight onto All-in, Contending, Rebuilding and Tanking.

### 5.6 Values at the trade's date

To say who "paid" what, we need the market's value for each player and pick on the trade's date. We hold that only from July 2026.

| Source | Covers | Note |
|---|---|---|
| Our own snapshots | July 2026 onward | Already stored |
| KeepTradeCut history | Years, daily, superflex and 1QB, picks | Best fit, if the operator's agreement covers historical values |
| DynastyProcess history | Years, weekly | Public; the app already uses its current values |

Trades before a value source's first date can still be used for structure, timing and outlook direction, but not for pricing.

### 5.7 Picks

A traded pick arrives as season, round and original team. For a draft that has happened, the draft results resolve it to its slot and the player taken. For a future pick, we record the original team's standing at the trade's date, which is the same input the live pick pricing uses.

### 5.8 Cleaning

Flag, do not delete: trades reversed within a day; trades where one side is an orphaned or inactive team; trades during a startup draft; leagues with fewer than three trades a season; leagues with unusual scoring; lopsided outliers past a threshold set in the pilot. Every analysis reports results with and without the flagged rows.

## 6. Hypotheses

Each is written so it can fail. "Changes" is what the product would do differently if it holds.

### Outlook

| # | Hypothesis | Measure | Changes |
|---|---|---|---|
| O1 | Contending teams buy current production and sell picks and youth; rebuilding teams do the reverse | Net age, points and pick capital acquired, by outlook at the trade's date | Confirms or resizes the win-now signal and the sell bonus |
| O2 | Contenders pay more than market for production, and the premium grows toward the trade deadline | Value paid over market, by week, for contender buyers | A time-of-season term in card ordering |
| O3 | Pairs with opposite outlooks trade far more often than pairs with the same outlook | Trade rate per pair, by outlook pair, against chance | Partner selection weights |
| O4 | Teams act on their standing with a lag: a team that falls out of contention keeps buying for weeks | Direction of trades after a team's playoff odds cross a threshold | Whether outlook should come from the forecast or from the manager's stated choice |
| O5 | A team's position needs predict what it buys better than its outlook does | Predictive power of need against outlook for the acquired position | Relative weight of need fit and outlook |

### Valuation and league context

| # | Hypothesis | Measure | Changes |
|---|---|---|---|
| V1 | Format moves prices in ways the market values under-state (superflex quarterbacks, tight-end premium, league size, lineup depth) | Implied price by format against market value | Format multipliers |
| V2 | Leagues have persistent "house prices": a league that overpays for picks this year did last year | League-level deviation, year over year, within a lineage | A league-specific adjustment learned from its own trade history |
| V3 | A league-adjusted value predicts that league's next trade better than the market value | Held-out trades, league-adjusted against global | The operator's question on league-specific context |
| V4 | Pick prices follow the projected slot, and rise before the rookie draft | Price of a first by the original team's standing and by month | Validates projected-slot pricing; adds seasonality |
| V5 | Future-year picks are discounted at a steady rate per year | Price of the same round one, two and three years out | A stated discount in pick values |
| V6 | Real prices fall off with age earlier or later than the labels assume | Price against market value by age and position | The age thresholds behind Cornerstone and Win-now |
| V7 | Real trades lead the published market after injuries and breakouts | Whether trade-implied prices move before market values do | A "market has not caught up" signal for cards |
| V8 | For low-value players the market value is noise and trades price them near zero | Price of bottom-of-roster players in multi-player trades | Filler muting |

### Structure and timing

| # | Hypothesis | Measure | Changes |
|---|---|---|---|
| S1 | A few shapes (1-for-1, 2-for-1, player for pick) make up most trades, and the mix differs by format | Shape frequencies | Shape priors in the generator |
| S2 | The side getting the single best asset gives more total value (a consolidation premium), and its size is stable | Value gap by shape | The package adjustment |
| S3 | A 2-for-1 often forces the receiver to drop someone, and that cost is priced in | Drops within 24 hours of a trade | A roster-spot cost in fairness |
| S4 | Trade volume has a known calendar: deadline, draft, the weeks after elimination | Trades per league by week | When to notify and how many cards to show |
| S5 | Accepted trades sit in a band around fair, and the band's width differs by league | Distribution of value gaps | The fairness window, per league |

### Managers (need the hashed owner key)

| # | Hypothesis | Measure | Changes |
|---|---|---|---|
| M1 | A manager's tendencies (pick hoarder, position preference, trade frequency) hold across their leagues | Same manager, different leagues | Manager profiles carry over between leagues |
| M2 | Trades cluster between repeat partners | Share of trades between pairs that traded before | Partner ordering |
| M3 | A manager who trades often is likelier to accept | Trade count against later trades | The partner-activity rule, currently off |

### Outcomes

| # | Hypothesis | Measure | Changes |
|---|---|---|---|
| R1 | Some trade types win in hindsight more often (for example, the side getting the best player) | Value and points gained 8 and 52 weeks later | Trade grades; what a "good" card is |
| R2 | Managers who trade more finish higher the next season | Trades this year against finish next year, same lineage | Product claim worth making publicly, if true |
| R3 | Title-winning rosters share a shape per format | Roster make-up of champions | Outlook advice |

### Other uses the data opens

- **Liquidity score per league:** some leagues make 3 trades a year, some 60. A league's own rate sets how many cards are worth showing and how patient to be.
- **League health:** orphaned teams, reversed trades and lopsided dumps are detectable, and commissioners care about them.
- **"Trades like this happened" on a card:** a count of similar real trades in similar leagues is evidence a user can trust.
- **A second opinion on values:** a price index built from real trades, by format, to hold against the market values we license.

## 7. How the data trains the card models

The data holds only trades that happened, so it cannot be used directly to predict acceptance. Three uses that do work:

1. **Price model.** Fit the values that best explain what was exchanged, by format and date. Compare with market values. This feeds V1 to V8.
2. **Plausibility ranker.** For each real trade, take the two rosters as they were, generate the alternatives our engine would have offered that pair, and train a model to rank the trade that happened above the ones that did not. The inputs are the things we want to weigh: value gap, need fit, outlook pair, shape, pick mix.
3. **Replay as the test.** For each held-out real trade, build the deck for the team that proposed it, as of that date. **Did the real trade, or one close to it, appear in the first 30 cards?** This is a direct measure of whether the generator finds the trades people make, and the repo already has replay tooling (`backend/eval/replay.py`).

The true negatives we do have (1,281 in-app passes and the declined Sleeper offers) are the check on all of it: a ranker trained on the wide data must also rank those declined trades low.

A caution that belongs in every result: a trade that happened is not a trade that was good for both sides. The app's job is trades its user should want. The plausibility ranker says what a partner will entertain; it must not become the definition of a good card.

## 8. Test plan and gates

### 8.1 Phases

| Phase | What | Gate to pass |
|---|---|---|
| 0 | Decisions in §11 | Done 2026-11-12 |
| 1 | Build the crawler and schema | Tests on fixtures only (no live calls in tests); an independent review confirms no name field can reach disk; the throttle is tested |
| 2 | Pilot: 150 league-seasons | Pilot report (§8.2) |
| 3 | Full pull | Completes inside the request budget with no 429 stop; resumes cleanly from a forced interruption |
| 4 | Data quality and bias report | §8.3; dataset frozen as v1 with checksums |
| 5 | Analysis, in parallel by question | §8.4 rules; every hypothesis reported, including the ones that fail |
| 6 | Model experiments | §8.5 |
| 7 | Product changes | Each goes through the existing route: Founders' review or a Calibration round, then shadow, then a flag |

### 8.2 Pilot report must show

- Trades per league-season, and the share of leagues the dynasty filter kept (30 kept and 30 skipped leagues checked by hand).
- Requests and seconds per league-season against the estimate.
- Roster reconstruction: share of roster-weeks that match the next snapshot (target 98%).
- How offseason trades are reported (which week they appear under), which the docs do not state.
- Share of traded picks resolved to a slot.
- How many seasons back lineages usually go.
- Proof that no name field is in the store (a scan of every written file for the fields we drop).

### 8.3 Data quality and bias

The sample comes from the seeds' circles, so it is not Sleeper as a whole. The report compares it with our own users' leagues on format mix, league size, trade rate and season coverage, and says plainly where it differs. Findings are claimed for "leagues like these", and re-checked on our own users' leagues before anything ships.

### 8.4 Rules for the analysis

- **Written first:** each hypothesis gets its measure, the smallest effect that would matter, and its split before anyone looks at test data.
- **Time split:** train on seasons through 2025, tune on the first half of 2026, and keep the second half of 2026 untouched until the final check.
- **League split:** a lineage is in one set only, so a league's habits cannot leak from training into test.
- **Many comparisons:** with about 25 hypotheses some will look true by chance. Results are corrected for that, and reported with intervals, not only pass or fail.
- **A skeptic pass:** one agent's only job is to break the findings (confounds, survivorship, flagged rows, sample bias) before they reach the operator.

### 8.5 What a model change must beat

| Test | Baseline | Pass |
|---|---|---|
| Replay: real trade in the first 30 cards | Today's generator on the same held-out trades | A clear, interval-backed gain, with no loss in speed to first page |
| Declined trades ranked low | Today's ordering on the 1,281 passes and declined offers | No worse |
| Price prediction on held-out trades | Market value alone | Lower error, by format |
| Live | Like and send rates on cards | Measured in shadow first, then behind a flag |

## 9. Team

All agents run on Opus, as the operator asked. One process talks to Sleeper.

| Role | Count | Does |
|---|---|---|
| Crawler builder | 1 | The program, schema, throttle, checkpoints, tests |
| Independent reviewer | 1 | Read-only review: identity stripping, reconstruction logic, rate limit |
| Main session | — | Runs the pilot and the full pull, watches it, writes the gates' reports |
| Analyst: data quality and bias | 1 | §8.3 |
| Analyst: valuation and league context | 1 | V1 to V8 |
| Analyst: outlook and roster make-up | 1 | O1 to O5, R3 |
| Analyst: structure, timing and managers | 1 | S1 to S5, M1 to M3 |
| Analyst: model experiments | 1 | §7 and §8.5, against the replay harness |
| Skeptic | 1 | §8.4's last rule |

The five analysts start together once the dataset is frozen. That is where running several agents at once pays off: the questions are independent and each takes real thought.

## 10. Risks and limits

| Risk | Effect | Handling |
|---|---|---|
| No declined offers | Cannot learn acceptance directly | §7: constructed alternatives, checked against our own true negatives |
| Sample is the seeds' circles | Findings may not hold for other leagues | §8.3; more and more varied seeds help most |
| Value history starts July 2026 | Older trades cannot be priced | §5.6; decision in §11 |
| Roster reconstruction errors | Wrong outlook at the trade's date | §5.5 check; failures excluded and counted |
| Lopsided, forced or collusive trades | Skew prices | §5.8 flags; results with and without |
| Learning "what happens" instead of "what is good" | Cards that mirror bad trades | §7's caution; product gates in phase 7 |
| A long unattended pull | Stops if the machine sleeps | Resumable checkpoints; keep the machine awake for the run |
| Sleeper changes or limits the API | Pull fails | Throttle well under the limit; hard stop on 429; raw responses kept so nothing is re-pulled |

Access is covered by the operator's agreement with Sleeper for this app's development, as stated by the operator on 2026-11-12. The plan stores no names regardless.

## 11. Decisions

Answered by the operator on 2026-11-12.

| # | Question | Decision |
|---|---|---|
| 1 | Seeds | Every owner in the operator's own leagues, plus six usernames the operator supplied. The seed list is kept in the git-ignored data folder, never in the repo |
| 2 | Owner key | Keyed hash of the owner id. No names stored |
| 3 | Seasons | 2024 to 2026 |
| 4 | Cap | 3,000 leagues |
| 5 | Historical values | Both: KeepTradeCut (the operator confirms the agreement covers it) and DynastyProcess. How KeepTradeCut's history is delivered is still to be settled |
| 6 | Retention | No limit. The data is kept for further analysis |
| 7 | Order | The analysts work in parallel, one per focus, once the data is pulled and frozen. Outlook is reported first |
