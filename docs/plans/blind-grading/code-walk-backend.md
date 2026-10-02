# Code-walk — Calibration backend (P2: routes, gate, flags)

**Date:** 2026-10-02 · **Branch:** `feat/blind-grading-p2` · Companion: [scope.md §3](scope.md#3-evidence-scope) · [specs.md §5.2](specs.md#52-p2--routes--flags--route-tests) · [lld.md §7–§8.1](lld.md#7-routes-backendserverpy)

The D-056 replacement for a simulator capture: a file:line trace of what the code does, for the
three paths P2 owns, plus the three claims scope §3 asks the backend code-walk to carry. Line
numbers are from this branch at P2's commit (`backend/server.py` new section `:26935-27128`);
they drift once P1/P3/P4 merge — anchor on the quoted code. Citations into P1's bodies are
marked **(verify after P1 merge)**: the skeleton in this worktree still raises
`NotImplementedError`, so those are read from [lld.md](lld.md), not from code.

Every path below is also pinned by a test; the test name is given with each step.

## Contents

1. [Path A — the gate: flag off · non-tester · tester](#path-a--the-gate)
2. [Path B — POST → background build → poll](#path-b--post--background-build--poll)
3. [Path C — the `draft.tab` flip](#path-c--the-drafttab-flip)
4. [Scope §3 claims](#scope-3-claims)
5. [Sabotage log](#sabotage-log)
6. [Deviations from the LLD text](#deviations-from-the-lld-text)

---

## Path A — the gate

All five user routes stack `@_grading_gate` directly under `@app.route`, above the verified
gate: `server.py:27038-27040` (POST sessions), `:27070-27072` (current), `:27082-27084` (next),
`:27094-27096` (answer), `:27106-27108` (results). Flask registers the outermost wrapper, so
`_grading_gate._wrapper` (`:26986-26993`) runs first on every request.

**Step 1 — session lookup, no 401.** `_wrapper` calls `_get_session(request.headers.get("X-Session-Token", ""))`
(`:26988`). `_get_session` (`:2491-2505`) returns `None` for an empty token (`:2497-2498`), for an
unknown in-memory token when `auth.persistent_sessions` is off (`:2503-2504`), or when the durable
store has no row (`:2505`). `None` ⇒ `jsonify({"error": "not_found"}), 404` (`:26989-26991`). The
route body — and therefore `_require_session`'s 401 (`:2558`) — is never reached.
*Test:* `test_blind_grading_routes.py::test_no_session_404` (no token and an unknown token, all five routes).

**Step 2 — `_grading_flag_for_caller(sess)`** (`:26955-26978`), evaluated before the allowlist (`:26989`, short-circuit `or`):
- `is_enabled("grading.blind")` (`:26962`) is the same import the rest of `server.py` uses
  (`:265`). It reads `config/features.json` → `false` (`config/features.json:270`), so in the
  shipped posture this branch is dead and the overlay decides.
- Otherwise the units are `device:<X-Device-Id>` (only when the header is present, `:26966-26967`)
  and the account unit `sess["user_id"]` (`:26968`) — the same two identities
  `feature_flags_route` resolves for the client (`:26266`, `:26284-26287`). For each,
  `experiments.resolve_for_unit(unit, None)` (`:26972`; `experiments.py:320-342`) returns the
  running experiments' `client_config`; any config whose `flags["grading.blind"] is True` wins
  (`:26973-26975`). This is the server-side twin of the merge `mobile/src/api/flags.ts:53-58`
  applies, so tab presence and route access agree.
- Any exception ⇒ `False` (`:26976-26977`). Fail closed.

*Tests:* `::test_routes_404_without_flag_for_caller` (flag off, no overlay, allowlisted ⇒ 404 ×5),
`::test_account_overlay_resolves_flag_for_caller` (overlay for the session's account unit ⇒ 200;
overlay for another account ⇒ 404), `::test_device_overlay_needs_x_device_id` (overlay for
`device:abc` ⇒ 200 only with `X-Device-Id: abc`).

**Step 3 — `_calibration_allowed(sess)`** (`:26944-26952`): `_load_tester_allowlist()` (`:26949`;
the import at `:26789` → `experiments.load_tester_allowlist`, `experiments.py:120-141`:
`FTF_TESTER_ALLOWLIST` ∪ `config/tester_allowlist.json`), then session `user_id` **or**
`league_user_id` ∈ allowlist (`:26950-26952`) — the `_value_core_live` rule at `:7456-7458`.
False ⇒ the same 404 (`:26989-26991`).
*Tests:* `::test_routes_404_when_not_allowlisted` (flag on, empty allowlist ⇒ 404 ×5);
`::test_calibration_allowed_is_the_single_audience_predicate` (flag on, empty allowlist ⇒ 404;
monkeypatching `server._calibration_allowed` to `lambda s: True` ⇒ 200 — the whole code change
to open Calibration to everyone).

**Step 4 — only now the verified gates.** For a tester whose flag resolves true, `_wrapper` calls
`fn` (`:26992`), which is `_gate_unverified_write._wrapper` (`:2663-2680`) or
`_gate_unverified_read._wrapper` (`:2699-2720`): `_verified_write_denial` / `_verified_read_denial`
(`:2653-2660`, `:2689-2696`) return 403 `verification_required` unless `sess["verified"]` or a
synthetic demo identity. So a non-tester with an unverified session gets **404**, a tester with an
unverified session gets **403**; the existence signal never leaks past the audience.
*Test:* `::test_gate_404_precedes_verification_403` (unverified, not demo: flag off ⇒ 404 on GET
and POST; flag on ⇒ 403 on both). Sabotage-proven: swapping the two decorators on `/current`
turned the 404 case into 403 (see [Sabotage log](#sabotage-log)).

**Three outcomes, summarised:**

| Caller | `_grading_flag_for_caller` | `_calibration_allowed` | Result |
|---|---|---|---|
| Anyone, flag off globally, no overlay (shipped) | False (`:26962`, `:26978`) | not evaluated | 404 (`:26991`) |
| Non-tester inside no overlay — or inside the overlay but off the allowlist | False / True | False (`:26951-26952`) | 404 (`:26991`) |
| Tester: allowlisted **and** in `calibration_rollout` (account or device unit) | True (`:26975`) | True | handler runs (`:26992`); verified gates apply |

`_calibration_allowed` and `_grading_flag_for_caller` are the only two functions in the section
that consult the allowlist or the flag; the five handlers (`:27041-27115`) never do.

## Path B — POST → background build → poll

Context: production is one synchronous gunicorn worker (`render.yaml:16`,
`--workers 1 --timeout 120`), so the 2–12 s value-core build cannot run inline (specs §3.3).

**B1 — request thread, fast half** (`grading_create_session_route`, `:27041-27067`):
1. Gate (Path A), then `_gate_unverified_write`.
2. `_require_initialized_session()` (`:27042` → `:2570-2585`): a valid-but-bare session (no
   `league` / `players` / `trade_svc`) raises `_SessionNotInitialized` (`:2584`), handled as 409
   `session_not_initialized` (`:2304-2308`). *Test:* `::test_create_requires_an_initialized_session`.
3. Body: `request.get_json(silent=True)` (`:27043`); a missing/blank `league_id` or a non-dict body
   ⇒ 400 `invalid_body` (`:27044-27046`). `league_id` ≠ the session's active league ⇒ 400
   `league_not_active` (`:27047-27049`), which keeps `_league_user_id(sess)` (`:2594`) unambiguous.
   *Test:* `::test_create_validates_body_and_active_league`.
4. **Resume short-circuit:** `_blind_grading.current_session(user_id, league_id)["session"]`
   (`:27052`). A `building` or `open` session ⇒ 200 `{"session", "resumed": true}` (`:27053-27054`)
   with no Sleeper helper called — `_value_core_standings`, `_league_lineup_slots` and
   `_sleeper_roster_limit` live only in `_grading_server_inputs` (`:27004-27011`), which only the
   build thread calls (`:27035`). A `failed` session is **not** resumed and falls through to a
   fresh start (`:27053` excludes it). *Tests:* `::test_create_resume_short_circuits_network`
   (parametrised `building` / `open`; every network helper and `start_session` fail the test if
   called), `::test_create_does_not_resume_a_failed_session` (sabotage-proven: dropping the status
   check resumed the failed row).
5. `_blind_grading.start_session(user_id=…, league_user_id=_league_user_id(sess), league_id=…)`
   (`:27055-27056`) — the fast half per the §3.1 contract (`blind_grading.py:54-63`): resume,
   `league_not_synced`, current-arm selection (`needs_fresh_deck`), insert the `building` row. No
   value core, no network **(verify after P1 merge)**. `GradingError` ⇒ `_grading_error`
   (`:27057-27058` → `:26996-26997`: `{"error": code, **detail}, status`).
   *Test:* `::test_grading_errors_map_to_json` (`needs_fresh_deck` 409 with the four detail keys,
   `league_not_synced`, `value_core_failed` 503 — body equality, not just status).
6. If `out["needs_build"]` (`:27060`): `threading.Thread(target=_build_grading_session,
   args=(dict(sess), league_id, session_id), name="grading-build", daemon=True).start()`
   (`:27063-27064`). `dict(sess)` snapshots the request-local `_RequestSession` view
   (`:2508-2543`) so the thread holds plain data, not a request-bound object. When `start_session`
   itself resumed (a race between the two reads), `needs_build` is false and no thread starts.
   *Test:* `::test_create_without_needs_build_starts_no_thread`.
7. Response: `{"session": out["session"], "resumed": out["resumed"]}` with **202** for a new
   session, 200 for a resume (`:27067`). `needs_build` is never sent to the client.
   *Test:* `::test_create_returns_202_and_builds_in_background` asserts 202, the body, that
   `start_session` got exactly `{user_id, league_user_id, league_id}`, and that one daemon
   `grading-build` thread was started.

**B2 — background thread, slow half** (`_build_grading_session`, `:27029-27035`):
1. `_grading_server_inputs(sess, league_id)` (`:27000-27026`) mirrors `_run_value_core_job`'s
   gathering (`:7495-7505`): standings + completed weeks from `_value_core_standings`
   (`:27004`; Sleeper only, fail-soft to `({}, 0)` at `:7462-7476`); lineup slots (`:27005-27008`)
   and roster limit (`:27009-27013`), each wrapped so a Sleeper failure yields `None`;
   untouchables / not-interested from `load_asset_preferences` only when
   `FLAGS.trade_preference_lists` (`:27014-27021`, warning on failure). Packed into the §3.1
   `ServerInputs` (`:27022-27026`; `blind_grading.py:44-51`) — ids stringified, duplicates folded
   by `frozenset`.
2. `_blind_grading.build_session(session_id=…, server=…)` (`:27034-27035`): value core, merge,
   shuffle, cards, then `status` → `open`, or `failed` with `error_json`; **never raises**
   (`blind_grading.py:66-73`) **(verify after P1 merge)**. Nothing in this thread touches the
   response: the 202 has already gone out.
   *Test:* `::test_create_returns_202_and_builds_in_background` runs the `grading-build` thread
   inline (a `Thread` subclass whose `start()` calls `run()` for that name only — the
   `test_players_refresh.py:290` / `test_account_only_harness.py:277` precedent) and asserts
   `build_session` received `session_id` and a `ServerInputs` equal to
   `(("QB","RB","RB","WR","WR","TE","FLEX"), 30, {stubbed standings}, 4, {"4046"}, {"9509"})`,
   with `load_asset_preferences` called once as `(user_id, league_id)`.

**B3 — poll** (`grading_current_session_route`, `:27073-27079`): gate, `_gate_unverified_read`,
`_require_session` (`:27074`), `league_id` required (`:27075-27077`), then
`_blind_grading.current_session(...)` verbatim (`:27078-27079`) — the newest `building` / `open` /
`failed` session (§3.2) **(verify after P1 merge)**. Mobile polls this every 1.5 s while
`status === "building"` (§3.3; P3). The SessionView's `error` carries `value_core_too_few` /
`value_core_failed`, which is why those codes are no longer HTTP errors on POST (specs §3.2
"moved" row). *Integration:* `test_blind_grading_e2e.py::test_no_response_reveals_an_arm_until_results`
POSTs (202 `building`), polls once (the inline thread has already flipped it to `open`), then
grades to completion.

**Grade / results / report** (for completeness; each is gate + one service call + `_grading_error`):
`next` `:27085-27091`, `answer` `:27097-27103` (the raw `request.get_json(silent=True)` reaches
`answer_card` untouched — `None` for a non-JSON body; *test* `::test_answer_passes_raw_body`),
`results` `:27109-27115`. `admin_grading_report_route` (`:27119-27128`) has **no** `_grading_gate`:
`_require_cron_auth()` (`:27122` → `:24339-24358`, `abort(401)` on a mismatch, `abort(503)` when
the secret is unset in prod) is its only check, so the report survives stopping
`calibration_rollout` (prd D4). *Tests:* `::test_admin_report_cron_secret_and_ungated` (401 without
/ wrong header; 200 with the flag off and nobody allowlisted; `since=bad` ⇒ 400 `invalid_since`),
`test_blind_grading_e2e.py::test_stopping_the_overlay_kills_routes_not_the_report`.

## Path C — the `draft.tab` flip

Operator decision 2026-10-02: Calibration takes the third tab slot; the Draft tab leaves the bar
for everyone; its code is kept.

| Where | Was | Now |
|---|---|---|
| `config/features.json:230` | `"draft.tab": true` | `"draft.tab": false`; `_comment_draft_tab` (`:229`) gains the dated OFF sentence from lld §8.1 |
| `backend/tests/fixtures/flags/release.json:203` | `true` | `false`, comment mirrored (`:202`) — `test_seed_ui_test_db.py::test_release_flags_mirror_features_json` enforces the mirror |
| `…/profiles-on.json:200`, `…/onboarding-v2.json:200` | `true` | `false` |
| `…/release-300.json:173`, `…/release-espn-send-off.json:159` | `true` | `false` |
| `…/all-on.json` | carries no `draft.tab` | unchanged |
| `backend/tests/fixtures/profiles/draft.json:22`, `draft-pre.json:22` | `"draft.tab": true` | **unchanged** — draft-room QA worlds |
| `backend/feature_flags.py:794` | `"draft.tab"` in `FLAG_KEYS` | unchanged (`DEFAULT_FLAGS` is all-False, `:1177`) |
| `mobile/src/navigation/TabNav.tsx:717` | `useFeatureFlags.getState().flags['draft.tab']` at mount | **unchanged** (P3 adds the Calibration branch in front of it) |

So the flip is data-only: the client predicate test `test_rookie_ranks_editable.py:268-280`
(`test_the_tab_is_gated_on_the_flag_and_nothing_else`) still passes unchanged, and `test_draft_tab_flag_is_mirrored_and_ships_off` (`:248-259`, renamed from
`…_ships_on`) now asserts `features["draft.tab"] is False` with the release mirror. The new
`test_blind_grading_routes.py::test_draft_tab_off_wherever_it_is_set` reads `false` from
`config/features.json` and all five fixtures and `true` from both draft profiles.

Rollback is the same edit in reverse plus `POST /api/feature-flags/reload`; the Draft Room stays
reachable via League › Rookie draft (`draft.room`) and the Acquire Draft chip either way.

**`grading.blind` (the companion flag):** registered at `feature_flags.py:1174` (after
`trade.value_core`, with the lld §8.1 comment); `false` in `config/features.json:270`,
`release.json:238`, `profiles-on.json:232`, `onboarding-v2.json:232`; absent from `all-on.json`,
`release-300.json` and `release-espn-send-off.json`, which carry no `trade.value_core` either.
`test_entitlements.py::test_features_json_keys_known` proves the key is registered, and
`test_seed_ui_test_db.py::test_profiles_on_flags_turn_on_public_pages_only` is why `profiles-on`
had to receive the key (it asserts `set(release) == set(profiles_on)`).
*Test:* `::test_flag_registered_default_off_and_mirrored`.

## Scope §3 claims

**Claim 1 — flag false or `_calibration_allowed` false ⇒ 404 before any other check, including the
verified gate.** Path A, steps 1–4: `_grading_gate` is outermost on all five routes
(`:27039`, `:27071`, `:27083`, `:27095`, `:27107`); its 404 at `:26991` precedes the verified
denials (`:2660`, `:2696`) and every handler's `_require_*session` call. Pinned by
`test_gate_404_precedes_verification_403`, `test_routes_404_without_flag_for_caller`,
`test_routes_404_when_not_allowlisted`, `test_no_session_404`.

**Claim 2 — no grading path writes `deck_impressions`, `trade_impressions`, `trade_decisions`,
`swipe_decisions` or `trade_service._trade_cards`.** Route layer: the section `:26935-27128`
references none of `trade_service`, `_trade_cards`, `log_*_impressions`, `record_event`,
`deck_*` or `swipe*` (`sed -n '26935,27130p' backend/server.py | grep -nE "trade_service|_trade_cards|impression|record_event|swipe|deck_"`
matches only the banner comment at `:26939`). The only module the section imports is
`backend.blind_grading` (`:26941`), whose contract (`blind_grading.py:1-11`) forbids importing
`backend.server` / `backend.tools`, and whose writes are limited to `grading_sessions` /
`grading_cards` (lld §4 `insert_grading_session`, §6.5) **(verify after P1 merge; P1's
`test_create_session_writes_no_engine_tables` and `test_module_never_imports_server_or_tools`
pin it from the service side)**. End-to-end: `test_blind_grading_e2e.py::test_grading_leaves_deck_and_swipes_untouched`
counts the four tables and the session's `trade_svc._trade_cards` across a whole session.

**Claim 3 — only `results` and `report` read `grading_cards.arms_json`.** The server section never
names `arms_json`; the route handlers pass through `next_card` (`:27088`), `results` (`:27112`)
and `report` (`:27124`) verbatim. In the service, `load_next_grading_card` returns
`{card_id, position, trade_json}` only (lld §4 `:144-146`), and `arms_json` is read by
`load_grading_cards` / `load_grading_report_rows` for `arm_summaries` in `results` and `report`
(lld §6.7) **(verify after P1 merge; P1's
`test_insert_load_round_trip_and_next_card_never_returns_arms` pins the DB helper)**. Note the
unrelated `bakeoff_runs.arms_json` (`database.py:1193`, written at `server.py:15339`) — a
different table. End-to-end: `test_blind_grading_e2e.py::test_no_response_reveals_an_arm_until_results`
deep-walks every body before `results` for the forbidden keys/values (`arm`, `arms`, `model_arm`,
`reasons`, `source`, `impression_id`, `"current"`, `"value_core"`, `vc_*`, …).

## Sabotage log

Standing repo practice (`backend/tests/CLAUDE.md` § Conventions): each new behavioural test is
shown RED against a named sabotage, then green on revert. Both reverted; `git diff --stat` on
`server.py` returned to the section's insertions only.

| # | Sabotage (in `server.py`) | Test that went RED | Observed |
|---|---|---|---|
| 1 | Swapped `@_grading_gate` and `@_gate_unverified_read` on `/api/grading/sessions/current` | `test_gate_404_precedes_verification_403` | `(403, {'error': 'verification_required'}) == (404, {'error': 'not_found'})` — the unverified non-tester saw the existence signal |
| 2 | `if current is not None:` (dropped the `status in ("building", "open")` check at `:27053`) | `test_create_does_not_resume_a_failed_session` | the `failed` SessionView came back as `resumed: true` |

## Deviations from the LLD text

- **`create_session` → `start_session` + `build_session`, 201 → 202, thread.** specs §3.3 (lead change) wins over lld §7's listing; the route keeps lld §7's `current_session` resume read in front of `start_session`, adding only the `status in ("building", "open")` filter §3.2 requires (a `failed` session starts fresh).
- **Thread name.** `threading.Thread(..., name="grading-build", daemon=True)` — the name is the seam the tests use to run the build inline without touching any other thread (same pattern as `session-init-bg-writes`). Not in the LLD text; no behavioural effect.
- **`dict(sess)`** is passed to the thread rather than the `_RequestSession` view, so the thread never holds a request-scoped object. `_grading_server_inputs` reads only `sess.get("league")` and `sess["user_id"]`, which the snapshot carries.
- **Docstring line citations** inside the new functions (`:7456-7458`, `:26252-26290`, `:26792-26809`) were replaced by the function names they pointed at (`_value_core_live`, `feature_flags_route`, `_test_users_denied`) — the numbers were already stale on this branch.
- **Fixtures.** `profiles-on.json` / `onboarding-v2.json` received `_comment_grading_blind` + `grading.blind` (lld §8.1 "lines", and `test_profiles_on_flags_turn_on_public_pages_only` requires key parity with `release.json`); their `_comment_draft_tab` text was left alone, as §8.1 scopes the comment edit to `features.json` / `release.json`.
- **E2E clock.** `test_blind_grading_e2e.py` serves the seeded deck one day before the **real** clock rather than the fixed `NOW` of the §5 common seed: the route does not inject `now`, so a fixed date would make the file fail with `needs_fresh_deck` after 2026-10-09.
