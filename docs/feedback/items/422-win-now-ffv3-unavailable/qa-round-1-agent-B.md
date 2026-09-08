# QA round 1 — agent B — 2026-09-08

## Summary: PASS (0 blocking findings; 2 minor observations, no code change requested)

Independent verification of the G-422 backend fix (`git diff 8bd536df..da1abb21`). Every PRD §5 defect test is proven RED on the pre-fix `win_now_service.py` and GREEN on the build tip; the fixture is byte-identical to the live FFV3 league; the early gate runs after `missing_scoring_settings` and before any `/matchups/` or `/projections/` fetch; the reason string, the simulator backstop, the route contract and both clients are untouched. Nothing was fixed or committed by this agent.

## Environment

- Worktree: detached at build tip `da1abb21` (`G-422 PRD: slot-count wording amended to match the built contract`); base `8bd536df`. `git status` clean before and after the RED/GREEN swap (blob check: pre-fix `09d7aa64` = `8bd536df:backend/win_now_service.py`; restored `9ced93de` = `da1abb21:…`).
- Python 3.14.4 (pytest via `python3 -m pytest`), Node v24.14.1, `mobile/node_modules` present in-worktree.
- DB: scratch SQLite only; `data/trade_finder.db*` removed before every pytest invocation. No production DB, no `DATABASE_URL`. Network use: two read-only GETs to Sleeper's public league endpoints (fixture-realism check only).
- Flags as checked in (`config/features.json`): `outlook.season_projections` true, `trades.win_now` true, `outlook.championship_probabilities` true. Not changed.
- No simulator, no Maestro (D-056).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| `pytest backend/tests/test_win_now_service.py backend/tests/test_win_now_api.py -q` | PASS | `93 passed in 2.32s` |
| PRD §5 `test_ffv3_active_kicker_idp_slots_refused_before_any_projection_fetch` | PASS | RED on `8bd536df`: `Failed: DID NOT RAISE <class 'backend.win_now_service.Unavailable'>` → GREEN on `da1abb21` |
| PRD §5 `test_ffv3_load_bundle_refusal_is_the_slot_reason_not_a_forecast_reason` | PASS | RED on `8bd536df`: `AssertionError: assert 'missing_forecast_week:1' == 'unsupported_roster_slots'` (the pre-fix reason can only arise after `_forecast_batch` ran, i.e. after the projection burst) → GREEN |
| PRD §5 `test_unsupported_slots_message_names_distinct_slots_in_roster_order` ("5 of 6" as amended) | PASS | RED on `8bd536df`: `AttributeError: module 'backend.win_now_service' has no attribute 'unsupported_slots_message'` → GREEN |
| PRD §5 `test_offense_only_lakeview_slots_pass_the_slot_gate` (over-refusal guard) | PASS | GREEN on both `8bd536df` and `da1abb21`, exactly as the PRD states ("GREEN before and after"). Not a defect test; not counted as a RED failure. |
| PRD §5 `test_win_now_api.py::test_projection_route_returns_slot_refusal_message_verbatim` | PASS | RED on `8bd536df`: `AttributeError … no attribute 'unsupported_slots_message'` → GREEN. RED/GREEN summary lines: `4 failed, 1 passed in 0.97s` → `5 passed in 0.76s` |
| Fixture realism — `ffv3_source_fixture()` vs live `GET /v1/league/1312140920132497408` (2026-09-08) | PASS | `roster_positions` list equal (36 entries, 15 active); scoring key set equal (55 keys) **and every coefficient value equal** (drift dict empty); all 10 pinned `settings` equal; live `status=in_season`, `season=2026`, `total_rosters=12`. Lakeview fixture list equals live `1312076055586050048` `roster_positions` (24 entries, 10 active incl. `SUPER_FLEX`). |
| Message text byte-for-byte = PRD §3(1) copy | PASS | `unsupported_slots_message(FFV3 slots) == <PRD sentence>` → `True` (266 bytes). Serialised `unavailable` body ≈ 340 bytes (was 98). |
| >12-slot offense-only sentence | PASS | 13 offense slots → `Win Now can't model this league yet. It starts 13 players and season projections support at most 12 starting slots.`; contains no "IDP". 12 offense slots → passes the gate. |
| Early gate ordering (code-walk, see below) | PASS | At refusal the recording stub had fetched exactly `[…/league/<id>, …/rosters, …/users]` — zero `/matchups/`, zero `/projections/`. |
| Lakeview-shaped leagues pass unchanged | PASS | `load_league` returns 10 `roster_slots`, buyer roster 1, 14 `/matchups/` fetches proceed as before. |
| `roster_positions` missing / `[]` / bench-only | PASS (unchanged) | All four produce `load_league OK slots=[]` on the build tip — same as pre-fix; the simulator backstop (`season_simulator.py:55-56`, `not slots`) still refuses at simulation time. No league that used to pass `load_league` is newly refused. |
| Import cycle `win_now_service` ↔ `season_simulator` | PASS | `season_simulator.py:18` imports only `season_forecasts`; `git grep` shows no reverse import of `win_now*` from `season_simulator.py`/`season_forecasts.py`; both import orders load cleanly. |
| Simulator backstop untouched | PASS | `git diff --stat 8bd536df..da1abb21 -- backend/season_simulator.py backend/season_forecasts.py backend/win_now_store.py backend/win_now_api.py web mobile` is empty. |
| Route passes `message` verbatim | PASS | `win_now_api.py:48-49` (`unavailable`) / `:58-59` (`guarded`) unchanged; route test above. |
| Store / job lifecycle unchanged | PASS | `win_now_store.py` untouched; `save_projection` (`win_now_service.py:309`) is only reached after a successful simulation, so the refusal writes no snapshot row. `_fetch` caches the league meta 30 s (`:93-100`) exactly as before the fix — not a new cache. |
| `cd mobile && npx tsc --noEmit` | PASS | exit 0 (regression only — no mobile diff) |
| `mobile/tests/check-*.js` (all 98) | PASS | 0 failed; `check-win-now.js`: `Win Now: 28 checks passed` |
| `mobile/scripts/testid-lint.sh` | PASS | `testid-lint OK` |
| `pytest backend/tests -q` (full suite) | PASS | `5872 passed, 1 skipped in 1466.55s (0:24:26)`, exit 0, zero `FAILED`/`ERROR` lines — the expected ~5872/1 exactly. Started 15:03 in the foreground; the harness backgrounded it at the 600 s ceiling; result read from the output file (slow because two sibling QA suites ran concurrently) |
| Web `/win-now` runtime check against local Flask | NOT RUN (code-walk instead) | Group is not web-touching (no `web/` diff). Code-walk: `web/js/win-now.js:79` calls `/api/league/season-projections`; `:231` renders `baseline.message` verbatim for `status === 'unavailable'`. The route test proves the body. |

## Code-walk proof (file:line on `da1abb21`)

- **Import.** `backend/win_now_service.py:24` `from .season_simulator import SLOT_POSITIONS` at module level. `season_simulator.py:18` is its only intra-package import (`season_forecasts`), which `win_now_service.py:23` already imported — no cycle. The lazy `from .season_simulator import simulate_season` inside `load_bundle` (`:240`) is unchanged, so tests that monkeypatch `simulate_season` keep working.
- **Helper.** `:42-61` `unsupported_slots_message`: distinct unsupported names in roster order (`:49-52`), count = number of unsupported *slots* (`:55`), total = `len(slots)`; the K/IDP sentence at `:56-59`; the >12 sentence at `:60-61`. Verified byte-equal to PRD §3(1).
- **Gate placement.** `:135` `missing_scoring_settings` → `:136-137` comment → `:138` the `slots` comprehension (moved up from old `:165`; no duplicate remains — `:195` reads the same `slots`) → `:139-140` `if len(slots) > 12 or any(s not in SLOT_POSITIONS for s in slots): raise Unavailable("unsupported_roster_slots", unsupported_slots_message(slots))`. Everything that costs a fetch comes later: the standings loop `:141-151`, the `/matchups/{week}` loop `:178-192` (`_fetch` at `:180`), and `_forecast_batch` (`:210`, called from `load_bundle:245`). Fetches made before the gate: `league` `:120`, `/rosters` `:121`, `/users` `:122` — matches the recorded `calls` at refusal.
- **Condition parity with the backstop.** `season_simulator.py:54-56`: `if not slots or len(slots) > 12 or any(s not in SLOT_POSITIONS for s in slots)`. The early gate deliberately omits `not slots` (empty lineup still reaches the simulator, as before). `SLOT_POSITIONS` (`:21-23`) and `BENCH_SLOTS` (`:24`) unchanged.
- **When the gate does *not* fire.** Any active slot set ⊆ {QB, RB, WR, TE, FLEX, SUPER_FLEX, REC_FLEX, WRRB_FLEX} with ≤12 entries (Lakeview: 10) — control falls through to `:141` exactly as pre-fix. Also does not fire before `platform_unsupported` `:117`, `league_unavailable` `:123`, `season_not_active` `:125`, `best_ball_unsupported` `:128`, `custom_start_week_unsupported` `:130`, `league_membership_unavailable` `:133`, `missing_scoring_settings` `:135` — those keep precedence.
- **Bench filtering.** `:138` drops `BN`, `IR`, `TAXI`, `RESERVE`. Sleeper's live FFV3/Lakeview `roster_positions` contain only `BN` as the non-starting token (IR/taxi are `settings.reserve_slots`/`taxi_slots`, not list entries). The simulator's `BENCH_SLOTS` (`:24`) is `{BN, IR, TAXI}`; the extra `RESERVE` in the service filter is harmless and pre-existing (same tuple was at old `:165`). Case-sensitive: a lowercase `bn` would be treated as an unsupported starting slot — Sleeper emits upper-case tokens, so not a real-data risk.
- **Reason string.** `unsupported_roster_slots` unchanged at `:140`, `season_simulator.py:56` and `:133`, `docs/api-reference.md:1005`.
- **Serialisation and rendering.** `win_now_api.py:48-49` builds `{status:"unavailable", reason, message}` from `exc.reason`/`exc.message`; `:58-59` catches `service.Unavailable`; `:83` is the `load_bundle` call on `GET /api/league/season-projections`. `mobile/src/screens/WinNowScreen.tsx:195` renders `baseline.message` under `win-now.unavailable`; `web/js/win-now.js:231` does the same. Neither file is in the diff.
- **Docs.** `docs/api-reference.md:1005` gained the one sentence the PRD §4 asked for (K/DEF/IDP or >12 active → `unsupported_roster_slots` before any standings/projection fetch, slot names in `message`).

## Findings

No blocking or major findings.

### O-1 (minor, observation — outside PRD §3 scope): the specific message does not travel on the search-job path
- Severity: minor
- Path: `POST /api/win-now/search` creates a job **without** loading the bundle (`win_now_api.py:103-125`); the worker's `run_search` → `load_bundle` raises the new `Unavailable("unsupported_roster_slots", <sentence>)`, but `process_pending` persists only `exc.reason` (`win_now_service.py:571`, `finish_job(reason=…)`), and the poll route re-derives `message` from the reason (`win_now_api.py:157`) → a client polling that job would read the old "Unsupported roster slots".
- Reachability: both clients gate the search button on `baseline.status === 'available'` (`WinNowScreen.tsx:31-34`, `win-now.js:233`), so an FFV3 user cannot reach it from the UI; only a direct API call or a client holding a stale "available" baseline could. The PRD scopes the fix to `GET /api/league/season-projections` (§3, §8), and the win-now jobs table has no message column (`win_now_store.py:144-155`) — carrying it would be a schema/contract change, i.e. out of fast-track scope. Recorded for the operator; no change requested for G-422.
- Not a masking risk: a failed job row is per-search, never re-read as a cached refusal (`pending_jobs` selects `queued` only, `win_now_store.py:105-110`; 7-day prune `:88-90`), and the projections route recomputes from source every call.

### O-2 (minor, copy): a `DEF` starting slot gets the "Kicker and IDP projections are not supported" sentence
- Severity: minor
- `unsupported_slots_message(["QB","RB","WR","TE","DEF"])` → "…uses DEF (1 of 5 starting slots)… Kicker and IDP projections are not supported…". The slot is named correctly and the refusal is right (`DEF ∉ SLOT_POSITIONS`); only the explanatory clause omits team defense. `docs/api-reference.md:1005` does say "K/DEF/IDP". The PRD copy is what shipped, so this is a wording note for the operator's copy sign-off (PRD §7.2), not a defect against the spec.

### Suspicion noted (not a finding): stderr noise in the full-suite log
The full-suite output file contains `sqlite3.OperationalError: no such table: user_events` from a `receipts_grade_run` daily-tick insert. It is emitted by a background tick thread during another test module's setup, is pre-existing (unrelated to any file in this diff), and does not fail a test; agent A's log should show the same line if so.

## Full suite

`python3 -m pytest backend/tests -q -p no:cacheprovider` on `da1abb21`, scratch SQLite, output at `scratchpad/full-suite-agent-B.txt`:

```
5872 passed, 1 skipped in 1466.55s (0:24:26)
EXIT=0
```

`grep -cE "^(FAILED|ERROR) "` → 0. The 37 `no such table: user_events` stderr lines are background-tick noise (see the suspicion above), not test failures.

## TestFlight checklist (operator-run)

Run after Render is LIVE on the merge sha. Existing binary 1.17.1 (149) is sufficient — no client change shipped. Sign in as mattmurf77.

1. **Trades tab → league switcher → select "Fantasy Football Version 3"** (`1312140920132497408`). Expect the league name in the header.
2. **League tab → "Season projections & Win Now"** (or Trades → "Win Now"). Start a stopwatch on tap. Expect the `WinNowScreen` to show, under the "Refresh season projections" button, within ~2 s: "Win Now can't model this league yet. Its starting lineup uses K, DL, LB, DB, IDP_FLEX (8 of 15 starting slots), and season projections cover QB, RB, WR and TE only. Kicker and IDP projections are not supported, so standings and trade search stay off for this league." **Fail** if the text is "Unsupported roster slots", if it names anything other than those five slots, if the count is not "8 of 15", or if it takes ≈10 s.
3. Same screen: expect **no** "Projected standings" card, **no** objective/priority buttons, **no** "Find Win Now trades" button, no stale banner.
4. **Tap "Refresh season projections"** → same sentence again, again within ~2 s (the label flips to "Loading season projections…" and back).
5. **Render logs** (operator): `GET /api/league/season-projections?league_id=1312140920132497408` → 200, body ≈ 340 bytes; there must be **no** `projections/nfl/2026/<week>` fetch burst in the seconds before it (before the fix: 17 of them, ~10 s).
6. **Switch to "Lakeview League"** (`1312076055586050048`) → League → "Season projections & Win Now". Expect anything **except** the K/IDP sentence: today either projected standings, or a transient reason ("Unknown starter availability…" / "Current-week play may have started…") in the same unavailable slot. **Fail** if the K/IDP or the "at most 12 starting slots" sentence appears for Lakeview.
7. **Web** (`https://<render host>/` → sign in → `Win Now` view, `#view-win-now`): with FFV3 active, expect the identical sentence as step 2 in the paragraph under "Refresh season projections"; with Lakeview active, expect step 6's behavior. **Fail** on "Unsupported roster slots".
8. Optional regression: on a league that *was* working before the deploy, confirm standings still render (proves the gate does not over-refuse offense-only lineups).
