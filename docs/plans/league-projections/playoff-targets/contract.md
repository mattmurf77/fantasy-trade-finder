# Playoff targets: the build contract (v1)

> The one contract the backend and the app both code against. Written 2026-11-14 against
> `origin/main` `f0ab507b`. Scope block and the operator's open choices: [scope.md](scope.md).
> It is the mirror of Max PF moves and borrows its vocabulary; where this file says "as Max PF
> moves", the rule is in [../max-pf-trade-away/contract.md](../max-pf-trade-away/contract.md).
> Names in examples are invented.
>
> If the code and this file disagree after build, `docs/api-reference.md` and
> `docs/data-dictionary.md` win and this file gets a correction note.

- [1. Summary](#1-summary)
- [2. The eligibility rule](#2-the-eligibility-rule)
- [3. The `playoff_targets` block](#3-the-playoff_targets-block)
- [4. States](#4-states)
- [5. Example payloads](#5-example-payloads)
- [6. What is saved with the run (backend only)](#6-what-is-saved-with-the-run-backend-only)
- [7. What the app derives versus reads](#7-what-the-app-derives-versus-reads)
- [8. Flag behaviour](#8-flag-behaviour)
- [9. Analytics](#9-analytics)
- [10. Copy](#10-copy)
- [11. Formatting rules](#11-formatting-rules)
- [12. The Find trades hand-off](#12-the-find-trades-hand-off)

## 1. Summary

- For the viewer's own team: which players, if acquired, raise the team's playoff chance the
  most, shown as playoff chance now → after per player.
- One new top-level key, `playoff_targets`, on the forecast read the app already downloads
  (`GET /api/leagues/<league_id>/projection-runs/latest`). Present only while flag
  `league.playoff_targets` is on. `version: 1`. No new route, no new table, no new column.
- The heavy numbers are computed in the weekly forecast job and saved inside the run's
  `result_json` under `playoff_targets`. That raw saved block never leaves the server: every
  read strips it from `run.result` (flag on or off), as it does Max PF moves' block.
- **What the number is.** The player joins the viewer's roster and leaves his own. Nothing the
  viewer gives up is modelled, and the other team gets no starter back. It is not a trade
  evaluation: a real trade costs something, so the true gain is usually smaller. The copy says
  so (C-FOOT). This is the mirror of Max PF moves, which removes a player and models no return.
- No new screen, no navigation entry, no new FeedbackFAB. The section is a fifth disclosure
  inside the user's own open team card on Standings, after "Max PF moves".

## 2. The eligibility rule

A player is suggested only when his team is **selling**. A team is selling when at least one
holds (`playoff_targets.is_seller`, the one definition):

1. its playoff probability in this forecast run is **strictly below 0.5**, on the unrounded
   value (`result.teams[].playoff_probability`); or
2. its manager's **saved** outlook is Rebuilding (`rebuilder`); or
3. its manager's **saved** outlook is Tanking (`jets`).

"Saved" is `league_preferences.team_outlook` for the roster's owner, or failing that a
co-owner, looked up by Sleeper user id (the lookup the trade engine uses for a league-mate's
declared outlook). An **inferred** outlook (`partner_outlook`'s projection or roster read)
never counts: the projection read is `rebuilder` at or below 45%, which rule 1 already covers,
and the roster read is a guess.

**Where it runs.** Twice:

| When | With | Effect |
|---|---|---|
| Weekly job (`playoff_targets.compute`) | this run's probabilities and the outlooks saved at that moment | chooses which teams' players are candidates; saves each other team's `eligible` flag and owner ids |
| Every read (`playoff_targets.compose`) | the same run's probabilities and the outlooks saved **now** (one bulk read) | drops every row whose team is not selling now; `eligible_teams` counts the teams selling now |

Rule 1 cannot change between the job and the read (same run). Rules 2 and 3 can. A team that
stopped selling loses its rows at once. A team that started selling after the job has no rows
until the next weekly forecast; `sellers_changed` is then true and the app says so (C-CHANGED).

**What a row gives away.** The block never carries a league-mate's saved outlook or the rule
that made a team eligible. A row for a team at or above 50% does imply that its manager saved
Rebuilding or Tanking; that follows from the rule itself (scope §0, choice P2).

## 3. The `playoff_targets` block

Types are TypeScript-style. Probabilities are 0..1, unrounded; points are fantasy points.
S = computed in the weekly job and saved with the run; R = computed when the page is read.

### 3.1 Top level

| Field | Type | Null? | S/R | Meaning |
|---|---|---|---|---|
| `version` | `1` | no | R | An app that does not know the version renders nothing |
| `state` | `PlayoffTargetsState` (§4) | no | R | What the section shows. Server-decided |
| `reason` | `string` | yes | R | Only with `unavailable`; §4.2. An open set |
| `viewer_roster_id` | `number` | yes | S | Null when `state` is `unavailable` for any reason but `not_computed` |
| `captured_at` | ISO-8601 string | yes | S | The forecast's capture time. Null exactly when `viewer_roster_id` is |
| `saved_outlook` | `'championship' \| 'contender' \| 'rebuilder' \| 'jets' \| 'not_sure' \| null` | yes | R | The viewer's own saved outlook, for the default-open rule (§7.1) |
| `baseline` | `Baseline` (§3.2) | yes | S+R | Null for `unavailable`, `season_over`, `after_trade_deadline` |
| `eligible_teams` | `number` | no | R | Teams selling now (§2). 0 before that step is reached |
| `sellers_changed` | `boolean` | no | R | The set of selling teams differs from the one the job used |
| `candidates_total` | `number` | no | S | Players on selling teams whose addition raised the viewer's projected lineup (before the top-8 cut) |
| `rows` | `TargetRow[]` (§3.3) | no | S+R | At most `candidates` (8), ordered by `rank`. Empty unless `state` is `ready` or `no_targets`. Includes rows that fail the threshold |

### 3.2 `Baseline`

| Field | Type | S/R | Meaning |
|---|---|---|---|
| `weeks_remaining`, `first_week`, `last_week` | `number` | S | Regular-season weeks the forecast still simulates |
| `weeks_excluded_played` | `number` | S | Weeks left out of the viewer's re-solve because one of the viewer's players had already played |
| `playoff_probability` | `number` | S | The viewer's playoff chance in this run |
| `playoff_band` | `'jets' \| 'rebuilder' \| 'contender' \| 'championship'` | R | `recommendation.classify`. Analytics only |
| `playoff_clinched`, `playoff_eliminated` | `boolean` | S | D-262 proof for the viewer's team. False when not proven |

### 3.3 `TargetRow`

| Field | Type | S/R | Meaning |
|---|---|---|---|
| `rank` | `number` | S | 1..N by playoff gain (`after − now`), largest first; ties by lineup gain, then player id |
| `player_id`, `name`, `short_name`, `position` | `string` | S | As Max PF moves |
| `lineup_gain` | `number` (integer) | S | Projected lineup points the viewer adds over the unplayed weeks with him on the roster, half away from zero |
| `lineup_gain_exact` | `string` | S | The same, two decimals |
| `weeks_affected` | `number` | S | Weeks in which the viewer's projected lineup total changes |
| `replaces` | `Replaced[]` | S | Who leaves the viewer's starting lineup for him, most weeks first, at most 3: `{player_id, name, short_name, free_agent, weeks}`. `player_id: null` is a slot nobody held |
| `replaces_more` | `number` | S | How many more there are beyond the 3 |
| `playoff_probability` | `{now: number, after: number}` | S | The viewer's playoff chance. `after > now` on every saved row |
| `passes_threshold` | `boolean` | S | `after − now ≥ min_playoff_gain` (0.01) |
| `seller` | `Seller` | S+R | `{roster_id, name, playoff_probability, playoff_clinched, playoff_eliminated}`: the team he is on, its name and playoff chance in this run. Never an outlook |

## 4. States

### 4.1 Server states (`state`)

Checked in order; the first that applies wins.

| # | `state` | When | `baseline` | `rows` |
|---|---|---|---|---|
| 1 | `unavailable` | The forecast is not usable (`recommendation.unusable_reason`), the viewer's team is not in the run, or the run has no computed block (§4.2) | null | `[]` |
| 2 | `season_over` | `weeks_remaining == 0` | null | `[]` |
| 3 | `after_trade_deadline` | The league's trade deadline week is set and `completed_weeks ≥ trade_deadline` (Max PF moves' rule) | null | `[]` |
| 4 | `clinched` | The viewer's `playoff_clinched` is proven | set | `[]` |
| 5 | `eliminated` | The viewer's `playoff_eliminated` is proven | set | `[]` |
| 6 | `near_certain` | `baseline.playoff_probability ≥ near_certain_min` (0.99) | set | `[]` |
| 7 | `no_sellers` | No other team is selling now (§2) | set | `[]` |
| 8 | `no_targets` | No served row has `passes_threshold` | set | every served row (may be empty) |
| 9 | `ready` | Otherwise | set | every served row |

The job skips its simulations for 2 to 7 as it sees them (§6.3); the read decides the state
from the same saved figures, so the two agree.

### 4.2 `reason` values (only with `unavailable`)

`no_forecast`, `update_pending`, `refresh_failed`, `stale`, `old_model`, `incomplete`,
`team_not_found`, `unsupported`, `missing_projections`, `read_failed`: the existing vocabulary
of `recommendation.unusable_reason`, same meanings. `not_computed`: the run is usable but
carries no block (the flag was off at save time, or the step failed or timed out, §6.4).

## 5. Example payloads

### 5.1 `ready`

```json
{
  "playoff_targets": {
    "version": 1,
    "state": "ready",
    "reason": null,
    "viewer_roster_id": 7,
    "captured_at": "2026-11-10T14:31:02+00:00",
    "saved_outlook": "contender",
    "baseline": {
      "weeks_remaining": 4, "first_week": 11, "last_week": 14, "weeks_excluded_played": 0,
      "playoff_probability": 0.62, "playoff_band": "contender",
      "playoff_clinched": false, "playoff_eliminated": false
    },
    "eligible_teams": 5,
    "sellers_changed": false,
    "candidates_total": 41,
    "rows": [
      {
        "rank": 1, "player_id": "9001", "name": "Rhett Sato", "short_name": "R. Sato", "position": "RB",
        "lineup_gain": 31, "lineup_gain_exact": "31.20", "weeks_affected": 4,
        "replaces": [
          {"player_id": "9104", "name": "Cal Mercer", "short_name": "C. Mercer", "free_agent": false, "weeks": 3},
          {"player_id": null, "name": null, "short_name": null, "free_agent": false, "weeks": 1}
        ],
        "replaces_more": 0,
        "playoff_probability": {"now": 0.62, "after": 0.71},
        "passes_threshold": true,
        "seller": {"roster_id": 3, "name": "Harbor Kings", "playoff_probability": 0.12,
                   "playoff_clinched": false, "playoff_eliminated": false}
      },
      {
        "rank": 2, "player_id": "9002", "name": "Dale Okafor", "short_name": "D. Okafor", "position": "WR",
        "lineup_gain": 6, "lineup_gain_exact": "6.40", "weeks_affected": 2,
        "replaces": [
          {"player_id": "9210", "name": "Ezra Quill", "short_name": "E. Quill", "free_agent": true, "weeks": 2}
        ],
        "replaces_more": 0,
        "playoff_probability": {"now": 0.62, "after": 0.624},
        "passes_threshold": false,
        "seller": {"roster_id": 9, "name": "Team 9", "playoff_probability": 0.66,
                   "playoff_clinched": false, "playoff_eliminated": false}
      }
    ]
  }
}
```

### 5.2 `unavailable`

```json
{
  "playoff_targets": {
    "version": 1, "state": "unavailable", "reason": "stale", "viewer_roster_id": null,
    "captured_at": null, "saved_outlook": null, "baseline": null,
    "eligible_teams": 0, "sellers_changed": false, "candidates_total": 0, "rows": []
  }
}
```

### 5.3 `near_certain`

```json
{
  "playoff_targets": {
    "version": 1, "state": "near_certain", "reason": null, "viewer_roster_id": 7,
    "captured_at": "2026-11-10T14:31:02+00:00", "saved_outlook": "championship",
    "baseline": {
      "weeks_remaining": 4, "first_week": 11, "last_week": 14, "weeks_excluded_played": 0,
      "playoff_probability": 0.9972, "playoff_band": "championship",
      "playoff_clinched": false, "playoff_eliminated": false
    },
    "eligible_teams": 0, "sellers_changed": false, "candidates_total": 0, "rows": []
  }
}
```

## 6. What is saved with the run (backend only)

The app never sees this shape.

### 6.1 Location and shape

`result_json["playoff_targets"]`, written only for `kind == "baseline"` runs while the flag is
on, by `playoff_targets.compute` (pure):

```
{ "version": 1, "computed": true | false, "reason": null | "not_eligible",
  "settings": {simulations_per_candidate, candidates, min_playoff_gain, near_certain_min,
               time_budget_seconds},
  "settings_hash": sha256 of settings,
  "viewer_roster_id", "trade_deadline": int | null,
  "baseline": {weeks_remaining, first_week, last_week, weeks_excluded_played},
  "sellers": { "<roster_id>": {name, playoff_probability, eligible: bool, owner_ids: [str]} },
  "skipped": null | "season_over" | "after_trade_deadline" | "clinched" | "eliminated"
             | "near_certain" | "no_sellers",
  "pool_size": int, "candidates_total": int,
  "rows": [ {rank, player_id, name, short_name, position, seller_roster_id, lineup_gain,
             lineup_gain_exact, weeks_affected, replaces, replaces_more,
             playoff_probability, passes_threshold} ],
  "elapsed_ms": int }
```

`sellers` has one entry per other team, selling or not. `eligible` is the §2 rule with the
outlooks saved when the job ran; the outlook itself is not saved. `owner_ids` are the roster's
Sleeper owner and co-owner ids, which the read uses to look the outlooks up again.

### 6.2 The two steps

Reuses Max PF moves' lineup builder (`maxpf_moves._Context.lineups`, which gains an `add`
argument), its snapshot shift (`_lowered`) and its anchoring of every "after" to the saved
250,000-run figure (`_after_teams`). `maxpf_moves.compute` and its saved block are unchanged.

1. **Every player on a selling team** (`players` and taxi; reserve left out under
   `ir_maxpf: exclude`; a player with no usable projection in an unplayed week that is not a
   verified bye is left out, unknown is not zero): the exact re-solve of the viewer's lineup
   with him added as an active player, summed over the weeks the viewer has not played. A week
   is skipped without a re-solve when the viewer's lineup is full of rostered players and he
   projects no higher than its lowest starter; this cannot change the answer (a test compares
   the two for every player in the fixture league). Players with a total gain above 0 are the
   candidates (`candidates_total`).
2. **The `candidates` (8) largest gains**, ties by player id: the same re-solve for both lanes
   (lineup and max PF), then Max PF moves' removal re-solve for his own team, then one
   `simulations_per_candidate` (5,000) run on a snapshot with the viewer's team-weeks raised and
   his team's lowered. One shared "before" run, same seed. A row is saved only when
   `after > now`; rows are then ranked by `after − now`.

Step 1 orders by projected lineup points, not by playoff chance, so a player outside the top 8
by points is never re-simulated even if his team's schedule would have made him matter more.

### 6.3 Skipped work

When the viewer's weeks are over, the trade deadline has passed, the viewer has clinched or
is eliminated, the viewer's chance is at or above `near_certain_min`, or no team is selling,
the block is saved `computed: true` with `skipped` set and no rows, and no simulation runs.

### 6.4 Never fail the forecast

`service._attach_targets` runs after Max PF moves' step and before `store.finish`, wrapped so
that any exception, a deadline hit included, returns the forecast result without a block (a
warning naming `failed` or `time_budget`, never the exception text); the read then serves
`unavailable` / `not_computed`. It stops at the earlier of its own `time_budget_seconds` (60)
and 480 s after the job started, the line Max PF moves uses. Max PF moves runs first, so this
step can never take time from it. When a prior result is reused, the step runs again only if
the prior block is missing, was made under other settings, or the set of selling teams has
changed.

### 6.5 Capture side channel

`provider.capture(..., sidecar=)` also writes `sidecar["owners"]`:
`{"<roster_id>": [owner_id, co_owner_ids...]}` from the rosters it already fetched. Like the
rest of the side channel it never enters the snapshot. The job passes a side channel when
either `league.max_pf_moves` or `league.playoff_targets` is on.

## 7. What the app derives versus reads

The app reads everything in §3 and never re-computes a number. It derives only these.

### 7.1 Open or closed by default

```
startsOpen = state is 'ready' or 'no_targets'
             && baseline.playoff_probability > 0.45
             && saved_outlook !== 'rebuilder' && saved_outlook !== 'jets'
```

The exact complement of Max PF moves' default-open rule (its §6.1), so on a card with both
sections one starts open and the other closed. There is no inner "Show" gate.

### 7.2 Rosters changed since the forecast

The page's `['league-rosters', leagueId]` query gives every team's live roster. A row is
dropped when its `seller.roster_id` is not in the live rosters or that roster no longer holds
`player_id`. When any row is dropped, C-ROSTER shows above the list. When the query has not
loaded, the check is skipped.

### 7.3 Which rows are listed

Every served row, passing or not, in `rank` order after §7.2. The first 5 show; "Show all"
reveals the rest. When no listed row passes, C-NONE-ALONE shows above the list. With no rows
listed: C-NO-TARGETS, unless §7.2 dropped them all (then C-ROSTER alone).

## 8. Flag behaviour

Flag `league.playoff_targets`: default False in `backend/feature_flags.py`, `false` in
`config/features.json` with a `_comment_` line, mirrored `false` in the three flag fixtures.
Requires `league.projections`.

| Path | Flag off | Flag on |
|---|---|---|
| `GET .../projection-runs/latest` | No `playoff_targets` key; `run.result` / `attempt.result` carry no `playoff_targets` key | Adds `playoff_targets` |
| `GET /api/projection-runs/<id>`, `/cancel` | The raw saved block is never served | Same |
| Weekly job | No extra work, no outlook read; capture is called without a side channel unless Max PF moves needs one | Capture fills the side channel; the step runs for fresh baseline runs |
| Stored `snapshot_json`, `input_hash`, `snapshot_hash`, `model_version` | Unchanged | Unchanged |
| App | Section not rendered | §7 |

The app mounts the section only when `useFlag('league.playoff_targets')` is on **and** the
block is present.

## 9. Analytics

Emitted by the app through `track()`, screen `'Standings'`. Registered in
`backend/analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS` in
the same commit as the emitter. No player id or name in any property.

| Event | Fires when | Properties | Class |
|---|---|---|---|
| `playoff_targets_viewed` (new) | The section body becomes visible, once per opening of the user's own card | `state` → the server `state` verbatim; `n_listed` → rows listed after §7.2 (integer ≥ 0); `any_pass` → a listed row passes (boolean); `n_sellers` → `eligible_teams` (integer ≥ 0); `band` → `baseline.playoff_band`, or `none` | Impression: `NON_INTENT_EVENTS` |
| `playoff_target_expanded` (new) | A listed row is opened | `position` → the row's `position`; `rank` → the row's `rank` (1..8) | Intent |
| `finder_target_pinned` (existing) | "Find trades for [player]" is tapped | `side` → `receive`; `source` → `playoff_targets` (new value) | Intent, already registered |

## 10. Copy

The app uses these strings verbatim. `{…}` are fills formatted per §11.

| Id | Where | String |
|---|---|---|
| C-TITLE | Disclosure label | `Playoff targets` |
| C-BASE | Baseline line, `ready` / `no_targets` | `Your playoff chance today: {playoff}.` |
| C-HEAD | Above the rows | `Lineup points added over the remaining {n} weeks` (n = 1 → `over the final week`) |
| C-ROW-1 | Row, line 1 | `{short_name}  {position}  {lineup_gain}` |
| C-ROW-2 | Row, line 2 | `Playoff chance {now} → {after}` |
| C-ROW-3 | Row, line 3 | `{team} · {playoff} playoff chance` |
| C-OPEN-WEEKS | Opened row | `Starts for you in {k} of the remaining {n} weeks.` (n = 1 → `Starts for you in the final week.`) |
| C-REPL-1 | Opened row, one player replaced in every affected week | `Starts over {name}.` |
| C-REPL-N | Opened row, several | `Starts over {name1} ({w1} weeks), {name2} ({w2} weeks).` up to 3 names, then ` and {k} more.` from `replaces_more`; `1 week` singular |
| C-REPL-FA | A free-agent name | `{name} (free agent)` |
| C-OPEN-SPOT | Opened row, a `replaces` entry with null `player_id` | `Fills an open lineup spot ({w} weeks).` |
| C-SHOWALL | Under the 5th row | `Show all` |
| C-BUTTON | Opened row | `Find trades for {short_name}` |
| C-FOOT | Under the list | `Each number assumes you give up only picks or players who would not start for you, and that the other team gets no starter back. A real trade costs something, so the true gain is usually smaller.` |
| C-ELIGIBLE | Under C-FOOT | `Only players on teams with a playoff chance under 50% in this forecast, or whose manager set a Rebuilding or Tanking outlook, are listed.` |
| C-CHANGED | Above the list, `sellers_changed` | `A team's outlook changed after this forecast. The list updates with the next weekly forecast.` |
| C-ROSTER | Above the list (§7.2) | `Rosters changed after this forecast. The list updates with the next weekly forecast.` |
| C-NO-TARGETS | A list state with no rows served | `No single player on those teams raises your playoff chance.` |
| C-NONE-ALONE | Above the list when no listed row passes | `None of these raises your playoff chance by a visible amount on its own.` |
| C-NO-SELLERS | `no_sellers` | `No other team has a playoff chance under 50% or a Rebuilding or Tanking outlook right now.` |
| C-CLINCHED | `clinched` | `You have clinched a playoff spot.` |
| C-ELIMINATED | `eliminated` | `Your team can no longer make the playoffs.` |
| C-NEAR-CERTAIN | `near_certain` | `Your team makes the playoffs in {playoff} of simulations, so no trade raises that by a visible amount.` |
| C-DEADLINE | `after_trade_deadline` | `Your league's trade deadline has passed.` |
| C-SEASON-OVER | `season_over` | `The regular season is over, so no trade can change your playoff chance.` |
| C-U-no_forecast | `unavailable` | `There is no saved forecast for this league yet.` |
| C-U-update_pending | | `A new forecast is being prepared. Playoff targets return when it is saved.` |
| C-U-refresh_failed | | `The latest forecast update failed. Playoff targets return after the next successful update.` |
| C-U-stale | | `The saved forecast is from an earlier week. Playoff targets return after the next weekly update.` |
| C-U-old_model | | `The saved forecast was made by an earlier version of the model. Playoff targets return after the next update.` |
| C-U-incomplete | | `This forecast is incomplete, so playoff targets are not shown.` |
| C-U-team_not_found | | `Your team could not be matched to the saved forecast.` |
| C-U-unsupported | | `Forecasts are not available for this league.` |
| C-U-missing_projections | | `The projection source had no projections for an upcoming week, so there is no new forecast.` |
| C-U-read_failed | | `The saved forecast could not be read just now.` |
| C-U-not_computed | | `Playoff targets are worked out with the weekly forecast. They appear after the next update.` |
| C-U-other | Unknown `reason` | `Playoff targets are not available right now.` |

## 11. Formatting rules

| Value | Rule | Example |
|---|---|---|
| Lineup gain | Whole number from the integer field, leading `+`; exactly 0 as `0`; a negative with U+2212 | `+31` |
| Playoff chance | D-262's rule (`utils/playoffOdds.playoffOddsText`, whole percents): the viewer's with the baseline's proof, a team's with that team's proof | `62% → 71%`, `>99%` |
| Arrows | ` → ` (U+2192, spaces either side) | |
| Team name | Verbatim from the server | `Harbor Kings` |

## 12. The Find trades hand-off

On "Find trades for {short_name}". It pins the **receive** side, the mirror of Max PF moves'
give-side pin (its §12):

```ts
const store = useFinderTargets.getState();
store.setSide('receive', [{ id: row.player_id, name: row.name, position: row.position }]);
store.setSide('give', []);
track('finder_target_pinned', { side: 'receive', source: 'playoff_targets' }, 'Standings');
navigation.popTo('Main', { screen: 'Trades', params: { screen: 'TradesHome',
  params: { canvasPrefill: { opponentId, give: [], receive: [row.player_id] },
            canvasPrefillSeq: Date.now() },
  pop: true } });
```

- `opponentId` is the `owner_id` of the live roster whose `roster_id` is `seller.roster_id`
  (§7.2's query). The canvas needs the partner to show a receive-side player, the way
  MatchesScreen's "edit in calculator" sends one. The button is not rendered when that owner
  cannot be resolved (the rosters have not loaded, or the roster has no owner).
- It replaces both sides, so an old pin cannot ride along unseen.
- No `setHandoff`, no auto-run: nothing runs until the user taps Find a Trade.
- The same known limitation as Max PF moves: with `calc.inline_home` off, TradesScreen ignores
  the prefill.
