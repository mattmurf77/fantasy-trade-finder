# Mini-PRD — G-428: Sleeper refuses spent-season pick sends (#428)

> Fast-track bug. Contract for a blind build agent. Evidence and hypothesis ranking: [investigation.md](investigation.md). Gates: [scope.md](scope.md). Predecessor: [#413 / D-176](../413-sleeper-send-draft-picks/prd.md). All file:line cites are against branch `claude/feedback-422-428`.

## 1. Repro (reconstructed)

1. FFV3 (`1312140920132497408`) held its 2026 rookie draft on 2026-08-26 (`/drafts` → `complete`). Sleeper's `traded_picks` still lists 34 season-2026 rows.
2. The league's `draft_picks` grid still carried 2026 rows on 2026-09-08 (mechanism: one flaked `/drafts` read at any member's `session/init` re-populates them — investigation §3.1; definitive check there).
3. The operator built a trade containing a 2026 pick (his only acquired pick is roster 11's 2026 4th; every other pick he can offer or receive is inside Sleeper's 2027–2029 window) and tapped Send in Sleeper.
4. `POST /api/trades/validate` → 0 warnings (grid row exists, `traded_picks` holder matches); `POST /api/trades/propose` encoded it and sent; Sleeper: `"These draft picks cannot be traded."` → 502 `sleeper_write_failed`; the app showed a raw JSON fragment.

## 2. Root cause

**Strongly indicated:** a spent current-season pick was offered, validated and sent because **nothing on the pick path knows the draft happened.** The two ground truths of D-176 — grid existence (`_sleeper_encode_ftf_picks`, `backend/server.py:30271-30320`) and live `traded_picks` holder (`:30254-30268`) — both still contain spent picks. The sync's only exclusion signal is the live `/drafts` read (`server.py:13329-13337`), fail-soft to "exclude nothing" (`:15979-15994`, D-089 fail-safe). **Confirmed:** the 502 `detail` is a JSON dump (`backend/sleeper_write.py:383-389`), not Sleeper's sentence. Refuted with platform evidence: a beyond-window 2029 pick, a wrong field-1 encoding (Q-037 — closes), deadline/`disable_trades`.

## 3. Fix

**F1 — one tradability predicate, `backend/draft_status.py`.**
```python
def completed_draft_seasons(drafts, current_season) -> set[int]
    # {int(d.season) for rookie-shaped-or-unknown d if d.status == "complete" and int(d.season) >= current_season}
def sleeper_pick_window(current_season, drafts, traded_picks=(), cached_verdict=None) -> tuple[int, int] | None
    # exclude = completed_draft_seasons(...)
    # if not drafts and cached_verdict is a positive `drafted` DraftStatus: exclude |= {current_season}   ← NEW fallback
    # return pick_horizon(current_season, exclude, observed_seasons=[tp.season for tp in traded_picks])
    # None only when current_season is unknown (caller abstains — never blocks)
def sleeper_pick_tradable(season, window) -> bool   # window is None → True (abstain); else first <= int(season) <= last
```
Used by:
- **Sync** `_sync_sleeper_owned_picks` (`server.py:13329-13337`): replace the inline loop with `completed_draft_seasons`, and when `_drafts == []` consult the cached #207 verdict via `get_league_draft_context(league_id)` → `_exclude |= {cur}` iff positive `drafted`. Live `/drafts` still wins whenever it answers (keeps `test_cached_verdict_does_not_leak_into_the_sleeper_sync` green). Log which signal excluded. This narrows the D-089 fail-safe: record as **D-189** (unknown-with-corroboration excludes; unknown-without-corroboration still shows).
- **Send + validate** `_sleeper_propose_core` (`server.py:18391-18411`) and the validate Sleeper branch (`:30052-30070`): when the trade carries a pick, additionally fetch `_fetch_sleeper_drafts` and (propose only — validate already has `meta`) `_fetch_sleeper_league_meta`; build `window = sleeper_pick_window(meta.season, drafts, traded, cached_verdict)`; extend `_sleeper_encode_ftf_picks` with a `window=None` kwarg returning a **fourth** list `untradable` (checked after the grid lookup, before the holder test). Propose: `422 {"error":"sleeper_pick_untradable","picks":[…],"season_window":[first,last],"message":…,"detail":…}` with `detail == message`; reported after `unmapped`, before `not_owned`. Validate: blocking advisory `code:"pick_untradable"`. Pick-free sends make **no** new fetch (R-4/R-12 of #413 stand). A drafts flake with no cached verdict ⇒ window excludes nothing ⇒ send proceeds; Sleeper stays the final authority (F3 then shows its reason).
- Copy (server, both routes): `"{n} draft pick{s} in this trade can’t be traded in Sleeper right now — {season list} picks are no longer tradable (Sleeper is trading {first}–{last} picks). Rebuild the trade with one of those."` Curly apostrophe, count-aware like #413.

**F2 — read paths inherit the clean grid.** Every surface (deck pool/eveners `server.py:1115`, `/api/league/picks` `:12456`, overhaul `pick_rows` `backend/overhaul_api.py:130`, Win Now) reads `load_draft_picks`; no per-read Sleeper call is added (rejected: one upstream call per read). The residual window (flaked sync **and** no cached verdict) is caught at send by F1.

**F3 — surface Sleeper's sentence.** `sleeper_write._post_graphql` (`:383-389`): `detail` = the first error's `message` string when present (fallback: the current JSON dump); the auth-word scan keeps reading the full dump. Route 502 body (`server.py:18435-18441`) additionally carries `message == detail`. Result on build 154, no EAS build: "Couldn’t send — These draft picks cannot be traded."

## 4. Files to touch

| File | Why |
|---|---|
| `backend/draft_status.py` | F1 predicate (owns `pick_horizon` already) |
| `backend/server.py` | sync fallback (`:13329-13337`); propose + validate guard (`:18391-18411`, `:30052-30070`); `_sleeper_encode_ftf_picks` 4th list (`:30271`); 502 `message` (`:18435`) |
| `backend/sleeper_write.py` | F3 `detail` extraction (`:383-389`) |
| `backend/analytics_taxonomy.py:1055-1074` · `docs/cross-client-invariants.md:872` · `docs/business/analytics/2026-08-11-p0-7-addendum.md:64-67` · `mobile/src/api/sendInSleeper.ts:5-7,214` · `mobile/src/components/SendInSleeperButton.tsx:252-253` | `sleeper_send_failed.error_code` closed enum 17 → 18 (`sleeper_pick_untradable`); validate `code` vocabulary + `pick_untradable`. Comment/doc sites only — `CLIENT_EVENT_PROPS` constrains keys, not values. |
| `mobile/src/components/SendInSleeperButton.tsx:305-327` | New `else if (code === 'sleeper_pick_untradable')` branch, count-aware, renders `detail` (the server sentence carries the season window), no `goConnect`. Optional for correctness — build 154's catch-all already renders `detail`. |
| `mobile/tests/check-send-button-platform.js` | pin the branch exists and never calls `goConnect` |
| `docs/api-reference.md:505-521` · `docs/integrations/sleeper.md` §2 rows 6–7, §3.3, §5 call budget | contract + tradability rule + `+drafts +meta` on pick sends only |
| `living-memory/OPEN_QUESTIONS.md` (close Q-037 on public evidence) · `DECISIONS.md` D-189 · `TEST_LEDGER.md` · `CHANGELOG.md` | session write-back |
| `backend/tests/…` | §5 |

## 5. Regression guards (pytest; prove RED on `origin/main` first)

Production fixture shape, reused across files: `META = {"season":"2026","status":"in_season","total_rosters":2,"settings":{"draft_rounds":4}}`; `DRAFTS_DONE = [{"draft_id":"d1","season":"2026","status":"complete","type":"linear","last_picked":1787707582674,"settings":{"rounds":4}}]`; `TRADED_2026 = [{"season":"2026","round":4,"roster_id":11,"owner_id":1,"previous_owner_id":11}]`; grid row `{"pick_id":f"{L}_2026_4_11","season":2026,"round":4,"original_roster_id":"11"}`. The `_propose` helper in `test_sleeper_write_route.py:293-330` patches `_sleeper_get` for every URL — add explicit `drafts=` / `meta=` kwargs patching `_fetch_sleeper_drafts` / `_fetch_sleeper_league_meta` (defaults: `DRAFTS_DONE`, `META`), and assert existing pick tests (`:368-393`, 2027 picks) stay 200.

- `test_pick_horizon.py::test_sleeper_pick_window_post_draft_is_next_three_classes` — `(2026, DRAFTS_DONE, traded with 2026+2028 rows)` → `(2027, 2029)`; 2026 rows must not widen. `…_pre_draft_anchors_current` → `(2026, 2028)`. `…_flake_with_cached_drafted_excludes_current` → `(2027, 2029)`. `…_flake_without_verdict_abstains` → `(2026, 2028)`. `…_unknown_season_is_none`.
- `test_owned_picks.py::test_daemon_step_flaked_drafts_uses_cached_drafted_verdict` — drafts `[]`, `set_league_draft_status(L,"drafted","high")` → no 2026 rows (**RED today**). `…_flaked_drafts_without_verdict_keeps_current_season` (pins the fail-safe). Existing `test_cached_verdict_does_not_leak…` unchanged.
- `test_sleeper_write_route.py::test_propose_refuses_spent_current_season_pick` — give `f"{L}_2026_4_11"` with the fixture above → 422 `sleeper_pick_untradable`, `picks == [id]`, `season_window == [2027, 2029]`, `detail == message`, `propose_trade` **not called**, no `sleeper_send_succeeded` row, no deck outcome (**RED today: 200 and `draft_picks == ["11,2026,4,1,2"]`**). `…_untradable_on_receive_side`. `…_untradable_reported_after_unmapped_before_not_owned`. `…_in_window_pick_still_sends` (2027 pick, same drafts → 200, `"1,2027,2,1,2"`). `…_drafts_flake_without_verdict_does_not_block` (drafts `[]` → 200). `…_pick_free_send_makes_no_drafts_or_meta_fetch`. `…_502_detail_is_sleepers_sentence` (`SleeperWriteError(detail="These draft picks cannot be traded.")` → body `detail` and `message` equal it).
- `test_sleeper_write.py::test_graphql_error_detail_is_first_message` — opener returns `{"errors":[{"message":"These draft picks cannot be traded.","path":["propose_trade"]}]}` → `ei.value.detail == "These draft picks cannot be traded."` (**RED today**: JSON dump). `…_auth_words_still_classified_from_full_dump`.
- `test_trade_send_validate.py::test_spent_current_season_pick_flags_pick_untradable` (blocking) and `…_in_window_pick_has_no_untradable_warning`.

## 6. Explicitly NOT changed

`encode_draft_pick` and the `orig,season,round,from,to` order (confirmed correct); `pick_horizon`'s 3-class rule and `PICK_HORIZON_MAX_CLASSES`; `load_draft_picks` and every read site; the `traded_picks` holder rule; #413's `unmapped`/`not_owned` contracts and copy; MFL/ESPN routes; schema; flags (`picks.owned_sync`, `picks.league_horizon`, `trade.send_in_sleeper` all stay as-is); the manual-assignment grid (Q-022); FAAB (Q-016); the `sleeper_send_succeeded` props.

## 7. Operator checklist (build ≥ 1.17.2 (154) after Render deploy; EAS optional)

1. **Pre-deploy definitive check:** read-only prod `SELECT season, COUNT(*) FROM draft_picks WHERE league_id='1312140920132497408' GROUP BY season`. Log the result in TEST_LEDGER (2026 rows present ⇒ root cause confirmed). Post-deploy, after one FFV3 app open, re-run: expect **2027, 2028, 2029 only** (48 each).
2. Open FFV3 → League picks list, In-league calculator pick rows, and one deck card with a pick: **no 2026 pick appears anywhere.** Any 2026 pick ⇒ stop, sync fix failed.
3. Build a trade giving your **2028 4th** for a player → Send in Sleeper → expect **"Sent"** and a pending proposal in Sleeper → cancel it in Sleeper. Repeat once with a **2029 1st** (logs Sleeper's window at runtime).
4. Build a trade **receiving** an acquired pick — e.g. roster 5 holds your original 2027 1st → ask for "2027 1st (orig. you)" → expect Sent → cancel in Sleeper. This is #413's TF-3; logging it closes Q-037 at runtime as well as on paper.
5. Negative path: on the web calculator (`web/`), hand-add the 2026 4th's id if the operator can still reach one (otherwise skip — log "not reachable"): expect the alert **"Couldn’t send — 1 draft pick in this trade can’t be traded in Sleeper right now … (Sleeper is trading 2027–2029 picks)"** and **no** `sleeper propose write-failed` line in Render.

## 8. Mobile copy

`SendInSleeperButton.tsx:323-327` renders `detail || 'Something went wrong…'` for every unlisted code, so **no mobile change is required for either the new 422 or the reshaped 502** — build 154 shows the server sentence. The dedicated `sleeper_pick_untradable` branch (§4) is a cosmetic parity item with #413's pair; ship it in the next EAS build, never as a blocker.
