# Plan G-413 — Send in Sleeper: server-side draft-pick split + encode, pick-aware validate

> Phase 1 Planner output (2026-09-02). Cites are against the worktree at `9b579ca3` (origin/main `ce3f443c` + the Phase 0 triage commit; no code in the cited regions moved between the two). Work-type: FEATURE, full gates — the Author produces `hld-delta.md`, `lld-delta.md`, `prd.md`, `scope.md`.

## 1. Problem statement and the user-visible failure sequence

Feedback #413 (mattmurf77, v1.16.12, `TradesHome`): "Send in sleeper isn't correctly identifying draft picks and causing trades with draft picks to fail."

Every FTF trade surface carries picks in the same arrays as players. The four `SendInSleeperButton` mounts forward mixed arrays verbatim: deck `mobile/src/screens/TradesScreen.tsx:8351-8355`, Matches `mobile/src/components/TradeCard.tsx:978-982`, Awaiting `TradeCard.tsx:1000-1004`, calculator `mobile/src/components/InLeagueCalculator.tsx:1467-1471` (owned picks enter the calculator pool as `CalcPlayer{id: pick_id, pos:'PICK'}` at `InLeagueCalculator.tsx:493-509`). Two pick-id shapes exist: owned `{league}_{season}_{round}_{original_roster}` (`backend/database.py:9756-9765` `make_pick_id`) and generic rung `generic_pick_{round}_{tier}` (`backend/pick_values.py:213`).

The failure the tester sees, in order:

1. Tap Send → `confirmSend` calls `POST /api/trades/validate` (`SendInSleeperButton.tsx:318-325`). The route computes `moved_give = [p for p in give if p not in my_players]` against `roster.players` (`backend/server.py:27797-27800`), which never contains a pick id, so every pick becomes a `player_moved` **blocking** warning (`:27801-27808`) and pollutes the `roster_limit` arithmetic (`:27819-27832`). The client renders "This trade will likely fail" with Cancel / Send anyway (`SendInSleeperButton.tsx:328-338`). This is the "isn't correctly identifying draft picks" half.
2. Send anyway → `POST /api/trades/propose`. The route reads `give`/`receive` as-is and `picks` only from a `draft_picks` body key nobody sends (`server.py:16194-16196`), builds `ProposeTradeRequest(give_player_ids=give, receive_player_ids=receive, draft_picks=picks or None)` with no split and no encoding (`:16228-16232`). `build_propose_trade_body` puts each pick id into `k_adds`/`k_drops` as a Sleeper player id (`backend/sleeper_write.py:286-292`); the `draft_picks` literal stays `[]` (`:294-302`).
3. Sleeper's GraphQL rejects the unknown player key → `SleeperWriteError` (`sleeper_write.py:364-371`) → 502 `sleeper_write_failed` (`server.py:16248-16254`) → the generic "Couldn't send" alert (`SendInSleeperButton.tsx:305-310`), with `sleeper_send_failed{error_code:'sleeper_write_failed'}` emitted (`:254-264`). This is the "causing trades with draft picks to fail" half.

Nothing regressed. Exposure rose: standing offers (#362, lit 2026-08-26) are pick-for-player by construction and land in the `awaiting` mount, and per-slot pick pricing made owned picks first-class engine assets (`backend/trade_optimizer.py:880-883`, flag `trade.picks_in_pool` on).

Precedents that already do this right: MFL propose splits with `_is_ftf_pick_asset` and encodes owned picks server-side against the stored snapshot, hard-blocking anything unresolvable with 422 `mfl_asset_unmapped` + `unmapped[]` (`server.py:28186-28208`; helpers `_ftf_pick_parts :27891-27900`, `_is_ftf_pick_asset :27903-27908`, `_mfl_encode_ftf_picks :27937-27960`). ESPN hard-blocks every pick with 422 `espn_pick_unsupported` + `picks[]` (`:28639-28644`). The MFL validate branch already has the pick-ownership advisory `pick_moved` (`:28009-28034`).

### Corrections to investigation.md

- "No encoder exists … semantics unverified" is only half right. The 2026-07-02 live capture DID observe non-empty `draft_picks` with two real examples, `"11,2026,1,1,2"` and `"1,2027,4,2,1"` (`docs/plans/sleeper-write-capture-runbook.md:158`): `<f1>,<season>,<round>,<from_roster>,<to_roster>`. Fields 2–5 are observed, not inferred. Only **field 1** is unconfirmed — the runbook says "likely the original-owner roster id — confirm on a multi-owner pick". Sleeper's public transaction shape corroborates the triple (`{roster_id (original), previous_owner_id (sending), owner_id (receiving)}`, `backend/suggestion_telemetry.py:209-211`, `server.py:13900`). So the residual unknown is narrow: is field 1 the original roster on a pick that has changed hands. Section 9 covers how the build proves it.
- The proposed helper signature `_sleeper_encode_ftf_picks(league_id, pick_ids, my_rid, their_rid)` loses the information it needs: `from`/`to` depend on which SIDE a pick sits on. The encoder must receive give-picks and receive-picks separately (section 2).
- `_record_send_success` (`server.py:16117-16150`) currently reports `give_n`/`receive_n` with picks counted as players and `pick_n` always 0 (it is fed the empty `picks` list at `:16275`). After the split the props become honest; the analytics addendum must record the semantic change.
- Test-harness gotcha the investigation missed: every propose-route test stubs `server._sleeper_get` with a single `return_value=rosters` (`backend/tests/test_sleeper_write_route.py:117,135,150,170,252,283,300`). `_fetch_sleeper_traded_picks` also goes through `_sleeper_get` (`server.py:13905`), so if the route fetched traded picks unconditionally, those stubs would hand the ROSTERS list back as traded picks. The design below fetches traded picks only when the trade carries picks, and new tests stub `_fetch_sleeper_traded_picks` directly.
- Line drift: `_ftf_pick_parts` is `:27891-27900` (not 27892-27901); validate's moved check is `:27797-27808`.

## 2. Approach — the server owns encoding, never the client

Mirror MFL exactly in the route shape, with Sleeper-native ground truth.

**Ground truth (two sources, both already paid for):**
- Existence: the league's `draft_picks` grid, `load_draft_picks(league_id)` with the default platform source (`database.py:10142-10183`). For Sleeper rows `original_roster_id` is the Sleeper roster_id (`:1100`, written at `:10027`/`:10073`), so `(season, round, original_roster_id)` from `_ftf_pick_parts` keys a row directly. This is what the client displayed, already horizon-corrected (#355) and completed-draft-excluded (#228).
- Current holder: the live public `traded_picks` list, `_fetch_sleeper_traded_picks(league_id)` (`server.py:13895-13908`), overlaid on "original roster holds by default". Roster-id keyed end to end, so co-owned rosters are a non-issue for holder resolution. Fetched only when the trade carries at least one pick — a player-only send makes zero new upstream calls.

**New helpers (backend):**

- `sleeper_write.encode_draft_pick(orig_rid, season, round_, from_rid, to_rid) -> str` — pure, returns `f"{orig},{season},{round},{from},{to}"`, guaranteed to satisfy `_is_valid_pick_str` (`sleeper_write.py:234-236`). Sits beside the template; module stays Flask/DB-free (`sleeper_write.py:33`). Mirrors `mfl_write.encode_future_pick`.
- `server._sleeper_pick_holder_index(traded_picks) -> dict[(season:int, round:int, orig:str), holder_rid:str]` — from the traded list's `{season(str), round, roster_id(orig), owner_id(current)}` (`server.py:13900`); same parsing the sync already does at `database.py:10037-10042`.
- `server._sleeper_encode_ftf_picks(league_id, give_picks, recv_picks, my_rid, their_rid, grid_rows, traded_picks) -> (encoded: list[str], unmapped: list[str], not_owned: list[str])`, placed beside `_mfl_encode_ftf_picks` (~`:27960`). Per pick:
  - `_ftf_pick_parts` is None (generic rung, other league's id, malformed) → `unmapped`.
  - No grid row for `(season, round, orig)` → `unmapped` (phantom season, completed draft, round beyond `draft_rounds`).
  - holder = `index.get(key, orig)`. Give side requires holder == `my_rid`; receive side requires holder == `their_rid`; otherwise → `not_owned`.
  - Else encode: give → `(orig, season, round, my_rid, their_rid)`; receive → `(orig, season, round, their_rid, my_rid)`.

**Exact behaviors:**

| Case | Result |
|---|---|
| Owned pick, my original, on give side | `"{my_rid},{season},{round},{my_rid},{their_rid}"` |
| Owned pick I acquired earlier (orig = roster 7), on give side; traded_picks shows holder = me | `"7,{season},{round},{my_rid},{their_rid}"` |
| Pick on the RECEIVE side (their roster gives it to mine) | holder must == their_rid; `"{orig},{season},{round},{their_rid},{my_rid}"` — from/to flipped |
| Generic rung `generic_pick_1_early` | 422 `sleeper_pick_unmapped`, `picks:[…]`, nothing sent. Never dropped |
| Pick id from another league / malformed / not in grid | 422 `sleeper_pick_unmapped` |
| Holder per traded_picks is neither the offering side (traded away since the card was built, or a third roster) | 422 `sleeper_pick_not_owned`, `picks:[…]`, nothing sent |
| Co-owned rosters | unchanged: my/their roster ids come from `_roster_id_for_owner` (`:15965-15983`, co-owner-aware); holder is roster-keyed |
| 2027+ seasons | `_ftf_pick_parts` accepts any 4-digit season; encoded as int. Existence bound by the grid's horizon, not a constant |
| Mixed trade, any single pick fails | whole send refused (a partially-mapped trade is a different trade — MFL comment `:28193-28198`) |
| `traded_picks` fetch flakes (`[]`, indistinguishable from "none traded") | holder defaults to original roster. Outcomes: a pick I acquired → holder ≠ me → 422 `not_owned` (safe refusal); my own original that I had traded away → encoded with from=me → Sleeper rejects → 502 (today's behavior). Never a silently wrong send. Accepted residual; noted in the LLD |

Route wiring in `propose_trade_to_sleeper` (`server.py:16155-16282`): after both roster ids resolve (`:16214-16226`) and before the request is built (`:16228`): split `give`/`receive` with `_is_ftf_pick_asset`; if any picks, `load_draft_picks` + `_fetch_sleeper_traded_picks` → encoder → 422 on `unmapped` first, then `not_owned`; build `ProposeTradeRequest(give_player_ids=give_players, receive_player_ids=recv_players, draft_picks=encoded or None)`. Pass `give_players`, `recv_players`, `encoded` to `_record_send_success` (`:16274-16278`) so `pick_n` becomes honest. `_save_deck_outcome_safe(... "propose")` (`:16264-16265`) is untouched and only reachable after a successful write, so the 422s never label an impression.

The `draft_picks` body key: today "accepted only pre-encoded" (`docs/api-reference.md:421`) with no producer anywhere. Recommendation: **reject a non-empty `draft_picks` with 400 `bad_request` + message** ("put pick ids in give/receive_player_ids"). Reasons: one way in; a client-asserted `from`/`to` is exactly the thing the server is supposed to own; silently ignoring it would violate never-drop-an-asset. Alternative (MFL parity, `give_pick_assets` at `:28219-28224`): keep appending validated pre-encoded strings. Author picks; the plan recommends reject.

No new flag. The change lives entirely inside `trade.send_in_sleeper`; a pick-free send is byte-identical (same arrays, no extra fetch); rollback is a code revert on an additive contract (D-063 precedent). Surface this as a scope §2 statement, not a waiver.

## 3. Contracts

**Request: unchanged.** `{league_id, their_user_id | their_roster_id, give_player_ids[], receive_player_ids[], impression_id?}` — the arrays stay MIXED, as the MFL route documents (`api-reference.md:429`). Justification versus a new `give_pick_ids` key: the four fielded mounts already send mixed arrays from `TradeCard`/`InLeagueCalculator` data that carries no player/pick discriminator beyond the id shape; builds 1.16.12–1.16.14 must start working the moment the server deploys, with no app update; and the MFL/ESPN routes prove the split-on-server pattern. The `draft_picks` key becomes rejected-if-non-empty (or stays MFL-style, per §2).

**Response, new 422s on `POST /api/trades/propose`:**

| Status | `error` | Fields | Meaning |
|---|---|---|---|
| 422 | `sleeper_pick_unmapped` | `picks: [pick_id…]`, `message` | ≥1 pick asset can't be resolved to a concrete pick in this league (generic rung, foreign/malformed id, not in the league's pick grid). Nothing sent |
| 422 | `sleeper_pick_not_owned` | `picks: [pick_id…]`, `message` | ≥1 pick's current holder (live `traded_picks`) is not the side offering it. Nothing sent |

Ordering: `unmapped` reported before `not_owned` (an unmappable pick has no holder to check). Both are refusals: no `sleeper_send_succeeded`, no deck outcome, no credential change.

**Analytics enum:** `sleeper_send_failed.error_code` grows from 15 to 17 values. Update the comment at `backend/analytics_taxonomy.py:1055-1058` ("14 server codes plus network | timeout | unknown. 17 values"), the addendum `docs/business/analytics/2026-08-11-p0-7-addendum.md:64-66`, the mobile comment `SendInSleeperButton.tsx:252-253`, and `docs/cross-client-invariants.md` (add the enum listing next to the `surface` enum at `:825`, which is the only place the invariants doc currently pins send-event enums). `CLIENT_EVENT_PROPS` constrains keys not values, so no ingest code changes. `sleeper_send_failed` is already in `WAT_LIVE` (`analytics_queries.py:53-55`); nothing to add to `NON_INTENT_EVENTS`.

**`POST /api/trades/validate`, Sleeper branch — two warning codes, both already in the MFL vocabulary (`api-reference.md:406,432`), so `TradeSendWarning.code`'s comment (`mobile/src/api/sendInSleeper.ts:214`) grows but no client type changes:**

| `code` | `severity` | Copy |
|---|---|---|
| `asset_unmapped` | `blocking` | "N draft pick(s) in this trade can't be sent to Sleeper (generic picks like 'Early 1st' name no real pick) — the send will be blocked rather than dropping them." |
| `pick_moved` | `blocking` | "N pick(s) in this trade are no longer owned by the expected team (already traded) — Sleeper will reject the offer." |

`player_moved` and `roster_limit` are computed over players only after the split. `checked` semantics unchanged.

## 4. Validate route fix (`server.py:27715-27834`)

After `mine`/`theirs` resolve (`:27787-27795`): split `give`/`receive` with `_is_ftf_pick_asset(league_id, p)` (same lines as the MFL branch `:27988-27991`). Run `_sleeper_encode_ftf_picks` only if picks are present (grid via `load_draft_picks`, holders via `_fetch_sleeper_traded_picks`) and translate `unmapped` → `asset_unmapped`, `not_owned` → `pick_moved`. Then the existing `player_moved` (`:27797-27808`) and `roster_limit` (`:27810-27832`) loops run over the player-only lists — roster counts must not include picks (Sleeper's roster limit is players only; picks are not roster slots). A traded_picks flake in validate degrades the same way as propose (default holder = original), which is advisory-only anyway.

## 5. Platforms and file ownership

Backend agent first (contract producer), mobile agent second (consumer). Disjoint files. Web and the extension have no send routes (`git grep trades/propose -- web extension` is empty), so nothing there.

| Owner | File | Change |
|---|---|---|
| backend | `backend/server.py` `:16155-16282` | propose: split, existence+holder resolution, 422s, honest `_record_send_success` args, `draft_picks` body-key handling |
| backend | `backend/server.py` ~`:27960` | new `_sleeper_pick_holder_index`, `_sleeper_encode_ftf_picks` beside the MFL helpers (banner comment mirroring `:27877-27889`) |
| backend | `backend/server.py` `:27751-27834` | validate: split, pick checks, players-only moved/limit math |
| backend | `backend/sleeper_write.py` | `encode_draft_pick`; docstring line `:230` and module header `:22` updated (draft_picks now produced server-side) |
| backend | `backend/analytics_taxonomy.py:1055-1058` | enum comment (17 values) |
| backend | `backend/tests/test_sleeper_write_route.py`, `test_sleeper_write.py`, `test_trade_send_validate.py` | cases in §7; fixture fix at `test_sleeper_write_route.py:288` |
| backend | docs: `docs/api-reference.md` (`:405-421`, `:406`), `docs/integrations/sleeper.md` (`:62`, `:197-203`), `docs/cross-client-invariants.md`, `docs/business/analytics/2026-08-11-p0-7-addendum.md`, `living-memory/DECISIONS.md` / `CHANGELOG.md` / `TEST_LEDGER.md` | §8 |
| mobile | `mobile/src/components/SendInSleeperButton.tsx` `:266-310` | two new `else if` branches before the catch-all; comment `:252-253` |
| mobile | `mobile/src/api/sendInSleeper.ts` `:5-6`, `:214` | error-code list comment; warning-code comment. No type change (`picks` is read as `body?.picks` like `detail`) — optional: add `picks?: string[]` to a typed error body if the Author wants it typed |
| mobile | `mobile/tests/check-send-button-platform.js` (+ `package.json:80` script already exists) | checks 7–8 (§7) |
| mobile | `mobile/src/components/CLAUDE.md` `SendInSleeperButton` row, `mobile/src/api/CLAUDE.md` `sendInSleeper.ts` row | one clause each |

Coordination point with G-414: G-414 must not touch `server.py:16155-16282`, `:27715-27834`, or the new helper block; the batch plan already reserves those regions.

## 6. Risks

1. **Field 1 (`orig`) semantics unverified on a previously-traded pick.** Observed: fields 2–5 and the whole string for two live examples (runbook `:158`). If Sleeper instead expects field 1 = current holder, a never-traded pick (orig == from) still works and only acquired picks fail with a GraphQL error → 502 `sleeper_write_failed` with `detail` — visible, not silent. The TestFlight checklist (§7) is the proof; log the outcome, and if it fails, the fix is one line in the encoder. Record as an open question the way Q-016 records `waiver_budget`: mark the shape "captured for fields 2–5, field 1 pending live confirmation" in `sleeper_write.py`'s header and `docs/integrations/sleeper.md` §3.3.
2. **`k_adds`/`k_drops` must stay correct alongside picks.** Players still ride the variables exactly as today (`sleeper_write.py:286-292`); picks ride only the inlined literal. The adapter's empty-trade guard (`:277-278`) already counts `draft_picks`, so a pure pick-for-pick trade (players-only arrays empty) is legal. Sabotage-provable in `test_sleeper_write.py`.
3. **Standing offers (#362) are the main producer** and land on the `awaiting` surface; the fix must not depend on any deck-only prop. Confirmed: `TradeCard.tsx:1000-1004` passes the same arrays as the match mount.
4. **Propose-label spine (D-152 / F1).** `_save_deck_outcome_safe(impression_id, "propose")` at `server.py:16264` runs only after a successful write; both 422s return earlier. Test: a 422 response leaves `deck_outcomes` empty (mirror of `test_propose_unmapped_hard_block_fires_no_trade_sent`, `test_mfl_propose_route.py:317`).
5. **`traded_picks` fail-soft ambiguity** (`server.py:13906-13908` returns `[]` on error). Bounded as in §2's table; the LLD should state it. If the Author wants it airtight, the smallest change is a `strict` variant that returns `None` on failure and a 502 `sleeper_write_failed{kind:"network"}` from propose when picks are present — but that is a second failure path for a flake the route already tolerates for rosters; the plan recommends accepting the residual.
6. **Test stubs.** `_sleeper_get` single-`return_value` stubs (§1 corrections) — new pick tests must patch `_fetch_sleeper_traded_picks` and `load_draft_picks` (`server.load_draft_picks` is imported into server's namespace — confirm the import name at build time with `git grep -n "load_draft_picks" -- backend/server.py`).
7. **Grid staleness.** `draft_picks` rows are replace-synced on `session_init`'s daemon (`server.py:11651-11714`); a pick added to Sleeper after the last sync (new season rolling into horizon) would 422 `unmapped` until the next sync. Acceptable: the client could not have displayed such a pick either.

## 7. Test plan skeleton (D-056)

**pytest — `backend/tests/test_sleeper_write.py`** (adapter, pure):
- `test_encode_draft_pick_shape` — `encode_draft_pick("7", 2027, 1, "3", "5") == "7,2027,1,3,5"` and passes `_is_valid_pick_str`. Sabotage: swap from/to in the f-string.
- `test_pick_only_trade_builds_body` — empty player arrays + one encoded pick → body builds, `k_adds == []`, literal contains the pick. Sabotage: drop `draft_picks` from the empty-trade guard at `:277`.

**pytest — `backend/tests/test_sleeper_write_route.py`** (route; stub `_sleeper_get`→rosters, `_fetch_sleeper_traded_picks`, `load_draft_picks`, `propose_trade`=MagicMock and inspect the `ProposeTradeRequest` it received):
- Fix the bogus fixture at `:288`: replace `"draft_picks": ["2027_1"]` with an owned pick id inside `give_player_ids` (+ grid row stub), and assert the request reaching the adapter carries `draft_picks == ["1,2027,1,1,2"]` and `give_player_ids == ["100","101"]`. Sabotage: remove the split (picks stay in `give_player_ids`) — test goes red for the right reason.
- `test_propose_encodes_give_pick_from_to` — own original pick on give → `"{my},{season},{round},{my},{their}"`. Sabotage: pass `their_rid` as `from`.
- `test_propose_encodes_receive_pick_flips_from_to` — pick on receive, holder == their → `"…,{their},{my}"`. Sabotage: use the give branch for both sides.
- `test_propose_acquired_pick_uses_traded_picks_holder` — grid row orig=7, traded_picks says owner_id=my → encodes `"7,…,{my},{their}"`. Sabotage: ignore the traded_picks overlay (default holder only) → `not_owned` instead of 200.
- `test_propose_hard_blocks_generic_pick` — `generic_pick_1_early` → 422 `sleeper_pick_unmapped`, `picks == [...]`, `propose_trade` not called. Sabotage: filter generic rungs out silently.
- `test_propose_hard_blocks_pick_missing_from_grid` — well-formed id, no row → 422 unmapped. Sabotage: skip the existence check.
- `test_propose_hard_blocks_pick_not_owned` — holder is roster 9 → 422 `sleeper_pick_not_owned`. Sabotage: skip the holder comparison.
- `test_propose_pick_free_send_makes_no_traded_picks_fetch` — assert the `_fetch_sleeper_traded_picks` mock is not called. Sabotage: fetch unconditionally.
- `test_propose_422_fires_no_success_event_and_no_deck_outcome` — no `sleeper_send_succeeded` row, no `deck_outcomes` row even with an `impression_id`. Sabotage: move `_save_deck_outcome_safe` above the pick gate.
- `test_propose_success_pick_n_honest` — `sleeper_send_succeeded.props.pick_n == 1`, `give_n` counts players only. Sabotage: keep passing the raw `give` list.
- `test_propose_rejects_client_supplied_draft_picks` — non-empty `draft_picks` body → 400 (if the reject option is chosen).

**pytest — `backend/tests/test_trade_send_validate.py`** (extend the fixture with `_fetch_sleeper_traded_picks` and `load_draft_picks` patches):
- `test_owned_pick_not_flagged_as_player_moved` — the #413 repro: an owned pick on give produces zero `player_moved`. Sabotage: revert the split.
- `test_generic_pick_flags_asset_unmapped` (blocking).
- `test_pick_owned_by_other_roster_flags_pick_moved` (blocking).
- `test_receive_side_pick_checks_their_roster` — holder == their → clean; holder == my → `pick_moved`.
- `test_roster_limit_excludes_picks` — a trade that would overflow only if picks counted stays clean. Sabotage: count picks in `post`.

**Code-walk proof targets** (file:line trace the mobile agent writes): (a) the four mounts still pass mixed arrays unchanged; (b) `doPropose` catch → the two new branches → alert copy; (c) `confirmSend` renders `asset_unmapped` / `pick_moved` messages through the existing warning list with no client change; (d) the 422 emits `sleeper_send_failed{error_code:'sleeper_pick_unmapped'|'sleeper_pick_not_owned'}` via the existing `body?.error` read at `:256-258`.

**Structural guard** — extend `mobile/tests/check-send-button-platform.js` with checks 7–8: the `doPropose` catch contains `code === 'sleeper_pick_unmapped'` and `code === 'sleeper_pick_not_owned'` branches that call `Alert.alert` and precede the catch-all `else`. Sabotage: delete one branch → guard red.

**Manual TestFlight checklist** (operator, real Sleeper league; each proposal is cancelled in Sleeper afterwards):
1. Open a deck/awaiting card that contains one of YOUR ORIGINAL future picks on the give side (e.g. your 2027 2nd). Tap Send. Expected: the plain "Send this trade?" confirm, no "likely fail" warning.
2. Send. Expected: "Trade sent"; in the Sleeper app the pending offer lists that exact pick (season + round, "via <you>"). Cancel it in Sleeper.
3. If you hold a pick acquired from another team, build a trade in the calculator giving that pick. Send. Expected: Sleeper shows the pick with the original team's name. Cancel. (This step is the field-1 proof; log pass/fail in TEST_LEDGER. If it fails with "Sleeper rejected/couldn't send" and a detail, capture the detail text.)
4. Build a trade in the calculator receiving one of the partner's picks. Send. Expected: Sleeper shows the pick moving from them to you. Cancel.
5. Build a trade with a pick the partner does NOT currently hold (one they traded away — visible in the Draft tab or Sleeper's picks list). Tap Send. Expected: warning "…no longer owned by the expected team", then on Send anyway: "Couldn't send" with the not-owned copy, nothing appears in Sleeper.
6. From a deck card that offers a generic rung ("Early 1st"), tap Send. Expected: warning about generic picks, then the unmapped refusal; nothing in Sleeper.
7. Player-only trade. Send. Expected: unchanged behavior (regression check).

## 8. Docs rows

| Doc | Row |
|---|---|
| `docs/api-reference.md:405` | `POST /api/trades/propose`: arrays are MIXED; server splits/encodes picks against the `draft_picks` grid + live `traded_picks`; `draft_picks?[]` removed (or "pre-encoded, no client sends") ; `sleeper_send_succeeded.pick_n` now honest |
| `docs/api-reference.md:408-420` error table | add 422 `sleeper_pick_unmapped` (+`picks[]`), 422 `sleeper_pick_not_owned` (+`picks[]`); update `:421` "v1 scope" line |
| `docs/api-reference.md:406` | validate Sleeper codes gain `asset_unmapped`, `pick_moved`; `player_moved`/`roster_limit` are players-only |
| `docs/integrations/sleeper.md:62,197-203` | `propose_trade` now emits non-empty `draft_picks`; `traded_picks` gains two consumers (propose, validate); field-1 caveat |
| `docs/cross-client-invariants.md` (§ Client analytics event contract, near `:825`) | `sleeper_send_failed.error_code` closed enum listed, 17 values |
| `docs/business/analytics/2026-08-11-p0-7-addendum.md:64-66` | 14 server codes; `pick_n`/`give_n` semantic correction dated |
| `docs/config-reference.md` | n/a — no flag, env var or knob |
| `docs/glossary.md` | n/a |
| `living-memory/LLD.md` | convention note only if the Author adopts "pick assets ride mixed arrays on every propose route; the server splits" as a stated invariant across Sleeper/MFL/ESPN (recommended: one line) |
| `docs/data-dictionary.md` | n/a — no schema change |
| `DECISIONS.md` | new D entry: server-owned Sleeper pick encoding; client `draft_picks` key rejected; no flag |
| `mobile/src/components/CLAUDE.md`, `mobile/src/api/CLAUDE.md` | one clause each on the new codes |

## 9. Spike needs

A live `propose_trade` with a non-empty `draft_picks` cannot be proven without creating a real pending offer in a real league — there is no dry-run in Sleeper's GraphQL and `FTF_TEST_MODE` fail-closes the route (`server.py:16167-16171`). No pre-build spike; the TestFlight checklist steps 2–4 are the proof, step 3 specifically closes the field-1 question. Until step 3 is logged, treat the acquired-pick path as "captured shape, unconfirmed on a multi-owner pick" in the module header and integrations doc, the Q-016 way.
