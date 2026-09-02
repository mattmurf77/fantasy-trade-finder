# QA round 1 — agent B — 2026-09-02

## Summary: PASS (7 findings — 1 major docs-gate, 6 minor; no code defect found)

Every PRD §7 item executed and green on the group tip; every PRD-named sabotage proven RED by me
except one that is self-satisfying (F-3); 9 sabotages of my own devising, 6 caught, 3 exposing
coverage gaps that are code-walk-only (F-4, F-5). The one major finding is that the four
`living-memory/` docs scope §4 marks **updated — required** (D-172, Q-035, LLD.md H2, HLD.md
line) are absent at `8e4e1648` (F-1). No fix applied to anything; tree left as found.

## Environment

- Worktree `scratchpad/wt-fb413-qa-b`, branch `qa/fb413-b`, tip `8e4e1648 feedback #413: mobile — count-aware alerts…` (confirmed via `git log --oneline -7`; chain `ad5adafa → b4aabcc3 → 31e8d590 → b938642b → 51794a35 → 8e4e1648`).
- Python 3.14.4 · node v24.14.1 · `npm ci` 801 packages, exit 0.
- Flags read from `config/features.json` (not pinned by me; relevant to the checklist): `trade.send_in_sleeper: true`, `picks.owned_sync: true`, `trade.picks_in_pool: true`, `picks.assign_tradeable: true`, `deck.signal_v2: true`, `trade.send_in_mfl: true`.
- `mobile/app.json` version `1.16.14`, buildNumber 2 (the build the checklist runs on; PRD says any ≥ 1.16.12).
- D-056: static + code-walk only. No simulator, no Maestro, no captures.

## Results

| Test | Verdict | Evidence |
|---|---|---|
| §7.5 full regression `rm -f data/trade_finder.db*; pytest backend/tests -q -p no:cacheprovider` | PASS | **4503 passed, 1 skipped in 307.67s** — baseline 4483/1 + 20, exactly PRD §7.5 |
| §7.5 `npx tsc --noEmit` (mobile) | PASS | exit 0, no output |
| §7.5 all `mobile/tests/check-*.js` | PASS | 89 guards ran, 0 FAIL |
| §7.5 `bash mobile/scripts/testid-lint.sh` | PASS | `testid-lint OK`, exit 0 |
| §7.5 `node tests/check-send-button-platform.js` | PASS | all blocks green incl. 4 new PASS lines (7, 8, 7b, 7c) |
| T-1 `test_encode_draft_pick_shape` | PASS | green; RED under P-T1a (`'7,2027,1,5,3' == '7,2027,1,3,5'`), P-T1b, O-3 |
| T-2 `test_pick_only_trade_builds_body` | PASS | green; RED under P-T2 (`SleeperWriteError: trade has no assets on either side`) |
| T-3 `test_propose_success_fires_no_trade_sent_on_sleeper` (fixed fixture) | PASS | green; RED under P-T3 (`assert ['100','101',…'_2027_2_1'] == ['100','101']`) |
| T-3b `test_propose_success_labels_impression_propose` | PASS | green; RED under P-T3b (`Expected 'mock' to be called once. Called 0 times.`) |
| T-4 `test_propose_encodes_give_pick_from_to` | PASS | green; RED under P-T4 (`['1,2027,2,2,2'] == ['1,2027,2,1,2']`) |
| T-5 `test_propose_encodes_receive_pick_flips_from_to` | PASS | green; RED under P-T5 (422 `not_owned` for `…_2026_1_2`) |
| T-6 `test_propose_acquired_pick_uses_traded_picks_holder` | PASS | green; RED under P-T6 (422 `not_owned` for `…_2027_1_7`), O-1, O-2, O-8 |
| T-7 `test_propose_hard_blocks_generic_pick` | PASS | green; RED under P-T7a (200 instead of 422), P-T7b (`['generic_pick_1_early'] == [both]`), P-T7c (`KeyError: 'detail'`) |
| T-8 `test_propose_hard_blocks_pick_missing_from_grid` | PASS | green; RED under P-T8b (200 `{"status":"proposed"}`); **GREEN under P-T8a** — see F-3 |
| T-9 `test_propose_hard_blocks_pick_not_owned` | PASS | green; RED under P-T9a (200), P-T9b (`KeyError: 'detail'`) |
| T-10 `test_propose_pick_free_send_makes_no_traded_picks_fetch` | PASS | green; RED under P-T10 (`Expected 'mock' to not have been called. Called 1 times.`) |
| T-11 `test_propose_422_fires_no_success_event_and_no_deck_outcome` | PASS | green; RED under P-T11 (`not have been called. Called 1 times.`) |
| T-12 `test_propose_rejects_client_supplied_draft_picks` | PASS | green; RED under P-T12 (200 instead of 400) |
| T-13 `test_propose_success_pick_n_honest` | PASS | green; RED under P-T13 (props dict mismatch, `give_n` 3 / `pick_n` 0) |
| T-14 `test_propose_reports_unmapped_before_not_owned` | PASS | green; RED under P-T14a (`'sleeper_pick_not_owned' == 'sleeper_pick_unmapped'`), P-T14b, O-7 |
| V-1 `test_owned_pick_not_flagged_as_player_moved` | PASS | green; RED under P-V1 (`[{'code': 'player_moved'…}] == []`) |
| V-2 `test_generic_pick_flags_asset_unmapped` | PASS | green; RED under P-V2 (`['player_moved'] == ['asset_unmapped']`), P-T7a |
| V-3 `test_pick_owned_by_other_roster_flags_pick_moved` | PASS | green; RED under P-T9a (`[] == ['pick_moved']`), P-T6, O-1, O-8, O-9 |
| V-4 `test_receive_side_pick_checks_their_roster` | PASS | green; RED under P-T5/V-4 (`['pick_moved'] == []` at :224), P-T9a |
| V-5 `test_roster_limit_excludes_picks` | PASS | green; RED under P-V5 (`['roster_limit'] == []`) |
| V-6 `test_pick_free_validate_makes_no_pick_fetch` | PASS | green; RED under P-V6 (`not have been called. Called 1 times.`) |
| C-7 unmapped branch, Alert, no goConnect | PASS | RED under M-1 |
| C-8 not-owned branch, Alert, no goConnect | PASS | RED under M-2, M-4, M-8 |
| C-7b both branches inside the chain before the final else | PASS | RED under M-1, M-2, **M-3 only-7b** (presence ≠ reachability, as designed) |
| C-7c catch-all copy survives | PASS | RED under M-5 |
| R-1 mixed arrays, server splits with `_is_ftf_pick_asset` | PASS | `server.py:16247-16250` (propose), `:27848-27851` (validate); T-3/T-4 |
| R-2 non-empty `draft_picks` → 400 with `detail == message` | PASS | `:16206-16209`; T-12 |
| R-3 existence = grid by `pick_id`, platform source | PASS | `:16257`, `:27856`, `:28109` (`grid = {str(r["pick_id"]): r …}`); T-7/T-8/V-2 |
| R-4 holder = live `traded_picks`, default original; fetched only with a pick | PASS | `:16252-16258`, `:27852-27857`, `:28053-28068`; T-6/T-10/V-3 |
| R-5 orientation, `orig` from the grid row | PASS | `:28113-28114` tuples, `:28126-28127` `orig` = row; T-4/T-5/T-6 |
| R-6 422 `sleeper_pick_unmapped` {error, picks, message, detail==message}, both sides give-then-receive, before R-7 | PASS | `:16263-16268`; T-7/T-8/T-14 |
| R-7 422 `sleeper_pick_not_owned` same shape | PASS | `:16269-16273`; T-9 |
| R-8 whole-send refusal; refusals invisible to the spine; positive half | PASS | code-walk below; T-7/T-9/T-11/T-3b |
| R-9 adapter gets players-only + encoded picks; pick-only legal | PASS | `:16275-16279`; `sleeper_write.py:295`; T-2/T-3 |
| R-10 honest `sleeper_send_succeeded` props | PASS | `:16321-16325`; T-13 |
| R-11 validate splits, two blocking advisories, players-only moved/limit | PASS | `:27848-27868`, `:27872-27873`, `:27895-27896`; V-1…V-5 |
| R-12 no extra upstream call for pick-free validate | PASS | `:27852`; V-6 |
| R-13 two alert branches, count-aware pinned copy, no reconnect, no `detail` | PASS (by code-walk; F-4 for coverage) | `SendInSleeperButton.tsx:305-322`; C-7/7b/7c/8 |
| R-14 comments follow the contract | PASS | `SendInSleeperButton.tsx:252-253`, `sendInSleeper.ts:5-7`, `:28-29`, `:215` |
| R-15 warnings render with zero client change | PASS | `confirmSend` `:336-367` not in the diff |
| R-16 17-value enum at four sites; no ingest change | PASS | grep: `analytics_taxonomy.py:1057`, `SendInSleeperButton.tsx:253`, addendum `:72`, `cross-client-invariants.md:827`; 0 hits for `15 values|12 server codes|players-only v1|picks pre-encoded` |
| R-17 the `:288` fixture fixed | PASS | diff removes `"draft_picks": ["2027_1"]`; T-3 asserts the adapter request |
| R-18 Q-035 logged | N/A (orchestrator) | but note F-1: not present at tip |

Every sabotage run restored its file (`git checkout --`) and `git status --porcelain` for that file was empty afterwards (`restored_clean: true` on all 40 records). Final `git status`: clean except this report.

## Sabotage table (PRD-named + my own)

Driver: apply one exact-string edit → run `test_sleeper_write.py + test_sleeper_write_route.py + test_trade_send_validate.py` (67 tests, `--tb=line`) or the AST guard `-k w3_02` or `node tests/check-send-button-platform.js` → restore. "RED" = named test failed with the quoted assertion.

| # | Sabotage (file) | Named test | Result | Failing assertion (or why GREEN) |
|---|---|---|---|---|
| P-T1a | swap from/to in the f-string (`sleeper_write.py`) | T-1 | RED (+T-3, T-4, T-5, T-6) | `assert '7,2027,1,5,3' == '7,2027,1,3,5'` |
| P-T1b | emit `orig` as the fourth field | T-1 | RED (+T-6) | `assert '7,2027,1,7,5' == '7,2027,1,3,5'`; T-6 `['7,2027,1,7,2'] == ['7,2027,1,1,2']` — note T-4/T-5 stayed green because their fixtures have `orig == from` |
| P-T2 | drop `(req.draft_picks or [])` from the empty-trade guard (`:295`) | T-2 | RED | `SleeperWriteError: trade has no assets on either side` |
| P-T3 | remove the split (pick stays in `give_player_ids`, `draft_picks None`) | T-3 | RED (10 failed) | `assert ['100','101',…'_2027_2_1'] == ['100','101']`; T-4 `assert None == ['1,2027,2,1,2']` |
| P-T3b | delete the `:16311` `_save_deck_outcome_safe` call | T-3b | RED (only T-3b) | `Expected 'mock' to be called once. Called 0 times.` — every negative test stayed green, as the PRD predicted |
| P-T4 | `to_rid` passed as `from` in the encode call | T-4 | RED (+T-3, T-5, T-6) | `['1,2027,2,2,2'] == ['1,2027,2,1,2']` |
| P-T5/V-4 | give branch for both sides (`(p, my_rid, their_rid) for p in recv_picks`) | T-5, V-4 | RED (+V-5 collateral) | T-5: 422 `sleeper_pick_not_owned picks=["…_2026_1_2"]`; V-4 `:224 assert ['pick_moved'] == []` |
| P-T6 | ignore the overlay (`holder = int(orig)` always) | T-6 | RED (+T-9, V-3) | T-6: 422 `not_owned picks=["…_2027_1_7"]`; T-9 `:433` got 200; V-3 `[] == ['pick_moved']` |
| P-T7a | silently drop generic rungs in the encoder | T-7 | RED (+T-11, T-14, V-2) | T-7 `:403` got `{"status":"proposed"}`; T-11 `assert 200 == 422`; V-2 `[] == ['asset_unmapped']` |
| P-T7b | `picks[]` from the give side only | T-7 | RED | `:406 assert ['generic_pick_1_early'] == ['generic_pick_1_early','generic_pick_2_mid']` |
| P-T7c | drop `detail` on the unmapped 422 | T-7 | RED | `:407 KeyError: 'detail'` |
| **P-T8a** | `if row is None:` → `if False:` | T-8 | **GREEN — 67 passed** | self-satisfying: `row` is `None`, execution falls into `row["season"]` → `TypeError` → the `except` branch appends to `unmapped` anyway. See F-3 |
| P-T8b | infer existence from rosters × horizon (synthetic grid) | T-8 | RED (+T-6) | `:419` got `{"status":"proposed"}`; T-6 422 `unmapped` (roster 7 not in rosters) |
| P-T9a/V-3 | skip the holder comparison (`if False:`) | T-9, V-3 | RED (+V-4) | T-9 `:433` got 200; V-3 `:215 assert [] == ['pick_moved']`; V-4 `:226` |
| P-T9b | drop `detail` on the not-owned 422 | T-9 | RED | `:437 KeyError: 'detail'` |
| P-T10 | `if give_picks or recv_picks:` → `if True:` (propose) | T-10 | RED | `Expected 'mock' to not have been called. Called 1 times.` |
| P-T11 | label the impression before the pick gate (moved call up) | T-11 | RED (+T-3b) | T-11 `not have been called. Called 1 times.`; T-3b `Called 2 times.` |
| P-T12 | delete the 400 block, `encoded = list(picks)` (MFL-style pass-through) | T-12 | RED | `:473` got `{"status":"proposed"}` |
| P-T13 | pass raw `give`/`receive`/`[]` to `_record_send_success` | T-13 | RED | `:495` props dict mismatch (`give_n` 3, `pick_n` 0) |
| P-T14a | check `not_owned` first (swap the two 422 blocks) | T-14 | RED | `:509 assert 'sleeper_pick_not_owned' == 'sleeper_pick_unmapped'` |
| P-T14b | merge both lists into one 422 | T-14 | RED (+T-9) | `:510 assert ['generic_pick_1_early','…_2027_2_1'] == ['generic_pick_1_early']`; T-9 `'sleeper_pick_unmapped' == 'sleeper_pick_not_owned'` |
| P-V1 | `moved_give` over `give` (revert the split, give side) | V-1 | RED (+V-2, V-3) | `:193 assert [{'code':'player_moved'…}] == []` |
| P-V2 | generic rungs classified as players in the validate split | V-2 | RED | `:201 assert ['player_moved'] == ['asset_unmapped']` |
| P-V5 | count picks in `post` (revert the loop tuples) | V-5 | RED | `:235 assert ['roster_limit'] == []` |
| P-V6 | fetch unconditionally (validate) | V-6 | RED | `not have been called. Called 1 times.` |
| M-1 | delete the unmapped branch | C-7 | RED | FAIL 7 + FAIL 7b |
| M-2 | delete the not-owned branch | C-8 | RED | FAIL 8 + FAIL 7b |
| M-3 | not-owned appended as a second `if` after the catch-all | C-7b | RED (7b only) | 7/8 stay green — presence is not reachability; 7b is the claim |
| M-4 | fold `sleeper_pick_not_owned` into the reconnect condition, dedicated branch kept | C-8 | RED | FAIL 8 (the "every matching `if`" rule catches the reconnect branch) |
| M-5 | swap the catch-all copy for `'Please try again.'` | C-7c | RED | FAIL 7c |
| **O-1** | holder index keyed on `owner_id`, holder from `roster_id` | T-6, T-9, V-3 | RED | T-6 422 `not_owned`; T-9 200; V-3 `[] == ['pick_moved']` |
| **O-2** | field 1 = `from_rid` instead of `orig` | T-6 | RED (T-6 **only**) | `:392 ['1,2027,1,1,2'] == ['7,2027,1,1,2']` — T-4/T-5 fixtures have `orig == from`, so T-6 is the sole pin on field 1 |
| **O-3** | drop `int()` coercion in `encode_draft_pick` | T-1 | RED | `:169 Failed: DID NOT RAISE ValueError` (the string-input case alone would NOT have caught it — same output) |
| **O-4** | bare-default `load_draft_picks(league_id)` in propose | `test_w3_02` | RED | `a sanctioned site stopped naming source=: ['propose_trade_to_sleeper']` |
| **O-5** | `source=_pick_read_source()` instead of the literal (guardrail 8) | `test_w3_02*` | **GREEN — 4 passed** | the AST guard checks that `source=` is *named*, not its value. See F-5 |
| **O-6** | not-owned pick also encoded (drop the `continue`) | — | **GREEN — 67 passed** | harmless in the route (422 still returned before the write); the encoder's "exactly one of three" is not pinned. Informational |
| **O-7** | `picks[]` lists every pick, not just failing ones | T-14 | RED | `:510` — T-7 stays green (both picks fail there); T-14 does the work |
| **O-8** | holder-index key without `str()` on `roster_id` | T-6, T-9, V-3 | RED | key `(2027,1,7)` never matches lookup `(2027,1,"7")` → default holder → T-6 422 |
| **O-9** | `pick_moved` severity `"warning"` | V-3 | RED | `:216 assert 'warning' == 'blocking'` |
| **M-6** | unmapped branch renders `detail \|\| 'x'` instead of the pinned sentence | C-7 | **GREEN** | guard checks `Alert.alert(` + no `goConnect` only. See F-4 |
| **M-7** | not-owned branch renders `body.picks.join(', ')` | C-8 | **GREEN** | same — "counted, never rendered" is code-walk only. See F-4 |
| **M-8** | not-owned branch adds a `Connect → goConnect` button | C-8 | RED | FAIL 8 |

Tally: 30 PRD-named runs (29 RED as intended, 1 self-satisfying), 12 own (9 RED, 3 GREEN gaps).

## Fixture-shape audit

| Fixture | Production shape | Verdict |
|---|---|---|
| `ROSTERS_1V2 = [{"owner_id": SLEEPER_UID, "roster_id": 1}, {"owner_id": "opp", "roster_id": 2}]` (route) / `ROSTERS` (validate) | `/v1/league/{id}/rosters`: `roster_id` int, `owner_id` string | OK — `_roster_id_for_owner` `int()`s `roster_id` (`:15981`); validate `by_rid` `int()`s too (`:27831`) |
| `GRID` rows `{"pick_id": f"{LEAGUE}_2027_2_1", "season": 2027, "round": 2, "original_roster_id": "1"}` | `load_draft_picks` row: `season`/`round` `Integer` (`database.py:1096-1097`), `original_roster_id` `String` (`:1100`, written as `str` at `:10027`/`:10073`), `pick_id` = `make_pick_id` (`:9765`) | OK — string `original_roster_id` is the production shape and is what makes the `str()` on the index key load-bearing (O-8 proves it) |
| `TRADED = [{"season": "2027", "round": 1, "roster_id": 7, "owner_id": 1, "previous_owner_id": 7}]` | `_fetch_sleeper_traded_picks` docstring `:13900`; live rows `season` str, `roster_id`/`owner_id` int | OK — exactly the live shape; the encoder casts both directions (`:28066-28067`) |
| T-9 / T-14 / V-3 traded override `roster_id: 1, owner_id: 9` | holder roster 9 is not in the rosters list | Acceptable — the holder test compares ints, not roster membership; production can legitimately show a holder not in a stale rosters snapshot |
| Grid mock `lambda lid, *a, **k` (validate) / `MagicMock(return_value=grid)` (route) | route calls `load_draft_picks(league_id, source=PICK_SOURCE_PLATFORM)` | OK — both accept the kwarg. **No test asserts the kwarg's value**; only the AST guard pins that `source=` is named (see F-5) |
| Route tests send `their_roster_id: 2` | mobile always sends `their_user_id` (`SendInSleeperButton.tsx:225`) | Not hiding a defect — the pick logic is downstream of both branches, and the pre-existing tests `:118-` cover `their_user_id` resolution. Noted only |
| Validate fixture patches `get_sleeper_credential → None` | linked users resolve `my_owner` from the credential | Same value for Sleeper (`user_id == sleeper_user_id`); OK |
| League ids `LEAGUE = "1312140920132497408"` (route) / `"987654321"` (validate) | `_ftf_pick_parts` regex is league-prefixed (`:27970`) | OK — pick ids in both fixtures use the same league as the body; a foreign-league id is never exercised (see F-2) |
| `caller-excluded league.members` convention | not used by either route | n/a |

No fixture that would hide a real defect was found. One gap worth stating: T-4/T-5 use picks whose `orig == from`, so the `orig`-from-the-grid-row rule (R-5) is pinned by T-6 alone (O-2).

## Code-walk proofs (per requirement)

All citations are the merged tree at `8e4e1648`.

**R-8 — ordering vs `_save_deck_outcome_safe` / `_record_send_success`.** `propose_trade_to_sleeper` (`server.py:16156`): the split is at `:16247-16250`; the pick block `:16252-16273` returns the unmapped 422 at `:16267-16268` and the not-owned 422 at `:16272-16273`. `ProposeTradeRequest` is built at `:16275-16279`, the write at `:16281`, and the two spine calls are `_save_deck_outcome_safe(body.get("impression_id"), "propose", acting_user_id=user_id)` at `:16311-16312` and `_record_send_success(user_id, league_id, give_players, recv_players, encoded, …)` at `:16321-16325`. Both are below the write's `except` blocks (`:16282-16301`), so a 422 return at `:16268`/`:16273` — and a 409/502 from the write — never reaches them. `sleeper_send_succeeded` has exactly one emitter, `_record_send_success` (`:16139-16140`; `git grep`). **When the path does NOT fire:** with `give_picks == recv_picks == []` the `if` at `:16252` is skipped, `encoded` stays `[]` (`:16251`), `draft_picks=None` (`:16278`), and the request is identical to the pre-change one — T-10. The positive half (`propose` labelled exactly once on a successful pick send) is `:16311` reached once per request — T-3b.

**R-13 — branch order and the fielded-build catch-all.** `doPropose` catch (`SendInSleeperButton.tsx:246`): `body` `:247`, `track('sleeper_send_failed')` `:254-264` (before the ladder), `code = body?.error` `:266`, `detail = body?.detail` `:267`. Ladder: `sleeper_not_linked || sleeper_expired` `:269` → `verification_required` `:280` → `sleeper_rejected` `:293` → `sleeper_unconfigured || feature_disabled` `:298` → `roster_not_found || opponent_roster_not_found` `:300` → **`sleeper_pick_unmapped` `:305`** → **`sleeper_pick_not_owned` `:316`** → catch-all `else` `:323-327` rendering `detail || 'Something went wrong sending to Sleeper. Please try again.'` (`:326`). The two new branches compute `n` at `:311`/`:318` and interpolate only `n` (`:314`, `:321`). `goConnect` occurrences: `:215` (def), `:277`, `:290` (auth buttons), `:330`, `:426` (deps), `:422` (pre-send alert) — none inside `:305-322`. **Fielded-build path:** a build without `:305-322` walks `:269-304` (unchanged) and lands at `:323-327`; the server sets `detail == message` on both 422s (`server.py:16267-16268`, `:16272-16273`), so the fielded alert reads the server's "Some draft picks …" sentence, not "Please try again". **Does not fire:** a 422 with any other `error` value, or a non-`ApiError`, takes the catch-all (`:323`) or the `network` branch of `track` (`:258`).

**R-15 — warnings rendering unchanged.** `git diff ad5adafa..8e4e1648 -- SendInSleeperButton.tsx` has two hunks only (`@@ -249` comment, `@@ -302` branches). `confirmSend` `:336-367`: `validateTradeSend` with the same mixed arrays `:338-343`; `warnings.length > 0` `:346`; `blocking = warnings.some(severity === 'blocking')` `:347`; title `:349`; body `warnings.map(w => \`• ${w.message}\`)` `:350`; Cancel / Send anyway `:351-354`. `TradeSendWarning.code` is `string` (`sendInSleeper.ts:215`), so `asset_unmapped`/`pick_moved` type-check with no change; the server emits both with `"severity": "blocking"` (`server.py:27860`, `:27866`). **Does not fire:** `warnings == []` → plain "Send this trade?" (`:359-366`) — V-1 is the #413 repro of exactly this.

**R-16 — the four enum-comment sites.** `backend/analytics_taxonomy.py:1055-1058` ("14 server codes … 17 values"); `SendInSleeperButton.tsx:252-253` ("14 server codes ∪ network | timeout | unknown = 17 values"); `docs/business/analytics/2026-08-11-p0-7-addendum.md:71-79` ("17 values, forever (15 → 17 on 2026-09-02 …)" + the dated `give_n`/`pick_n` note at `:67-72`); `docs/cross-client-invariants.md:827` (full 17-value listing + the 6-value validate vocabulary). The route emits exactly 14 distinct `"error"` values between `:16156-16330` (`test_mode_propose_disabled, feature_disabled, no_user, verification_required, bad_request, sleeper_not_linked, sleeper_unconfigured, sleeper_expired, roster_not_found, opponent_roster_not_found, sleeper_rejected, sleeper_write_failed, sleeper_pick_unmapped, sleeper_pick_not_owned`) — 14 + 3 = 17 ✓. Residue grep for `15 values|12 server codes|players-only v1|picks pre-encoded` across `backend`, `mobile/src`, and the four docs: 0 hits. `CLIENT_EVENT_PROPS["sleeper_send_failed"]` key set is unchanged (constrains keys, not values) and `NON_INTENT_EVENTS` is untouched in the diff.

**W-1 — the four mounts still pass mixed arrays.** Not in the diff. `TradesScreen.tsx:8351-8355` (`topCard.give_player_ids` / `receive_player_ids`), `TradeCard.tsx:978-982` and `:987-991` (`data.*`; the second carries `surface="awaiting"` at `:1009`), `InLeagueCalculator.tsx:1467-1471` (`giveIds` / `receiveIds`). `doPropose` forwards them verbatim (`:223-229`). Pick-id shapes: owned = `{league}_{season}_{round}_{orig}` (`TradesScreen.tsx:4442-4447` comment + prefix test; calculator prices `all_picks[].pick_id` at `InLeagueCalculator.tsx:493-509`), generic = `GENERIC_PICK_ID_PREFIX = "generic_pick_"` (`pick_values.py:213`); `_is_ftf_pick_asset` (`server.py:27977-27982`) splits on exactly those two.

**R-3 / guardrail 8 — literal platform source.** `:16257` and `:27856` pass `source=PICK_SOURCE_PLATFORM` literally; `test_pick_assignment.py:244-253` sanctions `propose_trade_to_sleeper` and `trades_validate` by name; O-4 shows the guard goes RED if the kwarg is dropped. O-5 shows it stays GREEN if the value becomes `_pick_read_source()` (F-5).

**R-4 / R-12 — no upstream call for pick-free sends.** Both fetches sit inside `if give_picks or recv_picks:` (`:16252`, `:27852`). `_fetch_sleeper_traded_picks` (`:13895-13908`) and `_fetch_league_rosters` (`:13886-13893`) both ride `_sleeper_get`, which is why the single-`return_value` stubs in the seven pre-existing propose tests stay honest only under this guard (LLD §7.1) — P-T10 / P-V6 prove the guard.

**Contract consistency.** Server 422 `message`/`detail` strings vs the mobile branches rendered with `n = 0`: **byte-equal for both codes** (scripted comparison over the actual source files; n=1 → "1 draft pick … has already changed hands …", n=2 → "2 draft picks … have …"). Validate `code`s `asset_unmapped` / `pick_moved` are listed in `docs/api-reference.md` (validate row + Sleeper codes sentence) and `docs/cross-client-invariants.md:827`; the two 422 rows and the `bad_request` extension are in the api-reference error table; `docs/integrations/sleeper.md` rows 6, 15 and §3.3 are updated; `docs/architecture.md` gains the `sleeper_write.py` component row and the two data-flow edges.

## Findings

### F-1: The four `living-memory/` docs scope §4 marks "updated — required" are absent at the group tip — Severity major (docs gate) — Repro: `git diff ad5adafa..8e4e1648 --stat -- living-memory/` is empty; `git grep -n "D-172\|Q-035" -- living-memory/` → 0 hits; `DECISIONS.md` max is D-171, `OPEN_QUESTIONS.md` max is Q-034 — Expected (PRD §11, §12, R-18, scope §4 rows for `living-memory/LLD.md` "updated", `HLD.md` "updated — one line", `DECISIONS.md` "updated — required", `OPEN_QUESTIONS.md` "updated") vs actual: none written. If the orchestrator owns these at ship (scope §4 marks only CHANGELOG/TEST_LEDGER/NEXT/status as "at ship"), this is a hand-off note, not a builder defect — but gate 3 ("scope block → evidence → docs → ledger, all four") is not met at `8e4e1648`.

### F-2: LLD §3.3 row 7 / api-reference / propose docstring say a foreign-league or malformed pick id is `422 sleeper_pick_unmapped`; the code treats it as a player — Severity minor — Repro: `_ftf_pick_parts` (`server.py:27965-27974`) matches `^{league_id}_(\d{4})_(\d{1,2})_(.+)$` only; `999_2027_1_3` or `abc_def` on league `L` returns `None`, so `_is_ftf_pick_asset` is `False` and the id lands in `give_players` → `k_adds` (`sleeper_write.py:286-292`) → Sleeper rejects → **502 `sleeper_write_failed`**, not 422; validate flags it `player_moved`. Expected (R-3 "other leagues' ids, malformed ids … fail this test identically", api-reference 422 row "foreign/malformed id") vs actual: never reaches the encoder. No client produces such an id (every mount uses the card's own `league_id`), so no user impact — the three doc sentences overstate the encoder's reach.

### F-3: PRD-named T-8 sabotage `if False:` is self-satisfying — Severity minor (test-plan accuracy) — Repro: P-T8a, 67 passed. With `row = None` the code proceeds to `row["season"]` → `TypeError` → `except (TypeError, ValueError, KeyError)` at `:28129` appends the id to `unmapped`, so T-8 still sees 422 `unmapped`. Expected (PRD §7.2 T-8 "must go RED") vs actual GREEN. T-8 is still a valid guard — the second-named sabotage (infer existence from rosters × horizon, P-T8b) goes RED — but TEST_LEDGER must not record the `if False:` variant as a proven-RED sabotage.

### F-4: R-13's "neither reads `detail`" and "counting is not rendering" are not mechanically pinned — Severity minor (coverage) — Repro: M-6 (branch renders `detail || 'x'`) and M-7 (branch renders `body.picks.join(', ')`) both leave `check-send-button-platform.js` green. Expected: PRD §7.4 names these as binding but only C-7/C-8 (Alert present, no goConnect) exist. Code-walk (above) confirms the shipped branches are correct; the gap is that a later edit could regress them silently. Suggest a `/\$\{n \|\| 'Some'\}/` + `!/detail/` + `!/picks\.(join|map)/` assertion inside 7/8 if the orchestrator wants it pinned.

### F-5: Guardrail 8 (literal `PICK_SOURCE_PLATFORM`, never `_pick_read_source()`) is not mechanically pinned — Severity minor (coverage) — Repro: O-5 replaces the literal with `source=_pick_read_source()` in the propose call; `test_w3_02*` stays green (4 passed) because the guard checks only that `source=` is named (`test_pick_assignment.py:272-288`). Expected (LLD §4.2 "not `_pick_read_source()`", PRD §8 guardrail 8) vs actual: no test reads the value. `test_w3_02d` pins the seven engine sites in the opposite direction only.

### F-6: Validate warning copy — grammar and quote-style — Severity minor (copy; matches the LLD literal) — Repro: `server.py:27867` renders n=1 as "1 pick in this trade **are** no longer owned by the expected team …" (the plural verb is fixed); `:27861` mixes a straight `can't` with curly `“Early 1st”` and an em dash in the same sentence, while the propose 422 at `:16266` uses curly `can’t`. LLD §5 pins both strings verbatim and also says the list "must not mix quote styles". Expected: the LLD; actual: the LLD, slip included — a planner-level copy fix, not a builder defect.

### F-7: `scope.md:128` still says "Suite counts (+18)" — Severity minor (stale doc) — Repro: `reconciliation-log.md` §"Test delta, recounted" and PRD §7.5 say +20; actual +20 (4483 → 4503). One number to correct.

Informational (no finding): O-6 — a not-owned pick that is *also* encoded is not detectable from outside the route (the 422 fires first); the encoder's "exactly one of three lists" contract is docstring-only. O-2 — T-6 is the only test that pins field 1 = grid `orig` (T-4/T-5 fixtures have `orig == from`).

## TestFlight checklist (operator-run)

Verified runnable on **1.16.14 (build 2)** against `config/features.json` as read above (`trade.send_in_sleeper`, `picks.owned_sync`, `trade.picks_in_pool` all true — the deck injects owned picks for non-ESPN leagues, `server.py:11343-11348`; the calculator's picker is grouped by `owner_user_id`, `InLeagueCalculator.tsx:517`, so the partner's picks are offered). Run only after Render has deployed `8e4e1648`'s backend. Real Sleeper league, verified session (Settings → Connect Sleeper if the send returns "Verify your account"). **Cancel every proposal in Sleeper afterwards. Log each outcome in TEST_LEDGER.**

| # | Screen → action | Expected |
|---|---|---|
| **TF-1** (mandatory, Half A) | Trades deck (or Matches → Awaiting row): open a card whose **give** side contains one of **your own original** future picks (e.g. your 2027 2nd). Tap **Send in Sleeper**. | The plain **"Send this trade?"** confirm. No "This trade will likely fail" and no "…no longer on the expected roster" line. |
| **TF-2** (mandatory, Half B / R-5 give) | Same card → **Send**. | **"Trade sent"** alert. In the Sleeper app the pending offer lists that pick (season + round, "via <your team>") on your side. Cancel it in Sleeper. |
| **TF-3** (conditional, Q-035) | Calculator: only if you hold a pick you **acquired from another team**: build a trade giving that pick → Send. If you hold none in any league, log **"not run — Q-035 stays open"**. | "Trade sent"; Sleeper shows the pick with the **original** team's name moving from you to the partner. Cancel. **If it fails** with "Sleeper wouldn't accept the send" / "Couldn't send" + a detail line, copy the detail text verbatim into the ledger — that is the field-1 falsification (encoder flips field 1 to the current holder). |
| **TF-4** (mandatory, R-5 receive) | Calculator: build a trade **receiving** one of the partner's own picks (pick it from their side of the picker) → Send. | "Trade sent"; Sleeper shows the pick moving from them to you. Cancel. |
| **TF-5** (opportunistic, R-7) | Calculator: only if a partner's pick has **changed hands in Sleeper since the app last synced** (a real pick trade happened after you opened the app): put that pick on their side → Send. | Pre-send alert **"This trade will likely fail"** with "1 pick in this trade are no longer owned by the expected team (already traded) — Sleeper will reject the offer." → **Send anyway** → **"Couldn't send"** — on 1.16.14: "1 draft pick in this trade has already changed hands, so nothing was sent. Rebuild the trade and try again." (a fielded build ≤1.16.14 without this branch shows the "Some draft picks …" server sentence). Nothing appears in Sleeper. Proof of record otherwise: T-9 / V-3. |
| **TF-6** (opportunistic, R-6) | Trades deck: only if a Sleeper card shows a **generic rung** ("Early 1st", "Mid 2nd"): tap Send. | Pre-send alert **"This trade will likely fail"** with "1 draft pick in this trade can't be sent to Sleeper (generic picks like “Early 1st” name no real pick) — the send will be blocked rather than dropping them." → Send anyway → **"Couldn't send"** — "1 draft pick in this trade couldn’t be matched to a pick in this Sleeper league, so nothing was sent. Generic picks like “Early 1st” can’t be sent — use a specific pick." Nothing in Sleeper. Proof of record otherwise: T-7 / V-2. |
| **TF-7** (mandatory, regression) | Any surface: a **player-only** trade → Send. | Unchanged: plain confirm → "Trade sent" → offer in Sleeper. Cancel. |

Note for the ledger: the app build cannot distinguish the new alert wording from the fielded catch-all except by the leading count ("1 draft pick …" vs "Some draft picks …"); record which sentence was seen.
