# QA round 1 — agent A — 2026-09-02

## Summary: PASS (7 findings: 0 blocker · 1 major · 4 minor · 2 observations)

The code under test does what the PRD says it does. Every requirement R-1…R-17 is either
mechanically proven green here or code-walked below; R-18 is orchestrator-owned (N/A). Every
PRD-named sabotage I could apply went RED on the named test, with one honest exception (T-8a's
`if False:` is not a behavior change — see Sabotage table). The one **major** finding is not a
code defect: the living-memory docs scope §4 marks "updated — required" (D-176, Q-037, the
`LLD.md` H2, the `HLD.md` line) are absent from the group tip `8e4e1648`. If those are the
orchestrator's ship-time writes, gate 3 is met at ship; if not, it is unmet at this tip.

## Environment

| Item | Value |
|---|---|
| Worktree / branch | `wt-fb413-qa-a`, `qa/fb413-a` |
| Tip under test | `8e4e1648` feedback #413: mobile — count-aware alerts… (confirmed top of `git log -7`; chain `ad5adafa` → `b4aabcc3` → `31e8d590` → `b938642b` → `51794a35` → `8e4e1648`) |
| Diff under test | `git diff ad5adafa..8e4e1648` — 20 files, +876/−49 |
| Node / Python | v24.14.1 / Python 3.14.4, pytest 9.0.3 |
| Mobile deps | `npm ci --no-audit --no-fund` → 801 packages, exit 0 |
| Flags | none pinned; route tests force `trade.send_in_sleeper` via patched `is_enabled` (existing idiom); validate tests likewise |
| D-056 | static + code-walk only. No simulator, no Maestro, no captures |
| Tree state at end | `git status` clean except this report |

Two run notes, recorded because they affect what the numbers mean:

- My first full-suite launch never ran — zsh's `rm -f data/trade_finder.db*` errors on no match
  and aborted the `&&` chain (`pytest exit 1`, empty log). Re-launched with `setopt nullglob`.
- The sabotage driver restores via `git checkout` between cases; for two consecutive same-file, same-size edits inside one second (only T-1a → T-1b qualified) Python's `.pyc` invalidation (mtime seconds + size) can reuse stale bytecode. T-1b was therefore rerun in isolation and that result is what the table reports.
- My targeted run then deleted `data/trade_finder.db` while the second full run was at ~47 %.
  That run still finished **4503 passed / 1 skipped** (52 swallowed `record_event … no such
  table` stderr lines, zero failures). I re-ran the suite a third time with nothing else
  touching the DB — see Results row 1 for the clean count. The clean run also emits 38 of
  those `no such table: user_events` stderr lines, so they are inherent to a fresh-DB suite run
  (best-effort `record_event` writes from `receipts_grade_run`), not an artifact of my deletion.

## Results

| Test | Verdict | Evidence |
|---|---|---|
| §7.5 `pytest backend/tests` (clean re-run, no interference) | **PASS** | **4503 passed / 1 skipped in 296.66s** (`pytest exit 0`) — exactly the PRD's expected +20 over the 4483 baseline |
| §7.5 same suite, second run (DB deleted mid-run by me) | PASS | 4503 passed / 1 skipped in 306.59s; no failures |
| Target files only (`test_sleeper_write.py`, `test_sleeper_write_route.py`, `test_trade_send_validate.py`, `test_pick_assignment.py`) | PASS | 103 passed in 5.24s |
| §7.5 `npx tsc --noEmit` (mobile) | PASS | exit 0, no output |
| §7.5 `for f in tests/check-*.js` (89 guard files) | PASS | 0 `FAIL` lines |
| §7.5 `bash scripts/testid-lint.sh` | PASS | `testid-lint OK`, exit 0 |
| §7.4 `node tests/check-send-button-platform.js` | PASS | 30 PASS lines incl. the 4 new (7, 8, 7b, 7c); "All send-button platform-routing checks passed." |
| T-1 `test_encode_draft_pick_shape` | PASS | green; sabotage T-1a/T-1b RED |
| T-2 `test_pick_only_trade_builds_body` | PASS | green; sabotage T-2 RED |
| T-3 `test_propose_success_fires_no_trade_sent_on_sleeper` (fixture fixed) | PASS | green; asserts adapter got `["100","101"]` + `["1,2027,2,1,2"]`; sabotage T-3 RED |
| T-3b `test_propose_success_labels_impression_propose` | PASS | green; sabotage T-3b RED (`Called 0 times`) while T-11 stayed green — the pair behaves as designed |
| T-4 `test_propose_encodes_give_pick_from_to` | PASS | green; sabotage RED |
| T-5 `test_propose_encodes_receive_pick_flips_from_to` | PASS | green; sabotage RED |
| T-6 `test_propose_acquired_pick_uses_traded_picks_holder` | PASS | green; sabotage RED |
| T-7 `test_propose_hard_blocks_generic_pick` | PASS | green; all three named sabotages RED |
| T-8 `test_propose_hard_blocks_pick_missing_from_grid` | PASS | green; sabotage T-8b RED; T-8a (`if False:`) GREEN — not a behavior change, see table |
| T-9 `test_propose_hard_blocks_pick_not_owned` | PASS | green; both named sabotages RED |
| T-10 `test_propose_pick_free_send_makes_no_traded_picks_fetch` | PASS | green; sabotage RED |
| T-11 `test_propose_422_fires_no_success_event_and_no_deck_outcome` | PASS | green; sabotage RED |
| T-12 `test_propose_rejects_client_supplied_draft_picks` | PASS | green; sabotage RED |
| T-13 `test_propose_success_pick_n_honest` | PASS | green; sabotage RED |
| T-14 `test_propose_reports_unmapped_before_not_owned` | PASS | green; both named sabotages RED |
| V-1 `test_owned_pick_not_flagged_as_player_moved` (#413 repro) | PASS | green; sabotage RED |
| V-2 `test_generic_pick_flags_asset_unmapped` | PASS | green; sabotage RED |
| V-3 `test_pick_owned_by_other_roster_flags_pick_moved` | PASS | green; sabotage RED |
| V-4 `test_receive_side_pick_checks_their_roster` | PASS | green; sabotage RED |
| V-5 `test_roster_limit_excludes_picks` | PASS | green; sabotage RED |
| V-6 `test_pick_free_validate_makes_no_pick_fetch` | PASS | green; sabotage RED |
| C-7 / C-8 / C-7b / C-7c | PASS | green; all named sabotages RED (see table) |
| Pre-existing `test_sleeper_write_route.py:112-330` unedited except T-3 | PASS | `git diff ad5adafa..8e4e1648 -- backend/tests/test_sleeper_write_route.py` touches only the module docstring, the new helpers, and T-3 |
| `test_pick_assignment.py::test_w3_02*` (ADR-010 AST guard) | PASS | green with `propose_trade_to_sleeper` / `trades_validate` sanctioned by name |
| R-1 contract unchanged, mixed arrays | PASS | T-3/T-4 + W-1 below |
| R-2 non-empty `draft_picks` → 400 with `detail == message`; `[]` accepted | PASS | T-12 |
| R-3 existence = grid by `pick_id`, platform source | PASS | T-7, T-8, V-2; call is `load_draft_picks(league_id, source=PICK_SOURCE_PLATFORM)` (`server.py:16257`, `:27856`) — literal, not `_pick_read_source()` |
| R-4 holder = live `traded_picks`, default original; fetched only with picks | PASS | T-6, T-10, V-3, V-6 |
| R-5 orientation, `orig` from grid row | PASS | T-1, T-4, T-5, T-6; own sabotage O-1 RED |
| R-6 422 `sleeper_pick_unmapped`, both sides give-then-receive, before R-7, `detail == message` | PASS | T-7, T-8, T-14; own sabotage O-8 RED |
| R-7 422 `sleeper_pick_not_owned`, `detail == message` | PASS | T-9 |
| R-8 whole-send refusal invisible to the success spine, positive half | PASS | T-7, T-9, T-11, T-3b + code-walk below |
| R-9 adapter gets players-only arrays + encoded picks; pick-only legal | PASS | T-2, T-3 |
| R-10 `give_n`/`receive_n` players only, `pick_n` encoded | PASS | T-13 |
| R-11 validate splits, two blocking advisories, players-only math | PASS | V-1…V-5; own sabotage O-7 RED |
| R-12 validate no extra upstream call pick-free | PASS | V-6 |
| R-13 two alert branches, count-aware pinned copy, no `goConnect`, no `detail` | PASS (partial mechanical) | C-7/C-8/C-7b/C-8alt RED; "no ids rendered" / "no `detail` read" proven by code-walk only (F-3) |
| R-14 comment sites | PASS | `SendInSleeperButton.tsx:252-253` (14 ∪ 3 = 17), `sendInSleeper.ts:5-7` (code list incl. both), `:215` (warning list incl. `asset_unmapped \| pick_moved`) |
| R-15 warnings render with zero client change | PASS | code-walk below; `confirmSend` unchanged in the diff |
| R-16 enum 15 → 17 at four sites | PASS | `analytics_taxonomy.py:1057`, `SendInSleeperButton.tsx:253`, addendum `:72`, `cross-client-invariants.md:827` all say 17; `git grep "15 values\|15-value"` over those paths → 0 hits; route emits exactly 14 distinct server codes (grep of `"error": "…"` in `server.py:16156-16340`) |
| R-17 `:288` false-confidence fixture fixed | PASS | T-3 now sends the pick in `give_player_ids` and asserts the adapter request |
| R-18 Q-037 logged | **N/A** (orchestrator) | not in the tree — `OPEN_QUESTIONS.md` max is Q-034 (see F-1) |
| §6 contract consistency | PASS | see "Contract consistency" below |

## Sabotage table (PRD-named + my own)

Driver: `scratchpad/sabotage_a.py` — applies one edit with an exact-count assertion, runs the
named test, restores with `git checkout --`, asserts a clean tree after every case. Full log
`scratchpad/sabotage_a.log`, JSON `scratchpad/sabotage_results_a.json`.

| # | Sabotage (file) | Named test | Result | Failing assertion (first `E` line) |
|---|---|---|---|---|
| T-1a | swap `from`/`to` in the encoder f-string (`sleeper_write.py`) | T-1 | **RED** | `assert '7,2027,1,5,3' == '7,2027,1,3,5'` |
| T-1b | emit `orig` as the 4th field | T-1 | **RED** | `assert '7,2027,1,7,5' == '7,2027,1,3,5'` — from an isolated rerun; the batch run's line for T-1b was identical to T-1a's because the two same-size edits landed within one second and Python's mtime+size `.pyc` check reused T-1a's bytecode (see run notes) |
| T-2 | drop `(req.draft_picks or [])` from the empty-trade guard `:295` | T-2 | **RED** | `SleeperWriteError: trade has no assets on either side` |
| T-3 | raw arrays to the adapter, `draft_picks=None` | T-3 | **RED** | `assert ['100','101','…_2027_2_1'] == ['100','101']` |
| T-3b | delete the propose route's `_save_deck_outcome_safe` (anchored to `:16309-16312`; the bare line occurs 3× in `server.py`) | T-3b | **RED** | `Expected 'mock' to be called once. Called 0 times.` — T-11 stayed green, as designed |
| T-4 | give side `from = their_rid` | T-4 | **RED** | 422 `sleeper_pick_not_owned` instead of 200 |
| T-5 | give branch for both sides | T-5 | **RED** | 422 `sleeper_pick_not_owned` instead of 200 |
| T-6 | `holder = None` (ignore overlay) | T-6 | **RED** | 422 `sleeper_pick_not_owned` instead of 200 |
| T-7a | drop generic rungs from both lists, send players | T-7 | **RED** | `{"status":"proposed","transaction_id":"TX9"}` (200) |
| T-7b | drop receive-side picks from the encoder | T-7 | **RED** | `assert ['generic_pick_1_early'] == ['generic_pick_1_early','generic_pick_2_mid']` |
| T-7c | drop `detail` from the unmapped 422 | T-7 | **RED** | `KeyError: 'detail'` |
| T-8a | `if row is None:` → `if False:` | T-8 | **GREEN** | — the `None` row then raises `TypeError` in `row["season"]`, which the encoder's `except (TypeError, ValueError, KeyError)` classifies as `unmapped`. Behavior is unchanged, so a green result is correct. This PRD-named sabotage does not prove T-8; T-8b does (F-6) |
| T-8b | synthesize the grid from `rosters × seasons 2026-2034 × rounds 1-5` instead of `load_draft_picks` | T-8 | **RED** | 200 `{"status":"proposed"…}` instead of 422 |
| T-9a | `if holder != from_rid:` → `if False:` | T-9 + V-3 | **RED** | T-9: 200 instead of 422; V-3: `assert [] == ['pick_moved']` |
| T-9b | drop `detail` from the not_owned 422 | T-9 | **RED** | `KeyError: 'detail'` |
| T-10 | propose `if give_picks or recv_picks:` → `if True:` | T-10 | **RED** | `Expected 'mock' to not have been called. Called 1 times.` |
| T-11 | label the impression `propose` before the unmapped return | T-11 | **RED** | `Expected 'mock' to not have been called. Called 1 times.` |
| T-12 | remove the 400, `draft_picks=(encoded + picks)` | T-12 | **RED** | 200 instead of 400 |
| T-13 | `_record_send_success(…, give, receive, [], …)` | T-13 | **RED** | props dict mismatch (`give_n` 3, `pick_n` 0) |
| T-14a | not_owned block before unmapped | T-14 | **RED** | `assert 'sleeper_pick_not_owned' == 'sleeper_pick_unmapped'` |
| T-14b | `if unmapped or not_owned:` with merged `picks` | T-14 | **RED** | `assert ['generic_pick_1_early','…_2027_2_1'] == ['generic_pick_1_early']` |
| V-1 | `moved_*` over raw `give`/`receive` | V-1 | **RED** | `assert [{'code':'player_moved',…}] == []` |
| V-2 | validate split on `_ftf_pick_parts` only (generic → player) | V-2 | **RED** | `assert ['player_moved'] == ['asset_unmapped']` |
| V-3 | (same edit as T-9a) | V-3 | **RED** | `assert [] == ['pick_moved']` |
| V-4 | both sides `(my_rid, their_rid)` | V-4 | **RED** | `assert ['pick_moved'] == []` (their own pick on the receive side now flags) |
| V-5 | roster-limit tuples over raw `give`/`receive` | V-5 | **RED** | `assert ['roster_limit'] == []` |
| V-6 | validate `if give_picks or recv_picks:` → `if True:` | V-6 | **RED** | `Expected 'mock' to not have been called. Called 1 times.` |
| C-7 | delete the `sleeper_pick_unmapped` branch | check 7 | **RED** | `FAIL sleeper button: sleeper_pick_unmapped has its own Alert branch…` + 7b |
| C-8 | delete the `sleeper_pick_not_owned` branch | check 8 | **RED** | `FAIL sleeper button: sleeper_pick_not_owned has its own Alert branch…` + 7b |
| C-7b | move the not_owned branch after the catch-all as a second `if` | check 7b | **RED** | only 7b fails — presence checks stay green, which is 7b's point |
| C-8alt | add `\|\| code === 'sleeper_pick_not_owned'` to the reconnect condition, dedicated branch kept | check 8 | **RED** | `FAIL … not_owned has its own Alert branch, no goConnect` |
| C-7c | catch-all copy → `'Please try again.'` | check 7c | **RED** | `FAIL … the catch-all else still renders the generic failure copy` |
| **O-1** (own) | encode always `(my_rid, their_rid)` while the holder check stays per-side — the receive-only orientation slip | route + validate | **RED** | T-5: `assert ['2,2026,1,1,2'] == ['2,2026,1,2,1']` (1 failed / 43 passed) |
| **O-2** (own) | `_sleeper_pick_holder_index` keyed on `owner_id` instead of `roster_id` | route + validate | **RED** | T-6 + 2 more: acquired pick 422 `not_owned` (3 failed / 41 passed) |
| **O-3** (own) | drop the `int()` coercion in `encode_draft_pick` | adapter + route | **RED** | T-1: `Failed: DID NOT RAISE ValueError` (1 failed / 50 passed). Note: string inputs still format identically without `int()`, so only the `raises` clause catches it — the route tests do not (orig is already `str`, ids `int`) |
| **O-4** (own) | `return encoded[::-1], …` (reverse give-then-receive order) | route + validate | **GREEN** | 44 passed — no test sends ≥2 encodable picks, so LLD §3.2's "encoded preserves give-then-receive order" is unpinned (F-2) |
| **O-5** (own) | default holder = `from_rid` ("assume the offerer holds it") | route + validate | **RED** | V-4 second half: `assert [] == ['pick_moved']` |
| **O-6** (own) | holder stored as `str` in the index (str-vs-int compare) | route + validate | **RED** | T-6 422 `not_owned` |
| **O-7** (own) | both validate advisories `severity: "warning"` | validate | **RED** | V-2 + V-3: `assert 'warning' == 'blocking'` |
| **O-8** (own) | receive picks listed before give picks | route + validate | **RED** | T-7: order mismatch |
| **O-9** (own) | mappable pick also left in `give_players` (double-send) | route + validate | **RED** | T-3 + T-13 (2 failed / 42 passed) |
| **O-M1** (own, mobile) | render `body.picks.join(', ')` in the unmapped alert | checks 7/8 | **GREEN** | structural checks assert `Alert.alert` + no `goConnect` only — "counting is not rendering" is code-walk-only (F-3) |
| **O-M2** (own, mobile) | unmapped branch renders `detail \|\| 'x'` | checks 7/8 | **GREEN** | same limit (F-3) |

Tally: 32 PRD-named cases run, 31 RED, 1 GREEN-by-design (T-8a). 11 own cases, 8 RED, 3 GREEN
(coverage gaps, all minor).

## Fixture-shape audit

| Fixture | Shape in test | Production shape | Verdict |
|---|---|---|---|
| `ROSTERS_1V2` (`test_sleeper_write_route.py`) | `roster_id` ints 1/2, `owner_id` strings | Sleeper `/v1/league/{id}/rosters` carries int `roster_id`; `_roster_id_for_owner` casts to `int` (`server.py`, `_roster_id_for_owner` → `int(hit.get("roster_id"))`) | faithful |
| `TRADED` rows `{season:"2027", round:1, roster_id:7, owner_id:1, previous_owner_id:7}` | string season, int ids | matches the captured live fixture `backend/tests/fixtures/outlook-hypotheses/ffv3-2024.json:6-12` (`"season": "2024"`, int `roster_id`/`owner_id`/`previous_owner_id`) and `_fetch_sleeper_traded_picks`'s docstring | faithful |
| `GRID` rows `{pick_id, season:int, round:int, original_roster_id:"1"}` | 4 keys | `load_draft_picks` returns `dict(r._mapping)` over `draft_picks_table` — `season`/`round` are `Integer` columns, `original_roster_id` is `String` written as `rid_str = str(roster_id)` (`database.py:10027`); production rows carry more keys, the encoder reads only these four | faithful (subset) |
| `load_draft_picks` patched as `MagicMock` (route) / `lambda lid, *a, **k` (validate) | accepts the `source=` kwarg | real signature `load_draft_picks(league_id, owner_user_id=None, source=PICK_SOURCE_PLATFORM, include_contested=False)` — `league_id` is positional, so the production call `load_draft_picks(league_id, source=PICK_SOURCE_PLATFORM)` is valid (I checked this specifically: every other `server.py` call site passes `league_id=` by keyword, and a mock would hide a keyword-only signature) | no defect hidden |
| Body `their_roster_id: 2` on every new route test | int, client-unused shortcut | mobile sends `their_user_id` (`ProposeTradePayload`); the `their_user_id` → `_roster_id_for_owner` → `int` path is covered by the pre-existing test at `:144` (`"their_user_id": "opp_uid"`) and both paths yield an `int` `their_rid` (`:16228-16233`) | no defect hidden (F-7 notes it) |
| Validate body `their_user_id: OPP` | production shape | `_roster_id_for_owner(rosters, OPP)` → 2 | faithful |
| Validate `get_sleeper_credential → None` | `my_owner = user_id` | the propose route uses `cred["sleeper_user_id"]`; the validate route falls back to `user_id` when unlinked — both are the Sleeper user id for Sleeper leagues (FTF user_id == Sleeper user_id) | faithful |
| `league.members` caller-excluded convention | n/a | neither route reads `league.members`; rosters come from the public rosters fetch | n/a |
| Pick ids `f"{LEAGUE}_2027_2_1"`, `generic_pick_1_early` | | the two shapes `_is_ftf_pick_asset` splits on: `_ftf_pick_parts` regex `^{league}_(\d{4})_(\d{1,2})_(.+)$` and `GENERIC_PICK_ID_PREFIX = "generic_pick_"` (`pick_values.py:213`); mobile produces exactly these (`TradesScreen.tsx:4442-4447`, `InLeagueCalculator.tsx:497-498` `id: p.pick_id`) | faithful |
| Phantom `f"{LEAGUE}_2031_1_1"` (T-8) | | passes the split (regex) and has no grid row — the intended path | faithful |

No fixture would hide a real defect.

## Code-walk proofs (per requirement)

All cites are against the merged tree at `8e4e1648`.

**R-8 — refusals precede the success spine; a success still labels once.**
`server.py:16249-16273` is the pick block (`if give_picks or recv_picks:` at `:16252`). The two refusals `return jsonify(...), 422` at
`:16267` (unmapped) and `:16272` (not_owned). The Sleeper write is `result =
_sleeper_write.propose_trade(token, req)` at `:16281`. `_save_deck_outcome_safe(body.get("impression_id"),
"propose", acting_user_id=user_id)` is at `:16311-16312` and `_record_send_success(...)` at
`:16321-16325` — both strictly after `:16281`, both reached exactly once on the success path
(no loop, no second call in the route). The 422s are `return` statements, so nothing below
`:16273` executes on refusal. **When the path does NOT fire:** the block is guarded by
`if give_picks or recv_picks:` (`:16252`) — a player-only body skips `:16253-16273` entirely,
`encoded` stays `[]`, and the request is built with `draft_picks=None` (`:16278`), which is the
pre-#413 request byte-for-byte. Mechanical twins: T-11 (gate before call), T-3b (call not
deleted), T-10 (no fetch pick-free).

**R-13 — branch order and the fielded-build catch-all.**
`SendInSleeperButton.tsx:246` `catch (err)` → `:247` `body` → `:254-264` `track('sleeper_send_failed', …)`
(before the ladder) → `:266` `code = body?.error`, `:267` `detail = body?.detail` → ladder:
`:269` `sleeper_not_linked || sleeper_expired` (→ `goConnect` `:277`), `:280` `verification_required`
(→ `goConnect` `:290`), `:293` `sleeper_rejected`, `:298` `sleeper_unconfigured || feature_disabled`,
`:300` `roster_not_found || opponent_roster_not_found`, **`:305` `sleeper_pick_unmapped`**,
**`:316` `sleeper_pick_not_owned`**, `:323` catch-all `else` rendering
`detail || 'Something went wrong sending to Sleeper. Please try again.'` (`:326`). The two new
branches sit inside the `else if` chain, so exactly one `Alert.alert` fires per 422. `goConnect`
is referenced at `:215` (def), `:277`, `:290`, `:330` (deps), `:422`, `:426` (deps) — never inside
`:305-322`. `detail` is read at `:267` and used only at `:296` (`sleeper_rejected`) and `:326`
(catch-all) — never inside `:305-322`. `n` at `:311`/`:318` is `body.picks.length`; the template
strings at `:314`/`:321` interpolate only `n`. **Fielded-build path (1.16.12–1.16.14):** the
ladder ends at `:300-304` there, so both 422s fall to the catch-all and render the server's
`detail`, which `server.py:16268`/`:16273` set to `_msg` — byte-equal to the new build's n=0
sentence (verified below). **When the path does NOT fire:** a 200 never enters the `catch`; a
non-`ApiError` (network) has `body === undefined` → `code === undefined` → catch-all.

**R-15 — warnings render unchanged.**
`confirmSend` `:336-367` is untouched by the diff (`git diff ad5adafa..8e4e1648 -- SendInSleeperButton.tsx`
shows only the comment at `:252-253` and the two branches). `:346` `if (warnings.length > 0)`,
`:347` `blocking = warnings.some(w => w.severity === 'blocking')`, `:349` title, `:350`
`warnings.map(w => \`• ${w.message}\`)` — code-agnostic. The server emits both new codes with
`"severity": "blocking"` (`server.py:27860`, `:27866`), so a pick advisory titles "This trade
will likely fail" with the server sentence. `TradeSendWarning.code` is `string` (`sendInSleeper.ts:215`),
so no type change is needed. **When it does NOT fire:** `validateTradeSend` resolves
`checked:false` / `warnings:[]` → plain "Send this trade?" (`:360`).

**R-16 — the four enum-comment sites.**
`backend/analytics_taxonomy.py:1055-1058` "14 server codes … 17 values"; `SendInSleeperButton.tsx:252-253`
"14 server codes ∪ network | timeout | unknown = 17 values"; `docs/business/analytics/2026-08-11-p0-7-addendum.md:71-79` (and the `give_n`/`pick_n` semantics note at `:59-64`)
"17 values, forever (15 → 17 on 2026-09-02, #413 …)"; `docs/cross-client-invariants.md:827` lists all
17 by name. Independent count of `"error": "…"` literals in `server.py:16156-16340` = 14 distinct
codes (`bad_request, feature_disabled, no_user, opponent_roster_not_found, roster_not_found,
sleeper_expired, sleeper_not_linked, sleeper_pick_not_owned, sleeper_pick_unmapped,
sleeper_rejected, sleeper_unconfigured, sleeper_write_failed, test_mode_propose_disabled,
verification_required`) — matches the invariants listing exactly. No "15 values" survives.

**W-1 — the four mounts still pass mixed arrays.**
Unchanged in the diff: `TradesScreen.tsx:8351-8355` (`topCard.give_player_ids` / `receive_player_ids`),
`TradeCard.tsx:978-982` and `:1000-1004` (`data.give_player_ids` / `receive_player_ids`),
`InLeagueCalculator.tsx:1467-1471` (`giveIds` / `receiveIds`). `doPropose` forwards them
verbatim (`SendInSleeperButton.tsx:223-229`); `git grep -n draft_picks -- mobile/src/api/sendInSleeper.ts mobile/src/components/SendIn*.tsx`
→ 0 hits (guardrail 6 holds by absence).

**R-3/R-4 — validate's pick block is only reached with both rosters resolved.**
`server.py:27827-27841`: `mine`/`theirs` come from `by_rid`, and `if mine is None or theirs is None`
returns `roster_not_found` before the pick block at `:27847-27868` (`if give_picks or recv_picks:` at `:27852`). So `my_rid`/`their_rid` are `int`
whenever `_sleeper_encode_ftf_picks` runs in validate — the int-vs-int rule (LLD §3.1) holds.

**W-5 — the 422 reaches analytics.** `:256-258` `error_code: err.isTimeout ? 'timeout' : (body?.error ?? 'unknown')`,
`:259` `status: err.status` (422), `:260` `kind: body?.kind ?? null` (null — neither 422 body
carries `kind`). Emitter untouched.

## Contract consistency

- **Server 422 `message`/`detail` vs mobile n=0 form:** rendered mechanically (script in the
  session log) — `sleeper_pick_unmapped`: byte-equal (`True`); `sleeper_pick_not_owned`:
  byte-equal (`True`). n=1 renders "1 draft pick in this trade has already changed hands…",
  n=2 "2 draft picks … have …".
- **`detail == message`** on both 422s (`:16268`, `:16273`) and the new 400 (`:16209`); T-7/T-9/T-12 pin it.
- **Validate warning codes** `asset_unmapped` / `pick_moved` (`:27860`, `:27866`) are listed in
  `docs/api-reference.md:406` (validate row) and in the `cross-client-invariants.md:827`
  vocabulary; both pre-exist in the MFL branch (`:28158`, `:28185`), so the shared field's
  vocabulary is unchanged in kind.
- **`docs/api-reference.md`:** propose row (`:405`) describes mixed arrays, the two ground
  truths, the whole-send refusal and the `draft_picks` 400; error table gains the two 422 rows
  (`:419-420`) and the 400 row gains the `draft_picks` reason (`:421`); the "v1 scope" line is
  replaced (`:423`, cites Q-016/Q-037). No `draft_picks?` remnant (`grep "draft_picks?"` → 0).
- **`docs/integrations/sleeper.md`:** op 6 `traded_picks` consumers (`:43`), op 15 `propose_trade`
  (`:62`), §3.3 element shape + field-1 caveat (`:208-217`) — present.
- **`docs/architecture.md`:** new `sleeper_write.py` row (`:154`), mermaid `SL → SRV` label
  gains `traded_picks - pick sends` (`:39`), new `DB → SRV` edge (`:50`) — present.
- **`backend/tests/test_pick_assignment.py`:** both routes sanctioned by name with a decision
  comment; `test_w3_02` green.

## Findings

### F-1: Living-memory docs owed by scope §4 are not in the group tip — Severity **major** (orchestrator-scoped) — Repro: `grep -o "^## D-[0-9]*" living-memory/DECISIONS.md | tail -1` → `D-171`; `grep -o "Q-0[0-9]*" living-memory/OPEN_QUESTIONS.md | sort -u | tail -1` → `Q-034`; `git grep -n 413 -- living-memory/LLD.md living-memory/HLD.md` → 0 — Expected (scope §4 "updated — required": `DECISIONS.md` D-176 + index row; `OPEN_QUESTIONS.md` Q-037; `LLD.md` new H2 per LLD §10; `HLD.md` one line; PRD §11/§12) vs actual: none of the four is present at `8e4e1648`; the diff touches no file under `living-memory/`. `docs/api-reference.md:423` already cites Q-037 as if it existed — Evidence: `git diff --stat ad5adafa..8e4e1648` (20 files, none in `living-memory/`). If the orchestrator writes these at ship (CHANGELOG/TEST_LEDGER/NEXT are explicitly "at ship"; D-176/Q-037/LLD/HLD are not labeled so), gate 3 closes then; otherwise it is open. R-18 is N/A for me either way.

### F-2: `encoded` give-then-receive order is unpinned — Severity **minor** (coverage) — Repro: sabotage O-4 (`return encoded[::-1], …`) → 44 passed — Expected (LLD §3.2 "`encoded` preserves give-then-receive order") vs actual: no test sends two encodable picks, so the claim has no mechanical guard — Evidence: sabotage table O-4. Sleeper's `draft_picks` list is very likely order-insensitive, so this is a documentation-vs-test gap, not a defect.

### F-3: R-13's "counting is not rendering" and "neither reads `detail`" are code-walk-only — Severity **minor** (coverage; expected under LLD §8.3) — Repro: sabotages O-M1 (render `body.picks.join(', ')`) and O-M2 (render `detail || 'x'`) → `check-send-button-platform.js` all green — Expected (R-13 → C-7/C-7b/C-7c/C-8 mapping) vs actual: checks 7/8 assert `Alert.alert` presence + no `goConnect` + chain position only; the pinned-copy half of R-13 rests on W-2 — Evidence: sabotage table O-M1/O-M2; LLD §8.3 says "presence of exact wirings, not behavior", so this is by design, but the PRD's R-13 → C-n mapping overstates it. A one-line regex on the branch body (`/body\.picks\.(join|map)|\bdetail\b/` must not match) would close it if wanted.

### F-4: Validate advisory copy — grammar and quote-style drift — Severity **minor** (copy) — Repro: render `server.py:27860-27868` with n=1 — Expected (Chalkline sentence-case body copy; LLD §5 "both strings can appear in the same alert list, so they must not mix quote styles") vs actual: `pick_moved` n=1 → "1 pick in this trade **are** no longer owned by the expected team…" (verb disagreement; mirrors the pre-existing `player_moved` quirk at `:27877-27880`); `asset_unmapped` n=1 → "…rather than dropping **them**"; the validate strings use a straight `can't` (`:27861`) while the propose strings and the mobile branches use curly `’` — all three are LLD §5 verbatim, so the LLD is the source; flag for the copy owner, no code deviation — Evidence: the rendering script output in the session log.

### F-5: File-name and path drift between PRD §9 and the delivered code-walk — Severity **minor** (docs) — Repro: `ls docs/feedback/items/413-sleeper-send-draft-picks/` — Expected `code-walk.md` (PRD §9, scope §3) vs actual `code-walk-mobile.md`; PRD §9 cites the calculator mount under `screens/`, the file is `components/InLeagueCalculator.tsx` (the code-walk itself notes this) — Evidence: directory listing; every line cite in `code-walk-mobile.md` re-verified correct on the merged tree (`:305`, `:311`, `:316`, `:318`, `:323-327`, `:254-264`, `:266-267`, `:336-367`; `server.py:16267`, `:16272`, `:27860`, `:27866`).

### F-6: PRD-named sabotage T-8a (`if False:`) does not go RED — Severity **observation** — Repro: sabotage table T-8a → 1 passed — Expected (PRD §7.2 "must go RED") vs actual: the sabotage is not a behavior change — the `None` row raises `TypeError` at `row["season"]` (`server.py:28099`) and the `except (TypeError, ValueError, KeyError)` at `:28104` classifies it `unmapped` anyway. T-8 is a correct test; the PRD's alternative sabotage (T-8b, rosters-derived existence) is the one that proves it — Evidence: sabotage table T-8a/T-8b. Recommend the TEST_LEDGER record T-8b as T-8's proof, not T-8a.

### F-7: New route tests use the client-unused `their_roster_id` body shortcut — Severity **observation** — Repro: `_propose()` hardcodes `"their_roster_id": 2` — Expected (PRD §7.2 fixtures per LLD §7.2) vs actual: mobile sends `their_user_id`; the `their_user_id` resolution path is covered by the pre-existing test at `test_sleeper_write_route.py:144` and both paths yield an `int` (`server.py:16228-16233`), so nothing is hidden — Evidence: fixture-shape audit row 5.

## TestFlight checklist (operator-run)

Runnable on **any build ≥ 1.16.12** once Render deploys the backend (request contract unchanged;
both 422s carry `detail`, which the fielded catch-all renders). On the new build the refusal
wording is count-aware ("1 draft pick …"); on a fielded build it is the server's "Some draft
picks …" — same sentence otherwise. Real Sleeper league, verified session
(`POST /api/sleeper/link` in this app session). **Cancel every proposal in Sleeper afterwards.**
Log each outcome in `living-memory/TEST_LEDGER.md`. Mandatory: TF-1, TF-2, TF-4, TF-7.
Conditional: TF-3. Opportunistic: TF-5, TF-6.

| # | Screen | Action | Expected |
|---|---|---|---|
| **TF-1** (mandatory, Half A) | Trades deck (`TradesHome`) or Matches → Awaiting row | Open a card whose **give** side has one of **your own original** future picks (e.g. your 2027 2nd). Tap **Send in Sleeper**. | The plain **"Send this trade?"** confirm. **Not** "This trade will likely fail" / "…no longer on the expected roster". |
| **TF-2** (mandatory, Half B, R-5 give) | same | Tap **Send**. Then open the Sleeper app → League → Trades. | "**Trade sent** — Check your Sleeper app for the pending offer." Sleeper's pending offer lists that exact pick (season + round, "via <your team>") on **your** side. Cancel it in Sleeper. |
| **TF-3** (conditional, field-1 proof / Q-037) | Calculator (in-league) | **Only if** you hold a pick you **acquired from another team** in some league: build a trade giving that pick, Send. If you hold none anywhere, log **"not run — Q-037 stays open"**. | "Trade sent"; Sleeper shows the pick with the **original** team's name, moving from you to the partner. Cancel. **If it fails** with "Sleeper wouldn't accept the send" or "Couldn't send" plus a detail, **copy the detail text verbatim** into TEST_LEDGER — that falsifies Q-037 and the encoder's field 1 flips to the current holder (one argument in `encode_draft_pick`). |
| **TF-4** (mandatory, R-5 receive) | Calculator (in-league) | Build a trade **receiving** one of the partner's **own original** picks (the picker offers their current grid picks). Send. | "Trade sent"; Sleeper shows the pick moving **from them to you**. Cancel. |
| **TF-5** (opportunistic, R-7 / V-3) | Calculator (in-league) | **Only if** a partner's pick changed hands in Sleeper **after** the app last synced (a real pick trade between opening the app and this send). Build a trade with that pick on their side. Tap Send. | Pre-send alert titled **"This trade will likely fail"** with "• N pick(s) in this trade are no longer owned by the expected team (already traded) — Sleeper will reject the offer." Tap **Send anyway** → "**Couldn't send**": new build "1 draft pick in this trade has already changed hands, so nothing was sent. Rebuild the trade and try again."; fielded build "Some draft picks … have already changed hands …". **Nothing** appears in Sleeper. Proof of record otherwise: T-9 / V-3. |
| **TF-6** (opportunistic, R-6 / V-2) | Trades deck | **Only if** a deck card on a Sleeper league shows a **generic rung** ("Early 1st", "Mid 2nd") — no producer was found, so this may never occur. Tap Send in Sleeper. | Pre-send alert "This trade will likely fail" with "• N draft pick(s) in this trade can't be sent to Sleeper (generic picks like “Early 1st” name no real pick) — the send will be blocked rather than dropping them." Send anyway → "**Couldn't send**": new build "1 draft pick in this trade couldn’t be matched to a pick in this Sleeper league, so nothing was sent. Generic picks like “Early 1st” can’t be sent — use a specific pick."; fielded build the "Some draft picks …" form. Nothing in Sleeper. Proof of record otherwise: T-7 / V-2. |
| **TF-7** (mandatory, regression) | any send surface | A **player-only** trade. Send. | Unchanged: plain "Send this trade?", "Trade sent", offer visible in Sleeper. Cancel. |

Each step names a reachable screen, a single action, and an observable result; none needs a
state the app cannot reach on the stated build except the two marked opportunistic, whose
preconditions are stated and whose proof of record is the named pytest case.
