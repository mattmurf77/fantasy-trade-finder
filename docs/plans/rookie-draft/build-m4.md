# Build status — M3-route + M4 (the Draft Room)

**Date:** 2026-08-06 · **Wave:** M3 route shim + M4 Draft Room UI
**Parents:** [plan.md](plan.md) §M3/§M4 + the 2026-08-06 operator decisions · [lld.md](lld.md) §2.1/§4.4/§4.5/§6
**Base:** `origin/main` @ `586aefd` (merge clean; `draft_board_service.py` already landed, schema:1, fixtures-driven, unrouted)
**Gates:** `python3 -m pytest backend/tests -q` → **1685 passed / 1 skipped** (baseline 1677/1; +8 route tests) · `cd mobile && tsc --noEmit` → **clean**

Both flags land **OFF**. With `draft.room` off the route 404s and the League tab is byte-identical to today.

---

## 1. What shipped

### Backend

| File | Change |
|---|---|
| `backend/server.py` | `GET /api/draft/board` — the route shim (`draft_board_route`). `@_gate_unverified_read`, `is_enabled("draft.room")` as the **first statement**, session + league resolution, production fetcher bindings, `jsonify(build_board(...))` |
| `backend/draft_board_service.py` | One addition: public `unsupported_board(req)` — see §3 |
| `backend/feature_flags.py` | `draft.room`, `draft.live_poll` appended to `FLAG_KEYS` (⇒ default `False`) |
| `config/features.json` + `backend/tests/fixtures/flags/release.json` | Both keys at `false`; `_comment_rookie_draft` extended |
| `backend/tests/test_draft_board.py` | T-M3-13 block — 8 route tests (§4) |

**Fetcher bindings.** `PlatformFetchers(sleeper_get=_sleeper_get, rookie_ids_fn=_rookie_player_ids)`.
- `_sleeper_get` rather than a fresh HTTP helper: it already routes through the `FTF_SLEEPER_FIXTURES_DIR` seam (A-7), so the route gets fixture replay for free and can never make a live call under `FTF_TEST_MODE`.
- `_rookie_player_ids` rather than the module default `database_rookie_ids`: same predicate (`load_rookie_player_ids`), but memoized on `(season, pool_generation)`, so the board shares M0's memo instead of re-querying per request.
- The LLD anticipated two new one-liner wrappers (`_fetch_sleeper_draft_detail` / `_fetch_sleeper_draft_picks`). They were **not** written: `PlatformFetchers` already builds those URLs internally, so the wrappers would have been dead indirection.

**League + season resolution.** The persisted league row (`get_league_draft_context`) is authoritative — it is what #207's detector reads. An in-session league with no row yet still resolves via `sess["league"].platform` + `_CURRENT_SEASON`. Anything else is `404 league_not_found`.

**Board values.** Consensus seed always (`_get_universal_pool(fmt)[1]`); the caller's live board only when `basis=my_board` was actually asked for — `get_rankings(position=None)` walks the whole pool and is not free.

### Mobile

| File | Change |
|---|---|
| `mobile/src/api/draft.ts` | **new** — `getDraftBoard(leagueId, basis)` + the payload types. Throws `DraftSchemaError` on an unknown `schema` |
| `mobile/src/screens/DraftRoomScreen.tsx` | **new** — the room |
| `mobile/src/hooks/useAppActive.ts` | **new** — `AppState === 'active'`, the third poll gate |
| `mobile/src/navigation/RootNav.tsx` | `DraftRoom` on the `AuthStack` type + a `<Stack.Screen>` copying the FreeAgents block **including the #151/RNS#3294 `headerBackVisible:false` + custom `HeaderBack`** (omitting it leaves iOS 26 back dead) |
| `mobile/src/screens/LeagueScreen.tsx` | The conditional Explore-tile swap (O1) |
| `mobile/src/utils/deepLinks.ts` | `DraftRoom: 'app/league/draft-room'` — URL-addressability is definition-of-done for a new screen (navigation/CLAUDE.md) |

`<FeedbackFAB activeScreen="DraftRoom" aboveTabBar={false} />` per CLAUDE.md's root-stack rule.

---

## 2. States covered

Each is a distinct render with its own copy and testID. None is a spinner.

| State | Trigger | What the user sees | testID |
|---|---|---|---|
| **order not set** | `order_confidence: 'unset'` | "The draft order isn't set yet, so we're showing who owns each round instead of exact picks." Section header flips to **Round ownership**; slots render `R1` not `1.04`. **Never an invented order** | `draft-room.notice.order_not_set` |
| **pre-class-load** | `notice.class_not_loaded` | "The 2027 rookie class loads after the NFL draft (late April)." + a **Show last year's class** toggle (session-only, #133 precedent) | `draft-room.notice.class_not_loaded`, `draft-room.last-year-toggle` |
| **startup-labeled** | `kind: 'startup'` | "This looks like a startup draft, not a rookie draft — we're not guessing at a rookie list for it." Undrafted section does not render | `draft-room.notice.startup_draft` |
| **platform unsupported** | non-Sleeper league | "Draft rooms aren't available for this platform yet." | `draft-room.notice.platform_unsupported` |
| **stale** | `stale: true` | "Last updated 6m ago" + the degraded reason in plain words. **`as_of` renders in EVERY state**, stale or not | `draft-room.as-of` |
| **unavailable** | `state: 'unavailable'` | Honest empty + pull-to-refresh; Refresh stays available | `draft-room.unavailable-text` |
| **schema too new** | `schema !== 1` | "This draft board needs a newer version of the app." No Retry — retrying cannot help | `draft-room.error-text` |
| **no league** | no session league | "Connect a league to see its rookie draft." | `draft-room.empty-text` |
| **live / complete / upcoming** | normal | State chip + board + your picks + undrafted | `draft-room.state` |

Undrafted section: `Consensus | My board` chips (`draft-room.basis.consensus` / `.my-board`), a my-board fallback notice, and a "some rookies have no consensus value" notice — those rows render with "No value" and sort last, never dropped (D7).

Deep-link CTA (`draft-room.deep-link`) with the line "Picks are made on the platform — Fantasy Trade Finder never drafts for you." **No write path exists anywhere in this wave** (D9).

---

## 3. Decisions taken during the build

**MFL is not bound here.** `draft_board_service` renders MFL fully and `test_m5_*` already covers it, but M5 owns the wiring behind its own `draft.mfl` flag. Binding it under `draft.room` would have made that flag retroactive. Passing an MFL league into `build_board` unbound would have produced `notice.mfl_reconnect` — telling the user to reconnect a league to fix a feature that hasn't shipped. So the shim short-circuits every non-Sleeper platform through a new public `draft_board_service.unsupported_board(req)`, which echoes the real platform and says `platform_unsupported`. Four lines, and it keeps `draft.mfl` meaning what M5 needs it to mean.

**The route is registered unconditionally; the TILE is what the flag gates.** Same reasoning that keeps `RookieDraftBoardSheet` mounted outside its flag at `LeagueScreen:662` — a flag revalidation mid-push would otherwise unmount the screen under the user.

**`'inactive'` counts as not-active** in `useAppActive`. App switcher and Control Center are brief, but the user cannot see the screen; the cost of being wrong is one skipped 15 s tick.

**The tile swap is `showDraftRoom ? … : showRookieBoard ? … : null`**, not two independent tiles. O1 says replace; the conditional is what makes flag-off restore rather than empty the slot.

---

## 4. Test coverage added (T-M3-13)

`backend/tests/test_draft_board.py`, 8 cases. The 28 pre-existing service tests are untouched.

| Test | Proves |
|---|---|
| `test_m3_13_flag_off_is_404_feature_disabled` | Flag off ⇒ `404 {"error":"feature_disabled"}` |
| `test_m3_13_flag_off_gates_before_any_session_work` | No token at all still 404s — the gate is the first statement, so an unauthenticated probe learns nothing |
| `test_m3_13_flag_off_changes_no_other_route` | D10: a neighbouring unflagged route (`/api/tier-config`) is byte-identical flag-off vs flag-on |
| `test_m3_13_flag_on_without_a_session_is_401` | The read gate falls through to `_require_session` |
| `test_route_rejects_an_unknown_basis` | `400 bad_basis` |
| `test_route_404s_a_league_it_has_never_seen` | `404 league_not_found` |
| `test_route_renders_the_honest_state_for_an_unbound_platform` | MFL ⇒ `platform_unsupported`, **not** `mfl_reconnect` |
| `test_route_serves_a_schema_1_board_from_the_corpus` | End-to-end through the shim on the Lakeview corpus: 48 picks, `state:"complete"`, `undrafted_basis:"my_board"`, deep link present, `my_picks` non-empty |

Flag-mirror tests (`test_seed_ui_test_db.py`, `test_entitlements.py`) re-run green — both new keys exist in all four touch points and default `False`.

---

## 5. Docs touched

`docs/api-reference.md` (new **## Draft room** section + the gated-read matrix row recording the RV-1 divergence from `power-rankings`) · `docs/config-reference.md` (both flags in the Rookie-draft table) · `docs/architecture.md` (the `draft_board_service.py` row now says routed, and what is bound) · `docs/runbook.md` (new **## Draft Room polling budget** — the zero-request rule, the per-process fan-in caveat, the kill order) · `mobile/src/{screens,api,hooks,navigation}/CLAUDE.md`.

`docs/glossary.md` already carried **Draft Room** and **Order confidence** from the M3 service wave — no change needed.

---

## 6. Not done here (by design)

- **T-M4-01..06** — Maestro + Jest + the instrumented zero-request check. T-M4-06 (throwaway-league live test) is the plan's **release** gate for `draft.live_poll`, explicitly not a batch gate.
- **M5 MFL wiring** (`draft.mfl`) and **M6 slot values** (`picks.slot_values`) — `slot_value` is typed optional in `api/draft.ts` so M6 is additive on the client.
- **Retiring `/api/rookies` + `RookieDraftBoardSheet`** — the LLD schedules that as a separate post-flip commit once `draft.room` is on and stable. The web overlay still consumes `/api/rookies` and has no flag.
- **Rank screens, `ranking_service.py`, `database.py`** — owned by the concurrent M2 agent; untouched. The only `LeagueScreen` edit is the tile swap.

## 7. Before flipping `draft.room` on

1. Re-run the flag-mirror pair.
2. Instrument T-M4-02 and confirm **zero** requests blurred/backgrounded before `draft.live_poll` follows.
3. Restate the ≤3 req/min/draft fan-in ceiling for the post-upgrade worker count (plan O8 / runbook).
