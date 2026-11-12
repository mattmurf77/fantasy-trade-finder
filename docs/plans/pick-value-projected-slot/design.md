# Next-year firsts priced by the projected draft order — design

> Design for pricing a NEXT-season round-1 pick by where its ORIGINAL team is projected to
> pick, using the saved league forecast (`backend/league_projections/`). Scope block:
> [scope.md](scope.md). Written 2026-11-11 (NFL week 10) against `origin/main` `564ff857`.
> **Built 2026-11-11 on `feat/pick-value-projected-slot`, flag off** — see §0 for the operator
> rulings that replaced parts of §4.2, §5 and §8.

## 0. Operator rulings, 2026-11-11 (these override the sections below)

- **All eight decisions in §12 approved as recommended** ("I'm aligned with the 8 decisions
  for draft picks"). Decision 7 (ship ON) is executed by the operator flipping the flag after
  the replay; the build leaves `picks.projected_slot_value` false.
- **Full strength; no season-played discount by default** (replaces §4.2 step 4 and the
  week-10 column of §5). Operator: *"For top end of draft picks, we should match that curve.
  Those owners are certainly going to value picks that highly."* `w = pick_projection_weight`
  once the ≥ 3-week gate passes. The weeks ramp survives behind a new knob,
  `pick_projection_season_scaling` (default 0; 1 = the ramp below). Zero-sum and every gate
  stay. At full strength a pick certain to land in slots 1–4 prices 3,160.6 against DP's
  "2027 Early 1st" 2,983.2, and slots 9–12 853.7 against "Late 1st" 844.9 (pinned within 10 %).
- **Show the exact projected slot, not "proj. early/late"** (replaces §8 and drops the
  `pick_projection_tag_threshold` knob). Operator: *"for presenting these picks we should
  include some sort of assumed pick number label or name… `1.01 [Projected]`"*. The slot is the
  rounded expected slot under the pricing distribution; every adjusted pick shows it:
  `name`/`label` = `"2027 1.02 (from dondags) · projected"`, plus wire fields `proj_slot`
  (`"1.02"`) and `proj_name` (`"2027 1.02 (from dondags)"`). Contract:
  `docs/cross-client-invariants.md` § Projected slot value.
- **Decision 8 built** as `config/league_projections.json` `baseline_retention_days` (90):
  complete weekly baseline runs are kept, result only, for scoring after the season.
- **Facts corrected at build time:** the current forecast model is
  `projected-lineup-universal-sd-v6` (read from `league_projections.core.VERSION`, never
  hard-coded), and DP's live file (2026-11-06) still prices per-slot rows for the 2026 class
  only plus 2027 Early/Mid/Late/1st, so §4.2's grid-as-shape design stands.

- [1. The ask](#1-the-ask)
- [2. Map of today](#2-map-of-today)
- [3. Options compared](#3-options-compared)
- [4. Recommended design](#4-recommended-design)
- [5. Worked example](#5-worked-example)
- [6. Edge cases](#6-edge-cases)
- [7. Consistency, caching, hashes](#7-consistency-caching-hashes)
- [8. What the user sees](#8-what-the-user-sees)
- [9. Risks](#9-risks)
- [10. Evaluation](#10-evaluation)
- [11. Build order](#11-build-order)
- [12. Open decisions for the operator](#12-open-decisions-for-the-operator)
- [13. What the code could not tell us](#13-what-the-code-could-not-tell-us)

---

## 1. The ask

Operator, 2026-11-11, verbatim: *"I also think we should add value adjustments to next year
firsts based on the projected draft order. I just got presented an offer for a first from a
team (dondags) projected as a top 3 pick. But our valuations don't consider that which makes
it difficult to present fair trades"*.

So a 2027 1st originally owned by a team the forecast expects to pick near the top should be
worth more than a 2027 1st from a projected contender. It has to be worth more in every place
a pick is priced, and the user has to be able to see why.

This partly reopens the operator's own ruling in D-146 (2026-08-21): *"Aligned that future
picks stay default for now."* That ruling is why every future pick prices generically today.
Decision 1 in §12 asks for the reversal explicitly, scoped to next year's draft only.

## 2. Map of today

### 2.1 How a 2027 1st gets its value

There is **one pricing seam**: `pick_values.priced_pool_value(row, slot=…)`
(`backend/pick_values.py:723-786`). It is reached in `server.py` only through
`server._priced_pick_value` (`backend/server.py:20700-20718`), which an AST test pins
(`backend/tests/test_league_pick_value_alignment.py:100-116`). It runs a three-step
waterfall:

1. **Slot known → that slot's DynastyProcess price** (`market_pick_slot_value`,
   `pick_values.py:515-563`). The slot comes from D-090: `server._league_slot_order`
   (`server.py:20612-20648`, 300 s cache) → `pick_slots.slot_for` (`pick_slots.py:199-237`).
   `slot_for` **refuses every season but the one stamped on the stored order**
   (`pick_slots.py:216`, "#273 — a future season has no order"). DP also publishes per-slot
   rows only for the current class. So **a 2027 pick never reaches step 1 today.**
2. **No slot → the round curve** (`market_pick_pool_value`, `pick_values.py:464-512`): the
   value-space mean of DP's slots 5–8 for that season, or DP's `"<season> Mid 1st"`, or
   `"<season> 1st"`. Then, for round 1 only, the **D-161 floor**: a future 1st may not price
   below `market_r1_yoy_floor` (1.0) × the current class's round-1 price
   (`_r1_yoy_floored`, `pick_values.py:692-720`; the anchor season is
   `market_anchor_season`, `pick_values.py:657-689`).
3. **No DP data → the stored ladder** `draft_picks.pool_value` (the Mid rung, 2117.0 for a 1st).

**The original owner affects none of the three for a 2027 pick.** The row's
`original_roster_id` is read only by `slot_for`, which returns None for 2027. Every 2027 1st
in a league therefore prices the same. With the pinned DP snapshot
(`backend/tests/fixtures/dp_values_picks_2026-08-06.csv`, 1QB), that price is **1859.5**. DP's
own "2027 Mid 1st" is 1504.6, and the D-161 floor raises it to the 2026 round-1 tercile mean of
1859.5.

### 2.2 The user-ranking value

None applies. Users rank the 12 **generic rungs** (`GENERIC_PICK_SEEDS`,
`pick_values.py:28-54`, `generic_pick_<round>_<tier>`). Those rungs never sit on a roster and
never enter a trade signal (`strip_generic_pick_pair`, `pick_values.py:246-266`). An
**owned** pick gets the consensus price on every board: `_inject_owned_picks` writes the same
bridged Elo into the seed map, the user's board and every member's board
(`server.py:20918-20925`, `user_elo.update(pick_elos)  # user board: consensus for picks`).
So a user's opinion of "2027 Early 1st" never reaches dondags' actual 2027 1st, and there is
no ranking to double-count against.

### 2.3 Every consumer of an owned pick's price

All of these go through `_priced_pick_value`, each hoisting `_league_slot_order` once per
league:

| Surface | Site |
|---|---|
| Deck engine (every generator: legacy, v2/v3, bilateral, rules-first): injected PICK pseudo-players + Elo maps | `_owned_pick_assets` `server.py:20753-20845`, `_inject_owned_picks` `server.py:20859-20926` |
| Roster eveners ("add their 2027 1st") | `server.py:1160-1175` |
| Calculator `/api/trade/evaluate` | `server.py:19630-19634` |
| Full-roster gate context | `server.py:11051-11055` |
| `/api/league/picks` (Picks screen value + tier badge) | `server.py:20320-20330` |
| Power rankings / roster history | `server.py:38566-38590` |
| Calibration (grading) capture | `backend/outlook_calibration_adapter.py:421-426` (order also in provenance, `:78`) |
| Prepared-inventory lookup receipt (order hashed) | `backend/prepared_trade_runtime.py:329` |

**One consumer bypasses the seam:** Win-Now prices exactly the next-season picks
(`season > league season`, `backend/win_now_service.py:343`) with a bare
`priced_pool_value(p, scoring_format=…)` (`:349`), so no slot and no league context reach it.

Deck rules (`deck_rules.py`, `deck_quality.py`, filler floor `max(450, 0.25×headliner)`), the
fairness/market score, and the card's `give_value`/`receive_value` all read the injected Elo
maps, so they see whatever `_priced_pick_value` returns.

### 2.4 Display today

`_owned_pick_label` (`server.py:20342-20367`) emits `"2027 1st"`, or `"2027 1st (from
dondags)"` when the pick was traded. A current-season pick with a known order reads `"2026
1.08"`. Card assets are `player_to_dict(Player)` (`trade_card_to_dict`,
`server.py:21288`), and an injected pick's `name` is that label (`server.py:20831`). **No
"projected early" or "proj. 1.02" text exists anywhere today.** The narrative mentions picks
only generically (`trade_narrative.py:161-166`).

### 2.5 What the forecast holds

The run lives in `league_projection_runs.result_json`, keyed by **(user, league)**
(`store.py:104-110`). It is written by the weekly batch (`batch.py:dispatch`: Tuesday 09:30
ET, 4 leagues per 15-minute tick, `config/league_projections.json`). The batch sets
`draft_season = league season + 1` (`batch.py:189`), which means 2027 today. Per team
(`simulation.py:281-296`), the run stores:

- `pick_probabilities`: **unconditional** probabilities of non-playoff slots 1…(n − playoff
  spots) (`simulation.py:158, 288`). The mass missing from that list is
  `playoff_probability`.
- `conditional_pick_probabilities` and `conditional_expected_pick` (given a miss),
  `playoff_probability`, `maxpf_mean`, `pick_owner_roster_id` (round-1 owner).
- Run level: `completed_weeks`, future `weeks`, `model_version`, `config.draft_season`,
  `coverage`, `captured_at`.

**The draft-order rule is assumed, not read.** Non-playoff teams are sorted by simulated Max
PF, lowest first (`simulation.py:262`), recorded as `draft_sort: "projected_maxpf_mean"` and
`nonplayoff_draft_order_basis: "regular_season_maxpf_scenario"`
(`provider.py:634`). The spec (`docs/plans/league-projections/specification.md:9-13`) calls
this "the demonstrated league class". **Playoff teams' slots are not projected**
(`simulation.py:325`). No lottery or reverse-standings rule exists anywhere in the code.

**Coverage and freshness:**

- Sleeper only (`api.py:73,102`).
- Leagues with divisions, median games, best ball, manual seeding, non-standard brackets or a
  non-week-1 start are refused (`provider.py:233-267`).
- Many runs stop `incomplete_projections`, per NEXT.md's v5 item.
- A run is "stale" after the next weekly slot (`batch.py:210-221`). After the regular season
  ends, the provider refuses (`season_state_mismatch`, `provider.py:246`), so the last
  in-season run is the final one.
- In production the flags are **on** through Render's `FTF_FLAGS`, even though
  `config/features.json` lists them false (`docs/config-reference.md:247`, G-076).

### 2.6 D-090 and the season boundary

D-090/D-144 already do the analogous thing for the **current** class, using the real order
once Sleeper publishes `draft_order`. Today is 2026-11-11, week 10. The 2026 rookie draft is
done, so its rows have been deleted (#228). "Next year's first" is the **2027** pick
(`draft_picks.season = 2027`). Its order becomes known only when the 2027 Sleeper draft object
gets a `draft_order`, which usually happens after league renewal in the off-season. From that
point D-090 step 1 takes over and this feature has nothing to do.

## 3. Options compared

| | a. Expected value over the slot distribution | b. Three buckets from expected slot | c. Multiplier from projected finish |
|---|---|---|---|
| Uses the forecast's uncertainty | Yes. A 40/30/15 % spread prices between slots 1 and 3 | No. Collapses to one number | No |
| Smooth week to week | Yes. Value moves with probabilities | **No.** Expected slot 4.4 → 4.6 moves a pick from "early" (≈3,690) to "mid" (≈1,860), half its value in one forecast run | Depends on the curve |
| Market-grounded | Yes, DP's own per-slot curve | Yes, DP publishes 2027 Early/Mid/Late 1st | No. We would invent the curve |
| Captures the convexity at the top (1.01 ≫ 1.04) | Yes | No, the early bucket averages 1.01–1.04 | No |
| Conserves the league's total pick value | Yes, with the normalisation in §4.2 | No | No |
| Cost | n multiplies per pick | Trivial | Trivial |

**Recommendation: (a)**, normalised so the league total is conserved and shrunk toward the
generic price by how much season is left. Option (b) survives in one place, as the fallback
curve when DP publishes no per-slot grid (§4.3). Option (c) is rejected: it carries less
information than (a), it would invent a curve, and nothing about it is simpler to explain.

Market sanity check for (a): DP itself prices 2027 Early / Mid / Late 1sts at 2983.2 / 1504.6
/ 844.9, against a generic "2027 1st" of 1522.7 (fixture). That is ×1.96 / ×0.99 / ×0.55.
With the normalised slot curve, a pick certain to land in slots 1–4 is ×1.70 the generic and
one certain to land in 9–12 is ×0.46. The design lands inside the market's own spread
without being told it.

## 4. Recommended design

### 4.1 Scope of the adjustment

- **Picks:** round 1 only (knob `pick_projection_max_round`, default 1). The reasons for
  holding rounds 2+ out:
  1. The absolute moves are small. A 2.01 is 728 and a 2.12 is 316 (fixture), so about ±300
     against a 1st's ±1,500.
  2. Snake drafts reverse round 2. A projected-early 1st becomes a late 2nd, and the 2027
     draft type is unknown until the draft object exists.
  3. The operator asked for firsts.
- **Seasons:** only the forecast's `config.draft_season`, which is league season + 1. 2028 and
  later stay generic, because no forecast says anything about them.
- **Leagues:** Sleeper leagues with a usable forecast (§4.5). ESPN, MFL, Fleaflicker, the demo
  league, and refused or incomplete Sleeper leagues all stay generic, byte for byte.
- **Ownership:** the value follows `draft_picks.original_roster_id`, which is the Sleeper
  `roster_id` the forecast keys teams by. It does not follow the current holder. A traded
  pick carries its original team's projection, and the label already says "(from dondags)".

### 4.2 The formula

For a 2027 1st originally owned by roster *r* in an *n*-team league:

1. **Slot distribution `p_r[1..n]`.** Non-playoff slots 1…(n−P) come from
   `pick_probabilities` as stored. Each team's `playoff_probability` is spread **evenly**
   over the playoff slots (n−P+1)…n, because the forecast does not project playoff finish
   (`simulation.py:325`). Every team's vector sums to 1, and every slot's column sums to 1
   across the league. Each simulated world fills each slot exactly once, and even spreading
   preserves the playoff columns.
2. **Per-slot curve `c[1..n]`** in **engine value units** (`elo_to_value(seed Elo)`, the
   `draft_picks.pool_value` scale). This is DP's per-slot round-1 grid for the season
   `market_anchor_season` reads, mapped to league size by percentile with
   `draft_board_service._basis_slot` (the Draft Room's mapping, so slot *k* of 10 means the
   same as it does on the board). Means are taken in value space, never Elo space: Elo is
   log-value, so an Elo mean would understate the top.
3. **Ratio.** `ratio_r = Σ_k p_r[k]·c[k] / mean(c)`. The denominator is the curve's mean
   under an uninformative (uniform) distribution, so a forecast that knows nothing gives
   ratio 1.
4. **Strength.** `w = pick_projection_weight` (default 1.0; 0 = off with no deploy).
   *Superseded 2026-11-11 (§0):* the original design multiplied by `completed_weeks /
   (completed_weeks + future_weeks)`; that ramp is now opt-in via
   `pick_projection_season_scaling` = 1.
5. **Price.** `value = G × (1 + w·(ratio_r − 1))`, where **G is exactly today's price** for
   that pick: step 2 of the waterfall including the D-161 floor, or the stored ladder if DP
   is unreachable.

**Why normalise by the uniform mean (zero-sum).** Every slot's column sums to 1, so
`Σ_r ratio_r = n` and the **league's total 2027-first value is unchanged**: dondags' pick
gains exactly what the contenders' picks lose. Without the normalisation, the forecast would
also add the lottery premium. The all-slot mean (2210.5) sits 19 % above the mid-tercile
generic (1859.5). That premium would inflate every forecast league's picks against its
players and against non-forecast leagues, and D-144 deliberately rejected it when it chose
the tercile basis (`pick_values.py:395-423`). The cost is a jump at handover in §6: once the
real order is known, D-090 prices the actual slot with no normalisation.

**Why shrink by weeks played, on top of the Monte Carlo** (the original argument, kept for
the record; the operator ruled for full strength on 2026-11-11, §0). The simulation's spread covers
only the score noise it models, with a provisional, uncalibrated 25-point SD
(`config/league_projections.json`, D-229). It excludes roster churn, injuries and trades. The
run says so itself ("Monte Carlo error excludes model and provider uncertainty",
`simulation.py:322`). That unmodelled error shrinks as the season runs out, so the weight
should rise with it. This is conservative on purpose, because the failure it guards against
is overpaying. A gate also applies: fewer than `pick_projection_min_weeks` (default 3)
completed weeks means no adjustment.

### 4.3 Fallbacks inside the formula

- **No per-slot grid in the DP map, but rungs exist:** use DP's season Early/Mid/Late 1st as
  a 3-step curve (slots in thirds), which is option (b) as a curve. DP publishes 2027
  Early/Mid/Late in the fixture.
- **DP unreachable:** G is the stored ladder, and there is no curve, so the value is G and
  the result is generic.
- **D-090 resolves a real slot but DP has no row for it:** treat the slot as a point mass
  through the same curve, rather than dropping back to the projection. Today this case falls
  through to the generic round curve.

### 4.4 Where it lives

- **New pure leaf `backend/pick_projection.py`** (no I/O, no flags). It holds:
  - `compact(result_json) -> PickProjection | None`: the per-roster `p_r`, season, n, P,
    weeks and a `key` (run_id + model version + knobs).
  - `distribution(projection, original_roster_id)`.
  - `ratio(dist, curve)` and `tag(dist)`.

  Add it to `_ENGINE_CODE_MODULES` (`server.py:4741`) so a code change colds stored pages.
- **`pick_values.priced_pool_value(..., projection=None)`** gets one new step between 1 and 2:
  when step 1 has nothing, the projection covers `(season, round)` and the original roster is
  in it, return `G × (1 + w·(ratio − 1))`. Rounding is 1 dp, as everywhere else.
  `tier_ladder` mode returns the stored value before this step runs, so bake-off arm A stays
  byte-identical.
- **`server._league_pick_projection(league_id)`** is a twin of `_league_slot_order`: one read
  per league with a 300 s TTL cache. It reads the newest `complete` **baseline** run for the
  league from **any** registered user (scenario runs are user what-ifs and excluded) and
  applies the gates in §4.5. It returns the compact projection or None and checks
  `picks.projected_slot_value` live.
- **`server._priced_pick_value(p, slot_order, fmt, projection=None)`**. Every caller in §2.3
  hoists the projection once per league, beside `slot_order`. Win-Now gets the same argument.

### 4.5 When a forecast is usable

Use the run only if all of these hold, otherwise return None and price generic:

1. The flag is on, the league is Sleeper and not the demo league.
2. `status == complete`, `model_version == VERSION`, and `config.draft_season == pick season`.
3. Completed weeks ≥ `pick_projection_min_weeks`.
4. The run is younger than `pick_projection_max_age_days` (8 days, one weekly cycle plus
   slack), **or** the run had at most one future week left. The last in-season run therefore
   stands through the off-season until D-090 takes over, since no newer run is possible
   (`provider.py:246`).
5. Every team's vector sums to 1 ± 1e-6, so the stored arithmetic is sound.

A refresh that failed (`refresh_failed`) leaves the last success in force while it is inside
the age window.

## 5. Worked example

Assumptions:

- Units: engine value (`draft_picks.pool_value` scale).
- 1QB format, with DP numbers from the pinned fixture
  `backend/tests/fixtures/dp_values_picks_2026-08-06.csv`, converted through
  `data_loader.seed_elo_for_value` and `trade_service.elo_to_value` (constants
  `trade_service.py:173-175`).
- A 12-team league with 6 playoff spots, week 10: 9 completed weeks of a 14-week regular
  season, so `w = 9/14 = 0.643`.
- **The slot distributions are illustrative.** No saved forecast is in the repo. A real run
  produces them from `pick_probabilities`.

The inputs:

- **Generic G today:** 1859.5 for every 2027 1st. That is DP "2027 Mid 1st" 1504.6, floored by
  D-161 to the 2026 tercile mean (slots 1.05–1.08: 2343.2, 1979.0, 1680.0, 1435.5).
- **Curve c, 2026 round 1:** 4867.1, 4025.0, 3343.0, 2793.0, 2343.2, 1979.0, 1680.0, 1435.5,
  1235.0, 1070.0, 934.0, 820.8. Uniform mean 2210.5.

| Team | Slot distribution (1→12) | E[slot] | ratio | Today | Proposed, w = 0.643 (week 10) | Proposed, w = 1 (season over) |
|---|---|---|---|---|---|---|
| Projected top 3 (dondags-like) | .40 .30 .15 .07 .03 0 + .05 spread over 7–12 | 2.4 | 1.80 | 1859.5 | **2817.2 (+52 %)** | 3349.2 (+80 %) |
| League-average bubble | .02 .04 .08 .12 .14 .15 + .45 over 7–12 | 6.7 | 0.92 | 1859.5 | 1758.7 (−5 %) | 1702.6 (−8 %) |
| Projected contender (picks 10–12) | 0 0 0 0 .01 .02 + .97 over 7–12 | 9.4 | 0.55 | 1859.5 | **1325.5 (−29 %)** | 1028.8 (−45 %) |

For scale:

- A certain 1.01 would price 4094.3 and a certain 1.12 690.5 (G × c[k] / 2210.5).
- DP's own 2027 Early 1st and Late 1st are 2983.2 and 844.9.
- The ladder Mid 1st is 2117.0.
- Superflex runs about 20 % higher throughout. The 2026 tercile is 2263.3 and the 1.01 is
  6181.1, so the ratios, and therefore the percentages, are nearly the same.

Read for the operator: today dondags' 1st and a contender's 1st are the same 1,860. At week
10 this design prices dondags' about 2,820, and the contender's about 1,330. By the last week
of the season they would be about 3,350 and 1,030.

## 6. Edge cases

| Case | Behaviour |
|---|---|
| No run, run incomplete, stale beyond the age window, other model version | Generic, as today |
| ESPN, MFL, Fleaflicker, demo | Generic. The forecast is Sleeper only |
| Traded pick | Priced by the **original** roster's projection. The label already names the original team |
| Pick held by a team whose own pick is also in the forecast | Each pick is priced by its own original roster. They are independent |
| 2028 and later | Generic, with the D-161 floor as today |
| Rounds 2+ | Generic (knob `pick_projection_max_round`) |
| League size ≠ 12 | `_basis_slot` percentile map, the same as the Draft Room. This also avoids the Q-027 literal-slot divergence for projected picks |
| n − P = 0 (everyone makes playoffs) | Every vector is uniform, so the ratio is 1 and the price is generic. No special case needed |
| Draft order not by Max PF (reverse standings, lottery, commissioner-set) | The forecast assumes Max PF, and nothing in the code can tell. Decision 4 in §12 |
| Regular season over, playoffs running | The last run stands (§4.5 rule 4) until D-090 resolves the real order. Follow-up: price the known non-playoff order exactly from final standings instead of the last run |
| Real 2027 order published (D-090) | Step 1 wins. If DP has no 2027 slot row yet, the slot is a point mass on the same curve (§4.3) |
| Handover jump | A pick certain to land at 1.01 moves from 4094 (normalised) to DP's real 1.01 price (4867 on the 2026 grid) when the order lands. That is the same 19 % convexity gap the tercile basis already creates between generic and slot prices today. It is documented, not fixed |
| Account deletion of the user whose run is used | Their runs go (`_lock_live_user` fence). The next read picks another leaguemate's run or returns generic |

## 7. Consistency, caching, hashes

**One number everywhere.** Every surface in §2.3 calls `_priced_pick_value` with the same
hoisted projection, so the deck engine, both sides of the bilateral and market math, deck
rules, the calculator, eveners, the Picks screen, power rankings, calibration capture and
Win-Now agree by construction. Extend the one-seam AST test: `_league_pick_projection` must
be hoisted once per league at each listed surface, mirroring
`test_power_rankings_resolves_the_draft_order_once_per_league`.

**Performance.** Per league: one indexed select of `result_json` for the newest qualifying
run, parsed once and compacted to n × n floats, then cached 300 s keyed by league. Per pick:
an n-term dot product. The deck's ~1 s budget is untouched, and nothing simulates at request
time. Parsing a full `result_json` costs a few ms; the per-week details in it make it large.
Select only `run_id, created_at, result_json` and drop everything but the teams' slot fields
immediately.

**Invalidation.** Required, because the price now changes when a new run lands:

- **`roster_snapshot.values_snapshot_id` (vsn1)** hashes stored `pool_value`, not served
  prices (`roster_snapshot.py:245-264`). Add an optional `pick_projection_key` folded into
  the hash, and pass it at all three call sites (`server.py:7454, 8498, 33433`). Otherwise
  stored first pages (`trade_page_store`) and cached jobs keep serving last week's pick
  prices. A test must assert that all three sites pass the same key, because a mismatch
  means permanently stale pages.
- **Prepared-inventory receipt:** add `"pick_projection": key` beside `"slot_order"`
  (`prepared_trade_runtime.py:329`).
- **Calibration provenance:** record the key beside `slot_order`
  (`outlook_calibration_adapter.py:78`).
- **`DECK_PIPELINE_VERSION` 22 → 23** with a new pin, since `_priced_pick_value`,
  `_owned_pick_assets`, `_inject_owned_picks` and the label are listed deck-pipeline
  functions and `test_deck_pipeline_digest` will demand it. Also add `pick_projection.py` to
  `_ENGINE_CODE_MODULES`.
- **Knobs** live in `model_config`, which enters the job config hash already.

## 8. What the user sees

> **Superseded 2026-11-11 (§0).** The shipped display names the projected slot on every
> adjusted pick: `"2027 1.02 (from dondags) · projected"`, plus `proj_slot` / `proj_name` on
> asset payloads. The early/late tag below was never shipped.

When the adjustment is material (|value / G − 1| ≥ 10 %), the pick's label gains a tag:
**`2027 1st (from dondags) · proj. early`** or **`2027 1st · proj. late`**. Early and late are
the thirds of the league by expected slot; a mid pick gets no tag. The tag comes from the same
projection that set the price, at the same five label sites as D-090 (`_owned_pick_label`
gains the projection argument). The label and the price therefore cannot disagree, which is
the same discipline D-090 follows.

Because cards, eveners, the calculator and the Picks screen render `name` / `label` from the
server, **no mobile or web release is needed.**

The tier badge on the Picks screen moves with the value: a badge reflects the served value
(D-320-2). The tag is the "why".

Not in v1:

- An exact "proj. 1.02", which is false precision in November.
- A probability readout such as "top-3 odds 85 %". It could be added to the narrative later.

## 9. Risks

1. **The forecast is wrong, and we overpay.** The week ramp (w = 0.64 at week 10, about 0.2
   at week 3, nothing before week 3) and the zero-sum normalisation cap the damage. The SD is
   uncalibrated (NEXT.md). Calibrating it is the real fix and is already queued.
2. **Self-defeating trades.** Sending dondags good players makes dondags better, so his pick
   gets worse. The price shown is the pre-trade forecast, and the deck will happily suggest
   "your stars for his projected top-3 1st". `outlook/trade_delta.py` computes
   post-trade playoff deltas but ignores picks. Conditioning on the post-trade roster is a v2
   item. For v1 the shrink and the tag are the mitigation. Flag it to the operator, because it
   is exactly the shape of the dondags offer.
3. **Weekly value jumps reshuffle decks.** Prices move once a week, when a run lands (Tuesday
   09:30 ET). Stored pages go stale and rebuild. The ramp keeps early-season moves small, and
   late-season moves are mostly real information.
4. **Double counting with user rankings.** None. Owned picks carry the consensus price on every
   board (`server.py:20922`) and generic rungs are untouched (§2.2). A test should pin this.
5. **The wrong draft-order rule** for leagues not ordered by Max PF (§12, decision 4).
6. **Tier badges and power rankings move weekly.** A contender's team value drops a little as
   its own 1st is marked down. That is coherent, but visible.
7. **Reading another user's forecast** to price a leaguemate's deck. The inputs are public
   league facts, and the run is account-fenced and deleted with its account. The output is a
   number on a pick, not the forecast itself.
8. **Partial coverage.** Many leagues will be generic, because runs are refused or incomplete.
   That is the honest default, but the operator should expect the feature to be absent in
   some leagues.

## 10. Evaluation

**Unit tests** (`backend/tests/test_pick_projection.py`, new). Each lists its sabotage target:

| Test | Sabotage that must fail it |
|---|---|
| Conservation: for random valid forecasts, Σ over a league's 1sts = n × G (±0.1 × n) | Drop the uniform-mean normalisation |
| An uninformative forecast (all vectors uniform) prices exactly G | Use the tercile instead of the full-curve mean as the denominator |
| w = 0 (knob 0, or min weeks not met) gives values byte-identical to the flag off | Apply the ratio before the weight |
| A point mass on slot k gives G × c[k] / mean(c) | Average in Elo space |
| Stochastic dominance: a team strictly more likely to pick early is never cheaper | Reverse the curve index |
| A traded pick uses the original roster, not the owner | Key by `owner_user_id` |
| Playoff mass is spread evenly, and vectors sum to 1 | Ignore `playoff_probability` |
| A 10-team and a 14-team league map through `_basis_slot` | Literal slot lookup |
| 2028 pick, round-2 pick, ESPN league, demo, stale or other-model run → generic | Remove any single gate |
| `tier_ladder` pin (bake-off arm A) is unchanged | Put the step before the mode check |

**Integration tests:**

- One league fixture with a stored synthetic run. The same pick has one value in
  `/api/league/picks`, power rankings, `/api/trade/evaluate`, the injected engine Elo
  (round-trip), the evener assets and Win-Now. Extend `test_league_pick_value_alignment.py`
  and its AST seam list.
- vsn1 changes when, and only when, the projection key changes. All three call sites pass the
  same key.
- The label tag appears only above the 10 % threshold and only with the flag on. The flag-off
  label is byte-identical (existing D-090 tests stay green).
- `test_deck_pipeline_digest` is bumped. `test_bakeoff_arm_a_golden` is untouched.

**Replay.** A new `backend/eval/pick_projection_replay.py` is aggregate-only, in the style of
`served_deck_replay.py`. It runs over the 247 recorded owner requests in the git-ignored
`data/prod-requests/` (operator machine only). For each request it re-prices the captured
2027 round-1 pick Elos with a projection and rebuilds the served deck both ways. It reports:

- the share of decks and cards that change
- cards containing a 2027 1st, before and after
- the distribution of pick-value deltas
- cards newly admitted or rejected by the deck rules
- the sum-of-pick-value conservation per league

Recorded requests carry no forecast, so it runs two arms:

1. **Synthetic:** distributions drawn around a random league order at three concentrations,
   approximating weeks 3, 10 and 14.
2. **Real:** read-only aggregate pulls of the latest baseline run for the replayed leagues,
   by the operator through `backend/tools/prod_analytics.py`.

Pass bar for shipping ON: conservation holds on every league; no deck loses more than about
20 % of its cards; and the operator signs off on a sample of before/after cards from their
own league, with dondags' 1st visible.

**Forecast-accuracy backtest, after this season.** Once the 2026 regular season ends (week
14), score every saved weekly run's slot distributions against the realised non-playoff
order using log loss and Brier, by week. Fit the ramp, and with it `pick_projection_weight`,
on that. Runs are retained 7 days (`config/league_projections.json`), so the operator must
copy runs out weekly from now, or raise `retention_days`. That ask is in §12.

**Manual TestFlight checklist:** see scope.md §3. It needs no new build.

## 11. Build order

1. **`backend/pick_projection.py`** (pure leaf) and its unit tests. Add it to
   `_ENGINE_CODE_MODULES`.
2. **`pick_values.priced_pool_value(projection=)`**: the new step between 1 and 2, plus the
   point-mass fallback for a slot without a DP row. Tests.
3. **Knobs:** `pick_projection_weight` (1.0), `pick_projection_min_weeks` (3),
   `pick_projection_max_age_days` (8), `pick_projection_max_round` (1),
   `pick_projection_tag_threshold` (0.10). They go in `database._MODEL_CONFIG_DEFAULTS` and
   `trade_service._DEFAULT_CFG`.
4. **Flag** `picks.projected_slot_value`: `FLAG_KEYS` and `DEFAULT_FLAGS` (False) in
   `backend/feature_flags.py`, `config/features.json` (with a `_comment_`), and
   `backend/tests/fixtures/flags/{release,profiles-on,onboarding-v2}.json`.
5. **`server._league_pick_projection`**: the run read, the gates and the cache. Invalidate the
   cache when a projection run completes (`store.finish`), or rely on the 300 s TTL.
6. **Thread the projection** through `_priced_pick_value` and every caller in §2.3, plus
   `_owned_pick_label` (the tag) at all five label sites, plus Win-Now
   (`win_now_service.py:349`). Extend the AST seam test.
7. **Hashes:** vsn1 (`roster_snapshot.py` plus 3 call sites), the prepared receipt, calibration
   provenance, and `DECK_PIPELINE_VERSION` 23 with a pin.
8. **Replay tool** `backend/eval/pick_projection_replay.py`. The operator runs it; aggregate
   output only.
9. **Docs:** `docs/config-reference.md` (flag and knobs), `docs/glossary.md` ("projected
   slot value"), `docs/cross-client-invariants.md` (a step added to the pick-pricing waterfall
   table near line 1180, and the label tag), `docs/architecture.md` (the forecast now feeds
   pricing), a DECISIONS entry (the D-146 partial reversal), and the README row.

## 12. Decisions for the operator — all approved as recommended, 2026-11-11

Each is yes/no, with the recommendation first. Decisions 3 and 6 were then revised by the
operator the same day (§0: full strength; exact projected slot).

1. **Price next year's firsts by the forecast, reversing the "future picks stay default for
   now" part of D-146 for the next draft only?** Recommend **yes**. It is the ask, and
   2028+ stay generic.
2. **Firsts only, so seconds and later stay generic?** Recommend **yes**. Seconds move by
   about ±300 at most, and snake drafts flip them.
3. **Scale the adjustment by how much of the season has been played (64 % of the full effect
   at week 10, full effect after week 14)?** Recommend **yes**. The forecast's error is
   uncalibrated, and overpaying is the worse mistake.
4. **Apply it to every forecast Sleeper league, assuming the worst Max PF picks first, rather
   than only leagues that confirm that rule?** Recommend **yes**. The forecast already
   assumes it, and reverse-standings leagues order nearly the same way. Saying no means
   building a per-league setting.
5. **Keep a league's total next-year-first value fixed, so early picks gain what late picks
   lose, rather than also letting the average first rise about 19 %?** Recommend **yes**. It
   moves value between teams without inflating picks against players.
6. **Show "· proj. early" / "· proj. late" on the pick's name wherever it appears?** Recommend
   **yes**. It is the "why", and it needs no app build.
7. **Ship it ON once the unit tests and the replay pass, rather than dark?** Recommend
   **yes**. You have a live trade this applies to. Knob `pick_projection_weight = 0` turns it
   off without a deploy.
8. **Start keeping each weekly forecast past 7 days, so the weighting can be calibrated
   against how the season actually ends?** Recommend **yes**. Without it there is nothing to
   test the weighting against in December.

## 13. What the code could not tell us

- **What DP's live `values.csv` publishes today.** The repo pins a July 31 snapshot. If DP
  has already rolled to a 2027 per-slot grid, `market_anchor_season` becomes 2027, the D-161
  floor stops applying to 2027 picks, and G becomes the 2027 tercile. The design handles
  both, but the worked numbers would shift.
- **Whether Sleeper exposes a league's draft-order rule** (Max PF, reverse standings,
  lottery). Nothing in the code reads one. The forecast assumes Max PF.
- **How many leagues have a complete, current v5 forecast right now.** That is a production
  read. NEXT.md says the first v5 runs had not completed as of 2026-11-11.
- **Whether dondags' league is forecastable at all.** It is refused if it has divisions,
  median games or a non-standard bracket.
- **How accurate the forecast's slot distributions are.** No backtest exists. It is possible
  after this season (§10).
