# Code walk — from the forecast row to the label on the app row (D-257)

This walk traces the code on branch `feat/projected-pick-rank`, cut from `origin/main` 53711036. Line numbers are taken from that branch.

## 1. The forecast writes what the rank needs

`backend/league_projections/simulation.py:279-283` sets the non-playoff draft order in each simulated world (lowest max PF gets slot 1) and counts `pick_counts`. For each team, `simulation.py:293-303` writes:

- `pick_probabilities`
- `playoff_probability`
- `expected_record` ([W, L, T] means, line 295)

The run is stored as `league_projection_runs.result_json`.

## 2. The server reads one run per league

`backend/server.py:20901` `_load_pick_projection_summary` takes the newest complete baseline run for the league from any user and calls `pick_projection.compact` on it (`server.py:20925`). `server.py:20931` `_league_pick_projection` caches that summary and applies the gates and knobs through `pick_projection.usable` (`server.py:20958`). Neither function changed.

## 3. `compact` builds the distribution and the rank, once per run

In `backend/pick_projection.py:98` `compact`:

- line 134 builds each team's slot distribution: the non-playoff probabilities, then the playoff probability spread evenly over the playoff slots. This is unchanged and is what the price reads.
- lines 140-142 read the team's `expected_record` through `_win_equivalents` (line 233), giving W + ½T, or None when the record is absent or malformed. A missing record never rejects the run, so pricing gates are unchanged.
- line 150 stores `slots=slot_ranks(dists, strength)` on the `RunSummary`.

`pick_projection.py:247` `slot_ranks` sorts the teams by `(round(E, 9), win-equivalents, roster id)` (line 259) and numbers them 1..N. Strength is dropped for the whole run unless every team has it. `usable` (line 199) carries `slots` onto the `PickProjection`. The key at lines 189-191 already identifies the run, and through the run everything the rank reads.

## 4. One function names the slot

- `pick_projection.py:264` `projected_slot(projection, original_roster_id)` returns `projection.slots[str(original_roster_id)]` (line 270). It reads the ORIGINAL roster, never the holder, so a traded pick shows its original team's rank.
- `backend/pick_values.py:794` `projected_pick_slot` is the only caller. It first requires that the price applied the projection (`market_pick_pool_value` and `_projection_terms`, lines 801-807), so a pick priced generic has no label. Then it returns `projected_slot(...)` (line 809).
- Pricing (`pick_values.py:770` `_projection_terms`, `:886` in `priced_pool_value`) reads `projection.dists` through `pp.distribution` / `pp.factor` and never reads `projection.slots`.

`git grep -n "projected_pick_slot\|projected_slot("` lists every reader. Outside tests, the only caller of `projected_pick_slot` is `server.py:20551`.

## 5. The server composes the name, and every surface shares it

- `backend/server.py:20539` `_owned_pick_name`: a real D-090 slot wins. Otherwise `projected_pick_slot` (line 20551) is formatted by `pick_slots.slot_suffix` as `"1.<NN>"`.
- `server.py:20503` `_owned_pick_label` adds `" · projected"`. `server.py:20562` `_owned_pick_projection_fields` returns `{"proj_slot", "proj_name"}` (line 20571).

Every surface that shows a projected pick name goes through those two functions:

| Surface | Site |
|---|---|
| League → team → Picks (power rankings `teams[].picks.items[]`) | `server.py:39890` `_power_picks_by_owner` → `:39960-39961` → `backend/power_rankings.py:315-320` copies `label`, `proj_slot`, `proj_name` |
| `GET /api/league/picks` rows | `server.py:20487-20488` |
| Deck cards and calculator assets (`player_to_dict`) | `server.py:1189-1190` (`_owned_pick_assets`) → `Player.proj_slot` / `proj_name` (`ranking_service.py:278-279`) → `server.py:15512` |
| `/api/trade/evaluate` eveners | `server.py:21132-21140` |
| Matches name arrays, OG card labels | `server.py:20650` `_pick_labels_by_id`, `:34366` |
| Team overhaul assets | `server.py:46531-46534` → `backend/overhaul_api.py:479-481` |

`blind_grading.pick_label` is a slot-free mirror and never shows a projected slot.

## 6. The app prints the server's string

- `mobile/src/screens/LeagueSummaryScreen.tsx:2353-2371`: Draft capital rows call `projectedPick(p)` and print `proj.name` with `ProjectedPickTag`.
- `mobile/src/utils/projectedPick.ts:54-63` only validates the pair (`PROJ_SLOT_RE`, length ≤ 60). It never composes or parses a slot.
- Every other app surface (`PlayerCard`, `TradeSide`, `PlayerPickerModal`, `TradeCard`, `InLeagueCalculator`) goes through the same helper.
- Web (`web/js`) and the extension do not read `proj_slot`/`proj_name`. Web prints the server's `label`, which carries the same rank.

## 7. What the change cannot reach

- **Prices.** `test_values_are_byte_identical_to_before_the_rank` compares the 12 values with those captured from `origin/main`'s own `pick_projection.py`/`pick_values.py`.
- **Stored deck pages.** Their `engine_version` hashes `pick_projection.py` and `pick_values.py` (`server.py:4861-4869`), so pages built before the deploy are not served after it.
- **The Standings "Expected pick if this team misses" line** (`mobile/src/components/LeagueProjectionDetail.tsx:44`, `web/js/league-projections.js:70`). It reads `conditional_expected_pick`, which this change does not touch.
