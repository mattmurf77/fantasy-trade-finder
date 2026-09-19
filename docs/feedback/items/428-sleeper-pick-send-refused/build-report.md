# Build report — G-428: Sleeper refuses spent-season pick sends (#428)

> Phase 2 build agent, 2026-09-08, branch `feat/fb428-sleeper-pick-tradability` (base `15dabe05`). Spec: [prd.md](prd.md) F1–F3 + the four rulings in [reconciliation-log.md](reconciliation-log.md). All file:line cites are against this branch's tip. **Phase 4 (QA round 1 resolution) amended this report in place:** shape-blind `completed_draft_seasons`, the dead `season_window: null` / `?–?` branches removed, check 9 of the mobile guard rewritten — see [reconciliation-log.md](reconciliation-log.md) § Round 1 resolution.

## 1. What shipped

| PRD item | Where | Summary |
|---|---|---|
| **F1** one tradability predicate | `backend/draft_status.py:165-233` | `completed_draft_seasons`, `sleeper_pick_window`, `sleeper_pick_tradable` — beside `pick_horizon`, which they reuse |
| **F1** sync consults the cached verdict on an empty `/drafts` (D-189) | `backend/server.py:13271-13284` (`_sleeper_cached_draft_verdict`), `:13346-13363` | Live read still wins; `[]` + cached `drafted` ⇒ current season excluded; `[]` + anything else ⇒ D-089 fail-safe (exclude nothing). Logs which signal excluded |
| **F1** send + validate refuse an out-of-window pick | `backend/server.py:18418-18452` (propose), `:30097-30115` (validate), `:30327-30387` (encoder, 4th list), `:30390-30400` (`_sleeper_pick_window_for_send`), `:30403-30423` (copy) | 422 `sleeper_pick_untradable` `{picks, season_window, message, detail == message}`; validate `pick_untradable` blocking advisory. Reported after `unmapped`, before `not_owned`. Pick-free sends make no new fetch |
| **F2** read paths inherit the clean grid | — (no code) | every surface still reads `load_draft_picks`; the residual flake-with-no-verdict window is caught at send by F1 |
| **F3** Sleeper's sentence | `backend/sleeper_write.py:384-398`; `backend/server.py:18477-18486` | `detail` = first `errors[].message` (JSON dump only as fallback; auth-word scan reads the full dump); 502 body gains `message == detail` |
| Enum 17 → 18 comment/doc sites | `backend/analytics_taxonomy.py:1069-1074` · `docs/cross-client-invariants.md` § Client analytics event contract · `docs/business/analytics/2026-08-11-p0-7-addendum.md` · `mobile/src/api/sendInSleeper.ts:5-7,214` · `mobile/src/components/SendInSleeperButton.tsx:252-254` | ruling 1 |
| Mobile parity branch (ruling 4) | `mobile/src/components/SendInSleeperButton.tsx:317-327`; `mobile/tests/check-send-button-platform.js` check 9 | own `else if (code === 'sleeper_pick_untradable')` inside the ladder, renders `detail`, never `goConnect`; count-aware fallback copy |
| Docs | `docs/api-reference.md` (propose + validate rows, error table, Q-037 scope line) · `docs/integrations/sleeper.md` (§1.1 rows 6–7, §3.2 tradability rule, §3.3 field-1 confirmed + F3, §5.2/§5.5 call budget) · `docs/cross-client-invariants.md` (enum + validate `code` vocabulary) | scope.md §4 rows owned by this agent |

## 2. Code-walk proof

**(1) Sync exclusion → grid.** `_sync_sleeper_owned_picks` (`backend/server.py:13287`) reads `/drafts` at `:13352`, then `_exclude = completed_draft_seasons(_drafts, _cur_season)` (`:13353` → `backend/draft_status.py:165-187`: `status == "complete"`, `season >= current`, **shape-blind** — a completed startup draft consumes the class exactly as a rookie draft does, restoring the pre-#428 loop's rule; Phase 4 ruling on A F-1 / B F-2). `if not _drafts:` (`:13354`) → `_sleeper_cached_draft_verdict(league_id)` (`:13271`, one `get_league_draft_context` read, DraftStatus or None) → `_exclude.add(_cur_season)` iff `.drafted` (`:13357`). A non-empty `_drafts` never reaches that branch — the live read wins outright. `_exclude` then feeds `save_draft_slot_order` (`:13369-13371`, unchanged) and `sync_draft_picks(exclude_seasons=_exclude)` (`:13378-13391`, unchanged) whose `pick_horizon` walks the anchor past the excluded class, so the replace-sync drops the spent season's rows league-wide.

**(2) Grid → validate.** `trades_validate` (`:30008`) Sleeper branch: `if give_picks or recv_picks:` (`:30097`) → `load_draft_picks(source=PICK_SOURCE_PLATFORM)` (`:30099`, the same sanctioned call as before — the ADR-010 AST guard `test_w3_02_ast_only_sanctioned_call_sites_name_source` stays green, no `test_pick_assignment.py` edit needed) → `_fetch_sleeper_traded_picks` (`:30100`) → `_sleeper_pick_window_for_send(league_id, meta, traded)` (`:30103` → `:30390-30400`: one `_fetch_sleeper_drafts` + the cached verdict only when it is empty + `meta["season"]` → `sleeper_pick_window`, `backend/draft_status.py:190-219`) → `_sleeper_encode_ftf_picks(..., window=window)` (`:30104`) → `warnings.append({"code": "pick_untradable", "severity": "blocking", ...})` (`:30114`). A pick-free validate never enters the block (V-10).

**(3) Grid → propose refusal.** `_sleeper_propose_core` (`:18349`; the route wrapper `propose_trade_to_sleeper` at `:18282` → `:18340`, and the overhaul send loop — `server.py:31637` passes it as `sleeper_propose`, `backend/overhaul_api.py:281` selects it — both reach it): `if give_picks or recv_picks:` (`:18418`) → grid (`:18423`) → traded (`:18424`) → `window = _sleeper_pick_window_for_send(league_id, _fetch_sleeper_league_meta(league_id), traded)` (`:18430-18431`; meta is the second new read, propose-only) → encoder (`:18432-18434`). In the encoder (`:30327`) the order per pick is: grid row missing → `unmapped` (`:30360-30362`); row fields unparseable → `unmapped` (`:30363-30368`); **`not sleeper_pick_tradable(season, window)` → `untradable` (`:30369-30371`)**; holder ≠ offering side → `not_owned` (`:30379-30381`); else `encode_draft_pick` (`:30383-30384`); the 4-tuple returns at `:30387`. The route returns `unmapped` first (`:18437`), then **`sleeper_pick_untradable` 422 with `picks`, `season_window` (always a 2-list — `window` cannot be None on this path, see below), `message`, `detail == message` (`:18443-18447`)**, then `not_owned` (`:18448`) — all before `_sleeper_write.propose_trade` (`:18461`), so nothing reaches Sleeper, no `sleeper_send_succeeded` row and no deck outcome (T-15). `sleeper_pick_tradable(season, None)` is True (`draft_status.py:222-233`), so an unknown season (meta None) abstains — `untradable` is then empty, which is why the 422 body and `_sleeper_untradable_copy` (`:30403-30423`) carry no None branch (Phase 4 removed the unreachable `null` / `?–?` paths, A F-3); an empty `/drafts` with no cached verdict yields the pre-draft window and the spent pick proceeds to Sleeper (T-19) — Sleeper stays the final authority.

**(4) Error detail.** `sleeper_write._post_graphql` (`backend/sleeper_write.py:384-398`): `errors[0]["message"]` → `detail` (`:392-394`), `dump.lower()` still drives the auth-word classification (`:395-396`); `SleeperWriteError(detail=…)` (`:398`) → `_sleeper_propose_core` except (`:18475-18486`) → 502 `{"error": "sleeper_write_failed", "kind", "detail": _detail, "message": _detail}`. `SendInSleeperButton.tsx:335-340` (catch-all) renders `detail` on build 154, so the user now reads "Couldn’t send — These draft picks cannot be traded." with no EAS build.

**(5) Mobile branch.** `SendInSleeperButton.tsx:317-327` sits between `sleeper_pick_unmapped` and `sleeper_pick_not_owned` inside the `if/else if` chain rooted at `sleeper_not_linked`; renders `detail || <count-aware fallback>`; no `goConnect`. `check-send-button-platform.js` check 9 pins presence, chain membership and — since Phase 4 (B F-1) — that the identifier `detail` sits inside the AST of the `Alert.alert` call's second (message) argument, so the branch comment's own mention of `detail` can no longer satisfy it.

## 3. Tests — RED first, then GREEN

RED run against `15dabe05` (pre-fix code, tests added first — saved verbatim during the build):

```
FAILED backend/tests/test_sleeper_pick_tradability.py::TestSleeperPickWindow::test_completed_draft_seasons_reads_only_complete_current_or_later
FAILED backend/tests/test_sleeper_pick_tradability.py::TestSleeperPickWindow::test_sleeper_pick_window_post_draft_is_next_three_classes
FAILED backend/tests/test_sleeper_pick_tradability.py::TestSleeperPickWindow::test_sleeper_pick_window_pre_draft_anchors_current
FAILED backend/tests/test_sleeper_pick_tradability.py::TestSleeperPickWindow::test_sleeper_pick_window_flake_with_cached_drafted_excludes_current
FAILED backend/tests/test_sleeper_pick_tradability.py::TestSleeperPickWindow::test_sleeper_pick_window_flake_without_verdict_abstains
FAILED backend/tests/test_sleeper_pick_tradability.py::TestSleeperPickWindow::test_cached_verdict_never_overrides_a_live_drafts_read
FAILED backend/tests/test_sleeper_pick_tradability.py::TestSleeperPickWindow::test_sleeper_pick_window_unknown_season_is_none
FAILED backend/tests/test_sleeper_pick_tradability.py::TestSleeperPickWindow::test_sleeper_pick_tradable
FAILED backend/tests/test_sleeper_pick_tradability.py::test_spent_current_season_pick_flags_pick_untradable
FAILED backend/tests/test_owned_picks.py::test_daemon_step_flaked_drafts_uses_cached_drafted_verdict
FAILED backend/tests/test_sleeper_write_route.py::test_propose_refuses_spent_current_season_pick
FAILED backend/tests/test_sleeper_write_route.py::test_propose_refuses_untradable_on_receive_side
FAILED backend/tests/test_sleeper_write_route.py::test_propose_untradable_reported_after_unmapped_before_not_owned
FAILED backend/tests/test_sleeper_write_route.py::test_propose_502_detail_is_sleepers_sentence
FAILED backend/tests/test_sleeper_write.py::test_graphql_error_detail_is_first_message
FAILED backend/tests/test_sleeper_write.py::test_graphql_error_auth_words_still_classified_from_full_dump
16 failed, 87 passed in 4.77s
```

The three headline RED assertions, verbatim:

```
test_propose_refuses_spent_current_season_pick
>       assert r.status_code == 422, r.get_data(as_text=True)
E       AssertionError: {"status":"proposed","transaction_id":"TX9"}
E       assert 200 == 422

test_daemon_step_flaked_drafts_uses_cached_drafted_verdict
>           assert all(r["season"] != 2026 for r in rows)
E           assert False

test_graphql_error_detail_is_first_message
>       assert ei.value.detail == "These draft picks cannot be traded."
E       - These draft picks cannot be traded.
E       + [{"message": "These draft picks cannot be traded.", "path": ["propose_trade"], "locations": [{"line": 2, "column": 3}]}]

test_spent_current_season_pick_flags_pick_untradable
>       assert _codes(r) == ["pick_untradable"]
E       AssertionError: assert [] == ['pick_untradable']
```

Tests that were GREEN on the pre-fix code by design (they pin behavior that must survive): `test_propose_in_window_pick_still_sends`, `test_propose_drafts_flake_without_verdict_does_not_block`, `test_propose_pick_free_send_makes_no_drafts_or_meta_fetch`, `test_daemon_step_flaked_drafts_without_verdict_keeps_current_season`, `test_in_window_pick_has_no_untradable_warning`, `test_validate_drafts_flake_without_verdict_does_not_flag`, `test_pick_free_validate_makes_no_drafts_fetch`. Existing `test_cached_verdict_does_not_leak_into_the_sleeper_sync` and every #413 test are unchanged and green.

GREEN after the fix: `python3 -m pytest backend/tests/test_sleeper_pick_tradability.py backend/tests/test_owned_picks.py backend/tests/test_sleeper_write_route.py backend/tests/test_sleeper_write.py backend/tests/test_pick_assignment.py backend/tests/test_trade_send_validate.py backend/tests/test_pick_horizon.py -q` → **171 passed**. Phase 4 re-run of the same command after the round-1 rulings (2 unit tests added: `test_completed_draft_seasons_is_shape_blind`, `test_sleeper_pick_window_post_startup_starts_next_class`; the shape test's expectation flipped) → **173 passed**.

Full suite (foreground, scratch SQLite): `python3 -m pytest backend/tests -q -p no:cacheprovider -x -q` → **exit 0 under `-x` (zero failures), 5,891 tests collected** (23 added by this build; `--co` count — the doubled `-q` swallowed the pass/skip summary line, and a sibling worktree's QA suite running concurrently pushed the wall time past 600 s, so the harness moved the run to the background; the run itself was a single uninterrupted pytest process on the scratch SQLite).

Mobile: `npx tsc --noEmit` → exit 0. `node tests/check-send-button-platform.js` → all checks pass, including the three new #428 lines (`sleeper_pick_untradable has its own Alert branch, no goConnect` · `renders the server detail` · `all three pick branches sit inside the ladder before the catch-all else`).

### Test placement (deviation from PRD §5 — placement only, not coverage)

The build brief owns `test_owned_picks.py`, `test_sleeper_write_route.py`, `test_sleeper_write.py` "+ a new test file if cleaner". PRD §5 also names `test_pick_horizon.py` and `test_trade_send_validate.py`, which the brief does not own, so those cases live in the new **`backend/tests/test_sleeper_pick_tradability.py`** (the window/predicate unit tests + the validate V-7…V-10 cases, which import the #180 `client` fixture rather than copying it). Names match the PRD's.

Second small deviation: the `_propose` helper's `drafts=` default is `DRAFTS_PRE` (not `DRAFTS_DONE`) so the existing T-5 (`test_propose_encodes_receive_pick_flips_from_to`, which sends `THEIR_2026_1ST`) keeps its fixture byte-for-byte; every #428 test passes `drafts=DRAFTS_DONE` explicitly, and `test_propose_in_window_pick_still_sends` proves a 2027 pick still sends under a completed 2026 draft with the same encoding as before.

## 4. D-189 text (for the orchestrator to allocate the id from origin/main)

> ## D-189 — A flaked Sleeper `/drafts` read consults the cached #207 verdict before showing current-season picks
>
> **Date:** 2026-09-08 · **Status:** accepted · **Narrows:** [D-089](#d-089) · **Origin:** feedback #428 (G-428)
>
> **Decision.** The Sleeper owned-pick sync (`_sync_sleeper_owned_picks`) and the pick-send tradability window (`draft_status.sleeper_pick_window`, used by `/api/trades/propose` and `/api/trades/validate`) still treat the live `GET /league/{id}/drafts` read as authoritative whenever it answers with a non-empty list. When it answers **empty** — a network flake and a draft-less league are indistinguishable there — they now consult the league's cached rookie-draft verdict (`leagues.draft_status`, #207): a positive `drafted` excludes the current season; `unknown`, `not_drafted` and NULL keep the D-089 fail-safe of excluding nothing. The cached verdict never overrides a live answer. Two deliberate blindnesses: the exclusion is **shape-blind** — any `complete` draft at or after the current season excludes that season, startup-shaped included, because a completed startup draft consumes the class exactly as a rookie draft does (Sleeper refuses the season's picks either way; this is the pre-#428 sync rule, restored after QA round 1) — and the corroboration is **confidence-blind** — any positive `drafted` counts regardless of confidence, matching `current_year_picks_visible`, with the failure mode bounded to one sync cycle (the next non-empty `/drafts` read overrides it).
>
> **Why.** D-089 chose "a flaked drafts read excludes nothing" because a phantom current-year pick is a visible, self-correcting error. #428 showed the cost once a draft has actually run: the grid is a replace-sync, so **one** member's flaked read re-populates the spent season for the **whole league** until the next healthy init, `traded_picks` keeps listing the spent season (so #413's holder check passes), and Sleeper then refuses the send with "These draft picks cannot be traded." — the operator's only acquired pick was exactly such a spent 2026 4th. Unknown-with-corroboration (a cached `drafted` written by the same signal chain on an earlier healthy read) is not the ambiguous case D-089 protected; unknown-without-corroboration still is, and still shows.
>
> **Consequences.** `test_cached_verdict_does_not_leak_into_the_sleeper_sync` stands (live `pre_draft` beats cached `drafted`). New guards: `test_daemon_step_flaked_drafts_uses_cached_drafted_verdict`, `test_daemon_step_flaked_drafts_without_verdict_keeps_current_season`, `TestSleeperPickWindow::test_sleeper_pick_window_flake_with_cached_drafted_excludes_current` / `…_flake_without_verdict_abstains` / `test_cached_verdict_never_overrides_a_live_drafts_read`. The residual window — flaked read **and** no cached verdict — is caught at send time by the #428 422 only if the window derives; otherwise Sleeper remains the final authority and F3 shows its sentence.

Also for write-back (not written by this agent): close **Q-037** on the public evidence in [investigation.md](investigation.md) §2 (`docs/api-reference.md` and `docs/integrations/sleeper.md` already say "confirmed / closed"); TEST_LEDGER + CHANGELOG entries per the suite line above.

## 5. Operator checklist (PRD §7 — build ≥ 1.17.2 (154) after the Render deploy; EAS optional)

1. **Pre-deploy definitive check:** read-only prod `SELECT season, COUNT(*) FROM draft_picks WHERE league_id='1312140920132497408' GROUP BY season`. Log the result in TEST_LEDGER (2026 rows present ⇒ root cause confirmed). Post-deploy, after one FFV3 app open, re-run: expect **2027, 2028, 2029 only** (48 each).
2. Open FFV3 → League picks list, In-league calculator pick rows, and one deck card with a pick: **no 2026 pick appears anywhere.** Any 2026 pick ⇒ stop, sync fix failed.
3. Build a trade giving your **2028 4th** for a player → Send in Sleeper → expect **"Sent"** and a pending proposal in Sleeper → cancel it in Sleeper. Repeat once with a **2029 1st** (logs Sleeper's window at runtime).
4. Build a trade **receiving** an acquired pick — e.g. roster 5 holds your original 2027 1st → ask for "2027 1st (orig. you)" → expect Sent → cancel in Sleeper. This is #413's TF-3; logging it closes Q-037 at runtime as well as on paper.
5. Negative path: on the web calculator (`web/`), hand-add the 2026 4th's id if the operator can still reach one (otherwise skip — log "not reachable"): expect the alert **"Couldn’t send — 1 draft pick in this trade can’t be traded in Sleeper right now … (Sleeper is trading 2027–2029 picks)"** and **no** `sleeper propose write-failed` line in Render.

## 6. Explicitly not changed (PRD §6)

`encode_draft_pick` and the `orig,season,round,from,to` order; `pick_horizon`'s 3-class rule and `PICK_HORIZON_MAX_CLASSES`; `load_draft_picks` and every read site (no new caller — the AST guard needed no sanction); the `traded_picks` holder rule; #413's `unmapped`/`not_owned` contracts and copy; MFL/ESPN routes; schema; flags; `backend/win_now_*`; `backend/overhaul_*` (inherits the clean grid and the same propose core); `sleeper_send_succeeded` props.
