# Window asset identification: how the engine tells win-now pieces from rebuild pieces

> Research only, 2026-11-11. Code baseline: `origin/main` at `adead776`. This binds nothing until it
> lands in a plan. Offline experiments used the public-player fixture pool and synthetic boards;
> there was no production database or API access. Every number below is either **measured**
> (an offline run, reproducible as described) or **inferred** (reasoning from code), and is marked.
> No user, league or roster data appears here.

The operator asked: *"If I'm win now, how does the generator (and the entire process) know which
RBs to suggest to me?"* The trigger was an All-in team ranked 1st of 12 at RB by consensus value. It
was shown "give a 33-year-old WR, get a 23-year-old rookie RB" with only league-rank facts as the
reason.

**Short answer.** The engine does not know which players help a team *this season*. It has one
number per player, dynasty market value, plus age. "Win-now" is age, nothing else: a fixed
per-position curve (`_now_lean`). Role, starting status, projected points and redraft value never
reach the deck generator. The app already holds all of these, in the Win Now search, in league
projections and in Sleeper's `search_rank` on every player row.

The card in question appeared because the user's own rankings liked the rookie more than the
market did. That preference gets 45% of the support score; the team plan gets 20%. No rule stops
a trade that moves *away* from a declared All-in plan, so the copy fell back to rank facts.
Reproduced offline in §1.7.

## Contents

- [1. Trace: from "Find a Trade" to the cards](#1-trace-from-find-a-trade-to-the-cards)
- [2. Gaps](#2-gaps)
- [3. How it could work](#3-how-it-could-work)
- [4. Option: outlook-specific player labels (operator's proposal)](#4-option-outlook-specific-player-labels-operators-proposal)
- [5. Recommendation and first step](#5-recommendation-and-first-step)
- [6. Decisions for the operator](#6-decisions-for-the-operator)
- [7. Sources](#7-sources)
- [Appendix: how the experiments were run](#appendix-how-the-experiments-were-run)

---

## 1. Trace: from "Find a Trade" to the cards

### Diagram in words: where outlook enters

```
saved league_preferences.team_outlook ──┐
  (else) roster seed: infer_team_outlook │   age shares + pick share only
                                         ▼
_run_trade_job (server.py:12780) ── outlook_value ─────────────┐
  opponents: saved outlooks, else infer_team_outlook per roster│
                                                               ▼
owner/bilateral generator (served: owner-v2-bilateral-2)
  per team: outlook → _WINDOW_WEIGHT (+1 All-in … −1 Tanking)
  per asset: _plan_asset = f(outlook, position, AGE)   ◄── the ONLY "window" signal per player
             _lineup proxy = dynasty value × age_now_mult (not points)
  candidate pools  ← _asset_interest (personal lean + 0.3·plan + 0.15·need + declared)
  per card support = 0.45 preference + 0.35 market + 0.20 team plan
  lane = "window" if team_plan_gain > 0.01 else "value"
                                                               ▼
deck_quality filters (no outlook) → presentment (keeps lane class) → fit block copy
  "Win-now: adds X" fires only if the proof carries benefit "outlook" AND X's age lean ≥ 0.05

NOT CONNECTED to any of the above: Win Now season simulator, league_projections
(weekly projections + best-lineup solver), outlook odds / trade_delta, power-ranking
Seller/Buyer bands, dp_values_history, trends, depth charts, search_rank.
```

### 1.1 Where outlook comes from

| Source | What it reads | Who consumes it |
|---|---|---|
| **Saved** `league_preferences.team_outlook` | The user's tap: `championship` (All-in), `contender`, `not_sure`, `rebuilder`, `jets` (Tanking) | The trade job reads it (`server.py:12983-12990`); it is the `outlook` kwarg for every generator (`server.py:13301`). |
| **Roster seed** (`trade.outlook_seed`, on) | `infer_team_outlook`: share of value held by players aged ≥27 vs ≤26, plus pick share (`trade_service.py:4010-4121`, thresholds `trade_service.py:49-50`). Never infers All-in or Tanking (docstring, `trade_service.py:4038-4040`). | The trade job when nothing is saved (`server.py:13021-13031`, `server.py:12455-12477`). |
| **Opponents** (`trade.outlook_infer`, on) | Each league-mate's saved outlook (`server.py:13055-13071`); otherwise the generator infers it from that roster (`trade_gen_owner.py:297-305`). | Each opponent's `_WINDOW_WEIGHT`, plan and need weights. |
| **#372 composite** (`trade.outlook_composite`, off) | Starter dynasty value plus playoff index (`trade_service.py:4161`). | Only Team Review supplies the signal; the trade job never does (INV-372b, `trade_service.py:4088-4095`). |
| **#371 odds bands** (`trades.window_from_odds`, off) | Playoff band → outlook (`team_review.py:65-111`). | Team Review only (`server.py:39137`). |
| **Projection suggestion** (`league.projection_outlook`, on; rides `league.projections`) | Saved playoff probability bands: ≤15% Tanking, ≤45% Rebuilding, ≤75% Contending, otherwise All-in (`league_projections/recommendation.py:60-69`; D-230). | Team Review and the projections route. It **suggests, never sets**; the saved outlook "is always what the trade engine uses" (`recommendation.py:9`). |

Every source is **team-level**. None says anything about an individual player.

### 1.2 What "value" a player has in the engine

- **Consensus market.** DynastyProcess `values-players.csv`, reading only `player`, `pos`,
  `value_1qb`, `value_2qb` (`data_loader.py:13-17`). There is an optional KeepTradeCut **dynasty**
  blend (`data_loader.py:189`). No redraft, ECR or rest-of-season column is read anywhere outside
  tests.
- **Age price adjustment, applied to everyone.** `age_pref_value` multiplies under-23 players by
  1.10 (increase capped at +500) and 30-and-over players by 0.90 inside the one consensus accessor
  (`trade_service.py:3478-3546`, defaults `trade_service.py:317-319`). The owner/bilateral market
  uses that accessor (`trade_gen_owner.py:219-224`).
  - It was set from like rates (`trade_service.py:302-305`), not from outlook. It applies to an
    All-in team exactly as to a rebuilder.
- **Personal value.** The user's Elo board converted with `elo_to_value`, falling back to
  consensus (`trade_gen_owner.py:281-296`). The bilateral generator turns personal-versus-market
  tier and percentile gaps into a "direction" per player (`trade_gen_bilateral.py:82-95`).
- **Picks.** Pick ladder values (`pick_values.py`). Every plan rule treats picks as pure future
  capital: `_now_lean("PICK") = −0.25` (`trade_service.py:3570-3573`).

**This-season inputs that exist but never reach the deck generator:**

| Input | Where | Connected to the deck generator? |
|---|---|---|
| Sleeper weekly projections (RotoWire-revised), scored with league settings | Win Now (`season_forecasts.py:212-236`), `league_projections/provider.py:52-78`, `fit_engine.fetch_ros_points` (`fit_engine.py:438-468`) | **No.** Win Now says "The existing dynasty generator is deliberately not called" (`win_now_service.py:3`). `league_projections` is imported only by routes, cron and Team Review (`server.py:30160, 32153, 39181, 44465`). `fit_engine` is used only in blind grading. |
| Best-lineup optimiser (Hungarian, flex-aware) | `league_projections/core.py:121-170` | **No.** |
| Projected marginal lineup points per package | `win_now_service._prepare_marginals` (`win_now_service.py:490-520`) | **No.** Win Now only. |
| Team strength / playoff odds | `outlook/strength.py:276-357`; `outlook/trade_delta.py:170-249` | **No.** Odds impact is drawn on the fronted card only via `/api/trade/evaluate` (`server.py:19777-19781`). It never ranks or filters. |
| NFL depth chart | `Player.depth_chart_order` (`ranking_service.py:266`) | **No.** The only reader is the handcuff label, which "no engine path reads" (`trade_service.py:2968-2999, 3033-3037`). |
| Sleeper `search_rank` (behaves like redraft ADP, see §3.2) | `Player.search_rank` (`ranking_service.py:273`) | **No.** Only draft-board ordering reads it (`draft_board_service.py:987-993`) plus eval tooling. |
| Value trend | `dp_values_history.py` (research only, `dp_values_history.py:23-28`); `trends_service` reads the user's own Elo history (`trends_service.py:600-640`) | **No.** |

**Production flags differ from the file.** Per G-076 (`living-memory/GOTCHAS.md:99-104`), production
sets `league.projections` and `league.projections_provider_approved` **true** through `FTF_FLAGS`,
even though `config/features.json` says false. So weekly projections *are* captured for connected
leagues in production today. The data exists; the deck does not read it.

### 1.3 How outlook changes generation and ranking

**Which generator serves.** Production organic requests run the owner-bilateral path
(`bakeoff_owner_only` plus `owner_bilateral_enabled` plus the revision selector,
`docs/plans/realtime-trade-engine/recommendation.md:15-27`). The constructor is
`owner-v2-bilateral-2` (the 247-request production replay ran "revision 2",
`living-memory/TEST_LEDGER.md:9746`). The selectors are DB knobs that default to 0
(`database.py:3864-3868`; dispatch at `bakeoff_runner.py:318-333`). I could not read the
production knob values; revision 2 is inferred from the ledger.

**In the served generator** (`trade_gen_owner.py`, `trade_gen_bilateral.py`,
`trade_gen_bilateral_candidate.py`):

| Mechanism | How it decides a player is win-now or rebuild | What it does with it |
|---|---|---|
| `_WINDOW_WEIGHT` (`trade_gen_owner.py:46-47`) | Team-level only: All-in 1.0, Contending 0.6, Rebuilding −0.6, Tanking −1.0 | Scales the plan term |
| `_plan_asset`, contender/All-in branch (`trade_gen_bilateral.py:141-143`) | **Age and position only**: `2·w·_now_lean(pos, age)`, where `_now_lean = age_now_mult − age_future_mult` (`trade_service.py:3565-3574`, curves `trade_service.py:3439-3459`) | Feeds asset interest (pool and focal order) and plan gain (support score, lane) |
| `_plan_asset`, rebuild/tank branch (`trade_gen_bilateral_candidate.py:29-52`; incumbent `trade_gen_bilateral.py:129-140`) | Pick = 1.0. Young non-RB (QB ≤27, WR/TE ≤25) favoured, more so if the user's own board likes him. RBs penalised unless elite on the user's board (`_YOUNG`, `trade_gen_bilateral.py:26`) | Same as above |
| Lineup proxy `_lineup` (`trade_gen_owner.py:339-363`) | Best legal lineup by **dynasty value × age_now_mult** (`trade_gen_owner.py:270-271`), plus 15% of the best bench player per position. The code itself says it is "NOT fantasy points" | `need_utility` weighted 0.25 for contending/All-in, 0.05 rebuilding, 0 tanking (`trade_gen_owner.py:273-275`); 0.15/0.025/0 inside asset interest (`trade_gen_bilateral.py:164-168`) |
| Revision 2's `starter_evidence` (`trade_gen_bilateral_candidate.py:80-89`) | Hard-coded `state: "unknown"`, `projected_starter_delta: None`, with missing items listed: `fresh_scoring_compatible_projections`, `projection_horizon` … | Diagnostics only. The engine records its own gap. |
| Support score (`trade_gen_bilateral.py:23-24, 192-208`) | Plan gain = value-weighted `_plan_asset` shift plus need, clipped | 0.45 preference + 0.35 market + 0.20 plan. Ranking maximises the weaker side (`trade_gen_bilateral.py:422-454`) |
| Intent gate (`trade_gen_bilateral.py:196-201`) | A card qualifies if the user's board likes the focal swap (`personal_board`), or a declared target/position matches, or a **declared** outlook plus plan gain ≥ 0.10 | There is no gate for plan gain below zero. Only the Tanking extras reject (`trade_gen_bilateral.py:281-302`) |
| Lane (`trade_gen_bilateral.py:507`) | `team_plan_gain > 0.01` → "window", else "value" | A slot class preserved by presentment (`trade_bilateral_presentment.py:109`); it does not promote |
| Revision 4 (dark, `trade_gen_bilateral_r4.py`) | Owned-pick premium by the *other* team's outlook | Ordering only |
| Revision 3 (dark, `trade_gen_outlook_evidence.py`) | Removes age cliffs; lists projections as a missing source (`trade_gen_outlook_evidence.py:228-235`) | Not served |
| `deck.quality_filters` (`deck_quality.py:1-19`) | No outlook at all: breakup, filler, redundant TE/QB, repeat cap | Drops or defers |

**In the legacy pipeline** (`trade_service.py` v2, `trade_optimizer.py` v3, `trade_gen_v2.py`;
still in the codebase and in bake-off arms, not the served organic path):

| Flag (file value) | Signal | Effect |
|---|---|---|
| `trade.outlook_blend` (off) | α-blend of the same age curves applied to *values* (`trade_service.py:3556-3560, 6344-6352`) | Would re-price; dark |
| `trade.lanes` (on) | `_now_lean` (age) → lane label (`trade_service.py:3562-3582, 6696`) | "Window/age steer LABELS, not values" (`trade_service.py:3565-3566`) |
| `trade.need_fit`, `trade.position_tiers` (on) | `analyze_roster_strengths`: starter counts per position from **dynasty-value rank bins** (`trade_service.py:3001-3092`) | Fit ranking |
| `trade.fit_premium` (on) | Received position in `position_needs`, give position not (`trade_service.py:3800-3830`) | Lets a 1-for-1 lose a little value |
| `trade.crown_asset` (on) | Best asset by value (`trade_service.py:1778, 1867`) | Pricing |
| `trade.marginal_value` (on) | Package value math (`trade_optimizer.py:285`) | Pricing |
| `trade.rb_handcuff` (on) | Depth-chart RB2 | Label only |
| `trade.outlook_direction`, `outlook_net_firsts`, `outlook_composite`, `trades.window_from_odds` (off) | — | Dark |
| `acquire_positions` / `trade_away_positions` | **User-set only**, never computed (`server.py:12979-12990`) | Bilateral: ±0.15 asset interest and a declared-intent path (`trade_gen_bilateral.py:154-155, 186-189`); v3: hard position filter (`trade_optimizer.py:493-507`) |

### 1.4 The fit-block copy

`fit_block` (`trade_narrative.py:706-775`) chooses each team's lead in this order: plan, then need,
then rank facts.

- **"Win-now: adds X"** (`plan_win_now.you`) requires all of the following:
  - the outlook is contender or All-in (`trade_narrative.py:404, 531-533`);
  - the proof's viewer benefits contain `"outlook"` (`trade_narrative.py:534-537`), which means
    the value-weighted `_plan_asset` shift was above 0.01 (`trade_gen_bilateral.py:219-220`);
  - a received player has `_now_lean ≥ 0.05` (`trade_narrative.py:392, 561-564`).

  The "asset" named is the most valuable such player. That is **age-only**: a 28-year-old RB
  backup qualifies and a 24-year-old bell-cow does not.
- **"Upgrades RB: adds X"** (`need.you`) requires the dynasty-value lineup proxy at that position
  to rise by more than one 15% bench credit and by ≥10% (`trade_narrative.py:585-611`).
- **Otherwise** the copy falls back to "Still RB 1st, WR 9th" or "Up at RB, down at WR"
  (`trade_narrative.py:626-642`). These are rank facts from consensus power rankings
  (`server.py:21083-21132`).

**Why the operator's card had no reason** (measured, §1.7): a 33-year-old WR has
`_now_lean = +0.15`; a 23-year-old RB has −0.05 (22: −0.15). Sending the first and receiving the
second is plan-negative for All-in. The receiving RB does not crack a #1-ranked RB room, so need
is zero. Neither the plan lead nor the need lead can fire, and the copy falls back to rank facts.
The card exists only because the user's board rates the rookie above market (`personal_board`
path).

### 1.5 The separate Win Now feature

Win Now (`trades.win_now` and `outlook.season_projections`, both on) is a season-gain trade search
that does what the main deck cannot:

- **Inputs.** Sleeper weekly projections fetched live (`season_forecasts.py:17, 212-236`), scored
  with the league's settings.
- **Shortlist.** Legal projected lineups and the marginal lineup points per package
  (`win_now_service.py:490-520`).
- **Gain test.** Paired Monte Carlo season simulations before and after the trade
  (`season_simulator.py:381-432`), with the objective set to next-three-week wins, playoff odds or
  title odds (`win_now_optimizer.py:48-52`).
  - Conservative gain = min(lower 95% bound, confirmation run) (`win_now_optimizer.py:302`).
  - It is gated at a minimum delta (`win_now_optimizer.py:277-326`).
- **"Dynasty budget".** The share of the buyer's total roster-plus-picks value the user will give
  up; default 3%, range 0–10 (`win_now_service.py:84`; `win_now_optimizer.py:194-241, 265-266`).
- **Ranking.** A Pareto frontier of conservative gain against dynasty cost
  (`win_now_optimizer.py:400-421`).
- **Offseason.** It refuses outside the regular season (`win_now_service.py:124-125, 153-154`).
- **Learning.** By design (D-184), season-motivated likes never teach dynasty Elo
  (`living-memory/DECISIONS.md:510-518`).

**Why the main deck doesn't use it.** It is a deliberate separation
(`win_now_service.py:3`; ADR-018). The dependency runs one way: Win Now borrows the main engine's
pricing helpers (`win_now_optimizer.py:28`), never the reverse. As a result, the app has two trade
finders that answer different questions, and the All-in user's main deck answers the dynasty one.

### 1.6 Team Review, Home labels and power rankings

- **Power rankings** (`power_rankings.py:200-339`) sum dynasty value over **all** rostered players
  at a position. Starters come from value only, and the code says so (`power_rankings.py:99-104`).
- **Seller / Buyer / Mid-pack.**
  - Computed on the client: the top 33% of teams by position value are "Seller", the bottom 33%
    "Buyer" (`mobile/src/utils/positionSplit.ts:101-113`).
  - Documented as "Changes no behaviour" (`positionSplit.ts:159-164`). They feed nothing in
    generation.
- **Team Review** composes:
  - the window, from `infer_team_outlook`, odds or the projection suggestion
    (`team_review.py:114-153`);
  - depth, from `analyze_roster_strengths` (dynasty bins).

  It writes nothing. It feeds generation only when the user taps to save an outlook or positions
  (`TeamReviewScreen.tsx:213, 336`).
- **Power rankings reach the card** only as the fit block's rank facts
  (`server.py:21083-21132`), and "presentation context, not ranking or filtering."

### 1.7 Experiment: two RBs, and the outlook flip

**Setup (measured).**
- **League:** a 12-team league built from the public fixture pool
  (`backend/tests/fixtures/player_pool_2026.json`: 340 real players, DynastyProcess 1QB values,
  ages). Built by a randomised snake draft; the viewer is the team with the **#1 RB room**, and was
  given Davante Adams (WR, 33). Each team holds 4 picks.
- **Boards:** synthetic, consensus × lognormal noise, as in `backend/eval/synthetic_league.py`.
- **Generator:** the served `trade_gen_bilateral_candidate.generate_bilateral_trades` (revision 2).
- No server, database or network was used. Method details are in the [appendix](#appendix-how-the-experiments-were-run).

**A. Two RBs of equal dynasty value (1,150), offered for Davante Adams.** The user's board has no
lean on them.

| Outlook | RB | `_now_lean` | plan per asset | asset interest | lineup-need gain | card vs. Adams |
|---|---|---:|---:|---:|---:|---|
| All-in | 23, backup | −0.05 | −0.10 | −0.041 | 0 | rejected `viewer_intent_unfulfilled` (plan gain −0.22) |
| All-in | **28, bell-cow** | +0.31 | **+0.62** | +0.175 | 0 | **eligible**, lane window, lead "Win-now: adds …" |
| All-in | 25, **starter** | +0.19 | +0.38 | +0.103 | 0 | rejected (plan gain +0.04 < 0.10) |
| All-in | 25, **backup** | +0.19 | **+0.38** | **+0.103** | 0 | **identical** to the starter |
| Rebuilding | 23, backup | −0.05 | −0.09 | −0.038 | 0 | rejected (unfulfilled) |
| Rebuilding | 28, bell-cow | +0.31 | −0.60 | −0.191 | 0 | rejected |
| Tanking | any | | | | 0 | rejected `tanking_rb_without_long_term_exception` |

Reading:
- The engine *does* prefer the 28-year-old for All-in, but **only because he is 28**. Age 25
  starter and age 25 backup are indistinguishable: role is invisible.
- The lineup-need gain is zero for every RB, because the dynasty-value lineup of a #1 RB room has
  no slot for them. It would also be zero for a bell-cow who would in fact outscore the viewer's
  RB2 this week. Points never enter.

**B. The operator's card, reproduced.** Same All-in team, the 23-year-old backup RB, with the
user's personal board lifting him above market:

| Board lift on the rookie | Eligible? | Path | Preference / market / plan components | Lane | Copy lead |
|---|---|---|---|---|---|
| none | no | unfulfilled | 0.458 / 0.753 / **0.392** | — | — |
| +15% | **yes** | `personal_board` | 0.479 / 0.753 / **0.392** | value | **rank-fact fallback** |
| +30% | yes | `personal_board` | 0.493 / 0.753 / 0.392 | value | rank-fact fallback |
| +60% | yes | `personal_board` | 0.525 / 0.753 / 0.392 | value | rank-fact fallback |

A modest personal lean is enough to serve a trade that the All-in plan scores *below neutral*.
That is exactly the card the operator saw.

**C. Outlook flip, same league, top 30 cards, mean of 6 seeds** (about 1,960–2,410 eligible
cards per run):

| Metric (top 30) | All-in | Contending | Not sure | Rebuilding | Tanking |
|---|---:|---:|---:|---:|---:|
| Value-weighted age received | **26.3** | 25.9 | 24.9 | 24.1 | **24.0** |
| Value-weighted age sent | 24.4 | 24.6 | 25.2 | 26.4 | 26.7 |
| Pick share of value received | 4% | 8% | 13% | 31% | 41% |
| Pick share of value sent | 30% | 25% | 16% | 5% | 3% |
| RB share of value received | 33% | 33% | 33% | 23% | 9% |
| Received players on NFL depth-chart #1 (value-weighted) | 54% | 52% | 47% | 40% | 42% |
| Cards in "window" lane | 79% | 68% | 36% | 73% | 93% |
| Viewer lead: plan / need / rank fact | 69% / 13% / 18% | 59% / 16% / 26% | 0 / 28% / 72% | 73% / 0 / 27% | 91% / 0 / 9% |
| Path: personal board | 88% | 93% | 98% | 98% | 92% |
| "Young RB (≤24) in for a 30+ player out" | 0.6% | 1.7% | 5.0% | 3.9% | 0.6% |

Reading:
- Outlook **does** move the deck strongly along the age and pick axes: All-in buys older and pays
  in picks; rebuilders and tankers do the reverse. So "outlook is ignored" is refuted.
- The All-in team with the #1 RB room still receives RBs as a third of incoming value, the same as
  a not-sure team. Nothing knows its RB slots are full of better players this season.
- Depth-chart starters received rise only from 40% to 54%, which is what age correlation alone
  would give.
- 88–98% of top cards qualify through the user's personal board, so the plan mostly re-orders
  what the board already wants.

These rates are for this synthetic world. The shape is what generalises, not the levels.

---

## 2. Gaps

| # | Candidate gap | Verdict | Evidence |
|---|---|---|---|
| G1 | Value is dynasty-only, so age is priced against what a contender wants | **Partly confirmed** | Value is dynasty-only (§1.2). The age adjustment cuts 30+ players by 10% for *everyone* (`trade_service.py:317-319`). That makes veterans cheaper to buy, which actually helps contenders on price. The plan term does favour older players for All-in (§1.7 C). The real issue is that "win-now" is approximated by age, not production. |
| G2 | Window is applied at team level, not asset level | **Partly confirmed** | Asset-level plan scores exist (`_plan_asset`), but they are a function of (outlook, position, age) only. The same score goes to every 25-year-old RB regardless of role or quality (§1.7 A). |
| G3 | No this-season points signal reaches the generator | **Confirmed** | Projections, best-lineup, odds, depth chart and `search_rank` all exist and are disconnected (§1.2 table). Revision 2 records the gap itself (`trade_gen_bilateral_candidate.py:80-89`). Production does capture weekly projections (G-076). |
| G4 | Lineup impact is not computed | **Partly confirmed** | A lineup *proxy* exists: legal slot assignment on dynasty value × age multiplier (`trade_gen_owner.py:339-363`). It is not points, and it cannot see that a 28-year-old bell-cow outscores a 22-year-old elite-value RB this week. Real points-based lineup gain exists only in Win Now. |
| G5 | Position need is rank-based on dynasty value, not starting-lineup strength | **Confirmed** | Legacy `position_needs` uses dynasty rank bins (`trade_service.py:3001-3092`). Home's Seller/Buyer bands use total position value across all rostered players, client-side only (§1.6). The bilateral need term is the dynasty lineup proxy. |
| G6 | Rebuild pieces are approximated by picks and youth, with no notion of appreciating vs depreciating | **Confirmed** | Rebuild plan = pick 1.0, young non-RB positive, RB negative (`trade_gen_bilateral_candidate.py:29-52`). No value trend, no pick seasonality, no breakout signal. `dp_values_history` is research-only. |
| G7 | *(new)* A declared plan cannot veto or even flag a plan-negative trade | **Confirmed** | There is no rule for plan gain below zero (`trade_gen_bilateral.py:196-201`). The personal-board path qualifies cards on preference alone (§1.7 B). The copy then has nothing true to say and falls back to rank facts. |
| G8 | *(new)* "Win-now" in the copy is an age claim | **Confirmed** | `plan_win_now` fires on `_now_lean ≥ 0.05` (`trade_narrative.py:561-564`). "Win-now: adds X, 28" can name a backup. |
| G9 | *(new)* Inferred outlook never reaches All-in or Tanking, and the projection suggestion never reaches the engine | **Confirmed (by design)** | `trade_service.py:4038-4040`; `recommendation.py:9`; D-230. Only a saved tap moves the engine to the extremes. |

---

## 3. How it could work

### 3.1 What the field does (outside research; sources in §7)

- **Two values per player.** Footballguys' trade value chart splits each player's value into
  rest-of-season points per game over replacement, plus discounted future value, and reports the
  current-season share [S1]. Harstad models contender vs rebuilder purely as a different discount
  rate on the same projections [S2]. *Confidence: high (both read directly).*
- **Market values are blended on purpose.** KTC tells voters to answer "in a vacuum", not as a
  contender or rebuilder, and keeps dynasty and redraft as separate databases [S5]. FantasyCalc is
  built from real trades (third-party description). *Confidence: high for KTC; medium for
  FantasyCalc.*
- **Contender/rebuild toggles elsewhere are shallow.**
  - RotoWire's toggle only changes which balancing assets it suggests [S6].
  - RotoBaller reportedly multiplies pick values for rebuilders [S7].
  - FantasyPros claims roster- and lineup-aware analysis but publishes no formula [S9].

  No public tool documents "points added to *your* best lineup". *Confidence: medium.* That is an
  opening.
- **League-specific replacement value.** Dynasty Nerds computes value above the league's starter
  and reserve baselines (RB/WR pooled for flex). It classifies teams as high-redraft/low-dynasty =
  contender, and the reverse = rebuilder [S4]. *Confidence: high.*
- **Age curves.**
  - **RB:** plateau from about 22 to 28 and a sharp drop at 29. 90% of top RBs are 28 or younger
    [S10]. PPG peaks at 27 and falls to 7.3 after 28 [S11]. Near-peak through 28, about 40% of
    baseline by 33 [S12].
  - **WR:** peak 26–28, decline from 29, falloff about 32 [S12, S13].
  - **TE:** holds to about 31 [S12].
  - **QB:** output into the mid-30s [S14].

  The engine's curves (RB cliff after 26, WR after 29, TE after 31,
  `trade_service.py:3439-3459`) are broadly consistent, if a little early on RB. *Confidence:
  high.*
- **Seasonality.** Picks appreciate from September into the May rookie drafts and dip in summer
  and right after the season [S15, S16]. Contenders should buy veterans in September–October;
  rebuilders sell aging veterans in November–December [S16]. *Confidence: medium (one-year sample
  and author estimates).*

### 3.2 A season signal is already in hand, year-round

Sleeper's `search_rank` sits on every `Player`, is stored in `players` and is re-synced at least
every 24 hours (`trade_service.py:2973-2976`). In the 2026-07 fixture it **behaves like redraft
ADP**, not dynasty value:

| RB | Age | Dynasty rank | `search_rank` order |
|---|---:|---:|---:|
| Christian McCaffrey | 29 | 11 | 4 |
| Josh Jacobs | 28 | 23 | 12 |
| Derrick Henry | 32 | 22 | 14 |
| Jeremiyah Love (rookie) | — | 4 | 86 (unranked pre-draft) |

*Measured on the fixture; inferred that it means "redraft". Sleeper does not document the field.
Whether it updates in-season was not verified.*

So the two-number model has a free offseason fallback, and weekly projections (live in production
per G-076) for the season. Rookies have no season rank before the draft, which is a correct
"not a this-season piece" signal until they get a role.

### 3.3 Options, smallest to largest

All costs below are inferred from the code paths named. The owner/bilateral evaluator already runs
a legal lineup assignment per side per candidate, up to 60,000 candidates per request
(`_LIMITS`, `trade_gen_owner.py:49-50`), so swapping what that assignment maximises is nearly free.

**O1 — Season-weighted lineup proxy (small).**
- **Change.** Replace `_lineup_value = value × age_now_mult` (`trade_gen_owner.py:270-271`) with a
  **season value** for contending and All-in teams:
  - in-season: rest-of-season projected points, from the league's latest saved projection run or
    the Win Now snapshot;
  - otherwise: a `search_rank`-derived season score mapped into value units;
  - fallback: today's age proxy.
- **What moves.** `need_utility`, asset interest (pool and focal order), plan gain, lane and the
  "Upgrades RB" line all become "does he start for *you*, and how much better than who he
  replaces". No new term and no new weight.
- **Operator's example.** A bench rookie behind a #1 RB room earns nothing; a bell-cow who beats
  the viewer's current RB2 earns real need credit. The 25-year-old starter vs backup tie (§1.7 A)
  breaks.
- **Build.** About one module plus a per-player season map in the request capture. The proof
  version is fenced like every revision.
- **Risks.**
  - Projection quality is uncalibrated (D-229 states the SD is provisional).
  - Provider dependence (Sleeper/RotoWire).
  - `search_rank` semantics are undocumented.
- **Validation.** Re-run §1.7 A/C. Replay the 247 recorded production requests
  (`docs/plans/realtime-trade-engine/real-leagues.md`) and compare decks for declared contenders.
  Run a Calibration round, revision 2 vs revision 2 + O1.

**O2 — Two-number asset model, S (season) + D (dynasty) (medium).**
- **Per asset.**
  - S = rest-of-season points above the *receiving team's* replacement at that lineup slot (from
    O1).
  - D = dynasty market value (unchanged).
  - Optionally, future value F ≈ D − λ·S, the Footballguys decomposition, with λ fitted so that
    units match.
- **Plan term weights S against F by outlook.** Illustrative only, to be tuned:

  | Outlook | Weight on S | Weight on F |
  |---|---:|---:|
  | All-in | 1.0 | 0.2 |
  | Contending | 0.7 | 0.5 |
  | Not sure | 0.5 | 0.5 |
  | Rebuilding | 0.2 | 1.0 |
  | Tanking | 0 | 1.0 |

  Picks have S = 0.
- **Prices stay on consensus D**, so fairness and the market floor are untouched.
- **Card copy:** "Season: +4.1 pts/wk to your lineup · Dynasty cost: 6% of your roster value", the
  same two numbers Win Now already speaks in.
- **Double counting.** D already contains current production. O2 never *adds* S to D; it changes
  which of the two the plan term rewards.
- **Build.** Medium: it replaces `_plan_asset` for both branches and the fit-block plan lead.
- **Offseason.** S comes from `search_rank` (season-long) with lower weight. A newly drafted rookie
  has S ≈ 0 until ranked.

**O3 — Lineup-aware need with real weekly points (medium-large).**
- **Change.** Per candidate, compute Win Now's marginal projected lineup points
  (`win_now_service._prepare_marginals`, `league_projections/core.optimize`) for both teams, over
  the next N weeks plus playoff weeks.
- **Cost.** Precompute each player's points per week; then each candidate needs one assignment per
  week per side. That is roughly weeks × today's cost, about 4–17×, unless reduced to
  rest-of-season totals, which is O1.
- **Gains.** Byes, flex and superflex handled exactly, and playoff-week weighting for All-in.
- **Limits.** In-season only.

**O4 — Trajectory tag: appreciating / peak / declining (small, mostly copy).**
- **Signals.**
  - Position age-curve phase (§3.1; the engine already has the curves).
  - Value trend from `dp_values_history` (needs a live feed; today it is research-only).
  - Pick seasonality.
- **Use.** Rebuild-side ordering ("buy appreciating, sell declining") and copy. It is weak on its
  own, because age is already in the plan, and adds information only through the trend.
  - *Inferred:* trend data is noisy week to week and lags news (third-party claim about
    FantasyCalc lag [S8]).

**O5 — Make the declared plan count (small, independent of O1–O4).**
- **Change.** For a *declared* outlook, a card whose viewer plan gain is clearly negative (say
  < −0.10) and whose need gain is zero is either:
  - **demoted** behind plan-neutral cards of comparable support; or
  - **shown honestly** ("Moves away from your All-in plan: you add a rebuild piece for a win-now
    piece; your rankings like him").
- **Why.** This addresses G7 directly. Without O1/O2 it still judges "plan" by age, so it fixes the
  *conflict* without fixing the *signal*.
- **Validation.** §1.7 B/C rerun; a Calibration round.

**O6 — Merge Win Now into the deck as the All-in lane (large).**
- **Change.** For All-in (or opt-in contending) teams in-season, serve Win Now's frontier as the
  deck's window lane, priced by the dynasty budget.
- **Gain.** It is the most honest answer to "help me win this year", because it simulates the
  season.
- **Costs.**
  - Win Now runs a simulator per shortlisted package (seconds per search).
  - It is in-season only and unavailable during a live week.
  - Its candidate set is buyer-centric.

  A product decision more than an engineering one. *Inferred.*

**What each outlook means as rules a manager recognises** (target state under O1+O2):

| Outlook | Target | Shop | Avoid |
|---|---|---|---|
| **All-in** | Players who start for *you* this season and add the most projected points over who they replace, even if old. Pay in picks and bench youth. | Picks, injured/stashed youth, bench rookies | Upgrades at a slot that is already full (the operator's RB case) |
| **Contending** | Lineup upgrades with some shelf life. Mild discount on 30+ RBs. | Distant picks, depth | Buying a declining RB at full dynasty price |
| **Rebuilding** | Appreciating assets: young WR/QB/TE, picks, especially 1–2 years out. Breakout candidates before the market moves. | Productive vets with high season value relative to dynasty value, in-season | Aging RBs at any price |
| **Tanking** | Picks, own next-year pick protected, elite young assets | Every season-only piece | Anything that adds wins this year |

---

## 4. Option: outlook-specific player labels (operator's proposal)

**Proposal.** Tag each player for each outlook, or with one trajectory label (win-now piece /
rebuild piece / both / neither). Use the tags as an input to who is shown which players.

**What the label is.** Two shapes are possible:
- a discrete tag per outlook (fit / neutral / poor);
- a single quadrant tag from two scores: season value S and dynasty value D (or F).

The second is the better shape. The quadrant is exactly the two-number model of O2 with
thresholds drawn on it. The engine should consume the *scores*, which are continuous, bounded and
weightable by outlook. The user should see the *label*, a readable summary on the card.

**Where it comes from.**
- **Derived** (projections or `search_rank` for S, consensus for D, age curve for direction): the
  only viable source today.
- **Curated by the operator:** does not scale past a few dozen players, and goes stale weekly.
- **Learned from behaviour:** not feasible now.
  - Every labelled bilateral card comes from **3 people**, and there are fewer than 5 counterparty
    responses ever (`docs/plans/realtime-trade-engine/acceptance-eval.md:14-24`).
  - The pass-reason code `fit_outlook` exists (`database.py:9385-9390`), but reasoned passes come
    almost entirely from the tester account (`acceptance-eval.md:252-260`).
- **Refresh.** Weekly in-season with the projection run; at player sync (24h) for `search_rank`;
  on the DP refresh for D.
- **Offseason.** S falls back to `search_rank`. Unranked rookies read as rebuild pieces until
  ranked, which is mostly right.

**League-relative vs global.** A global label cannot express the operator's case. A 28-year-old
RB2 is a win-now piece for a team that would start him, and a bench body for the #1 RB room. The
fix is a global label (S vs D) **plus** the lineup check of O1. The card can then say "win-now
piece, but would not start for you".

**Measured: global labels are fragile.** On the 340-player fixture I tried two reasonable rules,
both using season rank (`search_rank`) and dynasty rank within position, with a 12-team starter
cut-off:
- **Rule A:** rank ratio ≥ 1.6×.
- **Rule B:** startable-vs-dynasty-top quadrants.

What happened:
- They agree on only **13 of 50** players that either rule tags win-now or rebuild.
- Rule A labels Justin Jefferson, Patrick Mahomes and Lamar Jackson as "rebuild pieces", because
  their dynasty rank is slightly better than their season rank.
- Rule B labels George Kittle (32) a rebuild piece.
- Both call Davante Adams (33) either "win-now piece" or "both", depending on a one-rank boundary.
- Distribution under Rule B:
  - win-now: 15 players;
  - rebuild: 15;
  - both: 85;
  - neither: 225.
  - Win-now tags fall mostly on ages 27+ (13 of 15); rebuild tags mostly on ages ≤23 (10 of 15).

So discrete labels pass the eye test in aggregate but misfire on stars at the boundaries. That is
the strongest reason not to let a label gate the deck.

**How the label would be used, and which uses matter for the operator's example:**

| Use | Changes the operator's cards? | Verdict |
|---|---|---|
| Hard candidate filter (All-in never sees rebuild-tagged players) | Yes: the rookie card disappears | **No.** It hides fair value trades, a wrong label empties lanes, and it overrides the user's own board |
| Scoring (plan term) | Yes | Use the **scores** S/F (O2), not the tag |
| Deck ordering / demotion of plan conflicts | Yes: the card drops below plan-aligned cards | Via O5 |
| Quality filters | No | Not needed |
| Fit-block copy ("Win-now: adds X" because X is a win-now piece that starts for you) | Yes: the card gets a true sentence | **Best use of the label** |
| Partner side (offer a contender's rebuild pieces to rebuilders, and the reverse) | Indirectly: better counterparties | Use scores. Partner outlooks are mostly *inferred*, so the tags would be guesses about guesses |

**User disagreement.** Never let a label override the user's board; the board is the strongest
signal the engine has (0.45). Instead, surface the conflict: "You rank him above market; he's a
rebuild piece and you're All-in." That turns the operator's mystery card into an informed choice.

**The operator's example under the label approach.** The 23-year-old rookie RB has no season rank
→ rebuild piece. Davante Adams → win-now piece (Rule A) or both (Rule B). The All-in team gives a
win-now piece for a rebuild piece that would not start → plan conflict. With O5 the card is
demoted and its copy names the conflict. Without O5 or O2, a label changes nothing, because the
engine already scores this trade plan-negative (§1.7 B) and serves it anyway on the user's board.

**Verdict: adopt labels as the readable surface of the two-number model, not as an independent
engine input or filter.** The label adds no information beyond S, D and the lineup check. Its
value is explanation, and a quick read on cards and in Team Review. As a gate it would be fragile
and would hide value.

---

## 5. Recommendation and first step

**Path:** O1 → O5 → O2, with labels (§4) as the copy layer. Defer O3/O6 until O1's projections
prove useful; O4 only once a live value-trend feed exists.

**First step (ship-and-measure, about one revision): "season-aware lineup proxy for win-now
teams".** Behind a new default-dark selector, built like revisions 3/4:

1. **Build a per-request season map.** Use the league's latest saved projection run when current
   and complete (the D-230 completeness rule); otherwise `search_rank`; otherwise none, which keeps
   today's age proxy. Capture it in request evidence and hash it, as with the bound-age capture.
2. **For contending and All-in teams only**, `_lineup_value` uses that season value. Rebuild and
   tank branches are unchanged.
3. **Fill revision 2's empty `starter_evidence`** (`projected_starter_delta`, `state: "proxy"` or
   `"projected"`), and let `need.you` say "Starts for you at RB2" only when the season proxy
   supports it.

**How to measure it before serving:**
- Rerun §1.7 A, B and C. Expected:
  - the 25-year-old starter scores above the 25-year-old backup;
  - All-in RB share received falls for a full RB room;
  - depth-chart starters received rise beyond the age-only 54%.
- Replay the recorded production requests: deck change for declared contenders, and the share of
  received players who would start.
- Run one Calibration round (revision 2 vs revision 2 + season proxy) graded blind.
- Acceptance-rate evidence will not be available for months (3 labelled users), so do not wait
  for it.

**Then** O5 (plan-conflict demotion or honest copy), and then O2's explicit "Season +x · Dynasty
cost y" line.

---

## 6. Decisions for the operator

1. **Plan vs personal board.** When a declared All-in/Contending plan disagrees with your own
   rankings, should the deck demote the card, show the conflict, or keep today's behaviour (board
   wins silently)?
2. **Projections in the main deck.** Win Now and league projections already use Sleeper weekly
   projections (D-184 accepted them as restricted beta inputs; production has the provider flag on
   per G-076). Approve them as a *dynasty deck* input for win-now teams?
3. **Offseason season signal.** Accept Sleeper `search_rank` (undocumented, ADP-like) as the
   off-season and fallback signal, or require a documented redraft source?
4. **Labels.** Card and Team Review copy only (recommended), or also an engine input?
5. **Win Now vs main deck.** Keep them separate (today), or eventually make Win Now the All-in
   lane (O6)?

---

## 7. Sources

Outside sources were found by web search and read (fetched) unless marked. No project or user data
was sent. No text is reproduced.

| # | Source | Used for | Confidence |
|---|---|---|---|
| S1 | Dan Hindery, "Dynasty Trade Value Chart: November", Footballguys, 2025-11-04 — https://www.footballguys.com/article/2025-dynasty-trade-value-chart-november | Current-season + future split of value | High |
| S2 | Adam Harstad, "Dynasty, in Practice: How to Value Players in Dynasty", Footballguys, 2015 — https://www.footballguys.com/article/HarstadDiP21 | Contender vs rebuilder as discount rate; positional mortality tables | High |
| S3 | Harstad, Footballguys, 2023 rebuild article — https://www.footballguys.com/article/2023-dynasty-in-theory-69-how-to-rebuild | Market values are descriptive | Medium (snippet) |
| S4 | Lee Liberman, "The Ultimate Guide on Valuation", Dynasty Nerds, 2022 — https://www.dynastynerds.com/?p=114976 | League-specific value above replacement; redraft-vs-dynasty team classification | High |
| S5 | KeepTradeCut FAQ — https://keeptradecut.com/frequently-asked-questions | Votes "in a vacuum"; separate dynasty/redraft databases | High |
| S6 | RotoWire Dynasty Trade Calculator — https://www.rotowire.com/fantasy/football/dynasty-trade-calculator | Contend/rebuild toggle changes suggestions only | High |
| S7 | RotoBaller dynasty trade calculator — https://www.rotoballer.com/fantasy-football-dynasty-trade-calculator | Pick multipliers for rebuilders | Medium (snippet) |
| S8 | OfficePoolStop, trade-calculator limits, 2026-02-26 — https://www.officepoolstop.com/blog/the-importance-of-trade-calculators-in-dynasty-and-where-they-let-you-down | Calculators ignore team context; FantasyCalc trade-based and lags news | Medium |
| S9 | FantasyPros Trade Analyzer — https://fantasypros.com/analyzer | Claims lineup-aware analysis, no formula | Medium |
| S10 | Michael Moore, "The Running Back Cliff", PFF, 2015 — https://pff.com/the-running-back-cliff | RB cliff at 29 | High |
| S11 | Marvin Elequin, "The Lifecycle of a Dynasty Running Back", Fantasy Footballers, 2021 — https://www.thefantasyfootballers.com/articles/the-lifecycle-of-a-dynasty-running-back-fantasy-football/ | RB PPG by age | High |
| S12 | Tristan Bassett, "Production Curves…", 4for4, 2025 — https://www.4for4.com/2025/preseason/production-curves-positional-breakouts-prime-years-and-falloffs-age | RB/WR/TE curves | High |
| S13 | Scott Barrett, "Aging curves by position", PFF, 2018 — https://www.pff.com/news/fantasy-football-metrics-that-matter-aging-curves-by-position | Curves by years in league | High |
| S14 | Fox Sports (Bales, 2013); Fantasy Footballers TE lifecycle; Razzball WR/RB age analyses | QB/TE longevity | Medium (snippets) |
| S15 | Jay Stein, "Rookie Draft Pick Valuation", Footballguys, 2024 — https://www.footballguys.com/article/2024-dynasty-investor-rookie-pick-valuation | Pick price seasonality | High (one-year sample) |
| S16 | Kyle Borgognoni, "Dynasty Trade Windows: Timing the Market", Fantasy Footballers, 2025 — https://www.thefantasyfootballers.com/dynasty/dynasty-trade-windows-timing-the-market-fantasy-football/ | Contender/rebuilder calendar | High (author estimates) |

Not verified from first-party pages: FantasyCalc's dynasty/redraft toggle, Dynasty Daddy's
multi-market views, DynastyProcess's value-factor slider.

---

## Appendix: how the experiments were run

The scripts were throwaway and kept outside the repo. They are reproducible from this description.

**League and generator.**
- Load `backend/tests/fixtures/player_pool_2026.json`.
- Set age 22 for `years_exp == 0` rows with no age.
- Snake-draft 24 rounds into 12 teams, ordering by `dp_value_1qb × lognormal(0, 0.35)` (seeded).
- The viewer is the team with the highest RB value. Swap Davante Adams onto it for a same-position
  WR.
- Add 4 picks per team, valued 2600/1100/450/180 ± 80.
- Seed Elo = `value_to_elo(value)`.
- The viewer board and 4 opponent boards are consensus × lognormal noise (0.3 / 0.25). The
  remaining opponents have no board.
- Opponent outlooks cycle contender / rebuilder / not_sure / championship / jets.
- `fairness_threshold = 0.75`.
- Generator: `trade_gen_bilateral_candidate.generate_bilateral_trades(**kwargs)` (flags from
  `config/features.json`; DB knobs at code defaults). About 5 s per run.

**Fit leads.** Computed with the shipped `trade_narrative._fit_plan` / `_fit_need` on each card's
proof.

**Two-RB test.**
- Inject synthetic RBs (value 1,150; ages 23/28/25/25; depth chart 2/1/1/3) onto one opponent.
- Set the viewer board equal to consensus, so there is no personal lean; for test B, lift it by
  ×1.15/1.3/1.6.
- Evaluate `[Davante Adams] → [RB]` with the search's own `evaluate`.

**Labels.**
- Season rank = order by `search_rank` within position; dynasty rank = order by `dp_value_1qb`.
- Starter cut-offs: QB 14, RB 30, WR 42, TE 14.
- Rule A: tag when rank ratio ≥ 1.6 on the startable or dynasty-top side.
- Rule B: startable and not dynasty-top → win-now piece; dynasty-top and not startable → rebuild
  piece.
