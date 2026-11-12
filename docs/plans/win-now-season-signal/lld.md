# Win-now season signal — low-level design

**Date:** 2026-11-11 · **Status:** design, not built · **Baseline:** `origin/main` @ `8b5f076a`

Builders: this is the contract. Where it says "as revision 4 does", read that code first; the
pattern is deliberate. Constants marked *starting value* are to be graded, not defended.

- [1. Season evidence](#1-season-evidence)
- [2. League profile and labels](#2-league-profile-and-labels)
- [3. Revision 5](#3-revision-5)
- [4. Proof fields](#4-proof-fields)
- [5. Card payload and copy](#5-card-payload-and-copy)
- [6. Worker wiring](#6-worker-wiring)
- [7. Calibration round](#7-calibration-round)
- [8. Operator tools](#8-operator-tools)
- [9. Module-by-module change list](#9-module-by-module-change-list)
- [10. Invariants and their tests](#10-invariants-and-their-tests)

## 1. Season evidence

### 1.1 Per-player points from a saved snapshot

New pure module `backend/league_projections/season_points.py`.

```
player_points(snapshot) -> {week:int -> {player_id:str -> Decimal | None}}
```

- Input: a parsed `league_projection_runs.snapshot_json`. Reads `player_week_inputs`, `scoring`,
  `slots` (`provider.py:517-520`).
- For each entry, score `input.stats` exactly as capture's best-available branch does
  (`provider.py:400-406`): `active = normalize_scoring_for_slots(scoring, slots)`;
  `covered = {k: v for k in active if k in stats and k in supported_keys}`; no covered key with a
  non-zero coefficient → `None`; else `core.score(stats, covered, supported_keys)`.
- `None` (unknown) when: `projection_status == "unpriced"`, `availability` is not 1, the row is a
  completed game, or nothing is covered. A verified bye is recorded as a bye, not a number.
- Model v6 snapshots (the free-agent fill build) add entries marked `free_agent: true`. They are
  never a rostered player's points; they feed `free_agent_level` only.
- No I/O. Raises `core.Unavailable` on a malformed snapshot; the caller turns that into
  `unavailable: read_failed`.

**Parity check (a test, and a function the admin tool can call):** for every team-week with no
locked starters and no hypothetical fill, `core.optimize(slots, pool_from_derived_points,
empty_policy=...)["points"]` equals the stored `weeks[].teams[rid].actual.points`
(`provider.py:425, 484`). If capture's scoring ever drifts from this module, this fails.

### 1.2 The evidence object

New leaf `backend/season_value.py` (no database, flag, server or provider imports).

```
build_evidence(snapshot, *, as_of, league_id, slots, platform) -> dict
unavailable(reason) -> dict
```

```json
{
  "schema": "season-evidence-1",
  "state": "usable",
  "reason": null,
  "source": "league_projections",
  "run_id": "…", "model_version": "projected-lineup-universal-sd-v5",
  "captured_at": "2026-11-10T14:30:00+00:00",
  "as_of": "2026-11-11T18:00:00+00:00",
  "season": 2026, "weeks": [11, 12, 13, 14],
  "slots": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "FLEX"],
  "players": {"<id>": {"ppg": 13.14, "games": 4}},
  "unprojected": ["<id>", "…"],
  "free_agent_level": {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0},
  "rules_version": "season-signal-1",
  "digest": "<sha256 of everything above except as_of>"
}
```

- **Horizon:** snapshot weeks whose earliest `kickoff_at` across all rows is later than `as_of`.
  Empty → `unavailable: no_upcoming_week`.
- **`ppg`:** mean of a player's non-`None`, non-bye weekly points over the horizon, rounded to 2
  decimals (floats from here on; Decimal stays inside `season_points`). `games` = how many weeks
  that mean covers. A player with zero such weeks goes in `unprojected`.
- **`free_agent_level`:** per position, the best projected free agent's points per game over the
  horizon, from the snapshot's free-agent entries; zero for a position with none (and for every
  position under v5). Used only to fill an empty slot. v6 as first built stores only the free
  agents it used; [hld §4](hld.md#4-the-season-map) has the ask to store the best per position.
- **`as_of`** is recorded and excluded from the digest, so two searches in the same horizon share a
  request hash.
- Reasons for `unavailable`: `platform_unsupported`, `no_forecast`, `old_model`, `stale`,
  `league_changed` (slots or league id differ), `no_upcoming_week`, `viewer_unprojected_asset`
  (set by the caller, §6), `read_failed`.

## 2. League profile and labels

`season_value.league_profile(evidence, *, rosters, position, market, age, slots, inactive) -> dict`,
computed once per search. `LABEL_RULES_VERSION = "season-labels-1"`.

1. **Each team's season lineup:** `trade_roster.assign(slots, assets)` over that roster's projected,
   available players with `Asset.value = ppg` (the same assignment the engine uses today,
   `trade_gen_owner.py:343-350`). Starters only; no bench credit.
2. **Starter count per position** `n[pos]` = players at `pos` in the union of all teams' lineups.
3. **Starter line** `line[pos]` = the `n[pos]`-th highest `ppg` among rostered players at `pos`.
   `margin[pos] = max(0.5, 0.05 × line[pos])`. *(starting values)*
4. **Per player:**
   - `startable = ppg ≥ line + margin`; `not_startable = ppg ≤ line − margin`; else `borderline`.
   - `future = max(0, market − RATE × max(0, ppg − line))`, `RATE = 400` *(starting value)*.
   - `past_cliff = age > 25 and age_now_mult(pos, age) < age_now_mult(pos, 25)`: RB 27+, WR 30+,
     TE 32+, never a QB (`trade_service.py:3439-3451`). Not `_now_lean`: that is already positive at
     24–26 and would call Justin Jefferson past it.
   - `young = age ≤ _YOUNG[pos]` (`trade_gen_bilateral.py:26`).
5. **Label:**

   | Condition | `label` |
   |---|---|
   | unprojected, or borderline | `None` |
   | startable and (`future < 1500` or `past_cliff`) | `"win_now"` |
   | startable otherwise | `"cornerstone"` |
   | not startable, `market ≥ 450`, young | `"rebuild"` |
   | not startable otherwise | `"depth"` (never printed) |

   Picks: `label = "rebuild"`, `future = market`. `FUTURE_FLOOR = 1500` *(starting value)*;
   450 is `deck_quality.FILLER_FLOOR` (`deck_quality.py:27`), imported, not copied.

Returned: `{"line", "margin", "starters": {pos: n}, "players": {id: {"label", "future",
"startable"}}, "rules_version"}`.

**Why the starter line and not the free-agent level as the baseline for `future`.** Measured on the
fixture league: free agents project far below the last starter (RB 5.1 a game against a line of
8.8), so every starter's price looks "explained by this season" and 68 players come out win-now
against 16 cornerstones, Josh Allen and Brock Bowers among the win-now pieces. With the starter
line: 36 and 48, and the same list a manager would write. The free-agent level is the right
baseline for an empty slot (§1.2), not for a label.

## 3. Revision 5

New module `backend/trade_gen_bilateral_season.py`. `VERSION = BILATERAL_GENERATOR_VERSION =
"owner-v2-bilateral-5"`, `ARM` unchanged (`owner_v2_bilateral`).

```python
class SeasonLayer:            # a mixin; holds no revision-2 logic of its own
class _Search(SeasonLayer, previous._Search)            # previous = trade_gen_bilateral_candidate
class _GenerationSearch(_Search)                        # as revision 4, lines 196-200
def generate_bilateral_trades(**kwargs)
def evaluate_bilateral_trades(cards, **kwargs)
```

`__init__(self, *, season_evidence=None, **kwargs)`. Absent, or `state != "usable"`: every override
below calls `super()` and returns its value untouched.

### 3.1 Which teams are season-scored

`_season_scored(team)`: evidence usable **and** `team["outlook"] in ("championship", "contender")`
**and** (`team["uid"] == self.user_id` **or** `config["season_partner_matching"] == 1`). The
outlook is the one the engine already resolved (`trade_gen_owner.py:297-306`), declared or roster
read.

**Amended 2026-11-11, operator direction: the shed direction.** `_season_shed(team)`: evidence
usable **and** `team["outlook"] in ("rebuilder", "jets")` **and** (viewer **or**
`season_partner_matching == 1`) **and** not native bounds; declared or roster read. Such a team is
scored as a **ranking term only**: `_lineup`, `_plan_asset` (stage 1), `_pool`, `utility`,
`team_plan_gain`, the intent path and every gate stay revision 2's, so the inventory and terms are
revision 2's. After eligibility (`_season_signal`, where the demotion already sits):

```
d          = season lineup after − before (points a week, unrounded; §3.2's _season_total)
lineup_gain = clip(−w × RATE × d / gross_market)          # w: season_shed_weight_tanking 1.0,
                                                          #    season_shed_weight_rebuilding 0.5
team_plan  = clip(.5 + .5 × clip(plan_fit + lineup_gain), 0, 1)   # plan_fit: revision 2's plan shift
support   += 0.20 × (team_plan − revision 2's team_plan)         # 0.20 = the team-plan weight
```

For an All-in team `clip(4 × need_utility)` equals `clip(RATE × d / gross_market)` (weight 0.25,
season units), so at `w = 1` a point shed by a Tanking team moves `lineup_gain` exactly as a point
gained moves it for an All-in team. The replaced lineup part is revision 2's need term (0 for
Tanking, weight 0.05 for Rebuilding). The support move is recorded as
`support.season_adjustments.season_lineup_shed` beside `season_unadjusted_score`, and
`support.components.team_plan` carries the re-scored value. In stage 2 a Rebuilding / Tanking
partner's support moves the same way on its own side.

### 3.2 Season lineup

Built once in `__init__` after `owner._Search.__init__` has filled `_lineup_assets` and before
teams are built (hook: override `_team`, build on first call).

- `_season_assets[pid] = Asset(pid, frozenset([pos]), RATE × ppg)` for every player in
  `_lineup_assets` (so today's injury rule holds, `trade_gen_owner.py:229-232`) that has a `ppg`.
- `_lineup(roster, team)`: not season-scored → `super()`. Season-scored → `assign(team["slots"],
  usable season assets)`, sum **starters only** by position, in `RATE × ppg` units. An empty slot
  contributes `RATE × free_agent_level[first eligible position]`.
- Native position-range teams (`team["native_bounds"]`, Calibration's MFL path): not season-scored
  in this slice; they keep `super()`.
- `_need_utility` is **not** overridden. Its weight stays 0.25 for these teams
  (`trade_gen_owner.py:273-275`); only the deltas it is given change unit.
- `season_gain(team, pid)` = `(lineup(roster ∪ {pid}) − lineup(roster ∖ {pid})) / RATE`, points per
  week, memoised per `(team, pid)`.
- `starts_for(team, pid)` = `season_gain ≥ 0.5`. *(starting value)*

`RATE` turns points into the value units the need term already divides by the package's gross
market value. At 400 a 3-point-a-week upgrade weighs like 1,200 of usable value, about a
second-round pick. The prototype used 500 and the need term saturated on most real upgrades; the
replay reports how often it clips so the rate can be set.

### 3.3 Plan fit from the label table

`_plan_asset(team, pid)`:

- Not season-scored and `season_partner_matching != 1` → `super()` (revision 2's age rule and
  rebuild rule, unchanged).
- Pick → `−0.25` lean (today's value, `trade_gen_bilateral.py:142`).
- No `ppg` → `super()` for that asset (age rule), and the asset is marked `season: unknown`.
- Season-scored team:

  | Asset, for this team | lean |
  |---|---|
  | starts for the team, label `win_now` or `cornerstone` | `+0.40` |
  | starts for the team, other | `+0.25` |
  | would not start for the team | `−0.25` |

  `fit = clip(2 × _WINDOW_WEIGHT[outlook] × lean)`, the existing formula
  (`trade_gen_bilateral.py:143`): All-in ±0.8/+0.5/−0.5, Contending at 0.6 of that.
  `+0.40` and `−0.25` are the top and bottom of today's age lean, so the plan term keeps its range.

- **Stage 2 only** (`season_partner_matching == 1`), Rebuilding or Tanking team: pick `1.0`;
  `rebuild` `+0.7`; `cornerstone` `+0.45` when young, else `+0.2`; `win_now` `−0.8` (RB) or `−0.45`;
  `depth` or `None` → `super()`; all × `1.0` (Tanking) or `0.6` (Rebuilding). Revision 2's
  board-led refinements for young WR/TE/QB and elite RBs (`trade_gen_bilateral_candidate.py:43-51`)
  are applied on top, unchanged. *(starting values; stage 2 has its own replay)*

### 3.4 Candidate seats

`_pool(team, other)` (`trade_gen_owner.py:601-621`): when `other` is the season-scored viewer (the
receive pool), add one more list to the interleave: `team`'s players that `starts_for(viewer)`,
ordered by `season_gain` descending then id. When `team` is the season-scored viewer (the give
pool): add the viewer's picks and non-starters, by market value descending then id. Pool size and
every other list are unchanged. Deterministic.

### 3.5 Plan conflict

In `_owner(team, give, receive)` for the **viewer** only, after `super()`:

```
season = {"state": "projected", "delta_pts_week": d, "before": …, "after": …,
          "incoming_starters": [...], "outgoing_starters": [...]}
```

`conflict` is decided in `_decision(card, data, reason, eligible)`, before `super()`, exactly where
revision 4 applies its rules (`trade_gen_bilateral_r4.py:182-186`):

- preconditions: `eligible`; viewer `outlook_source == "declared"`; evidence usable; the card has no
  pinned asset (`self.give_pins`, `self.recv_pins`) and no `opponent_id`.
- **All-in / Contending:** `d ≤ −0.5` / `d ≤ −1.0`.
- **Rebuilding / Tanking:** the max-market received asset has label `win_now`; at least one given
  asset is a pick or has label `rebuild` or `cornerstone`; `Σ future(receive) < Σ future(give)`.
  *Amended 2026-11-11, operator direction:* checked second; first, the points mirror
  `d ≥ +0.5` (Tanking) / `d ≥ +1.0` (Rebuilding) (`season_value.CONFLICT_ADD`, beside
  `CONFLICT_DROP`). `plan_conflict` stays the one predicate and returns the trigger
  (`"points"` / `"label"`) or `False`; the proof records it as `conflict.trigger`.
- `kind`: `"board"` when `intent.path == "personal_board"`. When the path is `"declared_intent"`
  and `intent.declared_match` is true: `"target"` if the buy target is on the viewer's target list,
  else `"position"`. Any other case (including a card that qualified only because the plan itself
  scored it well) → no conflict recorded.
- `named`: the buy target when its viewer lean ≥ the sell candidate's negated lean, else the sell
  candidate (`intent.buy_target`, `intent.sell_candidate`, `_features[...]["direction"]`).
- **Demotion:** `kind == "board"` and `config["season_conflict_demotion"] > 0` → both sides'
  support moved by `−demotion` with revision 4's `_shift` (`trade_gen_bilateral_r4.py:95-102`:
  keeps the unadjusted score, records the adjustment). Both sides, as revision 4 does, so the weaker
  score falls by the full amount and presentment, which reads both, cannot undo it.

`utility` and eligibility are computed before this point (`trade_gen_bilateral.py:244`), so the
penalty cannot reject a card.

### 3.6 Ranker

Revision 2's `_rank` with `version=VERSION` (as revision 4 passes its own,
`trade_gen_bilateral_r4.py:261, 284`). No new ordering key.

## 4. Proof fields

Added to the frozen proof (private; impressions already store it). Present only under revision 5.

```json
"season_signal": {
  "rules_version": "season-signal-1", "label_rules_version": "season-labels-1",
  "evidence": {"state": "usable", "reason": null, "digest": "…", "run_id": "…",
               "captured_at": "…", "weeks": [11, 12, 13, 14]},
  "viewer": {"scored": true, "delta_pts_week": -1.82, "lineup_before": 118.4, "lineup_after": 116.6,
             "incoming_starters": [], "outgoing_starters": ["<id>"],
             "dynasty_cost_pct": 0.0, "roster_market_total": 61250.0},
  "assets": [{"id": "<id>", "ppg": 11.51, "label": "win_now", "future": 560.0,
              "starts_for_viewer": true, "gain_for_viewer": 1.82, "plan_lean": 0.40}],
  "conflict": {"fired": true, "plan": "championship", "kind": "board", "named": "<id>",
               "threshold": 0.5, "demotion": 0.10},
  "components": {"plan_fit": -0.65, "lineup_gain": -0.32, "team_plan": 0.0,
                 "ranges": {"plan_fit": [-1, 1], "lineup_gain": [-1, 1], "team_plan": [0, 1]}}
}
```

- *Amended 2026-11-11, operator direction:* `viewer.season_direction` (`"add"` for All-in /
  Contending, `"shed"` for Rebuilding / Tanking) whenever the viewer is scored, so copy and tooling
  never infer the direction from the outlook. A shed-scored viewer carries the same `viewer`
  season facts as a win-now one; `components.lineup_gain` is the shed term as scored (positive
  when points are shed), `components.team_plan` the re-scored team plan; `assets[].plan_lean` is
  `null` (the label table is not read for it); `conflict.trigger` names the rule that fired;
  `conflict.threshold` is `CONFLICT_ADD[plan]` for these plans.
- `viewer.starter_evidence` (revision 2's field, `trade_gen_bilateral_candidate.py:83-87`) becomes
  `{"state": "projected", "projected_starter_delta": d, "proxy": "season_points_per_game_v1", …}`
  when scored, and stays as revision 2 writes it otherwise. The report's `starter_evidence` string
  becomes `"projected_points_viewer"` or stays.
- `lineup_proxy` reads `"season_points_per_game_v1"` for a scored side.
- Evidence with `state == "unavailable"`: `season_signal = {"evidence": {state, reason}}` only.

## 5. Card payload and copy

### 5.1 Fit block (installed builds)

`trade_narrative.fit_block` gains a branch at the top of the You side when
`proof["season_signal"]["viewer"]["scored"]` or a conflict fired. New templates (lead codes are free
text to the app: it prints `lead.text`, `mobile/src/api/trades.ts:197-202`):

| Code | Text |
|---|---|
| `conflict.you` | `Away from {plan}: {delta} pts/wk` · Rebuild/Tank: `Away from {plan}: adds a win-now piece` |
| `season_win_now.you` | `Win-now: {name} starts, +{x.x}/wk` |
| `season_starter.you` | `Starts for you: {name}, +{x.x}/wk` |
| `season_shed.you` | *Amended 2026-11-11, operator direction.* `{plan}: {-x.x} pts/wk, adds {asset}` (`Rebuilding`, `Tanking`, or `Rebuild-leaning` for a roster read): a `shed` viewer's card that sheds ≥ 0.5 a week; `{asset}` the most valuable incoming pick or projected `rebuild` / `cornerstone` |

*Amended 2026-11-11:* a Rebuilding / Tanking conflict's lead is `conflict.you` with the signed
delta (`Away from Tanking: +2.1 pts/wk`) when `conflict.trigger == "points"`, and `conflict_plan.you`
(`Away from Tanking: adds a win-now piece`) when it is `"label"`. A shed-scored viewer gets the
season line and the Them side's label rule like a win-now viewer; with no season lead, today's
plan lead (`Rebuilding: adds …`). The copy reads `viewer.season_direction`; a scored proof without
it composes nothing.

`_fit_plan`'s win-now branch (`trade_narrative.py:561-564`) and `_fit_need`
(`trade_narrative.py:585-611`) are skipped for a side whose proof is season-scored. For the Them
side with usable evidence, `plan_win_now.them` additionally requires the named player's label to be
`win_now` or `cornerstone` and `starts_for` that team, computed from public rosters and the season
map. `FIT_TMPL_VERSION` stays `"fit-2"` (`trade_narrative.py:382`): shape unchanged.

### 5.2 Season block (next build)

`trade_card_to_dict` adds, beside `fit_block` and under the same conditions plus
`is_enabled("trade.season_signal")`:

```json
"season_block": {
  "v": "season-1",
  "line": "Season +2.1 pts/wk · Dynasty cost 3%",
  "season_pts_week": 2.1, "dynasty_pct": 3.0, "dynasty_dir": "cost",
  "weeks": 4, "as_of": "2026-11-10",
  "labels": [{"id": "<id>", "label": "win_now", "text": "Win-now piece", "starts_for_you": true}],
  "conflict": {"code": "conflict.board.above", "text": "You rank … above market, but this moves away from All-in"}
}
```

Absent when there is nothing to show. `labels` lists only printed labels. Text is composed by
`trade_narrative.season_block(proof, card, players)`: pure, returns `None` on any malformed input,
as `fit_block` does (`trade_narrative.py:706-775`). `dynasty_pct = max(0, |give − receive|) /
roster_market_total × 100` with the proof's own `market.give` / `market.receive`.

### 5.3 Mobile

`mobile/src/shared/types.ts`: optional `season_block`. `mobile/src/api/trades.ts`: validate
(`v === 'season-1'`, strings and finite numbers), drop on mismatch. `TradeCard.tsx`: under the You
team in the fit block, one `ChalklineText` line for `line`, one for `conflict.text` (two lines
allowed); label tags as `type.label` text beside the asset name. No colour beyond existing tokens,
no icon. Hidden on an edited card, as the fit block is (`TradeCard.tsx:286`). `testID`s:
`trade-card.season-line`, `trade-card.season-conflict`, `trade-card.asset-label.<id>`.

## 6. Worker wiring

All in `backend/server.py`.

- **`_season_evidence(user_id, league_id, platform, slots)`** (new helper, not a route): returns the
  evidence dict. `platform != "sleeper"` → `unavailable`. Reads `league_projections.batch.view`
  for state and `store.get(run_id, …)` for the snapshot; checks model version and `current`; calls
  `season_value.build_evidence`. LRU of 8 by `(run_id, horizon weeks)` behind a lock. Any exception
  → `unavailable: read_failed`, logged without payloads.
- **`_owner_generation_context`** (`server.py:21993`), after the `partner_activity` block
  (`server.py:22096-22100`):

  ```python
  if FLAGS.trade_season_signal and _bakeoff.owner_revision_enabled(config):
      evidence = _season_evidence(...)
      # viewer completeness rule (PRD §2.5 rule 5)
      context["season_evidence"] = evidence      # only if revision 5 is selected
      context["_season_record"] = evidence       # always, for the request record
  ```

  Only revision 5 accepts the keyword, so the generator key is set only when
  `owner_revision_5_enabled(config)`; the record key is stripped before the generator call and
  written into the request evidence by `_owner_selected_assignment` (digest in the canonical hash
  input, full object beside `input_evidence`). Flag off: neither key, hashes unchanged.
- **Shadow line**, once per organic owner job when the flag is on:
  `season-signal: state=… reason=… weeks=… viewer_outlook=… source=… scored=… unprojected=…
  revision=…`. Counts only.
- **Dark selector hygiene:** pop `owner_bilateral_revision_5_enabled` unless exactly 1, in
  `trade_gen_owner._Search.__init__` (`trade_gen_owner.py:205-209`) and in
  `_owner_selected_assignment` (`server.py:22219-22228`), as the revision 4 key is. The two
  other season knobs (`season_conflict_demotion`, `season_partner_matching`) are dropped from both
  places whenever revision 5 is not selected: a new `model_config` key that reached the canonical
  config would change every request hash and every constructor report.
- **Presentment version** (`server.py:14190`): replace the literal tuple with
  `_bakeoff.owner_presentment_version(owner_config)`, which returns the selected revision's version
  for revisions 3, 4 and 5 and presentment's default otherwise.
- **`bakeoff_runner.py`:** `owner_revision_5_enabled(config)` (exactly 1, inside revision serving,
  wins over 4 and 3); branches in `owner_generator`, `owner_version`, `owner_evaluator`
  (`bakeoff_runner.py:318-360`).
- **Knobs:** `owner_bilateral_revision_5_enabled`, `season_conflict_demotion`,
  `season_partner_matching` in `trade_service._DEFAULT_CFG` (`trade_service.py:1184-1188`) and
  `database._MODEL_CONFIG_DEFAULTS` (`database.py:3864-3868`).
- **Engine modules:** add `"season_value.py"`, `"league_projections/season_points.py"` to
  `_ENGINE_CODE_MODULES` (`server.py:4739-4756`). Bump `DECK_PIPELINE_VERSION` to the next free
  number at merge (rules-first holds 22), append a pin.
- **`season_value.plan_conflict(...)`** is the one conflict predicate. The search calls it; nothing
  else decides a conflict.
- **Admin route** `GET /api/admin/season-signal/labels?user_id=&league_id=` (`X-Cron-Secret`): the
  league profile as rows for the label review. Not flag-gated (operator tool), read-only.

## 7. Calibration round

`outlook_calibration.ROUNDS["outlook-v2-v5-1"] = {"flag": "grading.season_round",
"model_versions": {"current": "owner-v2-bilateral-2", "value_core": "owner-v2-bilateral-5"}}`
(`outlook_calibration.py:22-32`). Same aliases, so installed builds read it unchanged.

- `outlook_calibration_adapter.capture` freezes the season evidence into the captured owner
  context; `run_arm` (`outlook_calibration_adapter.py:156-172`) pins
  `owner_bilateral_revision_5_enabled` per arm and removes `season_evidence` from the revision 2
  arm's kwargs.
- A deck is built only when the evidence is usable and the viewer's outlook is saved; otherwise the
  build is refused with reason `season_round_not_applicable` and the app offers its other rounds.
- Offer order follows the revision-4 round's rule (`docs/plans/offer-learnings/
  scope-revision-4-round.md` §6): a part-graded deck first, then this round until completed.
- Report: the existing per-round admin report, plus per arm the count of unique cards flagged as
  plan conflicts and the mean `delta_pts_week` of each arm's unique cards.

## 8. Operator tools

- `backend/eval/season_replay.py`: per recorded request with season evidence (or a supplied
  fixture map), run revision 2 and revision 5, apply the served-deck stand-in, print aggregates
  ([validation §3](validation.md)). Aggregate-only output, as `acceptance_eval.py`. When
  rules-first's `served_deck_replay.py` exists, import its stand-in instead of carrying one.
- `backend/eval/season_label_review.py`: from the admin route's rows, write one self-contained HTML
  review page per league (the pattern of `docs/plans/realtime-trade-engine/sleeper-review.html`)
  into a git-ignored folder, and read the exported answers back into an aggregate report.

## 9. Module-by-module change list

Sizes are rough lines of new or changed code, tests excluded.

| File | Change | Size |
|---|---|---:|
| `backend/league_projections/season_points.py` (new) | §1.1 | 80 |
| `backend/season_value.py` (new leaf) | §1.2, §2 | 260 |
| `backend/trade_gen_bilateral_season.py` (new) | §3, §4 | 330 |
| `backend/bakeoff_runner.py` | selector, three dispatch branches, presentment version | 35 |
| `backend/trade_gen_owner.py` | pop the dark selector key | 2 |
| `backend/trade_service.py`, `backend/database.py` | three knobs | 10 |
| `backend/server.py` | §6 | 110 |
| `backend/trade_narrative.py` | §5.1, §5.2 | 150 |
| `backend/outlook_calibration.py`, `outlook_calibration_adapter.py` | §7 | 70 |
| `backend/feature_flags.py`, `config/features.json`, flag fixtures | two flags | 12 |
| `backend/eval/season_replay.py`, `season_label_review.py` (new) | §8 | 320 |
| `mobile/src/shared/types.ts`, `api/trades.ts`, `components/TradeCard.tsx` | §5.3 | 110 |
| `mobile/tests/check-season-signal.js` (new), `mobile/package.json` | structural guard | 150 |
| `backend/trade_first_page.py`, `trade_fast_deck.py` | the join (after rules-first) | 40 |
| `web/` | none | 0 |
| Docs | `api-reference` (card payload, admin route), `config-reference`, `architecture`, `glossary`, `data-dictionary` (proof field note), `cross-client-invariants` (label strings), `living-memory` | — |

No schema change. No change to revisions 1–4, `deck_quality.py`, `trade_significance.py`,
`trade_policy.py`, `win_now_*`, or `league_projections` capture, simulation and routes.

## 10. Invariants and their tests

Each test is proven red against the named sabotage, then green on revert
([build plan](build-plan.md)).

| # | Invariant | Test file | Sabotage that must turn it red |
|---|---|---|---|
| I1 | Flag off and selector 0: worker output byte-identical | `test_season_signal_worker.py` | attach the evidence key when the flag is off |
| I2 | Revision 5 without usable evidence = revision 2's identities, terms, order | `test_trade_gen_bilateral_season.py` | let `_lineup` use season assets when `state != "usable"` |
| I3 | "Not sure" viewer with usable evidence = revision 2 | same | add `not_sure` to the scored outlooks |
| I4 | Rebuilding / Tanking viewer: same inventory and terms as revision 2; the order differs (amended 2026-11-11, operator direction; was "penalty 0 → same order") | same | let the shed term qualify a card (add it to `team_plan_gain` / `utility` in `_owner`) |
| I5 | Equal value, equal age, starter beats backup for All-in | same | read the label table with `starts_for` always true |
| I6 | Non-starter's plan lean equals a pick's | same | give non-starters `0.0` |
| I7 | Conflict penalty never changes the inventory | same | apply the penalty before `utility` is computed |
| I8 | Pinned search: no conflict recorded | same | drop the pin precondition |
| I9 | Market terms, fairness and floor decisions equal revision 2's for shared cards | same | price a package with `RATE × ppg` |
| I10 | Derived points reproduce the snapshot's stored lineup totals | `test_season_points.py` | score with the raw scoring settings instead of the slot-normalised ones |
| I11 | Unprojected is never zero: no `ppg`, no label, no claim | `test_season_value.py` | default a missing player to `0.0` |
| I12 | Evidence is a pure function; digest ignores `as_of` inside one horizon | `test_season_value.py` | include `as_of` in the digest |
| I13 | Label printed = label read by the plan-fit table, every card | `test_season_copy.py` | recompute the label in `trade_narrative` from age |
| I14 | "Win-now" appears only under copy rule 1 when evidence is usable | `test_season_copy.py` | leave the age branch reachable |
| I15 | Request hash unchanged with the flag off; changes with the evidence digest when on | `test_season_signal_worker.py` | hash the full evidence including `as_of` |
| I16 | `test_deck_pipeline_digest` passes with the new pin | existing | forget the bump |
| I17 | Calibration: revision 2 arm never sees season evidence | `test_calibration_season_round.py` | pass the captured context unchanged to both arms |
| I18 | After the join: page path = gated full solve for revision 5 | `test_trade_first_page.py` (extended) | read `_lineup_assets` directly in the bound |
