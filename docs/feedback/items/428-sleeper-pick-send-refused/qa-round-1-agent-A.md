# QA round 1 — agent A — 2026-09-08

## Summary: FAIL (1 major finding pending adjudication, 3 minor observations)

The #428 fix does what the PRD says and every named defect test is proven RED on `15dabe05` / GREEN on `26ab3147`. The one FAIL-grade item (F-1) is a behavioral regression the PRD itself specified: the new `completed_draft_seasons` skips **startup-shaped** completed drafts, whereas the pre-fix sync loop excluded *any* completed current-season draft — a first-season startup league would re-show its spent current-season picks. It traces to PRD §3 wording, so it is a Phase 1 mini-round item, not a build defect. Everything else passes.

## Environment

- Worktree: detached at build tip `26ab3147` (`feedback #428: refuse spent-season Sleeper pick sends; sync consults cached draft verdict (D-189)`), base `15dabe05`. Diff under test `git diff 15dabe05..26ab3147` (16 files, +863/−70).
- Python 3.14.4 (`python3 -m pytest`, `-p no:cacheprovider`, scratch SQLite — `data/trade_finder.db*` removed before every run; production never touched). Node v24.14.1; `mobile/node_modules` is the populated symlink.
- Flags: none changed by the diff (`picks.owned_sync`, `picks.league_horizon`, `trade.send_in_sleeper` as on `main`).
- Live Sleeper public API read with `curl` (no auth) for fixture realism only.

## Results

| Test | Verdict | Evidence |
|---|---|---|
| Targeted pytest: `test_owned_picks.py test_sleeper_write_route.py test_sleeper_write.py test_sleeper_pick_tradability.py test_pick_assignment.py -q` | PASS | `139 passed in 16.18s` |
| Full `python3 -m pytest backend/tests -q` | PASS | `5890 passed, 1 skipped in 1297.94s (0:21:37)` — exit 0, 5,891 collected, 0 failed (wall time inflated by agent B's concurrent suite). Stderr carries 36 pre-existing `[receipts_*] failed: (sqlite3.OperationalError) no such table …` log lines from the receipts tests' stubbed engine — logged best-effort warnings, not failures, unrelated to this diff |
| RED-first proof — `git checkout 15dabe05 -- backend/draft_status.py backend/server.py backend/sleeper_write.py`, then the 4 test files | PASS (RED) | `16 failed, 87 passed in 5.82s` — exactly the 16 tests the build report names (8 `TestSleeperPickWindow`, `test_spent_current_season_pick_flags_pick_untradable`, `test_daemon_step_flaked_drafts_uses_cached_drafted_verdict`, `test_propose_refuses_spent_current_season_pick`, `…_untradable_on_receive_side`, `…_untradable_reported_after_unmapped_before_not_owned`, `…_502_detail_is_sleepers_sentence`, `test_graphql_error_detail_is_first_message`, `…_auth_words_still_classified_from_full_dump`). Headline RED lines verbatim below |
| RED-first proof — restore `26ab3147` files, rerun | PASS (GREEN) | `103 passed in 8.56s`; `git status` clean after restore |
| "Must-survive" tests green pre-fix by design (`test_propose_in_window_pick_still_sends`, `…_drafts_flake_without_verdict_does_not_block`, `…_pick_free_send_makes_no_drafts_or_meta_fetch`, `test_daemon_step_flaked_drafts_without_verdict_keeps_current_season`, `test_in_window_pick_has_no_untradable_warning`, `test_validate_drafts_flake_without_verdict_does_not_flag`, `test_pick_free_validate_makes_no_drafts_fetch`, `test_cached_verdict_does_not_leak_into_the_sleeper_sync`) | PASS | `8 passed, 70 deselected` on `15dabe05` — these pin behavior that must not change, they are not defect tests; none of the 16 defect tests is green pre-fix |
| Fixture realism vs live FFV3 (`1312140920132497408`) | PASS | `/drafts` → 1 entry `{status:"complete", season:"2026" (str), type:"linear", settings.rounds:4, last_picked set}`; `/traded_picks` → 57 rows, keys exactly `owner_id, previous_owner_id, roster_id, round, season` (season str), Counter 2026:34 / 2027:17 / 2028:6; `/league` → `season:"2026"` (str), `settings.trade_deadline:12`. Roster 11's 2026 R4 is held by roster 1 (`{round:4, season:"2026", roster_id:11, owner_id:1, previous_owner_id:11}`) — byte-identical to `TRADED_2026`. `DRAFTS_DONE` / `META` / grid row shapes in `test_sleeper_write_route.py:314-325` and `test_sleeper_pick_tradability.py:34-42` reproduce them |
| Real payload through the predicate | PASS | `_is_rookie_shaped(real FFV3 draft) = True`; `completed_draft_seasons(real, "2026") = {2026}`; `sleeper_pick_window("2026", real drafts, real traded_picks) = (2027, 2029)`; flake+no verdict → `(2026, 2028)`; flake+cached drafted → `(2027, 2029)`; season None → `None`; `sleeper_pick_tradable` over (2027,2029): 2026 F / 2027 T / 2029 T / 2030 F |
| Code-walk (a) sync: live read wins, cached verdict only on `[]` | PASS | below |
| Code-walk (b) `sleeper_pick_window` semantics | PASS | below |
| Code-walk (c) encoder order grid → window → holder | PASS | below |
| Code-walk (d) propose 422 shape + nothing sent | PASS | below |
| Code-walk (e) validate `pick_untradable` blocking | PASS | below |
| Code-walk (f) `/drafts` + `/league` fetched only with a pick | PASS | below |
| Code-walk (g) 502 `detail` = first `errors[].message`, `message == detail` | PASS | below |
| Code-walk (h) in-window 2027 pick under completed 2026 draft unchanged | PASS | below |
| Hunt: flaked `/drafts` + stale cached `drafted` in an undrafted league | PASS (observation F-2/F-4) | below |
| Hunt: startup-shaped completed draft | FAIL → F-1 | below |
| Hunt: overhaul path inherits clean grid | PASS | `backend/overhaul_api.py:130-137` `pick_rows` → `load_picks(league_id, source=pick_source_platform)` (= `load_draft_picks`, no per-read Sleeper call); sends go through `sleeper_propose=_sleeper_propose_core` (`backend/server.py:31637`), i.e. the same guarded core |
| Hunt: MFL / ESPN sends unaffected | PASS | `git diff 15dabe05..26ab3147 --stat -- backend/mfl_write.py backend/espn_write.py backend/mfl_service.py backend/espn_service.py backend/overhaul_api.py` is empty; `_sleeper_encode_ftf_picks` has exactly two callers (`server.py:18432`, `:30104`), both Sleeper-branch |
| `cd mobile && npx tsc --noEmit` | PASS | exit 0 |
| Every `mobile/tests/check-*.js` (100 files) | PASS | all 100 exit 0 |
| `check-send-button-platform.js` check 9 | PASS | `sleeper_pick_untradable has its own Alert branch, no goConnect` · `renders the server detail` · `all three pick branches sit inside the ladder before the catch-all else` · catch-all copy intact |
| Mobile branch code-walk | PASS | `SendInSleeperButton.tsx:268` `const detail = body?.detail`; new `else if (code === 'sleeper_pick_untradable')` at `:317-327` sits between `sleeper_pick_unmapped` (`:305`) and `sleeper_pick_not_owned` (`:328`), renders `detail || <count-aware fallback>`, no `goConnect`; catch-all `:335-340` unchanged. Enum comment 17 → 18 at `:252-254`, `sendInSleeper.ts:5-7,214` |
| Docs rows (api-reference propose/validate/error table, cross-client-invariants enum 18 + validate vocabulary, sleeper.md §1.1/§3.2/§3.3/§5) | PASS | diff read; contract text matches the code (`season_window`, `message == detail`, "after unmapped, before not_owned", pick-free sends make no new read) |
| PRD §7 step 1 — prod `SELECT season, COUNT(*) FROM draft_picks WHERE league_id='1312140920132497408'` | BLOCKED | no production access from QA (and none permitted); operator item |
| Runtime sends (PRD §7 steps 2–5) | BLOCKED | TestFlight-only evidence — checklist below |

### RED lines (pre-fix sources, `26ab3147` tests)

```
test_propose_refuses_spent_current_season_pick
E   AssertionError: {"status":"proposed","transaction_id":"TX9"}
E   assert 200 == 422
test_daemon_step_flaked_drafts_uses_cached_drafted_verdict
E   assert False   (all(r["season"] != 2026 for r in rows))
test_graphql_error_detail_is_first_message
E   - These draft picks cannot be traded.
E   + [{"message": "These draft picks cannot be traded.", "path": ["propose_trade"], "locations": [{"line": 2, "column": 3}]}]
test_spent_current_season_pick_flags_pick_untradable
E   AssertionError: assert [] == ['pick_untradable']
test_propose_502_detail_is_sleepers_sentence
E   KeyError: 'message'
test_graphql_error_auth_words_still_classified_from_full_dump
E   assert '[{"message":...ENTICATED"}}]' == 'request failed'
```

### Code-walk proofs (file:line against `26ab3147`)

**(a) Sync — live `/drafts` wins; cached verdict only on `[]`.** `_sync_sleeper_owned_picks` (`backend/server.py:13287`): `_drafts = _fetch_sleeper_drafts(league_id)` (`:13352`; `:16005-16021` returns `[]` on any exception or non-list) → `_exclude = completed_draft_seasons(_drafts, _cur_season)` (`:13353` → `draft_status.py:165-187`). The cached verdict is reached only through `if not _drafts:` (`:13354`) → `_sleeper_cached_draft_verdict` (`:13271-13284`, one `get_league_draft_context` read → `DraftStatus(status, confidence)`; None when no row / no status / read error) → `_exclude.add(_cur_season)` iff `.drafted` (`:13356-13357`). A non-empty list takes the `elif` at `:13360` and never consults the cache. `_exclude` feeds `save_draft_slot_order` (`:13369-13371`) and `sync_draft_picks(exclude_seasons=_exclude)` (`:13378-13391`, unchanged). Daemon ordering: the sync (`:21723`) runs **before** `_refresh_league_draft_status` (`:21739`) in the same pass, so the verdict consulted is always from an earlier pass — "corroboration from a previous healthy read", as D-189 says. Does-not-fire: `_drafts` non-empty (any content), or empty with a NULL / `unknown` / `not_drafted` row (`test_daemon_step_flaked_drafts_without_verdict_keeps_current_season` covers all three).

**(b) `sleeper_pick_window` (`draft_status.py:190-219`).** Unparseable `current_season` → `return None` (`:208-211`) → `sleeper_pick_tradable(…, None)` is `True` (`:226-227`) → abstain. `exclude = completed_draft_seasons(...)` (`:212`: `status == "complete"` `:177`, rookie-shaped-or-unknown `:179`, `season >= current_season` `:185`); cached verdict adds the current season only under `if not drafts and cached_verdict is not None and cached_verdict.drafted` (`:213-214`). `observed` = every `traded_picks[].season` (`:215-218`) → `pick_horizon(current, exclude, observed)` (`:219` → `:92-139`): the anchor walks past excluded seasons (`:126-127`), and an observed season widens `last` only when `first <= season <= ceiling` (`:136`), so a spent season (< `first`) can never re-enter — `test_sleeper_pick_window_post_draft_is_next_three_classes` (2026 + 2028 rows → `(2027, 2029)`).

**(c) Encoder order (`server.py:30327-30387`).** Per pick: `row = grid.get(str(pid))` → `unmapped` (`:30359-30362`); unparseable row → `unmapped` (`:30363-30366`); **`if not sleeper_pick_tradable(season, window): untradable`** (`:30369-30371`); holder lookup (`:30372-30378`); `if holder != from_rid: not_owned` (`:30379-30381`); `encode_draft_pick` (`:30383-30384`); 4-tuple returned `:30387`. So an in-window pick that changed hands still lands in `not_owned` (window passes at `:30369`, fails at `:30379`), and a spent pick lands in `untradable` before its holder is ever compared — `test_propose_untradable_reported_after_unmapped_before_not_owned` runs both orderings.

**(d) Propose 422 + nothing sent (`_sleeper_propose_core`, `server.py:18349`).** Guard `if give_picks or recv_picks:` (`:18418`) → grid (`:18423`) → traded (`:18424`) → `window = _sleeper_pick_window_for_send(league_id, _fetch_sleeper_league_meta(league_id), traded)` (`:18430-18431`) → encoder (`:18432-18434`). Returns: `unmapped` 422 (`:18437-18441`), then `{"error":"sleeper_pick_untradable","picks":untradable,"season_window":list(window),"message":_msg,"detail":_msg}` 422 (`:18443-18447`), then `not_owned` 422 (`:18448-18452`) — all before `req = ProposeTradeRequest(...)` (`:18454`) and `_sleeper_write.propose_trade(token, req)` (`:18461`). `test_propose_refuses_spent_current_season_pick` patches `server._sleeper_write.propose_trade` with a `MagicMock` and asserts `fake.assert_not_called()`, `_send_succeeded_rows() == []`, deck-outcome mock not called; `season_window == [2027, 2029]`, `detail == message`.

**(e) Validate (`trades_validate`, `server.py:30008`).** Same guard (`:30097`) → grid/traded (`:30099-30100`) → `window = _sleeper_pick_window_for_send(league_id, meta, traded)` (`:30103`; `meta` is the route's own `_fetch_sleeper_league_meta` at `:30045`, already required non-None for `checked:true`) → encoder (`:30104-30106`) → `warnings.append({"code":"pick_untradable","severity":"blocking", "message": _sleeper_untradable_copy(...)})` (`:30114-30115`). `test_spent_current_season_pick_flags_pick_untradable` asserts `_codes == ["pick_untradable"]`, severity blocking, window text.

**(f) Pick-only fetches.** The only `/drafts` read on the send paths is inside `_sleeper_pick_window_for_send` (`:30390-30400`, `:30397`), which is called only at `:18430` and `:30103`, both inside the `if give_picks or recv_picks:` blocks; the propose-side `/league/{id}` read is the inline `_fetch_sleeper_league_meta` at `:18431` in the same block (no other meta fetch exists in `_sleeper_propose_core` — only `_fetch_league_rosters` at `:18391`). `test_propose_pick_free_send_makes_no_drafts_or_meta_fetch` asserts `drafts_mock`, `meta_mock`, `grid_mock`, `traded_mock` all not called on a players-only 200; `test_pick_free_validate_makes_no_drafts_fetch` mirrors it.

**(g) 502 body.** `sleeper_write._post_graphql` (`backend/sleeper_write.py:384-398`): `first = errors[0]` (`:392`), `detail = str(msg).strip()[:500] if msg else dump` (`:394`), `low = dump.lower()` (`:395`) drives the auth-word scan, `SleeperWriteError(..., detail=detail)` (`:398`). Route except (`server.py:18475-18486`): `_detail = str(e.detail)[:200]`, body `{"error":"sleeper_write_failed","kind","detail":_detail,"message":_detail}`. Tests `test_graphql_error_detail_is_first_message`, `…_auth_words_still_classified_from_full_dump` (extensions.code UNAUTHENTICATED → `SleeperAuthError`, detail "request failed"; message-less error → JSON dump fallback), `test_propose_502_detail_is_sleepers_sentence`.

**(h) #413 unchanged.** The test diff for `test_sleeper_write_route.py` only (1) adds fixtures and (2) gives `_propose` `drafts=DRAFTS_PRE`, `meta=META` kwargs — no pre-existing test body is touched, and T-5 (`THEIR_2026_1ST` under a pre-draft list) keeps its fixture. `test_propose_in_window_pick_still_sends`: `MY_2027_2ND` under `DRAFTS_DONE` → 200 with `draft_picks == ["1,2027,2,1,2"]`, the same string as before #428.

## Findings

### F-1: `completed_draft_seasons` no longer excludes a completed **startup-shaped** current-season draft (pre-fix sync did)
- Severity: **major** (pending adjudication — PRD-level, not a build defect; downgrade to minor if no prod league is in its startup season)
- Repro (code path): pre-fix `server.py` loop excluded the current season for **any** `status == "complete"` draft with `season == _cur_season`. Post-fix `draft_status.completed_draft_seasons` skips drafts where `_is_rookie_shaped(d) is False` (`draft_status.py:179`, i.e. `settings.rounds >= 15`, `:306-315`). Probe on `26ab3147`: `startup = [{"season":"2026","status":"complete","last_picked":1,"settings":{"rounds":25}}]` → pre-fix loop `{2026}`, `completed_draft_seasons(startup, 2026)` → `set()`, `sleeper_pick_window(2026, startup, [])` → `(2026, 2028)`. So in a first-season dynasty league whose startup draft (≥15 rounds) is complete, the next sync **re-populates the spent 2026 class league-wide** (the replace-sync), and the send window admits it — the pick reaches Sleeper and is refused with F3's sentence. That is the #428 symptom class recreated for a different league type, and a regression of #228's exclusion for it. The cached #207 verdict cannot help: `/drafts` is non-empty, so the live read "wins" (`server.py:13354`, `draft_status.py:213`).
- Expected (PRD §2/§3: "nothing on the pick path knows the draft happened" → exclude spent classes) vs actual: PRD §3 literally specifies "rookie-shaped-or-unknown", and `test_completed_draft_seasons_reads_only_complete_current_or_later` pins the skip (`{"rounds": 25}` startup entry must be ignored) — the build followed the spec. The rookie/startup discrimination was designed for #207's *verdict* ("a completed startup says nothing about a still-pending rookie draft"), but for Sleeper **tradability** a completed startup consumes that season's draft object regardless. Not verifiable here: none of the three public league ids in the PRD is startup-shaped (all `rounds: 4`), so I could not observe Sleeper's answer for a post-startup current-season pick. Phase 1 mini-round: either drop the shape filter in `completed_draft_seasons` (and flip the unit-test expectation) or document why a startup-year league keeps current-season picks tradable.
- Evidence: `backend/draft_status.py:177-185`, `:306-315`; `backend/tests/test_sleeper_pick_tradability.py:53-63`; pre-fix `git show 15dabe05:backend/server.py` loop at the old `:13329-13337`; probe output above.

### F-2: D-189 corroboration ignores confidence (observation, not a defect)
- Severity: minor
- `_sleeper_cached_draft_verdict` builds `DraftStatus(status, confidence)` and the sync/window test only `.drafted` (`server.py:13356`, `draft_status.py:213`), so a rosters-heuristic `drafted/medium` (`rosters_verdict`, `draft_status.py:284`) corroborates a flake. This matches `current_year_picks_visible` (`:236-240`, also confidence-blind), so it is consistent with #207, and the failure mode is bounded: one sync cycle of a hidden current season, self-healed by the next non-empty `/drafts` read. Worth one sentence in the D-189 text ("any positive `drafted`, regardless of confidence").
- Evidence: cites above.

### F-3: dead branches in the untradable copy (cosmetic)
- Severity: minor
- `"season_window": list(window) if window else None` (`server.py:18446`) and the `("?", "?")` fallback in `_sleeper_untradable_copy` (`:30418`) are unreachable: when `window is None`, `sleeper_pick_tradable` returns True for every pick (`draft_status.py:226-227`), so `untradable` is always empty. Harmless; the api-reference row documents `null` as a possible `season_window` value, which cannot occur.

### F-4: cached verdict is not season-checked; `leagues.season` is a literal
- Severity: minor (pre-existing, out of #428 scope; noted because D-189 adds a consumer)
- `_sleeper_cached_draft_verdict` ignores `ctx["season"]`, and session-init upserts `season = "2026"` as a constant (`server.py:21439`). Mitigations already in place: the detector re-derives the season from live meta (`server.py:17955`), and Sleeper league ids are per-season (a new id each year), so a `drafted` verdict on a given id cannot refer to a prior season's draft. No action for #428; the hardcode is a 2027 rollover item for NEXT.md.

## TestFlight checklist (operator-run) — build ≥ 1.17.2 (154) after the Render deploy; EAS optional

1. **Pre-deploy (Render shell / read-only prod)** → `SELECT season, COUNT(*) FROM draft_picks WHERE league_id='1312140920132497408' GROUP BY season` → expect 2026 rows present (root cause confirmed); log the counts in TEST_LEDGER.
2. **Deploy → open the app once in FFV3** (any screen; session init runs the sync) → re-run the query → expect **2027, 2028, 2029 only**, 48 rows each, **no 2026**. Render log for that init carries `owned-pick sync for 1312140920132497408: excluding [2026] — Sleeper reports the draft complete`.
3. **League → Picks list** (FFV3) → expect no 2026 pick anywhere in the list; every pick is 2027–2029.
4. **Trades → Calculator → In-league → pick rows** → expect the pick picker offers only 2027–2029 picks; your side shows the 2028 4th and 2029 1st–4th (your Sleeper-tradable inventory), and the "2026 4th (orig. roster 11)" is gone.
5. **Trades → Deck** → swipe until a card carries a pick → expect the pick's season is 2027–2029; no card ever names a 2026 pick.
6. **Positive send, own pick:** Calculator → give your **2028 4th** for any player → Send in Sleeper → expect **"Sent"** and a pending proposal in the Sleeper app → cancel it in Sleeper.
7. **Positive send, far class:** same with your **2029 1st** → expect "Sent" (confirms Sleeper's window reaches 2029) → cancel in Sleeper.
8. **Positive send, acquired pick on the receive side:** ask roster 5 for "2027 1st (orig. you)" for a player → expect "Sent" → cancel in Sleeper (#413 TF-3; runtime close of Q-037).
9. **Negative send, spent pick (only if reachable):** on the web calculator (`web/`) hand-add the pick id `1312140920132497408_2026_4_11` to your give side → Send → expect the alert **"Couldn’t send — 1 draft pick in this trade can’t be traded in Sleeper right now — 2026 picks are no longer tradable (Sleeper is trading 2027–2029 picks). Rebuild the trade with one of those."**, **not** "Please try again", and **no** `sleeper propose write-failed` line in Render (a 422 is logged, not a 502). If the id is not reachable from any surface, log "not reachable" — the server-side refusal is covered by `test_propose_refuses_spent_current_season_pick`.
10. **Validate mirror (same trade as step 9, before tapping Send):** the pre-flight should show a blocking warning with the same sentence (`pick_untradable`); the confirm sheet must not offer to proceed.
11. **Players-only send unchanged:** Calculator → give one player for one player → Send in Sleeper → expect "Sent", one Render line for `/api/trades/propose` with **no** `→ Sleeper GET …/drafts` or `…/league/1312140920132497408` read in the same request → cancel in Sleeper.
12. **Mobile parity branch (only after the next EAS build ships `26ab3147`'s `SendInSleeperButton.tsx`):** repeat step 9 on the device → the alert title is "Couldn’t send" with the server sentence, and it does **not** open the Sleeper reconnect screen.
