# FB-413 — Phase 0 investigation: Send in Sleeper has no draft-pick handling

> Orchestrator's code trace (Explore agent, 2026-09-02) — input to the Phase 1 planner. File:line cites are against `origin/main` @ `ce3f443c`.

**Report (mattmurf77, 2026-08-30T15:38Z, v1.16.12):** "Send in sleeper isn't correctly identifying draft picks and causing trades with draft picks to fail."

## Verdict

The Sleeper send path **has no pick handling at all**. Picks ride the same `give_player_ids` / `receive_player_ids` arrays as players on every FTF surface, and the Sleeper route — unlike the MFL and ESPN routes, which both split/block — passes them through verbatim as Sleeper player ids. The `draft_picks` body key exists on the route and in `sleeper_write.py` but has **no producer anywhere in the codebase**. Nothing regressed; pick exposure on send-capable surfaces rose (standing offers lit 2026-08-26 are pick-for-player; per-slot pick pricing made picks first-class), so the tester hit it.

## Mobile hop

- `mobile/src/api/sendInSleeper.ts:26-33` `ProposeTradePayload` has no pick field; `:199-203` `proposeTradeToSleeper` → `POST /api/trades/propose`; `:226-238` `validateTradeSend` → `POST /api/trades/validate`.
- Body sent (`mobile/src/components/SendInSleeperButton.tsx:223-229`): `{league_id, their_user_id, give_player_ids[], receive_player_ids[], impression_id?}`.
- Pick ids inside those arrays, two shapes: owned pick `${league_id}_${season}_${round}_${original_roster_id}` (`backend/database.py:9756-9766` `make_pick_id`; `mobile/src/screens/TradesScreen.tsx:4442-4447`; `mobile/src/components/InLeagueCalculator.tsx:493-509` as a `CalcPlayer` with `pos: 'PICK'`), and generic ladder rung `generic_pick_{round}_{tier}` (`backend/pick_values.py:213-217`).
- Four mounts pass mixed arrays through unfiltered: deck `TradesScreen.tsx:8351-8359`; Matches `TradeCard.tsx:978-984`; Awaiting `TradeCard.tsx:1000-1006`; calculator `InLeagueCalculator.tsx:1467-1478`.
- Failure telemetry: `SendInSleeperButton.tsx:245-258` emits `sleeper_send_failed` with `error_code` (closed enum, `backend/analytics_taxonomy.py:1056`).

## Backend hop

- `POST /api/trades/propose` `backend/server.py:16155-16277`: `:16192-16194` reads `give`/`receive`/`picks` (`picks` only from a `draft_picks` key nobody sends); `:16228-16232` builds `ProposeTradeRequest(..., draft_picks=picks or None)` — no split, no `_is_ftf_pick_asset`, no encode. Roster resolution `:16211-16225` via `_roster_id_for_owner` (`:15965-15983`, co-owner-aware); only my/their roster ids — the pick's original-owner roster is never looked up.
- `backend/sleeper_write.py:224-231` `draft_picks` = pre-encoded `"orig,season,round,from,to"`; `:233-235` `_is_valid_pick_str` (5 comma parts, integer-ish); `:266-322` `build_propose_trade_body` puts every id in `give/receive_player_ids` into `k_adds`/`k_drops` as a raw Sleeper player id (`:294-301`), picks inlined separately at `:311`.
- Precedents that DO handle picks: MFL `backend/server.py:28186-28215` (split via `_is_ftf_pick_asset`, encode via `_mfl_encode_ftf_picks`, 422 `mfl_asset_unmapped` on misses; helpers `:27892-27962`); ESPN `:28625-28645` (422 `espn_pick_unsupported`).
- Engine/DB: picks injected as roster pseudo-assets under `trade.picks_in_pool` (`backend/trade_optimizer.py:880-883`; flag **true**). `draft_picks` table `backend/database.py:1092-1125`: for Sleeper `original_roster_id` IS a Sleeper roster_id (`:1099`), `owner_user_id` is a user_id. Public source for the traded-pick truth: `_fetch_sleeper_traded_picks` (`:13894-13908`).

## Ranked root causes

1. **No pick split in the Sleeper propose route** (`server.py:16192-16232`) → pick ids reach Sleeper as player keys → GraphQL rejects → `SleeperWriteError` → 502 `sleeper_write_failed` → generic "Couldn't send" (`SendInSleeperButton.tsx:296-300`). = "trades with draft picks fail".
2. **The pre-send validator flags every pick as a moved player** (`server.py:27798-27810`: `moved_give = [p for p in give if p not in my_players]`; `roster.players` never holds pick ids) → blocking `player_moved` warning → "This trade will likely fail" (`SendInSleeperButton.tsx:326-338`). Also pollutes `roster_limit` math `:27812-27831`. = "isn't correctly identifying draft picks".
3. **No encoder exists** for the `"orig,season,round,from,to"` shape anywhere.
4. **Generic rungs** (`generic_pick_1_early`) name no concrete Sleeper pick — must hard-block (MFL/ESPN precedent), never silently drop.
5. **Missing `orig`/current-holder resolution** for picks traded before: `from` must be the current holder verified against `traded_picks`.

Not causes: co-owned rosters (`server.py:15966-15977` handles), season parsing (`_ftf_pick_parts` `:27892-27901`), slot labels (display-only, `TradesScreen.tsx:4444-4446`).

## Test coverage today

- `backend/tests/test_sleeper_write.py:134-160` — adapter-only pick tests (`"11,2026,1,1,2"` valid; garbage rejected).
- `backend/tests/test_sleeper_write_route.py:273-292` — the only route test passing `draft_picks`, with **`["2027_1"]`**, a string the adapter would reject; passes only because `propose_trade` is `MagicMock`ed. **False confidence — fix this fixture.**
- `backend/tests/test_trade_send_validate.py` — zero "pick" occurrences.
- Mirrors to copy: `backend/tests/test_mfl_propose_route.py`, `backend/tests/test_espn_propose_route.py:204,217`.

## Functions to change (candidate)

1. `propose_trade_to_sleeper` `server.py:16155` (`:16192-16232`): split, encode owned picks, hard-block generic/unresolvable with 422 `sleeper_pick_unmapped` (+ `picks[]`), mirroring MFL.
2. NEW `_sleeper_encode_ftf_picks(league_id, pick_ids, my_rid, their_rid)` beside `_mfl_encode_ftf_picks` (`:27937`): `"{original_roster_id},{season},{round},{from_rid},{to_rid}"`, ground-truthed against `load_draft_picks` + `_fetch_sleeper_traded_picks` — never client-supplied.
3. `trades_validate` `server.py:27715` (`:27798-27831`): split picks before `player_moved`/`roster_limit`; add a pick-ownership check.
4. Mobile: `sleeper_pick_unmapped` branch in `SendInSleeperButton.tsx:279-305`; register the code in the closed enum (`analytics_taxonomy.py:1056`).
5. Tests: fix `test_sleeper_write_route.py:288`; pick cases in `test_trade_send_validate.py`; route tests mirroring MFL.
