# QA round 1 — agent A — 2026-09-08

## Summary: PASS (0 blocking findings; 3 minor — F-1 copy nit, F-2 doc count, F-3 out-of-diff suite flake needing an orchestrator re-run; 2 observations)

## Environment
- Worktree: detached at `da1abb21` (G-422 build tip; base `8bd536df`). Diff under test `git diff 8bd536df..da1abb21`: `backend/win_now_service.py` (+28/−1), `backend/tests/test_win_now_service.py` (+96), `backend/tests/test_win_now_api.py` (+16), `docs/api-reference.md` (1 sentence), PRD/build-report docs. No mobile, web, flag, schema, or store changes in the diff.
- Python 3.14.4; pytest run with `-p no:cacheprovider`; scratch SQLite only (`data/trade_finder.db*` removed before every run); working tree clean before and after (`git status --short` → 0 lines).
- Flags: none pinned; the route tests use the existing `harness` fixture. Network used once, read-only, to `GET https://api.sleeper.app/v1/league/1312140920132497408` for fixture verification. Nothing pointed at production.
- No simulator, no Maestro (D-056).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| `pytest backend/tests/test_win_now_service.py backend/tests/test_win_now_api.py -q` | PASS | 93 passed in 3.15s |
| `pytest backend/tests -q` (full) | PASS (1 environment flake, see F-3) | `1 failed, 5871 passed, 1 skipped in 1466.16s (0:24:26)`. The one failure is `test_rookie_scope.py::test_m2_11c_qc_branch_is_skipped_under_scope` — outside the diff, passes 3/3 in isolation and 34/34 for its file, failed on a wall-clock `session_expired` 401 during a 24-min run (2× the build report's 11 min; my probe scripts shared the machine). Expected count 5872 = 5871 + the flake. Log: `scratchpad/full-suite-a.log` |
| RED-first: `test_ffv3_active_kicker_idp_slots_refused_before_any_projection_fetch` | PASS | on `8bd536df` service: `Failed: DID NOT RAISE <class 'backend.win_now_service.Unavailable'>`; on `da1abb21`: green |
| RED-first: `test_ffv3_load_bundle_refusal_is_the_slot_reason_not_a_forecast_reason` | PASS | RED: `AssertionError: assert 'missing_forecast_week:1' == 'unsupported_roster_slots'` (forecast gap won, as the PRD says); GREEN after |
| RED-first: `test_unsupported_slots_message_names_distinct_slots_in_roster_order` | PASS | RED: `AttributeError: module 'backend.win_now_service' has no attribute 'unsupported_slots_message'` (`test_win_now_service.py:634`); GREEN after. Asserts "5 of 6" (amended PRD §5) |
| RED-first: `test_win_now_api.py::test_projection_route_returns_slot_refusal_message_verbatim` | PASS | RED: same `AttributeError` at `test_win_now_api.py:577`; GREEN after |
| `test_offense_only_lakeview_slots_pass_the_slot_gate` | PASS | green on both `8bd536df` and `da1abb21` — the PRD states this guard is GREEN-before-and-after (over-refusal guard), so its staying green on pre-fix code is expected, not a self-satisfying test. RED totals: `4 failed, 1 passed in 1.18s`; GREEN totals: `5 passed in 0.73s` |
| Fixture realism (`ffv3_source_fixture`) vs live Sleeper | PASS | live `roster_positions` == `FFV3_ROSTER_POSITIONS` (36 entries, 15 active, only `BN` as bench token); live `scoring_settings` == `FFV3_SCORING` key-for-key and value-for-value (55 keys, 0 diffs); the ten `settings` values match; `total_rosters` 12, `status` in_season, `season` 2026 |
| R: gate ordering (code-walk) | PASS | `win_now_service.py:134-135` `missing_scoring_settings` → `:138-140` slot gate → `:141-151` standings loop → `:180` first `/matchups/` fetch → `_forecast_batch` (`:211`, called from `load_bundle:246`). Fetch census on FFV3 with `_cache` cleared: exactly `league/…`, `league/…/rosters`, `league/…/users`; zero `/matchups/`, zero `/projections/` |
| R: reason string unchanged | PASS | `win_now_service.py:140` raises `"unsupported_roster_slots"`; consumers `season_simulator.py:56,133`, `season_history.py:40` untouched by the diff |
| R: simulator backstop untouched | PASS | `git diff 8bd536df..da1abb21 -- backend/season_simulator.py` is empty; `_validate` still refuses `not slots or len(slots) > 12 or any(s not in SLOT_POSITIONS …)` at `season_simulator.py:54-56` |
| R: route returns `message` verbatim | PASS | `win_now_api.py:48-49` `unavailable()` → `{"status":"unavailable","reason":exc.reason,"message":exc.message}`; `:58-59` `guarded` catches `service.Unavailable`; `season_projections_route` (`:76-93`) calls `service.load_bundle` directly — no job row. Test asserts `response.json["message"] == refusal.message` |
| R: message byte-for-byte PRD §3(1) copy | PASS | `unsupported_slots_message(FFV3 15 slots) == <PRD sentence>` → `True` (266 chars). Helper `:42-61` |
| R: Lakeview-shaped leagues pass unchanged | PASS | Lakeview 24-entry positions → `load_league` succeeds, `roster_slots` = the 10 active (incl. `SUPER_FLEX`), `buyer == 1`. Gate condition `:139` is exactly `_validate`'s minus the `not slots` clause, so nothing that passed the backstop is newly refused |
| R: >12-slot sentence | PASS | 13 offense-only slots → `"Win Now can't model this league yet. It starts 13 players and season projections support at most 12 starting slots."`, no "IDP" wording |
| Hunt: import cycle `win_now_service` ↔ `season_simulator` | PASS | fresh interpreter `import backend.win_now_service` OK; fresh `import backend.season_simulator` does not load `win_now_service` (`sys.modules` check); `season_simulator.py:18` imports only `season_forecasts`. The lazy `simulate_season` import in `load_bundle:241` is unchanged |
| Hunt: bench-token filtering | PASS | gate filters `("BN","IR","TAXI","RESERVE")` (`:138`) — a superset of `season_simulator.BENCH_SLOTS` (`:24`), `outlook/league_state.py:52`, and `server.py:5390,14155` (`BN/IR/TAXI`). Live FFV3 carries only `BN` in `roster_positions`; IR/taxi are `settings.reserve_slots`/`taxi_slots` (3/0), not position entries. No token Sleeper emits would be counted as a starter |
| Hunt: `roster_positions` missing / empty | PASS | with the key deleted or `[]`, `load_league` still passes the gate (`slots=[]`; `len 0 > 12` false, `any()` false) and proceeds to standings/matchups exactly as before — refusal is left to the backstop's `not slots` clause. No league that used to pass is newly refused |
| Hunt: store / job lifecycle changed | PASS | `win_now_store.py` not in the diff; `create_job/claim_job/finish_job/expire_jobs` unchanged |
| Hunt: early refusal cached as a failed job row | PASS | The GET route never creates a job (`win_now_api.py:76-93`). `_fetch` (`win_now_service.py:93-108`) caches *successful source responses only* (30 s TTL for league meta) — an `Unavailable` is never stored. Only `process_pending` (`:557-575`) writes failed rows, and search jobs cannot be enqueued for FFV3 because `canSearch` requires `available` (`WinNowScreen.tsx:128`, `:219`). A later K/IDP fix would take effect on the next GET with no stale row to mask it |
| `docs/api-reference.md` | PASS | `:1005` gains the one sentence the PRD §4 asks for (K/DEF/IDP or >12 active → `unsupported_roster_slots` before any standings/projection fetch, slot names in `message`) |
| Web `/win-now` view | PASS (code-walk) | `web/index.html:796-801` `#view-win-now`; `web/js/win-now.js:231` renders `baseline.message` first, same pattern as mobile `:195`. Not exercised against a running Flask server — the diff has no web change, and the message reaches the client on the same 200 body the route test asserts |

## Findings

### F-1: DEF-slot leagues get the "Kicker and IDP projections are not supported" sentence
- Severity: minor (copy)
- Repro: `unsupported_slots_message(["QB","RB","WR","TE","DEF"])` → "…uses DEF (1 of 5 starting slots)… Kicker and IDP projections are not supported…". `DEF` is not in `SLOT_POSITIONS` (`season_simulator.py:21-23`), so team-defense leagues are refused with a sentence that names K/IDP but not DEF.
- Expected (PRD §3(1)) vs actual: the PRD copy is FFV3-specific and the builder shipped it verbatim, so this is inside spec; `docs/api-reference.md:1005` does say "K/DEF/IDP". Suggest a follow-up copy tweak ("Kicker, team-defense and IDP projections…") rather than a G-422 block.
- Evidence: `backend/win_now_service.py:55-59`.

### F-2: PRD §5 / build-report §3 mis-count the fixture's scoring keys
- Severity: minor (docs only)
- Both say the 55-key `scoring_settings` has "12 `idp_*`, 9 kicker keys". Live and fixture have **13** `idp_*` keys (`idp_blk_kick … idp_tkl_solo`) and **8** kicker keys (`fgm_0_19/20_29/30_39/40_49/50p`, `fgmiss`, `xpm`, `xpmiss`). The fixture dict itself is exact; only the prose count is wrong. Also, `test_win_now_service.py:558` comment says "8 of them K/DL/LB/DB/IDP_FLEX" — that one is correct.
- Evidence: value-level diff against `GET /v1/league/1312140920132497408` on 2026-09-08 → 0 key diffs, 0 value diffs.

### F-3: one full-suite failure outside the diff — `test_rookie_scope.py::test_m2_11c_qc_branch_is_skipped_under_scope`
- Severity: minor — classified **environment / timing flake**, not an app bug of this diff; orchestrator should re-run to confirm (the build agent's run of the same sha reported 5872 passed / 0 failed).
- Repro: only in the full-suite run (`1 failed, 5871 passed, 1 skipped in 1466.16s`). The test loops `QC_TRIO_INTERVAL + 3` = 103 GETs on `/api/trio?position=RB&scope=rookie` with the fixture token `sess-m2-tok` (`test_rookie_scope.py:615-623`); one of them answered 401 `{"error":"session_expired","message":"Session expired — please reload the page."}` (`server.py:2266-2268`) instead of 200 (`:472 assert r.status_code == expect`). That 401 is raised only when `_get_session(token)` returns `None` (`server.py:2527-2529`), the session is `_revoked` (`:2813-2814`), or the request waited behind a user-data deletion lease (`:2829-2831`) — all suite-order/wall-clock conditions on the shared in-memory session store, none reachable from `win_now_service`.
- Expected vs actual: the diff touches no file the test imports (`git diff --stat 8bd536df..da1abb21` has no rookie/trio/session files). Isolated reruns on `da1abb21`: 3/3 passed (9.3 s, 5.2 s, 3.8 s); whole file 34/34 passed. My run took 24 min against the build report's 11 — the machine was also running my probe scripts and the FFV3 census concurrently, which is the likeliest cause of the timing difference.
- Evidence: `scratchpad/full-suite-a.log` lines 285-…; the `WARNING persisted-session purge failed: no such table: sessions` lines in the same log are the known scratch-SQLite noise, not the cause.

### Observations (not defects of this diff)
- O-1: A failed *search job* stores only `exc.reason` (`win_now_service.py:570-571` → `store.finish_job(reason=…)`), and `/api/win-now/jobs/<id>` synthesises `message` from the reason (`win_now_api.py:156-157`), so the specific slot sentence would not survive a job. Unreachable on FFV3 (search is gated on `available`), pre-existing, and outside PRD §3 scope — noting so nobody expects the long message from a job poll.
- O-2: `_fetch` caches league meta for 30 s: after a K/IDP league changes its lineup, the first Win Now load inside that window can still show the refusal. Pre-existing behaviour; bounded; not introduced by the diff.

## TestFlight checklist (operator-run)
Run after Render is LIVE on the merge sha; existing binary 1.17.1 (149) is enough — no client change shipped.

1. Sign in as mattmurf77 → switch active league to **FFV3** (`1312140920132497408`) → League tab → "Season projections & Win Now". **Expect:** within ~2 s (one round-trip: league meta + rosters + users), the `win-now.unavailable` text reads exactly: "Win Now can't model this league yet. Its starting lineup uses K, DL, LB, DB, IDP_FLEX (8 of 15 starting slots), and season projections cover QB, RB, WR and TE only. Kicker and IDP projections are not supported, so standings and trade search stay off for this league." No standings card, no priority buttons, no "Find Win Now trades". **Fail** if it still reads "Unsupported roster slots", omits any of K/DL/LB/DB/IDP_FLEX or "8 of 15", or takes ~10 s.
2. Same screen → tap "Refresh season projections". **Expect:** same sentence, again within ~2 s (a second `Loading season projections…` flicker at most).
3. Trades tab → "Win Now" entry → same screen. **Expect:** identical sentence (same route, same body).
4. Render logs (Dashboard → service → Logs, filter `season-projections`): `GET /api/league/season-projections?league_id=1312140920132497408` → 200, body ≈ 300 bytes; **no** `projections/nfl/2026/<week>` burst and no `matchups/<week>` calls in the seconds before it. **Fail** on any `/projections/` line tied to that request.
5. Switch active league to **Lakeview** (`1312076055586050048`) → League → "Season projections & Win Now". **Expect:** anything *except* the K/IDP sentence — today either the standings card, "Unknown starter availability:1:1", or the "Current-week play may have started…" text while week games are live. **Fail** if the slot sentence appears on Lakeview.
6. Web: sign in at the Render site → Win Now view (`#view-win-now`, "Season projections & Win Now" heading) with FFV3 active. **Expect:** the same sentence as step 1 under the "Refresh season projections" button; with Lakeview active, expect the step-5 behaviour.
7. (Regression) Any offense-only league with ≤12 starters that showed standings before this deploy still shows standings after it.

## BLOCKED
- None. The web view was verified by code-walk rather than against a local Flask server because the diff contains no web change and the route contract is covered by `test_projection_route_returns_slot_refusal_message_verbatim`.
