# PRD — G-413: Send in Sleeper handles draft picks (#413)

> Build spec for the group whose plan is [plan-g413.md](plan-g413.md). One report, two halves:
> the pre-send validator flags every pick as a moved player, and the propose route sends pick
> ids to Sleeper as player keys. **18 numbered requirements**, each mapped to at least one
> mechanical pass criterion.
>
> Mechanics: [lld-delta.md](lld-delta.md) (binding interfaces). Architecture:
> [hld-delta.md](hld-delta.md). Gates: [scope.md](scope.md). Two blind build agents code
> against this document: **backend first** (contract producer), **mobile second** (consumer).
>
> **Every file:line here was verified against worktree `9145d22f` on 2026-09-02.**

## Table of contents

- [1. What ships](#1-what-ships)
- [2. Report → cause → fix](#2-report--cause--fix)
- [3. Requirements](#3-requirements)
- [4. Known limits](#4-known-limits)
- [5. Success criteria](#5-success-criteria)
- [6. Out of scope](#6-out-of-scope)
- [7. Test plan (D-056)](#7-test-plan-d-056)
- [8. Guardrails](#8-guardrails)
- [9. Code-walk proof targets](#9-code-walk-proof-targets)
- [10. Operator TestFlight checklist](#10-operator-testflight-checklist)
- [11. Docs owed](#11-docs-owed)
- [12. The D-176 entry](#12-the-d-172-entry)

---

## 1. What ships

| Half | Report (mattmurf77, v1.16.12) | Fix |
|---|---|---|
| **A** | *"Send in sleeper isn't correctly identifying draft picks"* | `POST /api/trades/validate` splits picks out of the arrays before the `player_moved` / `roster_limit` math and adds two pick-specific blocking advisories (`asset_unmapped`, `pick_moved`). |
| **B** | *"…and causing trades with draft picks to fail"* | `POST /api/trades/propose` splits picks, resolves each against the league's `draft_picks` grid (existence) and live `traded_picks` (holder), encodes `"orig,season,round,from,to"` server-side, and refuses the whole send with a 422 on any pick it cannot resolve. Mobile gets two alert branches for the new codes. |

**Build honesty (one statement, repeated in scope §5):** all seven TestFlight steps run on any
build ≥ 1.16.12 the moment Render deploys — the request contract is unchanged, and both 422s
carry `detail`, which the fielded catch-all already renders (`SendInSleeperButton.tsx:305-310`).
The new build changes only the refusal alert's wording (count-aware, LLD §8.1) — never whether a
pick send works or whether a refusal is explained.

**No schema. No flag. No new route. No new analytics event.** Two new values in one closed enum
(`sleeper_send_failed.error_code`) and a semantic correction to `sleeper_send_succeeded` props.

---

## 2. Report → cause → fix

Traced in [investigation.md](investigation.md) and corrected in [plan-g413.md §1](plan-g413.md).
The load-bearing facts, re-verified:

1. Picks ride the same arrays as players on all four mounts (`mobile/src/screens/TradesScreen.tsx:8351-8355`,
   `mobile/src/components/TradeCard.tsx:978-982`, `:1000-1004`, `mobile/src/components/InLeagueCalculator.tsx:1467-1471`).
2. Validate computes `moved_give = [p for p in give if p not in my_players]` against
   `roster.players` (`backend/server.py:27797-27800`), which never contains a pick id → every pick
   is a blocking `player_moved` → "This trade will likely fail" (`SendInSleeperButton.tsx:328-338`).
3. Propose builds `ProposeTradeRequest(give_player_ids=give, receive_player_ids=receive, draft_picks=picks or None)`
   with `picks` read from a `draft_picks` key nobody sends (`server.py:16194`, `:16228-16232`);
   `build_propose_trade_body` puts every id into `k_adds`/`k_drops` (`backend/sleeper_write.py:286-292`)
   → Sleeper rejects the unknown key → 502 `sleeper_write_failed` → generic "Couldn't send".
4. The encoding shape is captured, not guessed: `"11,2026,1,1,2"`, `"1,2027,4,2,1"`
   (`docs/plans/sleeper-write-capture-runbook.md:159`); only field 1's meaning on a
   previously-traded pick is unconfirmed.
5. MFL already does the right thing (`server.py:28186-28208`, helpers `:27891-27960`); ESPN hard-blocks
   (`:28639-28644`). This change is the Sleeper instance of that pattern.

---

## 3. Requirements

Each requirement names its pass criterion: **T-n** = a pytest case in §7, **C-n** = a structural
check in §7.4, **W-n** = a code-walk step in §9, **TF-n** = a TestFlight step in §10.

### 3.1 Contract

**R-1 — The request contract is unchanged; the arrays are mixed.** `give_player_ids` /
`receive_player_ids` carry Sleeper player ids and FTF pick ids (owned
`{league}_{season}_{round}_{orig}` and generic `generic_pick_{round}_{tier}`) together. The
server splits with `_is_ftf_pick_asset(league_id, p)` (`server.py:27903-27908`) exactly as the
MFL route does (`:28188-28191`). No new body key. → T-3, T-4, W-1.

**R-2 — A non-empty `draft_picks` body key is rejected.** `400 {"error":"bad_request","message":…,"detail":…}`
(LLD §4.1 copy; `detail == message`). Absent or `[]` is accepted. No client sends it (`docs/api-reference.md:421`
documents a producer that does not exist). → T-12.

**R-3 — Existence ground truth is the `draft_picks` grid, by `pick_id`.** `load_draft_picks(league_id)`
with its **default** platform-only source (`backend/database.py:10142-10183`); a pick is mappable
iff its asset id equals a row's `pick_id`. Generic rungs, other leagues' ids, malformed ids,
out-of-horizon or completed-draft seasons all fail this test identically. → T-7, T-8, V-2.

**R-4 — Holder ground truth is live `traded_picks`, defaulting to the original roster; fetched
only when the trade carries a pick.** `_fetch_sleeper_traded_picks(league_id)` (`server.py:13895-13908`)
→ `_sleeper_pick_holder_index` (LLD §3.1). A player-only send performs **no** `traded_picks` call
and **no** `load_draft_picks` read. → T-6, T-10, V-3.

**R-5 — Orientation.** Give side: holder must equal `my_roster_id`; encoded
`"{orig},{season},{round},{my},{their}"`. Receive side: holder must equal `their_rid`; encoded
`"{orig},{season},{round},{their},{my}"`. `orig` is the grid row's `original_roster_id`, never
`from`. → T-1, T-4, T-5, T-6, TF-2, TF-3, TF-4.

**R-6 — `422 sleeper_pick_unmapped`** `{error, picks:[…], message, detail}` when ≥1 pick fails
R-3. `detail` is byte-equal to `message` — it is what fielded builds render. `picks[]` carries
every failing id from **both** sides, give-then-receive. Reported **before** R-7. Copy in LLD
§4.2. → T-7, T-8, T-14, TF-6.

**R-7 — `422 sleeper_pick_not_owned`** `{error, picks:[…], message, detail}` when ≥1 pick fails
R-4/R-5's holder test. `detail == message`. → T-9, TF-5.

**R-8 — Whole-send refusal, and refusals are invisible to the success spine.** On either 422:
`sleeper_write.propose_trade` is not called; no `sleeper_send_succeeded` row; no `deck_outcomes`
row even when `impression_id` is present (`_save_deck_outcome_safe` at `server.py:16264` is only
reachable after the write) — **and** a successful pick send still labels its impression
`propose` exactly once (the positive half; without it a deleted `:16264` call passes every
negative test). → T-7, T-9, T-11, T-3b.

**R-9 — The adapter receives players-only arrays plus encoded picks.**
`ProposeTradeRequest(give_player_ids=give_players, receive_player_ids=recv_players, draft_picks=encoded or None)`.
A pick-for-pick trade with empty player arrays is legal (the adapter's empty-trade guard already
counts `draft_picks`, `sleeper_write.py:277-278`). → T-2, T-3.

**R-10 — `sleeper_send_succeeded` props become honest.** `give_n`/`receive_n` count players only;
`pick_n` counts encoded picks. Helper signature unchanged (`server.py:16117-16120`); only the
route's arguments change. The semantic change is dated in the analytics addendum (R-16). → T-13.

### 3.2 Validate

**R-11 — The Sleeper validate branch splits picks and adds two blocking advisories.** Codes
`asset_unmapped` (from R-3 misses) and `pick_moved` (from R-4/R-5 misses), `severity:"blocking"`,
copy pinned in LLD §5. `player_moved` and `roster_limit` are computed over **players only**
(picks are not roster slots). → V-1, V-2, V-3, V-4, V-5, TF-1.

**R-12 — Validate makes no extra upstream call for a pick-free trade.** Same rule as R-4. → V-6.

### 3.3 Mobile

**R-13 — Two new alert branches, count-aware pinned copy, no reconnect.** In `doPropose`'s catch
(`SendInSleeperButton.tsx:266-310`), `sleeper_pick_unmapped` and `sleeper_pick_not_owned` get their
own `else if` branches placed after `roster_not_found` and before the catch-all `else`, with the
exact strings in LLD §8.1 — `${n || 'Some'} draft pick${n === 1 ? '' : 's'} …`, mirroring
`SendInMflButton.tsx:141-146`. `n` is `body?.picks?.length`; **counting is not rendering** — no
pick id reaches the screen. Neither branch calls `goConnect`; neither reads `detail`. → C-7,
C-7b, C-7c, C-8, W-2.

**R-14 — Comments follow the contract.** `SendInSleeperButton.tsx:252-253` (17 values),
`sendInSleeper.ts:5-6` (code list), `:214` (warning list). No TypeScript type change. → W-4 (grep-cited).

**R-15 — The new warnings render with zero client change.** `confirmSend` (`:318-339`) already
maps every warning's `message` into the alert body and flags `blocking`. → W-3.

### 3.4 Analytics, docs, tests

**R-16 — `sleeper_send_failed.error_code` grows from 15 to 17 values, as a taxonomy change.**
Update the enum comment at `backend/analytics_taxonomy.py:1055-1058`, the addendum
`docs/business/analytics/2026-08-11-p0-7-addendum.md:64-67` (+ a dated note on R-10), the mobile
comment (R-14), and add the enum listing to `docs/cross-client-invariants.md` beside the `surface`
enum (`:825`). No ingest code change (`CLIENT_EVENT_PROPS` constrains keys). `sleeper_send_failed`
is already in `WAT_LIVE` (`backend/analytics_queries.py:53-55`); `NON_INTENT_EVENTS` untouched.
→ W-5 (grep: the four comment sites agree on "17").

**R-17 — The false-confidence fixture is fixed.** `backend/tests/test_sleeper_write_route.py:288`
sends `"draft_picks": ["2027_1"]`, a string the adapter would reject; it passes only because
`propose_trade` is mocked. Replace with an owned pick id inside `give_player_ids` plus the grid /
traded stubs, and assert the adapter request. → T-3 (this **is** the fixed test).

**R-18 — The field-1 question is logged, not buried.** `living-memory/OPEN_QUESTIONS.md` gains
**Q-037** (next id; `Q-034` is the current max): field 1 = original-owner roster id, captured on
two live examples, unconfirmed on a multi-owner pick; closed by TF-3's logged outcome.
`sleeper_write.py:22` and `docs/integrations/sleeper.md` §3.3 carry the same caveat. → TF-3.

---

## 4. Known limits

- **`traded_picks` flake (LLD §3.3 rows 11–12).** `_fetch_sleeper_traded_picks` returns `[]` on
  any failure. Holder then defaults to the original roster: an acquired pick refuses safely
  (`not_owned`); one's own original that was already traded away encodes with `from = me` and
  Sleeper rejects it (502, today's behavior). Never a silently wrong send. Accepted.
- **Grid staleness.** `draft_picks` rows are replace-synced by `session_init`'s daemon
  (`docs/architecture.md:152`). A pick Sleeper added after the last sync 422s `unmapped` until the
  next sync — the client could not have displayed it either.
- **Field 1 on acquired picks** is unconfirmed until TF-3 is logged (R-18). Failure mode is
  visible (502 with `detail`), fix is one argument in `encode_draft_pick`.
- **Mobile copy counts, never lists.** The alerts say how many picks failed; the ids in `picks[]`
  are for logs and tests, not user copy.
- **User-asserted pick rows on a Sleeper league 422 `sleeper_pick_unmapped` by design (Planner
  ruling 1).** The encoder reads `load_draft_picks(league_id)` with its default platform-only
  source. A `source='user'` row (ADR-010) can only exist on a Sleeper league via a direct API
  call — the assignment routes have no platform guard (`server.py:14502-14545`, `:14591-14640`),
  but the only assignment UI is the ESPN Draft Room (`picks_not_assigned` is ESPN-only, `:10840`,
  `:11347`). Even if one exists and `picks.assign_tradeable` (ON, `config/features.json:219`)
  surfaces it on a card, it refuses: its `original_roster_id` is *"an OPAQUE, LEAGUE-LOCAL slot
  label … never resolved against a platform"* (`database.py:10217-10221`), not a Sleeper
  roster id, and Sleeper's `traded_picks`/rosters can validate a platform row and nothing else.
  The literal platform source (`source=PICK_SOURCE_PLATFORM`, sanctioned by name in the ADR-010 AST guard) is the containment, not an oversight (guardrail 8).

---

## 5. Success criteria

1. **Half A closed.** A trade whose give side holds one of the user's own picks validates with
   zero `player_moved` warnings and shows the plain "Send this trade?" confirm. (V-1; TF-1.)
2. **Half B closed.** The same trade proposes; Sleeper's pending offer lists the pick with the
   correct season/round. (T-4; TF-2.)
3. **Never dropped, never guessed.** Every pick in a request ends in exactly one of
   `encoded` / `unmapped` / `not_owned`; any non-empty failure list refuses the whole send and
   nothing reaches Sleeper. (T-7, T-8, T-9; TF-5, TF-6.)
4. **Byte-identical player-only path.** No new upstream call, same adapter request, same
   analytics props, all seven pre-existing propose tests green unedited (after the `:288` fix).
   (T-10; the existing suite.)
5. **Honest telemetry.** `pick_n` > 0 on a pick send; `give_n` excludes picks. (T-13.)
6. **Field 1 proven or falsified on device.** TF-3 outcome logged in TEST_LEDGER; Q-037 closed
   or converted into the one-line encoder change.

---

## 6. Out of scope

- FAAB / `waiver_budget` (Q-016 — unimplemented, not merely untested).
- Accept / reject / cancel of Sleeper trades; pending-trade reads.
- A `give_pick_ids` request key or any typed pick field on `ProposeTradePayload`.
- Rendering pick names in the refusal alerts.
- MFL / ESPN propose routes (already correct; untouched).
- The `_fetch_sleeper_traded_picks` strict variant (HLD D-f rejected it).
- Any engine, deck, calculator, or `TradeCard` change — the mounts already send the right arrays.

---

## 7. Test plan (D-056)

Maestro and the simulator are retired ([D-056](../../../../living-memory/DECISIONS.md)). Evidence
is: pytest (backend), a structural guard extension (mobile), a written code-walk (mobile), and
the operator's TestFlight checklist (the only runtime proof). `FTF_SKIP_SIM_GATE=1` is the
standing pre-push posture.

**Every sabotage below is run and proven RED before its test is accepted.** A sabotage is a
plausible wrong implementation, not the negation of the assertion's regex.

### 7.1 `backend/tests/test_sleeper_write.py` — adapter, pure

| # | Test | Asserts | Named sabotage (must go RED) |
|---|---|---|---|
| **T-1** | `test_encode_draft_pick_shape` | `encode_draft_pick(7, 2027, 1, 3, 5) == "7,2027,1,3,5"` and `_is_valid_pick_str` accepts it; string inputs (`"7"`, `"3"`) produce the same output | swap `from`/`to` in the f-string; or emit `orig` as the fourth field ("from = original owner" — the classic misread) |
| **T-2** | `test_pick_only_trade_builds_body` | empty player arrays + `draft_picks=["1,2027,2,1,2"]` → body builds; `variables.k_adds == []`; `'["1,2027,2,1,2"]'` inlined in `query` | drop `(req.draft_picks or [])` from the empty-trade guard at `sleeper_write.py:277` |

### 7.2 `backend/tests/test_sleeper_write_route.py` — route

Stubs per LLD §7: `_sleeper_get` → rosters (existing idiom), `server.load_draft_picks` → `GRID`,
`server._fetch_sleeper_traded_picks` → `TRADED`, `propose_trade` → `MagicMock`, and inspect
`fake.call_args[0][1]`. Fixture shapes in LLD §7.2.

| # | Test | Asserts | Named sabotage |
|---|---|---|---|
| **T-3** | `test_propose_success_fires_no_trade_sent_on_sleeper` (**the `:288` fixture, fixed**) | body has `give_player_ids: ["100","101", f"{LEAGUE}_2027_2_1"]`, no `draft_picks` key; 200; adapter request has `give_player_ids == ["100","101"]` and `draft_picks == ["1,2027,2,1,2"]`; still no `trade_sent` row | remove the split (pick stays in `give_player_ids`, `draft_picks is None`) — goes red for the right reason |
| **T-3b** | `test_propose_success_labels_impression_propose` (**the positive spine assertion**) | T-3's body plus `impression_id: "imp-1"`, `server._save_deck_outcome_safe` patched with a `MagicMock` → 200 and `mock.assert_called_once_with("imp-1", "propose", acting_user_id=USER)` (signature `server.py:4759-4767`; call site `:16264-16265`) | delete the `:16264` call — every negative test (T-11 included) stays green without this row |
| **T-4** | `test_propose_encodes_give_pick_from_to` | give `L_2027_2_1` → `draft_picks == ["1,2027,2,1,2"]` | pass `their_rid` as `from` |
| **T-5** | `test_propose_encodes_receive_pick_flips_from_to` | receive `L_2026_1_2` (orig 2 = their roster) → `["2,2026,1,2,1"]` | use the give branch for both sides |
| **T-6** | `test_propose_acquired_pick_uses_traded_picks_holder` | give `L_2027_1_7`, `TRADED` says holder 1 → 200, `["7,2027,1,1,2"]` | ignore the overlay (default holder only) → 422 `not_owned` instead of 200 |
| **T-7** | `test_propose_hard_blocks_generic_pick` | give `["100", "generic_pick_1_early"]`, receive `["200", "generic_pick_2_mid"]` → 422 `sleeper_pick_unmapped`, `picks == ["generic_pick_1_early", "generic_pick_2_mid"]` (both sides, give-then-receive), `body["detail"] == body["message"]`, `propose_trade` not called | filter generic rungs out silently and send the players; **or** report the give side only; **or** drop `detail` (fielded builds regress to "Please try again") |
| **T-8** | `test_propose_hard_blocks_pick_missing_from_grid` | well-formed `L_2031_1_1`, no row → 422 `unmapped` | replace the grid membership test with `if False:` / infer existence from the rosters list (every roster × horizon) instead of `load_draft_picks` rows |
| **T-9** | `test_propose_hard_blocks_pick_not_owned` | give `L_2027_2_1` with `TRADED` overridden to holder 9 → 422 `sleeper_pick_not_owned`, `picks == [f"{LEAGUE}_2027_2_1"]`, `body["detail"] == body["message"]`, adapter not called | skip the holder comparison; **or** drop `detail` |
| **T-10** | `test_propose_pick_free_send_makes_no_traded_picks_fetch` | players-only body → `_fetch_sleeper_traded_picks` mock and `load_draft_picks` mock both `assert_not_called()` | fetch unconditionally |
| **T-11** | `test_propose_422_fires_no_success_event_and_no_deck_outcome` | T-7's body plus `impression_id: "imp-1"` and `_save_deck_outcome_safe` patched → 422; no `sleeper_send_succeeded` `user_events` row; `_save_deck_outcome_safe` not called | move the pick gate below the write / label the impression before refusing |
| **T-12** | `test_propose_rejects_client_supplied_draft_picks` | body with `draft_picks: ["1,2027,2,1,2"]` → 400 `bad_request`; adapter not called; `draft_picks: []` → proceeds | accept and append (MFL-style pass-through) |
| **T-13** | `test_propose_success_pick_n_honest` | T-3's body → `sleeper_send_succeeded` props `{give_n: 2, receive_n: 1, pick_n: 1, …}` | keep passing the raw `give` / empty `picks` |
| **T-14** | `test_propose_reports_unmapped_before_not_owned` | give `["generic_pick_1_early", f"{LEAGUE}_2027_2_1"]` with `TRADED` holder 9 for `(2027,2,"1")` → 422 `sleeper_pick_unmapped`, `picks == ["generic_pick_1_early"]` **only** | check `not_owned` first / merge both lists into one 422 |

Pre-existing tests `:112-330` stay green **unedited** except T-3. T-11 uses the same
`_save_deck_outcome_safe` mock as T-3b (Planner ruling 3: mock, not flag-driving — driving
`deck.signal_v2` needs an owned, ≤30-day `deck_impressions` row, `server.py:4783-4796`, which this
fixture does not have and `test_deck_signal_v2.py` already covers). The pair is what makes the
mock sufficient: T-11 proves "gate before the call", T-3b proves "call not deleted".

### 7.3 `backend/tests/test_trade_send_validate.py` — validate

Fixture gains `server.load_draft_picks` → `GRID` and `server._fetch_sleeper_traded_picks` → `TRADED`
(LLD §7.2; league `"987654321"`, rosters 1 = USER, 2 = OPP).

| # | Test | Asserts | Named sabotage |
|---|---|---|---|
| **V-1** | `test_owned_pick_not_flagged_as_player_moved` (**the #413 repro**) | give `["100", "987654321_2027_2_1"]` → `warnings == []` | revert the split |
| **V-2** | `test_generic_pick_flags_asset_unmapped` | give `["generic_pick_1_early"]` → exactly `["asset_unmapped"]`, `severity == "blocking"`, message contains `"1 draft pick"` | treat generic rungs as players (today) |
| **V-3** | `test_pick_owned_by_other_roster_flags_pick_moved` | `TRADED` holder 9 for `(2027,2,"1")` → exactly `["pick_moved"]`, blocking | skip the holder check |
| **V-4** | `test_receive_side_pick_checks_their_roster` | receive `987654321_2026_1_2` → `[]`; receive `987654321_2027_2_1` (holder = me) → `["pick_moved"]` | check both sides against `my_rid` |
| **V-5** | `test_roster_limit_excludes_picks` | give `["100"]`, receive `["200","201","202", "987654321_2026_1_2"]` → my post-count 8 (at limit) → `[]` | count picks in `post` (today) |
| **V-6** | `test_pick_free_validate_makes_no_pick_fetch` | default body → both pick mocks `assert_not_called()` | fetch unconditionally |

### 7.4 `mobile/tests/check-send-button-platform.js` — checks 7–8

Per LLD §8.3. **C-7** unmapped branch exists, calls `Alert.alert`, no `goConnect`; **C-8** same
for not-owned; **C-7b** both precede the final `else`; **C-7c** the catch-all copy survives.
Sabotages: delete a branch; append it after the catch-all; route not-owned into the reconnect
branch.

### 7.5 Full gate

- `pytest backend/tests` — the three files above plus the untouched suite; baseline
  4483 passed / 1 skipped (TEST_LEDGER 2026-08-31b); expected delta = +2 (T-1, T-2) +12 (T-3b,
  T-4…T-13, T-14) +6 (V-1…V-6) = **+20** → 4503 / 1 skipped, with T-3 modified in place. The
  build agent records the actual numbers.
- `node mobile/tests/check-send-button-platform.js` — 8 blocks green.
- `npx tsc --noEmit` in `mobile/` — no type change, must stay clean.
- `bash mobile/scripts/testid-lint.sh` — no testIDs added; must stay green.
- Every sabotage proven RED before its assertion is accepted; recorded in TEST_LEDGER.

---

## 8. Guardrails

1. **Never drop a pick silently.** Every pick in a request ends in exactly one of `encoded`,
   `unmapped`, `not_owned`. Filtering a generic rung "to be helpful" is the T-7 sabotage.
2. **Whole-send refusal.** Any non-empty failure list → 422 before `propose_trade`. A
   partially-mapped trade is a different trade (`server.py:28193-28198`).
3. **No new upstream fetch for pick-free sends.** `traded_picks` and `load_draft_picks` are
   reached only inside `if give_picks or recv_picks`. This is also what keeps the seven
   single-`return_value` `_sleeper_get` stubs honest (LLD §7.1).
4. **The `propose` deck-outcome label and `sleeper_send_succeeded` fire only after a successful
   write.** Both 422s return above `server.py:16264`. Do not "record the attempt" on refusal.
5. **Closed-enum discipline.** `sleeper_send_failed.error_code` gains exactly two values, spelled
   `sleeper_pick_unmapped` and `sleeper_pick_not_owned`, and every comment site says 17. No
   alias, no `sleeper_pick_error` umbrella.
6. **The client never encodes.** No `from`/`to`/`orig` leaves the device; no `draft_picks` key is
   sent; a client that does is refused (R-2).
7. **Surgical.** The MFL/ESPN blocks, `_record_send_success`'s signature, `_roster_id_for_owner`,
   `build_propose_trade_body`'s player encoding (`sleeper_write.py:286-292`) and the four mounts
   are not edited.
8. **Default platform source for the grid.** `load_draft_picks(league_id)` — not
   `_pick_read_source()`; a user-asserted row is not proof a Sleeper pick exists (§4 has the
   ruling and the code cites).
9. **`detail` on every refusal this change adds.** Both 422s and the new 400 carry
   `detail == message`; the fielded catch-all renders `detail`. A refusal without `detail` is a
   "Please try again" loop for every build before this one (T-7/T-9's drop-`detail` sabotage).

---

## 9. Code-walk proof targets

Written by the mobile agent to `docs/feedback/items/413-sleeper-send-draft-picks/code-walk-mobile.md`,
file:line-cited against the post-change tree:

- **W-1** The four mounts still pass mixed arrays unchanged (`TradesScreen.tsx:8351-8355`,
  `TradeCard.tsx:978-982`, `:1000-1004`, `InLeagueCalculator.tsx:1467-1471`) and the pick ids
  they carry are the two shapes the server splits on (`TradesScreen.tsx:4442-4447`,
  `InLeagueCalculator.tsx:493-509`, `backend/pick_values.py:213`).
- **W-2** `doPropose` catch → `body?.error` → the two new branches → count-aware alert copy
  (`n = body.picks.length`, ids never rendered); both sit inside the chain before the catch-all;
  neither reaches `goConnect`. Also: on a build **without** these branches, the same 422 falls to
  the catch-all at `:305-310` and renders the server's `detail` — cite it, because that is the
  fielded-build path.
- **W-3** `confirmSend` renders `asset_unmapped` / `pick_moved` through the existing
  `warnings.map(w => w.message)` with `blocking` → "This trade will likely fail" title, with no
  client change.
- **W-4** The three comment sites (R-14) and the `TradeSendWarning.code` comment agree with
  the wire contract.
- **W-5** The 422 emits `sleeper_send_failed{error_code:'sleeper_pick_unmapped'|'sleeper_pick_not_owned'}`
  via the existing `body?.error` read at `:256-258`, with `status: 422`, `kind: null`; the four
  "17 values" comment sites agree (`analytics_taxonomy.py`, `SendInSleeperButton.tsx`,
  the addendum, `cross-client-invariants.md`).

---

## 10. Operator TestFlight checklist

**This is the only runtime evidence this change gets.** Real Sleeper league, verified session.
**Build honesty (same statement as §1 and scope §5):** all seven steps run on any build ≥ 1.16.12
once Render deploys; the new build changes only the refusal alert's wording (LLD §8.1) — on a
fielded build the refusal shows the server's `detail` ("Some draft picks …"), on the new build
the count-aware sentence ("1 draft pick …"). **Cancel every proposal in Sleeper afterwards.** Log
each outcome in TEST_LEDGER.

**Which steps are which:** TF-1, TF-2, TF-4, TF-7 are **mandatory**. TF-3 is **conditional** —
run it if the operator holds an acquired pick in any league; otherwise log **"not run — Q-037
stays open"** as the outcome (a legal result; the operator has sold more firsts than he has
acquired, so the precondition may be false everywhere). TF-5 and TF-6 are **opportunistic** —
they need a state the app does not let you build on demand (TF-5: the grid must be stale relative
to Sleeper, i.e. a real pick trade between the last `session_init` sync and the send, because the
calculator picker only offers the partner's *current* grid picks, `InLeagueCalculator.tsx:493-509`;
TF-6: a Sleeper deck card carrying a `generic_pick_*` rung, and with synced owned picks
`_owned_picks_available` is true for non-ESPN leagues, `server.py:11343-11348`, so the deck injects
owned picks — no producer of a generic rung on a Sleeper card was found). Run them if the
situation arises; **the proof of record for those two refusals is T-9/V-3 and T-7/V-2.**

| # | Where | Steps | Expected |
|---|---|---|---|
| **TF-1** | Trades deck or Matches → Awaiting | Open a card whose **give** side contains one of **your own original** future picks (e.g. your 2027 2nd). Tap **Send in Sleeper**. | The plain **"Send this trade?"** confirm. **No** "This trade will likely fail" / "no longer on the expected roster" warning. (Half A.) |
| **TF-2** | same | Tap Send. | **"Trade sent"**. In the Sleeper app, the pending offer lists that exact pick (season + round, "via <your team>") on your side. Cancel it in Sleeper. (Half B; R-5 give orientation.) |
| **TF-3** *(conditional)* | Calculator | **Field-1 proof.** Only if you hold a pick you **acquired from another team** in some league: build a trade giving that pick. Send. If you hold none, **log "not run — Q-037 stays open"** and move on. | "Trade sent"; Sleeper shows the pick with the **original** team's name, moving from you to the partner. Cancel. **If it fails** with "Sleeper wouldn't accept the send" / "Couldn't send" plus a detail, **capture the detail text verbatim** — that is the Q-037 falsification and the encoder's field 1 flips to the current holder. |
| **TF-4** | Calculator | Build a trade **receiving** one of the partner's own picks. Send. | "Trade sent"; Sleeper shows the pick moving from them to you. Cancel. (R-5 receive orientation.) |
| **TF-5** *(opportunistic)* | Calculator | Only if a partner's pick has **changed hands in Sleeper since the app last synced** (you or a leaguemate traded it after opening the app): build a trade with that pick on their side. Tap Send. | Pre-send warning **"…no longer owned by the expected team (already traded) — Sleeper will reject the offer."** Tap **Send anyway** → **"Couldn't send"** with, on a fielded build, *"Some draft picks in this trade have already changed hands, so nothing was sent…"* and on the new build *"1 draft pick in this trade has already changed hands…"*. Nothing appears in Sleeper. Proof of record otherwise: T-9 / V-3. |
| **TF-6** *(opportunistic)* | Trades deck | Only if a deck card shows a **generic rung** ("Early 1st", "Mid 2nd") on a Sleeper league: tap Send. | Pre-send warning **"…can't be sent to Sleeper (generic picks like “Early 1st” name no real pick)…"**. Send anyway → **"Couldn't send"** with *"Some draft picks in this trade couldn’t be matched to a pick in this Sleeper league… Generic picks like “Early 1st” can’t be sent — use a specific pick."* (fielded) / *"1 draft pick in this trade couldn’t be matched…"* (new build). Nothing in Sleeper. Proof of record otherwise: T-7 / V-2. |
| **TF-7** | any | A **player-only** trade. Send. | Unchanged: plain confirm, "Trade sent", offer in Sleeper. Cancel. (Regression: the byte-identical path.) |

---

## 11. Docs owed

Row-by-row in [scope.md §4](scope.md#4-docs-scope-mandatory--hld--lld--api). Summary: `docs/api-reference.md:405-406,408-421`;
`docs/integrations/sleeper.md:62,187-188,197-204`; `docs/cross-client-invariants.md:825` (enum
listing); `docs/business/analytics/2026-08-11-p0-7-addendum.md:56-57,64-67`; `living-memory/LLD.md`
(one H2, LLD §10); `living-memory/DECISIONS.md` (D-176, §12) + index row; `living-memory/OPEN_QUESTIONS.md`
(Q-037); `mobile/src/components/CLAUDE.md:33`; `mobile/src/api/CLAUDE.md:32`; CHANGELOG /
TEST_LEDGER / NEXT at ship.

---

## 12. The D-176 entry

Insert above D-171 in `living-memory/DECISIONS.md` and add the index row at the table under
`:438`.

> ## D-176 — Sleeper Pick Sends Are Encoded Server-Side From the Grid Plus Live `traded_picks`; the Client Never Encodes and Any Unresolvable Pick Refuses the Whole Send
>
> **Date:** 2026-09-02 (#413) · **Scope:** [`docs/feedback/items/413-sleeper-send-draft-picks/scope.md`](../docs/feedback/items/413-sleeper-send-draft-picks/scope.md) · **Mirrors:** the MFL propose route's split-and-encode (`_mfl_encode_ftf_picks`) and the ESPN route's hard block.
>
> **Decision:** `POST /api/trades/propose` keeps its mixed `give_player_ids` / `receive_player_ids` arrays and splits picks server-side (`_is_ftf_pick_asset`). Existence is the league's `draft_picks` grid (platform rows, by `pick_id`); the current holder is the live public `traded_picks` list overlaid on "original roster holds by default"; the give side must be held by the proposer's roster and the receive side by the counterparty's. Encoding `"orig,season,round,from,to"` happens only in `sleeper_write.encode_draft_pick`. Any pick that cannot be resolved refuses the whole send — 422 `sleeper_pick_unmapped` (existence) or 422 `sleeper_pick_not_owned` (holder) — before anything reaches Sleeper; both carry `detail == message` so every fielded build renders the reason. User-asserted (ADR-010) rows are outside the grid the encoder reads and refuse as `unmapped` by design — their `original_roster_id` is an opaque slot label, not a Sleeper roster id. The `draft_picks` body key is rejected when non-empty. Both fetches are skipped for pick-free sends. No feature flag: the change is additive inside `trade.send_in_sleeper`, and rollback is a code revert.
>
> **Alternatives considered:** a new `give_pick_ids` key (fielded builds already send mixed arrays; must work on server deploy alone); client-side encoding (the client cannot see `traded_picks`, and a client-asserted `from` is the value the server exists to verify); grid `owner_user_id` as holder (stale between syncs, and a user id, not a roster id); MFL-style pass-through of pre-encoded strings (a second unverified entry point for a producer that does not exist); a strict `traded_picks` variant that 502s on flake (a second failure path for a transient the route already tolerates on rosters — accepted residual instead).
>
> **Consequences:** `sleeper_send_failed.error_code` is 17 values; `sleeper_send_succeeded.pick_n`/`give_n` become honest (dated in the addendum). Validate's Sleeper branch gains `asset_unmapped` / `pick_moved` and counts roster limits over players only. Field 1 of the pick string is captured-not-confirmed on a multi-owner pick — Q-037, closed by the TestFlight step-3 outcome.
>
> **Status:** Active.


## 13. QA round 1 adjudication (2026-09-02, orchestrator)

Two independent QA agents (reports `qa-round-1-agent-A.md`, `qa-round-1-agent-B.md`) both **PASS** the group tip `8e4e1648`: full suite 4503/1, tsc clean, 89/89 guards, testid-lint OK, every PRD-named sabotage RED except T-8's `if False:` variant (self-satisfying — the `None` row raises inside the `try` and is classified `unmapped` anyway; **T-8's proof of record is the "existence inferred from rosters × horizon" sabotage**, which both agents proved RED). Agreed findings and dispositions:

| Finding (both agents) | Disposition |
|---|---|
| Living-memory docs (D-176, Q-037, LLD.md line, HLD.md line) absent at the tip | Orchestrator writes at ship (scope §4 "at ship" rows) — not a code defect |
| Validate advisory copy: n=1 "pick … are", "dropping them"; straight `can't` beside curly quotes | **Fixed on the group branch** after round 1 (server strings count-aware for the verb/pronoun, curly apostrophe); LLD §5 updated to match. Copy-only delta; V-1…V-6 re-run green |
| `code-walk.md` vs delivered `code-walk-mobile.md`; PRD cited the calculator under `screens/` | PRD corrected (this commit) |
| scope §3 said +18; actual +20 | scope corrected |
| Coverage gaps (mobile "never renders ids / never reads `detail`" unpinned; `encoded` give-then-receive order unpinned; guardrail 8's literal-source value unpinned by the AST guard) | Accepted as code-walk-only for this ship; logged as follow-up candidates in TEST_LEDGER |
| Doc overstatement: a foreign-league/malformed pick id is treated as a PLAYER by `_ftf_pick_parts` (league-prefixed) and fails as 502 `sleeper_write_failed`, not 422 `unmapped` | Noted here; no client produces such an id. api-reference wording narrowed to "generic rung / pick outside the synced grid" |
