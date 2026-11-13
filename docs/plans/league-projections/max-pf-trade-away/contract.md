# Max PF moves: the build contract (v1, with the v1.1 additions)

> **v1.1 change note (2026-11-13, D-261).** Operator decision: always show the top moves with
> their numbers, add a line for the top two and three combined, and keep a "none of these
> changes your pick on its own" sentence when that is true. Everything below is additive;
> `version` stays 1 and every v1 key and the §4.1 state rules are unchanged, so installed builds
> (191) keep working (§6.5, §8). Changed sections: §3.1 (`combined`), §3.7 (new), §4.1 (note),
> §5.1 (example gains `combined`), §6.3, §6.5, §9, §10 (C-NONE-ALONE, C-COMB-1, C-COMB-2), §12
> (combined entries have no hand-off), §13.1 (saved `combined`, `combined_sizes`, hash re-run).
> Scope addendum: [scope-v1-1.md](scope-v1-1.md). The v1 §5.1 example is kept as a golden in
> `backend/tests/fixtures/maxpf_moves/v1-example.json`.

> The one contract the backend builder and the app builder both code against. Written
> 2026-11-12 against `origin/main` `4a8cd70d` (D-257 merged). Design and reasons:
> [exploration.md](exploration.md) (operator accepted §14 as written). Scope block:
> [scope.md](scope.md). Backend commit plan: [plan.md](plan.md). Every `file:line` here was
> read on `feat/max-pf-moves`. Names in examples are invented.
>
> If the code and this file disagree after build, `docs/api-reference.md` and
> `docs/data-dictionary.md` win and this file gets a correction note.

- [1. Summary](#1-summary)
- [2. Where the block travels](#2-where-the-block-travels)
- [3. The `max_pf_moves` block](#3-the-max_pf_moves-block)
- [4. States](#4-states)
- [5. Example payloads](#5-example-payloads)
- [6. What the app derives versus reads](#6-what-the-app-derives-versus-reads)
- [7. Draft-order answer: storage and route](#7-draft-order-answer-storage-and-route)
- [8. Flag behaviour](#8-flag-behaviour)
- [9. Analytics](#9-analytics)
- [10. Copy](#10-copy)
- [11. Formatting rules](#11-formatting-rules)
- [12. The Find trades hand-off](#12-the-find-trades-hand-off)
- [13. What is saved with the run (backend only)](#13-what-is-saved-with-the-run-backend-only)
- [14. Departures from the exploration, and code that contradicted it](#14-departures-from-the-exploration-and-code-that-contradicted-it)

## 1. Summary

- One new top-level key, `max_pf_moves`, on the forecast read the app already downloads
  (`GET /api/leagues/<league_id>/projection-runs/latest`). Present only while flag
  `league.max_pf_moves` is on. `version: 1`.
- One new write route, `POST /api/leagues/<league_id>/draft-order-rule`, for the
  once-per-league draft-order question. 404 while the flag is off.
- Two new nullable columns on the existing `leagues` row: `draft_order_rule`,
  `draft_order_rule_set_at`. No new table.
- The heavy numbers (lineup re-solve, paired re-runs) are computed in the weekly forecast job
  and saved inside the run's `result_json` under `max_pf_moves`. That raw saved block never
  leaves the server: every read strips it from `run.result` (flag on or off) and the app sees
  only the composed top-level block described here.
- Pick values, the Keep tag, the draft-order answer, the saved outlook and the state are added
  when the page is read.
- No new screen, no navigation entry, no new FeedbackFAB. The section renders inside the
  user's own open team card on Standings, under Draft pick odds.

## 2. Where the block travels

| Piece | Today | With this change |
|---|---|---|
| Route | `GET /api/leagues/<league_id>/projection-runs/latest`, `backend/league_projections/api.py:95-117` | Same route. After `outlook_recommendation` (`api.py:112-116`), when `is_enabled("league.max_pf_moves")`, the response gains `max_pf_moves` |
| Saved run shape | `public(row)` returns the whole `result_json` (`api.py:41-45`) | `public(row)` drops the key `max_pf_moves` from `result` always. Applies to `/projection-runs/latest` (`run` and `attempt`), `GET /api/projection-runs/<run_id>` (`api.py:119-125`) and `POST .../cancel` (`api.py:127-133`). `/teams`, `/draft`, `/weeks` and the exports build their own dicts from named keys (`api.py:146-170`) and are unchanged |
| App fetch | `getLeagueProjectionBatch` → `ProjectionView` (`mobile/src/api/leagueProjections.ts:44-55`) | `ProjectionView` gains `max_pf_moves?: MaxPfMoves` (absent = flag off or older server) |
| App consumer | `StandingsScreen` holds the one query (`mobile/src/screens/StandingsScreen.tsx:105-110`, key `['league-projection-batch', userId, leagueId]`) and passes `team` + `result` to `ProjectionTeamDetail` (`StandingsScreen.tsx:263`) | Also passes `data.max_pf_moves` and the live roster; `ProjectionTeamDetail` (`mobile/src/components/LeagueProjectionDetail.tsx:29-54`) renders a fourth `Disclosure`, "Max PF moves", after "Draft pick odds", only on the viewer's own card |

"The viewer's own card" is `team.roster_id === result.viewer_roster_id`
(`simulation.py:330` writes `viewer_roster_id`; `provider.py:639` sets it from the caller's
roster). The block itself also carries `viewer_roster_id`; the two are equal by construction.

## 3. The `max_pf_moves` block

Types are TypeScript-style; `number` is a JSON number. **Units**: probabilities are 0..1,
unrounded; points are fantasy points; pick slots are 1-based positions among the non-playoff
picks; pick values are engine value units (the number the trade finder prices the pick at).
**Timing**: S = computed in the weekly job and saved with the run; R = computed when the page
is read.

### 3.1 Top level

| Field | Type | Null? | S/R | Meaning |
|---|---|---|---|---|
| `version` | `1` | no | R | Contract version. An app that does not know the version renders nothing for the section |
| `state` | `MaxPfMovesState` (§4) | no | R | What the section shows. Server-decided |
| `reason` | `string` | yes | R | Set only when `state == "unavailable"`; one of §4.2's reasons. Treat as an OPEN set: an unknown reason uses the generic line |
| `viewer_roster_id` | `number` | yes | S | The user's roster in the saved forecast. Null only for `unavailable` without a usable run |
| `captured_at` | ISO-8601 string | yes | S | The forecast's capture time (`result.captured_at`). Null when there is no saved run |
| `draft_season` | `number` | yes | S | `result.config.draft_season`, e.g. 2027 |
| `draft_round` | `number` | yes | S | Always 1 in v1 (`result.config.draft_round`) |
| `draft_order` | `DraftOrder` (§3.2) | no | R | The league's stored answer. Present in every state, so the "Change" link works everywhere |
| `saved_outlook` | `'championship' \| 'contender' \| 'rebuilder' \| 'jets' \| 'not_sure' \| null` | yes | R | The user's saved outlook for this league (`league_preferences.team_outlook`, `database.py:1991-2001`). Null when none is saved |
| `pick_owner` | `PickOwner` (§3.3) | yes | S | Who holds the user's own next-year 1st. Null when there is no usable run |
| `baseline` | `Baseline` (§3.4) | yes | S+R | The "today" line. Null unless `state` is `ready`, `no_moves`, or `no_miss` |
| `roster_player_ids` | `string[]` | no | S | The user's Sleeper roster (`players`, which on Sleeper includes taxi and reserve) as captured. Sorted. Empty when there is no usable run. Used only for the roster-changed check (§6) |
| `rows` | `MoveRow[]` (§3.5) | no | S+R | The re-simulated candidates, at most `candidates` (8), ordered by `rank`. Empty unless `state` is `ready` or `no_moves`. Includes rows that fail the threshold (`passes_threshold: false`); v1 apps list only passing rows, v1.1 apps list every row (§6.5) |
| `candidates_total` | `number` | no | S | How many roster players had a non-zero max PF change (before the top-8 cut). 0 when not computed |
| `combined` | `MaxPfCombined[]` (§3.7) | no | S+R | **v1.1.** The top 2 and top 3 rows removed together, smallest first. `[]` outside `ready`/`no_moves`, for a block saved before v1.1, when the combined step failed or timed out (§13.5), or when there are fewer rows than the size. Absent entirely on a pre-v1.1 server |

### 3.2 `DraftOrder`

| Field | Type | Null? | Meaning |
|---|---|---|---|
| `rule` | `'maxpf_lowest_first' \| 'reverse_standings' \| 'lottery_or_other' \| null` | yes | The league's stored answer. Null = never answered (or only "not sure"), and the list shows with the assumption line |
| `set_at` | ISO-8601 string | yes | When the stored answer was last written. Null when `rule` is null |

### 3.3 `PickOwner`

| Field | Type | Null? | Meaning |
|---|---|---|---|
| `owns_own_pick` | `boolean` | no | `pick_owner_roster_id == viewer_roster_id` for the user's team in the saved run (`simulation.py:191-196`, `:307`) |
| `owner_roster_id` | `number` | no | The roster that holds the user's own `draft_season` round-1 pick |
| `owner_name` | `string` | no | That roster's team name from the saved run (`result.teams[].name`) |

### 3.4 `Baseline`

| Field | Type | Null? | S/R | Meaning |
|---|---|---|---|---|
| `weeks_remaining` | `number` | no | S | Regular-season weeks the forecast still simulates (`len(result.teams[viewer].weeks)`) |
| `first_week` / `last_week` | `number` | no | S | First and last of those weeks |
| `weeks_excluded_played` | `number` | no | S | Weeks inside that range left out of the re-solve because some of the user's players had already played (§13.2). Usually 0 |
| `playoff_probability` | `number` | no | S | `result.teams[viewer].playoff_probability` |
| `playoff_band` | `'jets' \| 'rebuilder' \| 'contender' \| 'championship'` | no | R | `recommendation.classify(playoff_probability, thresholds)` (`recommendation.py:60-70`). Analytics only; the app never re-derives it |
| `pick_if_miss` | `number` | yes | S | `conditional_expected_pick` (`simulation.py:303`). Null when fewer than `min_pick_samples` simulations miss; then `state` is `no_miss` |
| `top3_probability` | `number` | no | S | Chance the user's own pick lands in slots 1 to 3 of the non-playoff order: `sum(pick_probabilities[0:3])` (unconditional, `simulation.py:301`). If the league has fewer than 3 non-playoff picks, the sum over all of them |
| `label` | `string` | yes | S | The D-257 ranked label for the user's own pick in this run, formatted by `pick_slots.slot_suffix` (`pick_slots.py:240-244`), e.g. `"1.02"`. From `pick_projection.slot_ranks` (`pick_projection.py:247-261`) over this run's slot distributions |
| `label_slot` | `number` | yes | S | The integer behind `label` (1..N) |
| `pick_value` | `number` | yes | R | Engine value of the user's own pick under projected-slot pricing (D-240), one decimal. Null when `pick_value_status` is `not_priced` |
| `pick_value_status` | `'priced' \| 'not_priced'` | no | R | `not_priced` when projected-slot pricing does not apply to this league now (flag `picks.projected_slot_value` off, weight 0, too early in the season, the pick's season not covered: the gates of `pick_projection.usable`, `pick_projection.py:165-199`). The app then hides every value figure |

### 3.5 `MoveRow`

| Field | Type | Null? | S/R | Meaning |
|---|---|---|---|---|
| `rank` | `number` | no | S | 1-based order: most negative `maxpf_change_exact` first; ties by most negative `lineup_change_exact`, then `player_id` ascending |
| `player_id` | `string` | no | S | Sleeper player id |
| `name` | `string` | no | S | Full name as captured (`provider.py:484`) |
| `short_name` | `string` | no | S | First initial + rest of name, e.g. `"R. Sato"`; equal to `name` when the name is one word |
| `position` | `string` | no | S | First of the player's captured `fantasy_positions` (QB, RB, WR, TE, K, DEF, DL, LB, DB, ...) |
| `maxpf_change` | `number` | no | S | Rest-of-season change to the user's max PF, whole points, ≤ 0. `maxpf_change_exact` rounded half away from zero |
| `maxpf_change_exact` | `string` | no | S | The exact Decimal sum, e.g. `"-31.24"` |
| `lineup_change` | `number` | no | S | Rest-of-season change to projected lineup points (lineup lane), whole points. Usually ≤ 0; 0 for a taxi player; can be positive when a free agent outprojects the removed player (see `MoveWeek.maxpf_change`) |
| `lineup_change_exact` | `string` | no | S | Exact Decimal |
| `weeks_affected` | `number` | no | S | Weeks with a non-zero max PF change |
| `replacements` | `Replacement[]` | no | S | Who enters the max PF lineup in his place, summed over the weeks. Sorted by `weeks` desc, then `name`. At most 3; see `replacements_more` |
| `replacements_more` | `number` | no | S | How many further replacement players were cut from `replacements` |
| `weeks` | `MoveWeek[]` | no | S | One per simulated week, ascending |
| `playoff_probability` | `NowAfter` | no | S | `now` = baseline; `after` = baseline + paired difference, clamped to 0..1 |
| `pick_if_miss` | `NowAfterNullable` | no | S | `after` null when either 5,000-run gives no conditional pick (fewer than `min_pick_samples` misses) |
| `top3_probability` | `NowAfter` | no | S | Clamped to 0..1 |
| `label` | `{now: string \| null, after: string \| null}` | no | S | D-257 label before and after; `after` ranks every team's "after" expected slot (§13.3) |
| `label_slot` | `{now: number \| null, after: number \| null}` | no | S | The integers |
| `pick_value` | `{now: number, after: number, change: number} \| null` | yes | R | One decimal each; `change = after − now`. Null when `baseline.pick_value_status` is `not_priced` |
| `keep` | `boolean` | no | R | The user marked this player Keep / untouchable (D-241) for this league: `player_id ∈ load_asset_preferences(user_id=<account id>, league_id)["untouchables"]` (`database.py:13458`) |
| `passes_threshold` | `boolean` | no | S | §3.6 |

`NowAfter` = `{now: number, after: number}`. `NowAfterNullable` = `{now: number | null, after: number | null}`.

`Replacement`:

| Field | Type | Null? | Meaning |
|---|---|---|---|
| `player_id` | `string` | yes | Null for an empty slot (nobody, not even a free agent, could fill it: scored 0) |
| `name` | `string` | yes | Null with `player_id` |
| `short_name` | `string` | yes | As above |
| `free_agent` | `boolean` | no | The replacement is a free agent from the forecast's own fill rule (D-234), not on the user's roster |
| `weeks` | `number` | no | Weeks in which this player enters the max PF lineup when the traded player is removed |

`MoveWeek`:

| Field | Type | Null? | Meaning |
|---|---|---|---|
| `week` | `number` | no | NFL week |
| `status` | `'changed' \| 'no_change' \| 'bye' \| 'played' \| 'not_projected'` | no | `changed`: non-zero max PF drop. `no_change`: he does not start in the max PF lineup that week. `bye`: verified bye (`provider.py:451-457`). `played`: the week was excluded because the user's team already has a completed game in it (§13.2). `not_projected` cannot occur in a listed row (unprojected players are excluded, §13.1) and is reserved |
| `maxpf_change` | `number` | no | That week's max PF change, one decimal. Usually ≤ 0. It can be positive: the forecast's free-agent rule fills only open slots and never displaces a rostered starter (D-234, `core.py:197-205`), so when a free agent outprojects the removed player the week's total rises. The row's rest-of-season `maxpf_change` is always < 0 (only drops are listed) |
| `lineup_change` | `number` | no | That week's lineup-lane change, one decimal; same sign rule |
| `replaced_by` | `Replacement[]` without `weeks` | no | Players who enter the max PF lineup that week. Empty unless `status == "changed"` |

### 3.6 The threshold

`passes_threshold` is true when **both**:

1. `maxpf_change_exact ≤ −min_drop_points` (setting, 5), and
2. **either** `pick_if_miss.now − pick_if_miss.after ≥ min_pick_change` (setting, 0.1; both
   non-null) **or** `top3_probability.after − top3_probability.now ≥ min_top3_change`
   (setting, 0.02).

Computed at save time on the unrounded values (exploration §4.3).

### 3.7 `MaxPfCombined` (v1.1)

The top `size` rows (rank 1..`size`) removed **together**: one exact weekly re-solve with all of
them off the roster in both lanes (not the sum of the single drops: the replacements interact,
e.g. two backs who both needed the same bench back), then one paired 5,000-run re-run like a
row's (§13.3, same "before" run). No week detail, no replacements, no Find trades (§12).

| Field | Type | Null? | S/R | Meaning |
|---|---|---|---|---|
| `size` | `2 \| 3` | no | S | How many rows are removed together |
| `player_ids` / `names` / `short_names` | `string[]` | no | S | The members in rank order (equal to rows 1..`size`) |
| `maxpf_change` / `maxpf_change_exact` | `number` / `string` | no | S | As on a row, for the combined removal. Never smaller in magnitude than the largest member's drop |
| `lineup_change` / `lineup_change_exact` | `number` / `string` | no | S | As on a row |
| `playoff_probability`, `pick_if_miss`, `top3_probability`, `label`, `label_slot` | as on a row | | S | As on a row |
| `pick_value` | as on a row | yes | R | As on a row, priced from the entry's saved after-distribution |
| `keep` | `boolean` | no | R | Any member is a Keep player |
| `passes_threshold` | `boolean` | no | S | §3.6 on the combined numbers. Never changes `state` |

## 4. States

### 4.1 Server states (`state`)

The server checks these in order; the first that applies wins.

| # | `state` | When | `baseline` | `rows` |
|---|---|---|---|---|
| 1 | `unavailable` | The forecast is not usable: `recommendation.unusable_reason(state, saved, failure_reason=...)` (`recommendation.py:83-103`) is non-null, or the viewer's team is not in the run, or the saved run has no moves block / was not computed (§4.2) | null | `[]` |
| 2 | `season_over` | `weeks_remaining == 0` (the forecast has no weeks left to change) | null | `[]` |
| 3 | `after_trade_deadline` | The league's trade deadline week, captured with the run (§13.4), is set and `completed_weeks ≥ trade_deadline` | null | `[]` |
| 4 | `draft_order_not_maxpf` | `draft_order.rule` is `reverse_standings` or `lottery_or_other` | null | `[]` |
| 5 | `no_miss` | `baseline.pick_if_miss` is null (the team almost never misses the playoffs) | set | `[]` |
| 6 | `no_moves` | No row has `passes_threshold` | set | all re-run rows (may be empty) |
| 7 | `ready` | Otherwise | set | all re-run rows |

The pick-owner case is not a state: it applies on top of `ready` and `no_moves` through
`pick_owner.owns_own_pick` (§6).

**v1.1 note.** These rules are unchanged: `state` is decided by the rows alone (a passing
combined entry with no passing row is still `no_moves`). `no_moves` has always served every
re-run row; v1.1 apps list them (§6.5), build 191 shows only C-NO-MOVES for it.

### 4.2 `reason` values (only with `unavailable`)

| `reason` | Source |
|---|---|
| `no_forecast`, `update_pending`, `refresh_failed`, `stale`, `old_model`, `incomplete`, `team_not_found`, `unsupported`, `missing_projections`, `read_failed` | The existing vocabulary of `recommendation.unusable_reason` / `UNAVAILABLE` (`recommendation.py:34-46`, `:83-103`). Same meanings. `read_failed` when the saved result cannot be parsed |
| `not_computed` | The run is usable but carries no moves block, or its block says `computed: false` (the flag was off at save time, the step timed out or failed, §13.5) |

### 4.3 App states (derived, §6)

| App state | Rule |
|---|---|
| hidden | No `max_pf_moves` key, unknown `version`, not the viewer's own card, or the league is not Sleeper (the page's existing unavailable card covers it) |
| collapsed | `ready`/`no_moves` and the default-open rule (§6.1) is false |
| behind "Show anyway" | `ready`/`no_moves` and `pick_owner.owns_own_pick == false` |
| roster changed | `ready`/`no_moves` and the live roster differs from `roster_player_ids` (§6.3) |
| question shown | `draft_order.rule == null`, not dismissed on this device for this league, and `state` is `ready`, `no_moves` or `no_miss` |
| first-time sentence | First time this device shows the section body open for any league (§6.4) |

## 5. Example payloads

### 5.1 `ready` (full)

Invented league, 12 teams, 6 make the playoffs, weeks 10 to 14 left. Values echo
exploration §6.

```json
{
  "max_pf_moves": {
    "version": 1,
    "state": "ready",
    "reason": null,
    "viewer_roster_id": 7,
    "captured_at": "2026-11-10T14:30:05+00:00",
    "draft_season": 2027,
    "draft_round": 1,
    "draft_order": {"rule": null, "set_at": null},
    "saved_outlook": "rebuilder",
    "pick_owner": {"owns_own_pick": true, "owner_roster_id": 7, "owner_name": "Harbor Herons"},
    "baseline": {
      "weeks_remaining": 5,
      "first_week": 10,
      "last_week": 14,
      "weeks_excluded_played": 0,
      "playoff_probability": 0.0271,
      "playoff_band": "jets",
      "pick_if_miss": 3.6912,
      "top3_probability": 0.4583,
      "label": "1.02",
      "label_slot": 2,
      "pick_value": 2480.4,
      "pick_value_status": "priced"
    },
    "roster_player_ids": ["10021", "10477", "11233", "4034", "5022", "6130", "7611", "8150", "9488"],
    "candidates_total": 11,
    "rows": [
      {
        "rank": 1,
        "player_id": "8150",
        "name": "Rhett Sato",
        "short_name": "R. Sato",
        "position": "RB",
        "maxpf_change": -31,
        "maxpf_change_exact": "-31.00",
        "lineup_change": -31,
        "lineup_change_exact": "-31.00",
        "weeks_affected": 5,
        "replacements": [
          {"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false, "weeks": 4},
          {"player_id": "10477", "name": "Ezra Quill", "short_name": "E. Quill", "free_agent": false, "weeks": 1}
        ],
        "replacements_more": 0,
        "weeks": [
          {"week": 10, "status": "changed", "maxpf_change": -5.0, "lineup_change": -5.0,
           "replaced_by": [{"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false}]},
          {"week": 11, "status": "changed", "maxpf_change": -5.0, "lineup_change": -5.0,
           "replaced_by": [{"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false}]},
          {"week": 12, "status": "changed", "maxpf_change": -11.0, "lineup_change": -11.0,
           "replaced_by": [{"player_id": "10477", "name": "Ezra Quill", "short_name": "E. Quill", "free_agent": false}]},
          {"week": 13, "status": "changed", "maxpf_change": -5.0, "lineup_change": -5.0,
           "replaced_by": [{"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false}]},
          {"week": 14, "status": "changed", "maxpf_change": -5.0, "lineup_change": -5.0,
           "replaced_by": [{"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false}]}
        ],
        "playoff_probability": {"now": 0.0271, "after": 0.0122},
        "pick_if_miss": {"now": 3.6912, "after": 3.3604},
        "top3_probability": {"now": 0.4583, "after": 0.6177},
        "label": {"now": "1.02", "after": "1.02"},
        "label_slot": {"now": 2, "after": 2},
        "pick_value": {"now": 2480.4, "after": 2649.6, "change": 169.2},
        "keep": false,
        "passes_threshold": true
      },
      {
        "rank": 2,
        "player_id": "6130",
        "name": "Dale Okafor",
        "short_name": "D. Okafor",
        "position": "WR",
        "maxpf_change": -28,
        "maxpf_change_exact": "-28.00",
        "lineup_change": -28,
        "lineup_change_exact": "-28.00",
        "weeks_affected": 4,
        "replacements": [
          {"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false, "weeks": 4}
        ],
        "replacements_more": 0,
        "weeks": [
          {"week": 10, "status": "changed", "maxpf_change": -7.0, "lineup_change": -7.0,
           "replaced_by": [{"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false}]},
          {"week": 11, "status": "changed", "maxpf_change": -7.0, "lineup_change": -7.0,
           "replaced_by": [{"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false}]},
          {"week": 12, "status": "bye", "maxpf_change": 0.0, "lineup_change": 0.0, "replaced_by": []},
          {"week": 13, "status": "changed", "maxpf_change": -7.0, "lineup_change": -7.0,
           "replaced_by": [{"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false}]},
          {"week": 14, "status": "changed", "maxpf_change": -7.0, "lineup_change": -7.0,
           "replaced_by": [{"player_id": "9488", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false}]}
        ],
        "playoff_probability": {"now": 0.0271, "after": 0.0131},
        "pick_if_miss": {"now": 3.6912, "after": 3.3887},
        "top3_probability": {"now": 0.4583, "after": 0.6094},
        "label": {"now": "1.02", "after": "1.02"},
        "label_slot": {"now": 2, "after": 2},
        "pick_value": {"now": 2480.4, "after": 2633.1, "change": 152.7},
        "keep": true,
        "passes_threshold": true
      },
      {
        "rank": 3,
        "player_id": "11233",
        "name": "Bo Halvorsen",
        "short_name": "B. Halvorsen",
        "position": "TE",
        "maxpf_change": -4,
        "maxpf_change_exact": "-4.20",
        "lineup_change": -4,
        "lineup_change_exact": "-4.20",
        "weeks_affected": 1,
        "replacements": [
          {"player_id": "20391", "name": "Ike Brennan", "short_name": "I. Brennan", "free_agent": true, "weeks": 1}
        ],
        "replacements_more": 0,
        "weeks": [
          {"week": 10, "status": "no_change", "maxpf_change": 0.0, "lineup_change": 0.0, "replaced_by": []},
          {"week": 11, "status": "changed", "maxpf_change": -4.2, "lineup_change": -4.2,
           "replaced_by": [{"player_id": "20391", "name": "Ike Brennan", "short_name": "I. Brennan", "free_agent": true}]},
          {"week": 12, "status": "no_change", "maxpf_change": 0.0, "lineup_change": 0.0, "replaced_by": []},
          {"week": 13, "status": "no_change", "maxpf_change": 0.0, "lineup_change": 0.0, "replaced_by": []},
          {"week": 14, "status": "no_change", "maxpf_change": 0.0, "lineup_change": 0.0, "replaced_by": []}
        ],
        "playoff_probability": {"now": 0.0271, "after": 0.0262},
        "pick_if_miss": {"now": 3.6912, "after": 3.6581},
        "top3_probability": {"now": 0.4583, "after": 0.4712},
        "label": {"now": "1.02", "after": "1.02"},
        "label_slot": {"now": 2, "after": 2},
        "pick_value": {"now": 2480.4, "after": 2493.0, "change": 12.6},
        "keep": false,
        "passes_threshold": false
      }
    ],
    "combined": [
      {
        "size": 2,
        "player_ids": ["8150", "6130"],
        "names": ["Rhett Sato", "Dale Okafor"],
        "short_names": ["R. Sato", "D. Okafor"],
        "maxpf_change": -55,
        "maxpf_change_exact": "-55.00",
        "lineup_change": -55,
        "lineup_change_exact": "-55.00",
        "playoff_probability": {"now": 0.0271, "after": 0.0064},
        "pick_if_miss": {"now": 3.6912, "after": 3.1458},
        "top3_probability": {"now": 0.4583, "after": 0.7012},
        "label": {"now": "1.02", "after": "1.01"},
        "label_slot": {"now": 2, "after": 1},
        "pick_value": {"now": 2480.4, "after": 2761.9, "change": 281.5},
        "keep": true,
        "passes_threshold": true
      },
      {
        "size": 3,
        "player_ids": ["8150", "6130", "11233"],
        "names": ["Rhett Sato", "Dale Okafor", "Bo Halvorsen"],
        "short_names": ["R. Sato", "D. Okafor", "B. Halvorsen"],
        "maxpf_change": -59,
        "maxpf_change_exact": "-59.20",
        "lineup_change": -59,
        "lineup_change_exact": "-59.20",
        "playoff_probability": {"now": 0.0271, "after": 0.0058},
        "pick_if_miss": {"now": 3.6912, "after": 3.1203},
        "top3_probability": {"now": 0.4583, "after": 0.7154},
        "label": {"now": "1.02", "after": "1.01"},
        "label_slot": {"now": 2, "after": 1},
        "pick_value": {"now": 2480.4, "after": 2774.0, "change": 293.6},
        "keep": true,
        "passes_threshold": true
      }
    ]
  }
}
```

### 5.2 `unavailable`

```json
{"max_pf_moves": {"version": 1, "state": "unavailable", "reason": "stale",
  "viewer_roster_id": 7, "captured_at": "2026-11-03T14:30:02+00:00", "draft_season": 2027, "draft_round": 1,
  "draft_order": {"rule": "maxpf_lowest_first", "set_at": "2026-11-05T01:12:44+00:00"},
  "saved_outlook": null, "pick_owner": {"owns_own_pick": true, "owner_roster_id": 7, "owner_name": "Harbor Herons"},
  "baseline": null, "roster_player_ids": ["10021", "4034"], "candidates_total": 0, "rows": []}}
```

With no saved run at all (`reason: "no_forecast"`): `viewer_roster_id`, `captured_at`,
`draft_season`, `draft_round`, `pick_owner` are null and `roster_player_ids` is `[]`.

### 5.3 `draft_order_not_maxpf`

```json
{"max_pf_moves": {"version": 1, "state": "draft_order_not_maxpf", "reason": null,
  "viewer_roster_id": 7, "captured_at": "2026-11-10T14:30:05+00:00", "draft_season": 2027, "draft_round": 1,
  "draft_order": {"rule": "reverse_standings", "set_at": "2026-11-11T22:04:10+00:00"},
  "saved_outlook": "jets", "pick_owner": {"owns_own_pick": true, "owner_roster_id": 7, "owner_name": "Harbor Herons"},
  "baseline": null, "roster_player_ids": ["10021", "4034"], "candidates_total": 11, "rows": []}}
```

### 5.4 `no_miss`, pick owned by another team

```json
{"max_pf_moves": {"version": 1, "state": "no_miss", "reason": null,
  "viewer_roster_id": 3, "captured_at": "2026-11-10T14:30:05+00:00", "draft_season": 2027, "draft_round": 1,
  "draft_order": {"rule": null, "set_at": null}, "saved_outlook": "championship",
  "pick_owner": {"owns_own_pick": false, "owner_roster_id": 9, "owner_name": "Saltmarsh Owls"},
  "baseline": {"weeks_remaining": 5, "first_week": 10, "last_week": 14, "weeks_excluded_played": 0,
    "playoff_probability": 0.9997, "playoff_band": "championship", "pick_if_miss": null,
    "top3_probability": 0.0, "label": "1.12", "label_slot": 12, "pick_value": 1214.0, "pick_value_status": "priced"},
  "roster_player_ids": ["2210", "3391"], "candidates_total": 0, "rows": []}}
```

## 6. What the app derives versus reads

The app reads everything in §3 and never re-computes a number. It derives only these:

### 6.1 Open or collapsed by default

```
defaultOpen = baseline.playoff_probability <= 0.45
              || saved_outlook === 'rebuilder' || saved_outlook === 'jets'
```

Unrounded probability, inclusive at 0.45 (the `REBUILDING_MAX` cut, `recommendation.py:25`).
"Rebuilding" and "Tanking" are the saved outlook ids `rebuilder` and `jets`. Applies to
`ready` and `no_moves`. Collapsed shows the collapsed line (copy C-COLLAPSED) and a "Show
moves" tap that opens the list. Every other state shows its one line, open, with no list.

The outer "Max PF moves" `Disclosure` itself starts **open** when `defaultOpen` is true and
the pick-owner gate is not active, otherwise closed. (The three existing disclosures start
closed, `LeagueProjectionDetail.tsx:18`; this one takes an `initialOpen` prop.)

### 6.2 Pick owned by another team

If `pick_owner.owns_own_pick === false` and `state` is `ready` or `no_moves`: show C-OWNER
and a "Show anyway" button; the baseline line and list render only after that tap. Overrides
§6.1 (always starts behind the tap).

### 6.3 Roster changed since the forecast

```
live = set(findMyRoster(rosters, userId).players)   // the page's ['league-rosters', leagueId] query
saved = set(max_pf_moves.roster_player_ids)
rosterChanged = live and saved are both available and live != saved
```

When `rosterChanged`: show C-ROSTER above the list and drop every row whose `player_id` is not
in `live`, and every combined entry with **any** member not in `live` (v1.1). Numbers on the
remaining rows are shown unchanged. If no row survives, show C-ROSTER only. The live roster query already exists on the page
(`StandingsScreen.tsx:91-96`); when it has not loaded, skip the check (no notice).

### 6.4 Once-only prompts (device storage)

| Item | Key | Rule |
|---|---|---|
| First-time sentence (C-RULES) | `maxpf.rulesNoteShown` (one per device) | Shown under the baseline the first time the section body is open; the flag is written then |
| Draft-order question | `maxpf.draftOrderAsked.<leagueId>` | Shown when `draft_order.rule === null`, the key is absent, and `state` is `ready`, `no_moves` or `no_miss`. Any answer, including "Not sure", writes the key. A stored league answer (any member's) means the question never shows; "Change" re-opens it on demand |

Use the app's existing AsyncStorage helper pattern (the builder picks the module; no new
dependency).

### 6.5 Which rows are listed

**v1.1 (D-261):** every row, passing or not, in `rank` order (largest max PF drop first), after
the roster-changed drop, in **both** `ready` and `no_moves`. The first 5 show; "Show all"
reveals the rest (at most 8 total). Under the rows, one combined line per `combined` entry
(after the §6.3 drop), smallest first, not expandable into week detail; tapping it shows
C-OPEN-TOP3 and C-OPEN-PLAYOFF. When no listed row and no listed combined entry passes,
C-NONE-ALONE shows above the list. When some pass and some do not, nothing marks the
difference: the numbers speak. C-NO-MOVES is kept for a block with zero rows.

v1 (build 191 and earlier) listed only passing rows and showed C-NO-MOVES alone for `no_moves`;
it ignores `combined`. The server serves both shapes from one block.

### 6.6 Values to hide

When `baseline.pick_value_status === 'not_priced'`, hide the baseline value sentence part and
the value figure on every row. When `row.pick_if_miss.after === null`, show "—" for that pair.

## 7. Draft-order answer: storage and route

### 7.1 Storage: per league, two columns on `leagues`

| Column | Type | Values |
|---|---|---|
| `leagues.draft_order_rule` | TEXT NULL | `maxpf_lowest_first` \| `reverse_standings` \| `lottery_or_other` \| NULL |
| `leagues.draft_order_rule_set_at` | TEXT NULL | ISO-8601 UTC of the last write |

Added to `leagues_table` (`database.py:616`) and to the `_migrate_db` column list
(`database.py:4393-4444` neighbourhood).

**Why per league, not per user-league.** The draft order is a fact about the league; every
member has the same answer, and the forecast and the pick price are league-level too (D-240
prices a league's picks from one forecast, `server.py:20900-20928`). A per-user table
(`league_preferences`, `database.py:1991-2001`, keyed `(user_id, league_id)`) would let two
members of one league hold contradictory facts and would make the later D-240 follow-up
ambiguous. Last writer wins. The risk, one member's mistake hiding the list for others in
the same league, is small and visible (the "Change" link on C-NOT-MAXPF), and v1 uses the
answer only to show or hide this section.

**Why these names.** The column name and two of the three values are the ones the unbuilt
ESPN/MFL forecast design already proposes (`docs/plans/forecasts-espn-mfl/design.md` §5.2,
line 285). It adds `lottery_or_other`. **Not stored:** "not sure" (it is not a fact about the
league; the device remembers that it asked), and who answered (no user id lands on a league
row, so account deletion has nothing to clear here). The ESPN/MFL design treats the column as
operator-set and read by the simulation; reconciling that with member answers is that
design's job when it is built (open question for the operator, scope §0).

### 7.2 Write route

`POST /api/leagues/<league_id>/draft-order-rule`

Installed in `backend/league_projections/api.py` beside the forecast routes, through the same
`guarded` wrapper (`api.py:17-32`: 404 `feature_disabled` while `league.projections` is off;
session required; `read_denial` and, for POST, `write_denial`, i.e. a verified session).

| Item | Rule |
|---|---|
| Flag | `league.max_pf_moves` off → 404 `{"error": "feature_disabled"}` |
| Who | Any signed-in, verified user whose current session league is `<league_id>` (`identity(sess)`, `api.py:34-35`; mismatch → 404 `{"error": "not_found"}`). No owner/commissioner check: every member may answer |
| Platform | Not Sleeper → 422 `{"status": "unsupported_policy", "reason": "sleeper_only", "details": {}}` (the `Unavailable` path, `api.py:28-29`) |
| Body | `Content-Length` ≤ 8192 else 413 `{"error": "payload_too_large"}` (the scenario POST's cap; a lower cap would sit below the test-profile fence's body scan limit). An empty body is a 400. The route is classified FREE in `paywall_gate.ROUTES`. JSON object with exactly one key `rule` ∈ `maxpf_lowest_first`, `reverse_standings`, `lottery_or_other`, `not_sure`. Anything else → 400 `{"error": "invalid_draft_order_rule"}` |
| Effect | `not_sure`: nothing written. Otherwise sets both columns on the `leagues` row. No `leagues` row → 404 `{"error": "not_found"}` |
| Response 200 | `{"draft_order": {"rule": <stored rule or null>, "set_at": <iso or null>}}`, the stored state after the call |
| Side effects | None beyond the row. The answer reaches the forecast read on the next `GET .../projection-runs/latest` (R-time read of the row). The app invalidates `['league-projection-batch', userId, leagueId]` after a 200 |

Request: `{"rule": "reverse_standings"}` → `{"draft_order": {"rule": "reverse_standings", "set_at": "2026-11-12T19:03:51+00:00"}}`.
Request: `{"rule": "not_sure"}` on an unanswered league → `{"draft_order": {"rule": null, "set_at": null}}`.

There is no separate read route: the answer is on `max_pf_moves.draft_order`.

App client: `setDraftOrderRule(leagueId, rule)` in `mobile/src/api/draftOrderRule.ts` (through
`api.post`; app builder's choice, 2026-11-12).

### 7.3 D-240 pick pricing: out of scope

A `reverse_standings` or `lottery_or_other` answer does **not** change projected-slot pick
pricing (D-240) in v1; picks in such a league are still priced from the max PF forecast.
Follow-up item: when the answer is not `maxpf_lowest_first`, `_league_pick_projection`
(`server.py:20931`) should return None for that league (price generic). Logged in plan.md
§Follow-ups for NEXT.md.

## 8. Flag behaviour

Flag `league.max_pf_moves`: default False in `backend/feature_flags.py` (`FLAG_KEYS` and
`DEFAULT_FLAGS`), `false` in `config/features.json` with a `_comment_` line, mirrored `false`
in `backend/tests/fixtures/flags/release.json`, `onboarding-v2.json`, `profiles-on.json`.
Requires `league.projections` (no forecast without it: `api.py:20`, `service.py:17`).

| Path | Flag off | Flag on |
|---|---|---|
| `GET .../projection-runs/latest` | Byte-identical to today: no `max_pf_moves` key; `run.result`/`attempt.result` carry no `max_pf_moves` key (stripped if a run saved while the flag was on) | Adds `max_pf_moves` |
| `GET /api/projection-runs/<id>`, `/cancel` | Byte-identical (strip applies; a result never had the key before this change) | Same as off: the raw saved block is never served |
| `POST .../draft-order-rule` | 404 `feature_disabled` | §7.2 |
| Weekly job (`service._run`) | Does no extra work: capture is called without the side channel, no moves step, no extra DB read | Capture fills the side channel; after `simulate` the moves step runs for baseline runs (§13) |
| Stored `snapshot_json`, `input_hash`, `snapshot_hash`, `model_version` | Unchanged | Also unchanged: the extra free agents and the deadline never enter the snapshot (§13.4) |
| App | Flag false and no key → section not rendered | §6 |

The app reads the flag too: the section mounts only when `useFlag('league.max_pf_moves')` is
on **and** the block is present (app builder, 2026-11-12). The flag reaches the app the way
`league.projections` does: `GET /api/feature-flags` returns `flags_dict()`, every key of
`FLAG_KEYS` (`server.py:36601`, `feature_flags.py:1449`), which `mobile/src/api/flags.ts`
fetches. Pinned by `test_maxpf_moves_analytics.py::test_flags_endpoint_serves_the_flag`.

## 9. Analytics

All four are emitted by the **app** through `track()` (`mobile/src/api/events.ts`). The
backend registers the two new ones in `backend/analytics_taxonomy.py` (`CLIENT_EVENT_PROPS`
and the event-name set) and classifies them in `backend/analytics_queries.NON_INTENT_EVENTS`
(`analytics_queries.py:63`) in the same commit as the app emitter lands, per the root
CLAUDE.md rule. No player id or name in any property. Screen: `'Standings'`.

| Event | Fires when | Properties (exact names → allowed values) | Class |
|---|---|---|---|
| `maxpf_moves_viewed` (new) | The section body becomes visible: on render when it starts open (§6.1), or on the tap that opens it. Once per opening of the user's own card | `state` → `ready` \| `no_moves` \| `unavailable` \| `no_miss` \| `draft_order_not_maxpf` \| `after_trade_deadline` \| `season_over` (the server `state` verbatim); `n_moves` → integer ≥ 0, passing rows listed after §6.3 (0 unless `ready`; the v1 meaning); `band` → `baseline.playoff_band` (`jets` \| `rebuilder` \| `contender` \| `championship`) or `none` when `baseline` is null; v1.1: `n_listed` → every row listed after §6.3 and §6.5; `any_pass` → a listed row or combined entry passes | Impression: add to `NON_INTENT_EVENTS` |
| `maxpf_move_expanded` (new) | A listed row is opened (v1.1: or a combined line) | `position` → the row's `position` string (`combined` for a combined line); `rank` → the row's `rank` (1..8), or `combined_2` \| `combined_3` | Intent |
| `finder_target_pinned` (existing, `analytics_taxonomy.py:1809`) | "Find trades for [player]" is tapped | `side` → `give`; `source` → `maxpf_moves` (new value; add it to the row's comment) | Intent, already registered |
| `draft_order_rule_answered` (new) | The draft-order POST returns 200 | `answer` → `maxpf_lowest_first` \| `reverse_standings` \| `lottery_or_other` \| `not_sure`; `source` → `first_ask` (the once-per-league question) \| `change` (opened from a "Change" link) | Intent |

## 10. Copy

The app uses these strings verbatim. `{…}` are fills formatted per §11. Tone: neutral, plain
English; never "tank", never anything about who to start or bench.

| Id | Where | String |
|---|---|---|
| C-TITLE | Disclosure label | `Max PF moves` |
| C-BASE | Baseline line, `ready`/`no_moves` | `Your {season} 1st today: {label} projected. If you miss the playoffs, pick {pick_if_miss} on average. {top3} chance of a top-3 pick.` then, when priced, ` Value {value}.` When `label` is null the first sentence is `Your {season} 1st:` and the rest is unchanged. |
| C-HEAD | Above the rows | `Max PF change over the remaining {n} weeks` (n = `weeks_remaining`; n = 1 → `over the final week`) |
| C-ROW-1 | Row, line 1 | `{short_name}  {position}  {maxpf_change}` |
| C-ROW-2 | Row, line 2 | `Pick if you miss {now} → {after}` then, when priced, ` · Value {change}` |
| C-KEEP | Tag on a `keep` row | `Keep` |
| C-OPEN-TOP3 | Opened row | `Top-3 chance {now} → {after}` |
| C-OPEN-PLAYOFF | Opened row | `Playoff chance {now} → {after}` |
| C-OPEN-LABEL | Opened row | `Projected pick {now} → {after}` (when both labels non-null; `{now}` alone if unchanged: `Projected pick {now}, unchanged`) |
| C-REPL-1 | Opened row, one replacement in every affected week | `{name} starts instead.` |
| C-REPL-N | Opened row, several | `{name1} starts instead ({w1} weeks), {name2} ({w2} weeks).` up to 3 names, then ` and {k} more.` from `replacements_more`; `1 week` singular |
| C-REPL-FA | A free-agent replacement name | `{name} (free agent)` |
| C-REPL-EMPTY | A replacement with null `player_id` | `an empty spot` (e.g. `An empty spot starts instead (1 week).` — capitalise when first) |
| C-BYE | Appended when any week is `bye` | `Bye in week {w}.` / `Byes in weeks {a} and {b}.` / `Byes in weeks {a}, {b} and {c}.` |
| C-WEEK | Week list in the opened row | `Week {w}: {maxpf_change}, {names} instead` / `Week {w}: bye` / `Week {w}: no change` / `Week {w}: already played` |
| C-SHOWALL | Under the 5th row | `Show all` |
| C-BUTTON | Opened row, not `keep` | `Find trades for {short_name}` |
| C-KEEP-NOTE | Opened row, `keep` | `You marked {short_name} Keep, so Find trades is off for this player.` |
| C-FOOT | Under the list | `Largest possible change: assumes you get back picks or players who would not start for you.` |
| C-ORDER-ASSUMED | Under C-FOOT, rule null | `Estimates assume regular-season Max PF draft order.` + link `Change` |
| C-ORDER-MAXPF | Under C-FOOT, rule `maxpf_lowest_first` | `Your league orders the draft by lowest max PF.` + link `Change` |
| C-RULES | First time open (§6.4) | `Check your league's rules on trades made for draft position.` |
| C-Q | Question title | `How does your league set next year's draft order for non-playoff teams?` |
| C-Q-OPTS | Answer buttons | `Lowest max PF` · `Reverse standings` · `Lottery or other` · `Not sure` |
| C-Q-ERR | POST failed | `Couldn't save your answer. Try again.` |
| C-COLLAPSED | Collapsed (§6.1) | `Your team makes the playoffs in {playoff} of simulations. Moving these players lowers that.` + button `Show moves` |
| C-OWNER | Pick owned elsewhere (§6.2) | `{owner_name} owns your {season} 1st, so lowering your max PF improves their pick.` + button `Show anyway` |
| C-ROSTER | Roster changed (§6.3) | `Your roster changed after this forecast. The list updates with the next weekly forecast.` |
| C-NO-MOVES | A list state with zero rows (or every row dropped by §6.3 → C-ROSTER only). v1.1: no longer shown for a `no_moves` block that has rows | `No single player moves your projected pick by a visible amount.` |
| C-NONE-ALONE | v1.1. Above the list when no listed row and no listed combined entry passes | `None of these changes your projected pick on its own.` |
| C-COMB-1 | v1.1. Combined line, line 1 (`{n}` = `size`, `{names}` = `short_names` joined "A and B" / "A, B and C"; the `maxpf_change` on the right as on a row) | `Top {n} together: {names}` |
| C-COMB-2 | v1.1. Combined line, line 2: C-ROW-2's words and rules (value only when priced) | `Pick if you miss {now} → {after}` |
| C-NO-MISS | `no_miss` | `Your team is not projected to miss the playoffs.` |
| C-NOT-MAXPF | `draft_order_not_maxpf` | `Your league doesn't set its draft order by max PF, so these moves wouldn't change your pick.` + link `Change answer` |
| C-DEADLINE | `after_trade_deadline` | `Your league's trade deadline has passed.` |
| C-SEASON-OVER | `season_over` | `The regular season is over, so there are no weeks left to change.` |
| C-U-no_forecast | `unavailable` | `There is no saved forecast for this league yet.` |
| C-U-update_pending | | `A new forecast is being prepared. Max PF moves return when it is saved.` |
| C-U-refresh_failed | | `The latest forecast update failed. Max PF moves return after the next successful update.` |
| C-U-stale | | `The saved forecast is from an earlier week. Max PF moves return after the next weekly update.` |
| C-U-old_model | | `The saved forecast was made by an earlier version of the model. Max PF moves return after the next update.` |
| C-U-incomplete | | `This forecast is incomplete, so Max PF moves are not shown.` |
| C-U-team_not_found | | `Your team could not be matched to the saved forecast.` |
| C-U-unsupported | | `Forecasts are not available for this league.` |
| C-U-missing_projections | | `The projection source had no projections for an upcoming week, so there is no new forecast.` |
| C-U-read_failed | | `The saved forecast could not be read just now.` |
| C-U-not_computed | | `Max PF moves are worked out with the weekly forecast. They appear after the next update.` |
| C-U-other | Unknown `reason` | `Max PF moves are not available right now.` |

## 11. Formatting rules

| Value | Rule | Example |
|---|---|---|
| Max PF / lineup change, row | Whole number from the integer field; negatives with U+2212 `−`, positives with `+`; exactly 0 as `0` | `−31` |
| Week change | One decimal; `−` / `+` as above; exactly 0 as `0` | `−7.0` |
| Pick if you miss | One decimal | `3.7 → 3.4` |
| Probabilities | Whole percent, round half up; `<1%` when 0 < p < 0.005; `>99%` when 0.995 ≤ p < 1; `0%` and `100%` exact | `46% → 62%`, `3% → 1%` |
| Pick value (baseline) | Whole number, thousands separator | `2,480` |
| Pick value change | Whole number, leading `+` or `−`, thousands separator; a change that rounds to exactly 0 renders `0`, never `+0` | `+169` |
| Arrows | ` → ` (U+2192, spaces either side) | |
| Labels | Verbatim from the server, never composed | `1.02` |

## 12. The Find trades hand-off

On "Find trades for {short_name}" (only on rows with `keep === false`). Revised 2026-11-12 after
the app builder found that, on today's flags, TradesHome opens on the canvas, which neither shows
nor sends store pins (app-evidence.md §3):

```ts
const store = useFinderTargets.getState();          // mobile/src/state/useFinderTargets.ts:98-118
store.setSide('give', [{ id: row.player_id, name: row.name, position: row.position }]);
store.setSide('receive', []);
track('finder_target_pinned', { side: 'give', source: 'maxpf_moves' }, 'Standings');
navigation.popTo('Main', { screen: 'Trades', params: { screen: 'TradesHome',
  params: { canvasPrefill: { give: [row.player_id], receive: [] }, canvasPrefillSeq: Date.now() },
  pop: true } });
```

- The store pin and the event stay exactly as before; the existing `canvasPrefill` route param
  (`CanvasPrefill`, `components/TradeBuildCanvas.tsx:60-70`; MatchesScreen already sends it) puts
  the player visibly on the canvas's give side, replacing what was there.
- `popTo('Main', …)` because Standings is a root-stack push. `canvasPrefillSeq` is required:
  TradesScreen's consumer is keyed on it alone (`TradesScreen.tsx:1362-1368`). `pop: true` keeps
  a second TradesHome from stacking over a results deck (G-056). No `opponentId` is sent, so the
  canvas partner becomes the page's scoped opponent.
- It **replaces** both sides (the League Summary "Offer" convention,
  `LeagueSummaryScreen.tsx:1314-1316`), so an old pin cannot ride along unseen.
- **No `setHandoff`, no auto-run** in v1, no new event and no new R1 source. Nothing runs until
  the user taps Find a Trade. Auto-run is a follow-up.
- Pins are session-only and clear on league switch (`useFinderTargets.ts:120-138`), unchanged.
- **Keep / untouchable rows:** the row is listed with the `Keep` tag; the opened row shows
  C-KEEP-NOTE instead of the button. The app does not pin a Keep player. (The engine would
  accept it: a viewer's own give-side pin overrides Keep, `database.py:4023`; v1 does not offer
  that path.)
- **Combined entries (v1.1) have no hand-off.** A combined line opens to top-3 and playoff chance
  only; there is no "Find trades" for two or three players at once in v1.1 (follow-up in NEXT.md).
- **Known limitation (follow-up, not built):** with `calc.inline_home` OFF (it is true in
  `config/features.json` today) TradesScreen ignores the prefill (`TradesScreen.tsx:1364`); the
  give pin is then not shown on the guided landing and is sent only if no model search has run
  since the screen's last reset. Smallest fix if that flag is ever turned off: a TradesScreen
  effect that calls `resetDeckForNewTargets()` when the store pins change from outside the
  screen (about 8 lines).

Accepted on the app side (2026-11-12): an unknown `state` renders nothing; replacement names use
the full `name`; the draft-order line with "Change" also shows in `no_moves` and `no_miss`.

## 13. What is saved with the run (backend only)

The app never sees this shape; it is here so the backend's tests and the validation agent's
backtest share one definition.

### 13.1 Location and shape

`result_json["max_pf_moves"]`, written only for `kind == "baseline"` runs while the flag is on,
by `maxpf_moves.compute` (pure; its docstring states the inputs and outputs, so a validation
agent can call it on historical inputs):

```
{ "version": 1, "computed": true | false, "reason": null | "not_eligible",
  "settings": {simulations_per_candidate, candidates, min_drop_points, min_pick_change,
               min_top3_change, time_budget_seconds, combined_sizes},
  "settings_hash": sha256 of settings,
  "viewer_roster_id", "roster_player_ids", "trade_deadline": int | null,
  "baseline": {weeks_remaining, first_week, last_week, weeks_excluded_played,
               label, label_slot, top3_probability},
  "candidates_total": int,
  "rows": [ {rank, player_id, name, short_name, position, maxpf_change, maxpf_change_exact,
             lineup_change, lineup_change_exact, weeks_affected, replacements, replacements_more, weeks,
             playoff_probability, pick_if_miss, top3_probability, label, label_slot,
             after_pick_probabilities: number[], after_playoff_probability: number,
             passes_threshold } ],
  "combined": [ {size, player_ids, names, short_names, maxpf_change, maxpf_change_exact,
                 lineup_change, lineup_change_exact, playoff_probability, pick_if_miss,
                 top3_probability, label, label_slot, after_pick_probabilities,
                 after_playoff_probability, passes_threshold} ],          // v1.1, may be absent
  "free_agent_pool": { "<week>": [ {player_id, name, positions, points} ] },
  "elapsed_ms": int }
```

**v1.1 (D-261).** `combined_sizes` (setting, `[2, 3]`; distinct, ascending, each 2 or 3; `[]`
turns the step off) joins the settings, so the `settings_hash` of a block saved before v1.1
differs from the current one. `combined` is computed after the rows, inside the same time
budget, two more 5,000-run simulations (sharing the rows' "before" run); a size larger than the
number of rows is skipped. If that step fails, is cancelled or hits the budget, the block is
saved with its rows and **without** `combined` (a warning `max_pf_moves combined not computed`
is logged). `batch._moves_missing` treats a computed block whose `settings_hash` is not the
current one as missing, so the operator's `retry_missing_moves` dispatch re-runs pre-v1.1
blocks; `_attach_moves` already recomputes a reused prior result on a hash mismatch.

`after_pick_probabilities` (the viewer's full non-playoff slot odds after the move, same
length as `pick_probabilities`) and `after_playoff_probability` are what read-time pricing
needs. A failed or timed-out step saves **no block at all** (§13.5); `computed: false` with
`reason: "not_eligible"` means the team was not in the run. `free_agent_pool` makes the
re-solve reproducible for the backtest.

**Excluded candidates.** Players on reserve (not in either pool under `ir_maxpf: exclude`,
`provider.py:404-406`), and any player with no usable projection (`None`) in a week that is
not a verified bye (unknown is not zero, `season_points.py:39-55`). A week the provider says he
will not play (`availability: 0`) is a known zero, not unknown: that week's change is 0 and he
stays a candidate.

### 13.2 The re-solve (per player *p*, per week *w*)

Exactly exploration §7.1's formula, run in a new pure module
`backend/league_projections/maxpf_moves.py`, reusing `core.optimize`,
`core.free_agent_fill` and `core.idp_bye_fill` (`core.py:145`, `:197`, `:240`) with the same
arguments capture used (`provider.py:507-531`), on the pools rebuilt from the snapshot by
`season_points.player_points` and the week's `exclusions`/`replacement_means`, plus the kept
free agents. A week in which the user's team has any completed player
(`actual_score_observed`, a `locked_actual` lineup row or a `completed_game` input) is left
out (`status: "played"`, change 0) and counted in `weeks_excluded_played`: the job runs on
Tuesday before any game, so this is rare, and it avoids reconstructing locks. Parity proof
(build test): with nobody removed, the re-solve reproduces `modeled_actual_projection` and
`modeled_maxpf_projection` for every team-week it does not exclude, including free-agent
filled weeks.

### 13.3 The paired re-run

`cfg5 = {**result.config, "iterations": simulations_per_candidate}`; one `simulate(snapshot,
cfg5)` for "before" (shared by all candidates) and one per candidate on a copy of the
snapshot whose viewer team-weeks have `modeled_actual_projection` and
`modeled_maxpf_projection` lowered by `dA_w`, `dM_w`. Same seed, so an unchanged roster gives
a difference of exactly 0. "After" for every team = saved 250,000 figure + (after₅ₖ −
before₅ₖ), slot probabilities clamped at 0 and each team's row renormalised to the team's
"after" non-playoff probability. The "after" label ranks every team by "after" expected slot
with `pick_projection.slot_ranks`, strength tie-break from "after" expected win-equivalents.
`simulation.py` is not modified.

### 13.4 Capture side channel

`provider.capture(..., sidecar=None)` gains an optional keyword. When a dict is passed
(flag on, baseline run) capture writes into it, and nothing else changes:

- `sidecar["free_agents"][str(week)]`: for each slot type in the league's `slots`, the top
  `K` eligible free agents from the week's already-built `free_agents` list
  (`provider.py:357-373`) by `(points desc, player_id)`, `K = SIDECAR_EXTRA_SLOTS (1) + the
  most open slots of any team's lineup or max PF lineup that week` (every team, so the re-solve
  is exact for any roster, which the backtest needs). Removing one player shrinks a maximum
  assignment by at most one slot, so this always contains the free agents
  `core.free_agent_fill` would pick (`core.py:213-217`). No extra fetch: the list is already
  in memory.
- `sidecar["trade_deadline"]`: the league's `settings.trade_deadline` when it is an integer in
  1..98, else None (0, 99, absent or non-integer mean no deadline), from the league object
  capture already holds (`provider.py:232`). The service copies it into the block
  (`trade_deadline`); the read compares it with the run's `completed_weeks` (§4.1 row 3).
- `sidecar["names"]`: `{player_id: full name}` for every rostered player, from the player
  metadata capture already fetched (the snapshot's inputs carry no names).

The sidecar is never put in the snapshot, so `semantic_facts`, `input_hash`
(`store.py:172-181`), `snapshot_hash` (`simulation.py:334`) and every simulated number are
unchanged.

### 13.5 Never fail the forecast

The moves step (`service._attach_moves`) runs between `simulate` and `store.finish` and is
wrapped so that any exception, including `Unavailable` and a deadline hit, returns the forecast
result **without** a block (a warning naming `failed` or `time_budget` is logged, never the
exception text); the read then serves `unavailable` / `not_computed`. It stops at the earlier of
`time_budget_seconds` (setting) and 480 s after the job started (the job's own cancel line is
540 s, `service.py:83`). Its `simulate` calls get a `cancelled` callback that checks that
deadline and the job's lease (`_checkpoint`), so it still yields to foreground requests. When
`prior` is reused (`service.py:109`), the step runs only if the prior result has no block or a
different `settings_hash`.

## 14. Departures from the exploration, and code that contradicted it

| # | Exploration said | Contract does | Why / evidence |
|---|---|---|---|
| 1 | `band` = "the playoff band `home_tile_tapped` already carries" (§12) | `band` = `baseline.playoff_band`, the outlook classifier's band | `home_tile_tapped.band` is a per-POSITION seller/buyer/mid band, not a playoff band (`analytics_taxonomy.py:2084-2089`) |
| 2 | "Show all for the rest of the 8" | v1: only passing rows were listed. **v1.1 (D-261): all rows are listed again**, 5 then Show all | v1 reasoned a row below the threshold is inside the noise; a live 12-team check showed 6 of 12 teams saw nothing at all, so the operator chose to show the numbers and say plainly when none moves the pick on its own |
| 3 | Ranked label "not on main" (§2) | Uses `pick_projection.slot_ranks` | D-257 merged in `4a8cd70d` (`pick_projection.py:247-261`) |
| 4 | Find trades "puts the player on the give side" with the League Offer hand-off | Pins only; no auto-run | §12: auto-run needs an opponent or a new R1 source |
| 5 | Pick value formula cited at `pick_projection.py:203-211`, `pick_values.py:770-792` | Same formula | `factor` moved to `pick_projection.py:224-226`; `_projection_terms` is still `pick_values.py:770-791`; `priced_pool_value` starts `pick_values.py:812` |
| 6 | Playoff share spread "`pick_projection.py:123`" | Same rule | Now in `compact`, `pick_projection.py:134` |
| 7 | Points-view columns at `StandingsScreen.tsx:66-69` | n/a | `COL_WIDTH` is `StandingsScreen.tsx:62-64`; `VIEW_FOOT` is `:66-69` |
| 8 | Top-3 chance undefined as conditional or not | Unconditional: `sum(pick_probabilities[0:3])` | The pick is worth what it is worth across all worlds, the same basis D-240 prices on |
| 9 | Draft-order answer "asked once per league" | One stored answer per league; "Not sure" is remembered per device only | §7.1 |
| 10 | Pick value of the user's pick | Priced from this user's own run's distribution, with the league's live pricing knobs | The trade finder prices from the league's newest baseline from any user (`server.py:20900-20928`), which can be a different run; both use the same formula |
