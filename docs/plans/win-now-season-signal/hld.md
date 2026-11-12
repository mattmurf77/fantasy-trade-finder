# Win-now season signal — high-level design

**Date:** 2026-11-11 · **Status:** design, not built · **Baseline:** `origin/main` @ `8b5f076a`

Read with the [PRD](prd.md) (rules and definitions), the [LLD](lld.md) (schemas, algorithms, change
list) and [validation](validation.md). Every claim about existing code cites this worktree; "inferred"
marks what was reasoned and not run.

- [1. One paragraph](#1-one-paragraph)
- [2. What exists today](#2-what-exists-today)
- [3. Data flow](#3-data-flow)
- [4. The season map](#4-the-season-map)
- [5. Who consumes it, and who must not](#5-who-consumes-it-and-who-must-not)
- [6. Labels: what the engine reads](#6-labels-what-the-engine-reads)
- [7. Named components (for a later grades view)](#7-named-components-for-a-later-grades-view)
- [8. Flags, knobs and versions](#8-flags-knobs-and-versions)
- [9. Cost, caching, determinism](#9-cost-caching-determinism)
- [10. Failure modes and fallbacks](#10-failure-modes-and-fallbacks)
- [11. The seam with the rules-first build](#11-the-seam-with-the-rules-first-build)
- [12. What this design does not do](#12-what-this-design-does-not-do)

## 1. One paragraph

Once per trade search the worker reads the league's latest saved weekly projection (already captured
by `backend/league_projections/` for Sleeper leagues) and turns it into a **season map**: projected
points per game for every rostered player over the rest of the regular season. A new bilateral
revision, `owner-v2-bilateral-5` (revision 2 plus a season layer), uses that map for the viewer's
team: "helps you now" stops meaning "is old" and starts meaning "adds points to your starting
lineup". The same numbers produce a **label** per player (win-now piece, cornerstone, rebuild piece)
that the engine reads and the card prints. Prices, fairness and the weight of the user's own rankings
do not change. With no usable projection the revision returns exactly revision 2's cards in exactly
revision 2's order.

## 2. What exists today

Verified in this worktree unless marked.

| Fact | Where |
|---|---|
| The plan weight is per team: All-in 1.0, Contending 0.6, Rebuilding −0.6, Tanking −1.0 | `trade_gen_owner.py:46-47` |
| For All-in / Contending, a player's plan fit is `2 × weight × _now_lean(position, age)`: age and position only | `trade_gen_bilateral.py:141-143`; `trade_service.py:3574-3582` |
| `_now_lean` is already positive for a 26-year-old WR (+0.08) and a 24-year-old RB (+0.07), so most players 24 and over read as "win-now" | curves at `trade_service.py:3439-3459` (computed) |
| The lineup check uses dynasty value × an age multiplier, plus 15% of the best bench player per position. The code says it is "NOT fantasy points" | `trade_gen_owner.py:270-271, 339-364` |
| Revision 2 records its own gap: `starter_evidence.state = "unknown"`, `projected_starter_delta = None`, missing `fresh_scoring_compatible_projections` | `trade_gen_bilateral_candidate.py:80-87` |
| A card qualifies on the user's rankings alone (`personal_board`: focal lean ≥ 0.025). No rule looks at a negative plan gain | `trade_gen_bilateral.py:196-201` |
| Support = 0.45 preference + 0.35 market + 0.20 team plan | `trade_gen_bilateral.py:23-24, 205-208` |
| "Win-now: adds X" fires on `_now_lean ≥ 0.05` | `trade_narrative.py:392, 562-564` |
| The league projection snapshot stores a stat row per rostered player per remaining regular-season week, the league's scoring and slots, and each team's projected lineup | `league_projections/provider.py:214-219, 267-270, 378-379, 484-496, 517-520` |
| Snapshots are per account and league, Sleeper only, refreshed weekly (Tuesday 09:30 Eastern); the last success per league is kept, other runs for 7 days | `league_projections/batch.py:38-47, 210-232`; `store.py:17-29`; `api.py:74`; `config/league_projections.json` |
| The deck quality rules use market value only and drop any card holding a piece under max(450, 25% of the headliner) | `deck_quality.py:26-31, 57-63` |
| The mobile card prints the fit block's lead text verbatim, whatever its code | `mobile/src/api/trades.ts:190-215`; `mobile/src/components/TradeCard.tsx:675-713` |

Inferred, not run: production serves revision 2 (the research's reading of the ledger; the selector
knobs default 0 in code, `database.py:3864-3868`), and production has `league.projections` on through
`FTF_FLAGS` (G-076, `living-memory/GOTCHAS.md:99`), with about six leagues holding a forecast
(D-231, `living-memory/DECISIONS.md:23`).

## 3. Data flow

```
league_projection_runs (latest success for this account + league)
        │  snapshot_json: player_week_inputs, scoring, slots, weeks, captured_at
        ▼
league_projections/season_points.py   (new, pure)
        │  re-scores each stored player-week with the snapshot's own scoring
        ▼
season_value.build_evidence()         (new leaf, pure)
        │  horizon = upcoming whole weeks · points per game · unprojected list
        │  state: usable | unavailable(reason) · digest
        ▼
server._owner_generation_context      (one read per trade job, flag trade.season_signal)
        │  recorded on the owner request (replayable)
        │  passed to the generator only when revision 5 is selected
        ▼
trade_gen_bilateral_season  (owner-v2-bilateral-5 = revision 2 + season layer)
        │  league profile: starter line per position, label per player
        │  viewer's season lineup: who starts, points per week
        │  plan fit ← label table · lineup gain ← points · pool seats ← labels
        │  plan conflict: flag, demote (order only), record
        ▼
frozen proof per card  (season block: numbers, labels, conflict, named components)
        ▼
unchanged downstream: significance → policy → presentment → deck quality → publication
        ▼
trade_narrative.fit_block + season_block  (server templates, read only from the proof)
        ▼
card: label · "Season +2.1 pts/wk · Dynasty cost 3%" · conflict line
```

Nothing above calls a provider. The only new read is one row of `league_projection_runs`.

## 4. The season map

**Source.** The viewer's own account and league's last successful **weekly baseline** run: the one
`league_projections.batch.view` reports (`batch.py:210-232`, the target's `last_success_id`), read
with `store.get` (`store.py:73-77`). Not `store.latest`, which could return a what-if scenario the
user ran with other settings. Its `snapshot_json` holds
`player_week_inputs` (one entry per rostered player per week: stats limited to the league's scoring
keys, supported keys, bye and kickoff facts), `scoring`, `slots` and `captured_at`
(`provider.py:378-379, 517-520`). Per-player points are not stored: only each team's chosen lineup
is. The map is therefore **derived at read time** by scoring the stored rows the way capture did
(`provider.py:400-412`, `core.score`). A parity test proves the derivation: re-optimising each
team-week from the derived points must reproduce the snapshot's stored lineup total.

**Why derive and not store.** It works on snapshots production already holds, changes no table and
no capture code, and cannot disturb the forecast feature.

**"Current" means all of:**

1. a completed run exists for this account and league;
2. it was made by the current projection model (`result.model_version == core.VERSION`), the same
   test the outlook suggestion uses (`recommendation.py:93-94`);
3. it is not past its next weekly slot (`batch.view` state `current`, `batch.py:217-220`);
4. its season, league id and starting slots match the trade job's;
5. at least one whole upcoming week remains in its horizon (below).

**Horizon.** The snapshot covers the current week to the last regular-season week
(`provider.py:214-219`); fantasy playoff weeks are not in it. The map uses the weeks whose first
kickoff is still ahead at the time of the search. A week already in progress is left out for
everyone. Value = **projected points per game** over that horizon (bye weeks are not games).

**Unprojected is unknown, never zero.** A player with no usable row (no forecast, a changed NFL team
per D-231, a waiver add since Tuesday) has no season value. He cannot "start" in the season lineup
and no card makes a season claim about him. If the viewer's own roster holds an unprojected,
healthy player worth 450 or more (the deck's filler floor), the viewer's lineup is unknown and the
request falls back (reason `viewer_unprojected_asset`).

**Injuries.** Unchanged from today: a player listed Out, IR, PUP, Suspended, Doubtful or Inactive
is not a lineup asset (`trade_gen_owner.py:229-232`, `trade_roster.py:21`).

**Empty slot, and the v6 free-agent rule.** The operator's rule for the playoff forecast (model v6,
being built in parallel): an empty starting slot is filled by the best projected free agent for
that slot and week, or 0 if there is none. The season value uses the same rule for the same case:
a team's replacement is its own next man up, and only when its roster has nobody for the slot is it
the best projected free agent (0 if none). So "replacement" here and in the forecast mean the same
thing for an empty slot, and the number is reused, not recomputed.

One gap: as built in its worktree on 2026-11-11, v6 stores the free agents it actually used as
fills (`provider.py` there records them in `player_week_inputs` with `free_agent: true` and in
`projection_coverage.free_agent_fills`), not the best free agent at every position. A trade can
empty a slot that was full when the forecast was saved (you send your only TE). **Ask of the v6
build:** also store the best projected free agent per starting position per week; it already ranks
them (`core.free_agent_fill`). Until it does, such a slot counts 0, which overstates the lineup
cost of emptying a slot and never understates it.

The free-agent level is **not** the baseline for labels: [lld §2](lld.md#2-league-profile-and-labels)
has the measurement.

**Leagues with no supported forecast** (ESPN, MFL, Fleaflicker; Sleeper leagues the forecast
refuses, such as best ball or divisions, `provider.py:199-210`; the off-season): state
`unavailable`. The rule is in §10.

## 5. Who consumes it, and who must not

| Component | Reads the season map? | What changes |
|---|---|---|
| Owner context (`server._owner_generation_context`, `server.py:21993`) | builds and records it | one new key, as `partner_activity` is attached today (`server.py:22096-22100`) |
| Revision 5 search, viewer team with an All-in or Contending outlook | **yes** | lineup in points; plan fit from the label table; pool seats; conflict rule |
| Revision 5 search, viewer team Rebuilding or Tanking | labels and points | conflict rule (flag, demote, state); the shed term (amended 2026-11-11); the re-scored team plan's plan fit from the label table (amended 2026-11-12, `season_viewer_label_fit`). Order only: gates, pools and inventory unchanged |
| Revision 5 search, viewer "Not sure" | no | nothing |
| Revision 5 search, the other team | no in stage 1; label table in stage 2 (`season_partner_matching`) | seller–buyer matching, graded separately. Stage 2 is partner matching only from 2026-11-12 |
| Revision 2's `starter_evidence` field | filled by revision 5 | `state: "projected"`, `projected_starter_delta` in points per week |
| Lane (`window` / `value`, `trade_gen_bilateral.py:507`) | indirectly | it already keys on plan gain, which is now season-based for win-now viewers |
| Fit block and the new season block (`trade_narrative.py`) | reads the proof only | a "Win-now" claim requires the new definition |
| `trade_policy.py` (market floor, live in production) | **must not** | the floor is consensus value; a season number never loosens or tightens it |
| `deck_quality` rules, `trade_significance`, and the future `deck_rules.py` | **must not** in this plan | they stay functions of terms and market values, which is what lets rules-first run them before ranking |
| Package pricing, fairness score, `age_pref_value` | **must not** | prices stay on dynasty market value |
| Presentment (`trade_bilateral_presentment.py`) | no | it reads the support scores revision 5 writes, as it does for revision 4 |
| Win Now (`win_now_service.py`) | no | separate feature, untouched |
| Legacy v2/v3, `trade_gen_v2`, owner v1, revisions 1–4 | no | untouched and byte-identical |

## 6. Labels: what the engine reads

The operator's decision: labels are an engine input, defined precisely, derived from the engine's
own numbers, graded before they touch a served deck. The definitions are in the
[PRD §4](prd.md#4-labels). The design question left to this plan is whether the engine reads the
label or the number under it.

**Decision: the engine reads the label where the question is "what kind of asset is this for this
team", and the number where the question is "how much".**

| Engine decision | Reads | Why |
|---|---|---|
| Plan fit of one asset for one team | the **label** (a small table) | The continuous version tried in the prototype sat at its floor for every non-starter and reached its cap for a starter unless his dynasty price was several times his season worth (seen in the cases run, not counted). It was already close to a label, with a made-up scale. A table is readable, gradeable and stable |
| Which assets get a seat in the candidate pools | the **label** | a guaranteed seat is a yes/no |
| Seller–buyer matches (stage 2) | the **label** | "a rebuilder's win-now piece that would start for a contender" is a label statement |
| Plan conflict flag | the **label** plus one number (points per week lost) | the flag is itself printed |
| How much the package changes the lineup | the **number** (points per week) | a label cannot say +3.2. The number is printed |
| What the trade costs in dynasty terms | the **number** | printed |

**Cannot disagree, by construction.** The search computes one record per asset and team (points per
game, starts for this team or not, lineup gain, league label). Scoring reads that record. The same
record is frozen into the card's proof. The card copy is composed from the proof and nothing else.
A test asserts, for every card of a generated deck, that the label the copy would print is the label
the plan-fit table was read with.

**Does a label improve trade quality?** Plainly: a label holds less information than the numbers it
is cut from, so it cannot make the engine smarter than the numbers can. What it adds is that a
person can check it. The operator can look at 60 labels and say which are wrong; nobody can do that
with a column of decimals. Wrong labels mean wrong numbers, and the grading step finds that before a
deck is affected. Whether labels beat the bare numbers as the plan-fit input is measured, not
assumed: validation runs both arms on the same requests ([validation §3](validation.md)).

## 7. Named components (for a later grades view)

A separate assessment (`docs/plans/card-logic-grades/assessment.md`, in progress) asks whether cards
should show a 1–10 grade per input and be ranked by a weighted average. This design is compatible
with either answer because it adds no hidden term.

- The ranking score stays `0.45 × preference + 0.35 × market + 0.20 × team plan`, each in 0–1,
  each computed without reading the others (`trade_gen_bilateral.py:205-208`).
- Revision 5 changes only what feeds **team plan** for the viewer, and records the two parts
  separately in the proof: `plan_fit` (−1 to +1, from labels) and `lineup_gain` (−1 to +1, from
  points). `team_plan = 0.5 + 0.5 × clip(plan_fit + lineup_gain)` as today.
- The conflict demotion is a separate, recorded adjustment (`−0.10` or `0`), applied after
  eligibility the way revision 4 applies its demotions (`trade_gen_bilateral_r4.py:95-102, 182-186`).
  The unadjusted score is kept beside it. It is a subtraction, not a sort class, so the page
  search's bounds stay valid (the assessment's §5.3 reaches the same conclusion).
- **One conflict predicate.** `season_value.plan_conflict(...)` decides it once per card; the
  result is frozen in the proof (`season_signal.conflict`). The demotion, the card sentence and any
  later tooltip line all read that record. None re-derives it.
- Raw quantities sit beside the bounded ones: `season_pts_week_delta` (points per week),
  `dynasty_cost_pct` (percent of roster value), and per asset `label`, `starts_for_you`,
  `pts_per_game`.

So a grades view could show, without recomputing anything: User Rankings ← preference, Market Value
← market, Team Outlook ← `plan_fit`, a fourth row "This season" ← `lineup_gain`, and a "Plan
conflict" line. The assessment (read 2026-11-11) recommends exactly this split and asks the win-now
revision to record the two parts separately; this design does. Its composer keys wording on
`generator_version`, so revision 2 cards keep "by age and position" and revision 5 cards say what
revision 5 used. If user-set weights ever happen, the weights are the three numbers above; nothing
in the season layer assumes their values.

## 8. Flags, knobs and versions

| Name | Kind | Default | Effect |
|---|---|---|---|
| `trade.season_signal` | flag | false | the worker builds and records season evidence once per owner job. Off: no read, no key, bytes unchanged |
| `owner_bilateral_revision_5_enabled` | `model_config` | 0 | exactly 1 selects revision 5 (when the bilateral and revision selectors are on); wins over the revision 3 and 4 selectors |
| `season_conflict_demotion` | `model_config` | 0.10 | support taken from a plan-conflict card (order only). 0 = flag and state, no push-down |
| `season_partner_matching` | `model_config` | 0 | 1 = stage 2, partner matching: label table on every team's plan fit |
| `season_shed_weight_tanking` / `_rebuilding` | `model_config` | 1.0 / 0.5 | the shed term's strength (amended 2026-11-11) |
| `season_viewer_label_fit` | `model_config` | 1 | exactly 1: a Rebuilding / Tanking viewer's re-scored team plan reads the label table, stage 2 off (amended 2026-11-12); order only |
| `grading.season_round` | flag | false | Calibration round `outlook-v2-v5-1` (revision 2 beside revision 5) |

Code constants, versioned together as `SEASON_RULES_VERSION = "season-signal-1"` and
`LABEL_RULES_VERSION = "season-labels-1"`: points-to-value rate 400, start margin 0.5 points, future
floor 1500, conflict thresholds 0.5 (All-in) and 1.0 (Contending) points per week. These are
starting values to grade, not measured ones. A change is a new rules version.

**Built dark and compared.** With everything at default nothing runs. Stage A: flag on, selector 0:
evidence is recorded with each request and one log line says what would have applied; decks are
revision 2's. Stage B: the Calibration round and the label review. Stage C: selector 1.

**Engine hash and pipeline digest.** `trade_gen_bilateral_season.py` is covered by the existing
`trade_gen_*.py` pattern in `_ENGINE_CODE_MODULES` (`server.py:4739-4756`); `season_value.py` and
`league_projections/season_points.py` are added to it. `_owner_generation_context`,
`_owner_selected_assignment`, `_run_trade_job` and `trade_card_to_dict` are deck-pipeline functions
(`server.py:4600-4648`), so `DECK_PIPELINE_VERSION` (21 on main, `server.py:4584`; the rules-first build
takes 22) moves once with a new pinned row, the next free number at merge. Stored first pages rebuild once. The request hash includes the evidence digest, so a
new weekly forecast is a new request, never a stale page.

## 9. Cost, caching, determinism

- **Read:** one row; the snapshot is roughly 12 teams × 28 players × up to 14 weeks of small stat
  rows (inferred: 1–3 MB of JSON). Parsing and scoring it is tens of milliseconds. The built
  evidence is cached in process by `run_id` (immutable once written), a few entries, behind a lock.
- **Search:** no measurable change. Prototype, same machine, six seeds: 3.28 s → 3.21 s per full
  solve for an All-in viewer ([validation §2](validation.md)). The season lineup is the same
  assignment the engine already runs, on a different number.
- **Deterministic:** evidence is a pure function of (snapshot, as-of time, rosters). The as-of time
  only decides which weeks are still ahead; it is recorded. Same inputs, same deck. No randomness,
  no provider call, no wall clock inside the generator.
- **Memory:** the evidence handed to the generator is one small dict per player.

## 10. Failure modes and fallbacks

**The rule when there is no usable projection** (off-season, unsupported league, stale or missing
run, incomplete viewer lineup, any read error): the request behaves as it does today. Under
revision 5 that means the same cards, same terms and same order as revision 2 for that request,
proven by test; only the version stamp differs. The card shows no season line, no label and no
conflict line, and "Win-now: adds X" keeps today's age rule for that request.

| Situation | State and reason | What the user gets |
|---|---|---|
| Flag off | no evidence | today |
| ESPN / MFL / Fleaflicker league | `unavailable: platform_unsupported` | today |
| Sleeper league the forecast refuses (best ball, divisions, IDP gaps) | `unavailable: no_forecast` | today |
| Off-season, or after the last regular week has kicked off | `unavailable: no_upcoming_week` | today |
| Run older than its weekly slot, or made by an older model | `unavailable: stale` / `old_model` | today |
| Viewer holds an unprojected player worth ≥ 450 | `unavailable: viewer_unprojected_asset` | today |
| Slots or league changed since capture | `unavailable: league_changed` | today |
| Snapshot unreadable, scoring error, any exception | `unavailable: read_failed`, logged | today |
| An incoming player is unprojected | usable; that player gets today's age fit and no season claim | season card without a claim about him |
| Revision 5 raises | the owner job fails as any generator failure does today; kill = selector 0 | — |

Kill switches, deploy-free: `owner_bilateral_revision_5_enabled = 0` (engine back to revision 2);
`trade.season_signal` false (no read); `season_conflict_demotion = 0` (no push-down).

## 11. The seam with the rules-first build

Rules-first (`docs/plans/realtime-trade-engine/fast-deck-v2-design.md` on its branch, flag
`deck.rules_first`) moves the per-card deck rules ahead of ranking and builds the whole admitted
inventory with the page-first search. It is being built now. The two builds are independent by
design and meet in four named places.

**Why they are orthogonal.** Rules-first decides *which packages may be shown*, from the package's
terms and request inputs the worker already holds (market values, positions, rosters, slots). The
season signal decides *how good an admitted package is for the viewer* and what the card says.
Neither needs the other's output.

**What each side must not touch.**

| Rules-first must not | Season signal must not |
|---|---|
| read `season_evidence` or any projection in `DeckRules` | change `deck_quality` predicates, `trade_significance`, or `deck_rules.py` |
| change `_owner`, `_plan_asset`, `_lineup` or the support formula in any generator | edit `trade_first_page.py` or `trade_fast_deck.py` before rules-first has merged |
| change `_owner_generation_context` beyond reading what it returns | edit the body of `_gen_owner` or the `DeckRules` construction in `_run_trade_job` |
| assume the generator module is one of two names without a registry | change `_generate_with_search` or either ranker |

**State of the rules-first build, read from its worktree on 2026-11-11 (uncommitted, may move):**
`backend/deck_rules.py` exists (`VERSION = "deck-rules-1"`); `trade_fast_deck.py` has
`supported(generate)`, `gated_full(...)` and `serve(generate, context, rules, ...)`;
`_PARITY_TESTED` is still the two module names; `DECK_PIPELINE_VERSION` is 22 with its pin;
`backend/eval/served_deck_replay.py` exists; ADR-030 is its decision record. The points below are
written against that.

**The four meeting points.**

1. **`DECK_PIPELINE_VERSION` and its pin row** (`server.py:4584, 4707-4732`). Both builds bump it.
   Rules-first holds 22. Whoever merges second rebases, takes the next number and adds its own row.
   Rows are append-only, so this is a two-line conflict.
2. **`_run_trade_job`.** Rules-first edits `_gen_owner` (`server.py:13371-13414`). The season build
   needs one line elsewhere in the same function: the presentment call passes the generator version
   through a hard-coded tuple of revisions 3 and 4 (`server.py:14190`), which must admit revision 5.
   The season build makes that line read the version from `bakeoff_runner` so no later revision
   edits it again.
3. **Which generators rules-first supports.** `trade_fast_deck._PARITY_TESTED` names two modules
   (`trade_fast_deck.py:28` on main), and `supported(generate)` in the rules-first build tests
   against it. Revision 5 is a new module, so on the day rules-first serves, a revision 5 request is
   "unsupported" and takes today's path: full solve, rules after ranking. That is correct but slow.
   **Ask of the rules-first build:** nothing to change now; keep the supported set a named tuple a
   later revision can join, and keep `gated_full` free of anything specific to revision 2 beyond the
   module protocol (`_Search` / `_GenerationSearch`, `VERSION`, `_rank`).
4. **The join (a season work item that lands after rules-first).** Revision 5 becomes a supported
   generator by: (a) its own page-first parity suite; (b) the page search asking the search for a
   team's lineup asset value instead of reading `_lineup_assets` directly
   (`trade_first_page.py:406-414`), because revision 5's lineup values differ by team; (c) the
   lineup memo accepting a search that overrides `_lineup` (`trade_first_page.py:193-196` skips one
   today). The bounds stay valid for the season layer because it changes only per-asset inputs the
   bounds already read from the search (`_plan_asset`, `_lineup`, `_need_utility`,
   `trade_first_page.py:28-30, 256-257, 331-336`), keeps the support formula and the ranker, and
   applies only penalties after eligibility. That is the argument; the parity suite is the proof.

**Order of landing.** Either can merge first. Stage A and B of the season build (capture, replay,
label review, Calibration round) need nothing from rules-first: Calibration and replay run full
solves by design. Serving revision 5 (stage C) wants the join so it serves at rules-first speed.

**If rules-first is delayed or turned off.** Revision 5 serves on today's full solve, exactly as
slow as revision 2 is today (interactive jobs have run the full solve since D-232). Nothing in the
season build depends on `deck.rules_first` being on. If rules-first is on and the join has not
landed, revision 5 requests fall back to the full solve and are logged with that reason; the
operator can choose to wait.

**If revision 4 becomes the serving engine first.** The season layer is a mixin over a search
class. Revision 5 applies it to revision 2's search. Applying it to revision 4's search is one class
line and a new version string, with its own parity run.

## 12. What this design does not do

- No off-season signal, no redraft rank, no paid source (deferred by the operator).
- No playoff-week weighting: the saved forecast stops at the last regular-season week.
- No per-week lineup solve: one assignment on points per game. Byes are not modelled.
- No merge with Win Now, no simulation, no odds.
- No change to prices, fairness, the market floor, deck quality rules or significance.
- No new table, no new route for users, no new client event.
- The deck's filler rule still removes any card holding a player under 450 in dynasty value, so a
  cheap veteran who would start cannot appear on an owner card. Measured: 4 such starters in the
  fixture league. Changing that is a rule change inside rules-first's territory, listed in
  [open questions](open-questions.md).
