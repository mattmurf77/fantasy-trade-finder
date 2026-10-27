# Feature Scope — Platform sign-in (proof-based ESPN/MFL team claim)

**Date:** 2026-10-26 (head-eng conditions and analytics grants folded in 2026-10-27)
**Entry point:** direct ask — platforms-eng's ESPN/MFL sign-in design (D1–D10, §2–§4); onboarding-eng's four review amendments (2026-10-26); head-eng's security review, "APPROVED to build, with conditions" (2026-10-27); analytics-lead's ESPN/MFL sign-in grants (2026-10-26)
**Builder:** platforms-eng backend worker, branch `feat/platform-sign-in` (pushed for head-eng's read; no PR; merge waits for onboarding-eng's mint review and head-eng's diff check)
**Operator sign-off on waivers:** pending — the deferrals below are surfaced in the build report to platforms-eng → head-eng

**What changes:** the team-claim step of the sessionless `POST /api/entry/platform` stops minting a claim-only `entry:*` session. It now proves ownership (ESPN: cookie read, anonymous read refused, pair-binding control refused, owner SWID matches; MFL: login + myleagues lists the claimed franchise) and signs into an account anchored on the proven identity — a verified, persisted `acct_*` session (or the bound Sleeper user's). Unprovable claims are refused with a readable `message`. Failed proofs are rate-limited; every claim writes one `PLATFORM-SIGNIN` audit line. Contract: [api-reference § `/api/entry/platform`](../../api-reference.md); ESPN reads: [integrations/espn.md §2.5](../../integrations/espn.md); MFL password handling: [integrations/mfl.md §2](../../integrations/mfl.md).

**Ships dark (D10):** no new flag. The route already sits behind `landing.platform_options` (operator ask 12 turns it off now) plus `espn.link` / `mfl.link`. This build flips nothing.

**Disconnect semantics (head-eng condition 6, for legal R28.15 W2 via head-bizops):** disconnecting an ESPN or MFL league in Settings (`DELETE /api/espn/link`, `DELETE /api/mfl/auth-link`) removes the import credential but **keeps** the sign-in identity (`linked_identities`) until account deletion. Those routes are unchanged; this is today's behaviour, now pinned by tests.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it** — the client already fires `signin_attempted` / `signin_succeeded` / `signin_failed` with `method` = `espn` / `mfl` around the mint (`mobile/src/api/platformEntry.ts`, `entryPlatformMint`). They answer "how many platform sign-ins start, succeed and fail, and why": `signin_failed.error_code` carries the response's `error`. Server side, `obs.api_events` now records `user` = `acct_*` for these sessions instead of an `entry:espn:<SWID>` id (the D2 log-leak fix). The `PLATFORM-SIGNIN` line is an operational audit log, not an analytics event.

  **analytics-lead grants (2026-10-26), both exercised in this build:**
  1. **`signin_failed.error_code` gains `proof_required`, `proof_unavailable`, `platform_identity_in_use`, `too_many_attempts`** — value-only, no registry change, no client change (the client passes the server's `error` through). Condition met: the dated value-only addendum [`docs/business/analytics/2026-10-27-signin-failed-error-codes.md`](../../business/analytics/2026-10-27-signin-failed-error-codes.md) lists the closed domain for `method` espn/mfl — every refusal code the route can return, plus the client's `timeout` / `http_<status>` / `unknown` and the sign-in screen's `owner_resolve_failed` / `platform_unsupported` / `smart_start_invalid`. Codes only, never an identity value. The 2026-08-26 entry-method addendum points to it.
  2. **`espn` joins `prepared_trade_cohort.VERIFIED`.** **E1:** the value is defined once, `accounts.VERIFIED_VIA_ESPN = "espn"` (next to `VERIFIED_VIA_MFL = "mfl_login"`), and the mint uses both constants; `test_prepared_trade_cohort.py::test_platform_sign_in_verified_via_values_are_cohort_eligible` pins both in `VERIFIED` (sabotage: cohort literal → `espn_login` → red). **E2:** the prepared-inventory flag is untouched (`prepared_trade_inventory_enabled` stays 0; DEC-9's byte budget is unaffected).
- [ ] **(c) WAIVED** — n/a.

## 2. Schema & flag scope

- New/changed tables or columns: **none (no DDL).** `linked_identities.provider` gains `espn` / `mfl` (subject = canonical SWID braced + upper-cased / MFL username trimmed + lower-cased, both via `accounts.platform_subject`) and `verified_via` (users, sessions) gains `espn` (`mfl_login` already existed). Neither column has a CHECK constraint (design D3). → `docs/data-dictionary.md` updated.
- New/changed feature flags: **`espn.signin`** (new, ships `true`) — the ESPN sign-in kill switch; see the addendum below. Otherwise gated by the existing `landing.platform_options` + `espn.link` / `mfl.link` (actions also by `espn.league_picker` / `mfl.auth_link`). Rollback levers: `espn.signin` → false (ESPN sign-in only), `landing.platform_options` → false (the whole entry surface); both deploy-free and hot-reloadable.
- New env vars / `model_config` keys: **none.** The D7 limits are module constants in `backend/server.py` (`_SIGNIN_IP_MAX_FAILURES` = 300 / `_SIGNIN_IP_WINDOW_S` = 600, `_SIGNIN_SUBJECT_MAX_FAILURES` = 5 / `_SIGNIN_SUBJECT_WINDOW_S` = 900 — per (subject, client IP) since the 2026-10-27 lockout fix, `_SIGNIN_SUBJECT_CEILING_FAILURES` = 30 / `_SIGNIN_SUBJECT_CEILING_WINDOW_S` = 3600 — per subject across IPs, added by that fix, `_SIGNIN_TRUSTED_PROXY_HOPS` = 1); state is in-process and resets on deploy (one gunicorn worker × 4 threads, lock-guarded).
- Code-level vocabulary: `accounts.PLATFORM_PROVIDERS = ("espn", "mfl")`, allowed by `find_or_create_account`; `accounts.PROVIDERS` stays `("apple", "google")` and keeps meaning the `/api/auth/*` issuers. `accounts.VERIFIED_VIA_ESPN` / `VERIFIED_VIA_MFL`. `espn_service.swid_identity` (the one SWID identity form). `prepared_trade_cohort.VERIFIED` gains `"espn"`.

## 3. Evidence scope

D-056: no Maestro flows and no simulator captures — that tooling is retired, so those rows do not exist here.

- [x] **Structural guard:** `mobile/tests/check-landing-platform-options.js` updated — V2.6 now pins "the mint never creates an `entry:*` id" and "both claims prove ownership, then mint via `_platform_sign_in`"; the V2.1 action-before-mint and store-nothing assertions key on `_platform_sign_in(`. (Still `npm run`-only; the check suites gate nothing in CI yet.)
- [x] **Unit tests:** `backend/tests/test_platform_sign_in.py` (new, 86 tests), `backend/tests/test_entry_platform_route.py` (claim-only `entry:*` assertions rewritten for proven mints; 27 tests), `backend/tests/test_prepared_trade_cohort.py` (+1 pin). The condition-1 and condition-3 tests run the **real** `espn_service.fetch_league`, `mfl_service.login` and `fetch_my_leagues` over a fake urllib opener, so the real `obs.api_events` capture and error mapping are exercised. **Private MFL leagues** (platforms-eng follow-up): the MFL claim logs in first and reads the bundle with the login's cookie — `test_mfl_private_league_bundle_is_read_with_the_login_cookie`, `test_mfl_private_league_unreadable_by_this_login_is_wrong_account`, `test_mfl_bad_login_is_refused_before_any_bundle_fetch`, `test_c7_refusal_mfl_proof_required_makes_zero_mfl_calls` (sabotage: bundle fetched without the cookie → the two private-league tests red). `test_entry_platform_route.py`'s fixture now denies live `mfl.login` / `fetch_my_leagues` by default.

### head-eng's conditions → tests (each has a recorded sabotage in the `living-memory/TEST_LEDGER.md` 2026-10-26 "Platform sign-in" entry)

| # | Condition | How it's met | Tests |
|---|---|---|---|
| 1 | No secret reaches a log, an event or an error body | `entry_platform` catches any unexpected exception, logs its **type and code frames only**, and answers 500 `internal_error` with a fixed message; the proof reads log exception types only; refusal bodies are fixed strings; the audit line carries no ids; session-build failures answer a fixed message. Exception messages never embed request values | `test_c1_markers_never_leak_through_any_outcome` — marker `espn_s2` / SWIDs / MFL username / password through proven, every refusal, both 429s, the two actions, a forced DB error (SQL params carry the SWID), forced exceptions inside the ESPN control read, the ESPN cookie read and the MFL login, and the #279 AUTH-DENY handler; asserts no marker in caplog (all loggers), any response body or header, stdout/stderr, or `obs.api_events` rows; and in the DB a SWID / username only in `linked_identities.provider_subject`, `espn_credentials.swid`, `mfl_credentials.mfl_username`, never an s2 / password / cookie |
| 2 | One canonical SWID form | `espn_service.swid_identity` (braced, upper, trimmed) via `accounts.platform_subject`, used for the claimed SWID, every `owner_swid`, the control choice, `linked_identities.provider_subject` (also normalised inside `find_or_create_account` / `get_account_by_identity`), and the D6 check, which normalises the stored `espn_credentials.swid` (stored as captured today) in Python on both sides | `test_c2_swid_normaliser_folds_braces_case_and_whitespace`, `test_c2_formatting_cannot_dodge_identity_exists`, `test_c2_formatting_cannot_dodge_the_d6_conflict` (×2) |
| 3 | Steps 3 and 4 fail closed | `_espn_signin_read` returns `auth` only for `EspnError.kind == "auth"` (HTTP 401/403); anything else → 403 `proof_unavailable`, `reason: "espn_unavailable"`. The control SWID comes from the league's own owners and is never echoed or logged | `test_c3_any_non_auth_answer_on_steps_3_and_4_refuses` × {anon, control} × {500, 503, ESPN 429, 404, 418, non-JSON 200, timeout, URLError, connection reset} (18 cases) |
| 4 | Rate-limit key = the real client IP | `_client_ip()` = the `X-Forwarded-For` hop `_SIGNIN_TRUSTED_PROXY_HOPS` from the right (1 = rightmost; Render's layout pending release-lead), else `remote_addr` when there are fewer hops. Per-IP ceiling raised to 300 failures / 10 min so a wrong hop count can't 429 real users (the per-subject 5 / 15 min stays the real guard). TEMPORARY first-deploy diagnostic `PLATFORM-SIGNIN-XFF hops=N` (count only, never an IP) on claims and the two actions — remove after release-lead confirms the layout | `test_c4_spoofed_leading_xff_neither_resets_nor_splits_the_ip_count`, `test_c4_trusted_proxy_hops_pick_the_hop_counted_from_the_right` (×4: hops 1/2/3 and fewer-hops → `remote_addr`, plus no header), `test_c4_two_trusted_hops_key_the_ip_limit_on_the_client_hop`, `test_c4_ip_ceiling_is_300_failures_per_10_minutes`, `test_c4_xff_diagnostic_logs_only_the_hop_count` (sabotage: hard-coded rightmost → 4 red) |
| 5 | The R1 script is env-only, GET-only, ESPN-only, prints statuses + a verdict, writes nothing | `scripts/espn_pair_check.py` rewritten: standard library only (no `backend` import), environment only, four GETs, status lines + verdict | `test_c5_r1_script_is_stdlib_only_and_matches_espn_service`, `test_c5_r1_script_verdicts` (×9), `test_c5_r1_script_env_only_get_only_espn_only_prints_statuses` (×2; `open` patched to fail, all requests GET to `lm-api-reads.fantasy.espn.com`, 5 output lines, no marker) |
| 6 | Disconnect keeps the identity | Routes unchanged (confirmed); pinned | `test_c6_espn_disconnect_keeps_the_identity_then_same_account`, `test_c6_mfl_disconnect_keeps_the_identity_then_same_account` |
| 7 | Refusal per code; mint → import → delete; race; #279 gate pinned | — | `test_c7_refusal_espn_proof_required`, `test_c7_refusal_mfl_proof_required_makes_zero_mfl_calls`, `test_c7_refusal_espn_public_league`, `test_c7_refusal_espn_ownerless_team`, `test_c7_refusal_espn_unproven_pair_leaguemate_attack`, condition-3 cases (`espn_unavailable`), `test_c7_c8_refusal_espn_wrong_account_…`, `test_c7_c8_refusal_mfl_wrong_account_…`, `test_c7_refusal_espn_platform_identity_in_use`, `test_c7_refusal_mfl_platform_identity_in_use_case_insensitive`, `test_c7_too_many_attempts_ip_limit_counts_claims_and_actions`, `test_c7_too_many_attempts_subject_limit`, `test_c7_c11_mint_import_delete_then_a_fresh_sign_in_is_a_new_account`, `test_c7_c9_uq_linked_identity_race_signs_into_the_winner`, `test_c7_the_279_gate_is_byte_identical_and_still_on_the_link_routes` (sha256 of the four gate functions pinned to `origin/main` @ `732a6b7f`, `_MUTATING_METHODS`, and the gate wrapper on all four link routes), `test_c7_unverified_session_still_403s_on_espn_link_but_minted_passes` |
| 8 | `wrong_account` names the login's own team, only after proof | ESPN: after all three reads succeeded, a team in this league whose `owner_swid` is the pair's → "This ESPN login owns {Team} in this league. Pick that team to continue."; MFL: after login, a franchise of this login in this league (myleagues `franchise_name`, else the bundle's) → same wording with "MFL"; otherwise the sign-in's own not-the-owner line (row 8) | `test_c7_c8_refusal_espn_wrong_account_names_the_team_this_login_owns`, `test_c8_espn_wrong_account_generic_when_login_owns_no_team_here`, `test_c7_c8_refusal_mfl_wrong_account_names_the_franchise_this_login_owns`, `test_c8_mfl_wrong_account_generic_when_login_owns_nothing_here`, `test_c8_nothing_is_named_before_the_proof_read` |
| 9 | Response gains `account_created` | `true` = the proof created the account; `false` = existing account (incl. the race loser and the bound-Sleeper restore) | `test_c9_second_sign_in_same_identity_returns_the_same_account`, `test_c7_c9_uq_linked_identity_race_signs_into_the_winner`, plus assertions in the first-sign-in, bound-Sleeper, condition-2 and condition-6 tests |
| 10 | Export has the identity, never the secrets | Already true: `accounts.export_user_data` exports `linked_identities` (provider + subject) and omits `espn_credentials.espn_s2_encrypted` / `mfl_credentials.cookie_encrypted`; no code change | `test_c10_espn_export_has_the_identity_not_the_cookie`, `test_c10_mfl_export_has_the_identity_not_the_cookie_or_password` |
| 11 | Deletion releases the identity | Already true: `DELETE /api/account` removes `accounts` + `linked_identities`; the next proof creates a new account | `test_c7_c11_mint_import_delete_then_a_fresh_sign_in_is_a_new_account`, `test_c11_mfl_deletion_releases_the_identity` |

- [x] **Code-walk proof** (`backend/server.py`, functions named because line numbers move):
  1. `entry_platform` wraps `_entry_platform(audit)`: an unexpected exception → type + code frames logged, 500 `internal_error`; in a `finally`, one `PLATFORM-SIGNIN` line whenever `audit["claim"]` was set (`_log_platform_signin`).
  2. ESPN claim (`team_id` present): `espn_cookies_incomplete` (unchanged) → `proof_required` if no pair → subject = `accounts.platform_subject("espn", swid)` → `_signin_limit_gate` → the existing cookie read `_espn_import_payload` (an auth failure charges the failure budgets) → team lookup → `_espn_signin_proof`: anonymous `_espn_signin_read` must return `"auth"`; control read with the first other owner SWID must return `"auth"`; anything else → `espn_unavailable`; owner check (named `wrong_account`) → `_platform_sign_in`.
  3. MFL claim (`franchise_id`/`team_id` present): password popped from the parsed body → `proof_required` if missing (no MFL call yet) → limiter → `_mfl_resolve` (parse + public host redirect) → `mfl_service.login` (password `del`-ed in `finally`) → `fetch_league_bundle(..., cookie=cookie)` with the login's cookie, so private leagues work (an auth refusal for a good login → `wrong_account`) → franchise lookup (400) → `fetch_my_leagues(cookie, year)` → (`league_id`, `franchise_id`) membership (named `wrong_account`) → `_platform_sign_in`. The cookie is never stored, logged or returned.
  4. `_platform_sign_in`: `identity_work_key` lease → `accounts.get_account_by_identity` → if none, `accounts.platform_identity_in_use` (409) else `find_or_create_account` (IntegrityError → re-read winner) → bound Sleeper user ⇒ `_extension_build_session` restore, else `_account_build_session(acct_*)` → `verified` / `verified_via` (`accounts.VERIFIED_VIA_*`) / `account_id` on the session → `mark_user_verified` → `_persist_session_if_eligible` → `_link_device_identity` → response with `expires_at` from the persisted 90-day window and `account_created`.
  5. The #279 gates (`_gate_unverified_write`, `_verified_*_denial`) and `/api/espn/link`, `/api/espn/import`, `/api/mfl/link`, `/api/mfl/auth-link` are untouched (pinned by condition 7's hash test); `_provider_auth_response` (Apple/Google) is untouched.
- [x] **Manual TestFlight checklist** (operator, on the 11-06 binary that carries the client MFL change; flag `landing.platform_options` on in a test window only). Prerequisite: head-eng has reviewed `scripts/espn_pair_check.py`, and the operator's run printed `PAIR_BOUND`. If it printed `PAIR_NOT_BOUND`, steps 1–2 are expected to refuse and only the refusal copy is checked.
  1. Sign-in screen → ESPN → sign in to ESPN in the WebView → pick a **private** league → claim your own team. Expect: you land signed in; Settings → Account shows an account (no Sleeper); the league import completes (no "verification required" error).
  2. Sign out, repeat step 1 with the same ESPN account. Expect: the same board (rankings you made in step 1 are there) and the display name you had.
  3. ESPN → a **public** league you're in → claim a team. Expect "In a public ESPN league, team ownership can’t be confirmed. Sign in with Apple, then link your league." and no sign-in.
  4. ESPN private league → claim a team that is **not** yours. Expect "This ESPN login owns {your team} in this league. Pick that team to continue." and no sign-in.
  5. Sign-in screen → MFL → sign in with your MFL username/password → pick your league (repeat with a **private** MFL league if you have one). Expect: signed in; the client's `auth-link` → `auth-import` completes the import; "Send in MFL" works later (auth-link stored the cookie).
  6. MFL → wrong password. Expect "MFL didn't accept that username and password." Repeat 5 more times quickly: expect "Too many sign-in attempts…".
  6b. **MFL username case (QA P2-3; settles the decision rule below).** Sign in to MFL with your real username in a **different case** (e.g. `MattM` → `mattm`) and the right password. Record whether MFL **accepts** it.
  7. Settings → disconnect the ESPN league, sign out, sign in with ESPN again. Expect the same account and board.
  8. Settings → Delete account on an ESPN-signed-in account. Expect deletion succeeds; signing in with ESPN again starts a fresh, empty account.
- [ ] **WAIVED** — n/a.
- `testID`s added/renamed: none (server-only change).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `/api/entry/platform` row: the proof, every refusal and its closed `reason` set (incl. `espn_unavailable`), named `wrong_account`, response fields incl. `account_created`, the 429, the fixed 500, the audit line, the verified handoff; the stale "unverified-write grace" text in that row and under the write-gate table fixed |
| `living-memory/LLD.md` | n/a | no route/schema *convention* shifted: the provider and `verified_via` vocabularies live in `docs/data-dictionary.md` and `docs/cross-client-invariants.md`, both updated |
| `docs/architecture.md` | n/a | no module wiring change — the proof runs inside the existing route with existing primitives |
| `living-memory/HLD.md` | n/a | no new module, client or major flow; the entry flow's shape (preview → claim → import) is unchanged; since #421 the import is `POST /api/espn/link` (ESPN) or `POST /api/mfl/auth-link` → `POST /api/mfl/auth-import` (MFL) |
| `docs/cross-client-invariants.md` | updated | "Verified-via strings": `mfl_login`, `espn`; `linked_identities.provider` `espn` / `mfl`; `PLATFORM_PROVIDERS` |
| `docs/glossary.md` | updated | "Platform sign-in" (new); "Linked identity" note |
| ADR or `DECISIONS.md` entry | deferred | the design doc (platforms-eng, D1–D10) plus head-eng's review are the decision record; the D- entry is written at merge by the decision owner. Build-level choices are recorded here |
| `docs/data-dictionary.md` | updated | `users.verified_via`, `linked_identities`, `sessions.verified_via`, `espn_credentials.swid` / `mfl_credentials.mfl_username` (stored as captured; compared normalised) |
| `docs/integrations/espn.md` | updated | §1.3 call-site row; §2.5 (the extra reads, fail-closed, the one SWID form, disconnect vs. delete, R1 script) |
| `docs/integrations/mfl.md` | updated | §2 — the password at the mint is transient; named `wrong_account`; disconnect keeps the identity |
| `docs/business/analytics/2026-10-27-signin-failed-error-codes.md` | new | analytics-lead grant 1 addendum (closed `error_code` domain) |
| `scripts/README.md` | updated | `espn_pair_check.py` (operator R1 check, env-only) |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests`, `tsc --noEmit`, testid-lint — to be confirmed on the PR's sha (the branch is pushed for review; no PR yet)
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-10-26 "Platform sign-in" entry (targeted tests, sabotage per condition, full-suite counts; `FTF_SKIP_SIM_GATE=1` per D-056)
- **TestFlight verification:** §3 checklist, run by the operator on the 11-06 binary; outcome logged in TEST_LEDGER
- **R1:** head-eng reviews `scripts/espn_pair_check.py`; then the operator runs it once (read-only, prints statuses only) before 11-06
- **Merge gate:** onboarding-eng mint review → head-eng diff check against conditions 1–7 → merge dark by 11-03
- Express lane declared by the operator? **no** — full gates

---

## Addendum (2026-10-27) — `espn.signin` kill switch

head-eng's 11-06 item. Full gates (it is a feature-flag surface).

- **What it gates:** the **whole ESPN branch** of the sessionless `POST /api/entry/platform`: the `my_leagues` action, the league preview and the proof-based ESPN team claim. When `espn.signin` is off, every ESPN entry request returns **404 `feature_disabled`**. The check runs right after the platform is validated, before any ESPN call or rate-limit accounting.
- **What it does not gate:** MFL entry and sign-in, and Settings ESPN league linking (`espn.link`, `/api/espn/*`), which keep working.
- **Why:** the operator can turn ESPN sign-in off (for example, if the R1 pair-binding check says `PAIR_NOT_BOUND`) without losing MFL sign-in or ESPN league linking.
- **Flag surface:**
  - `espn.signin` is in `backend/feature_flags.py` `FLAG_KEYS`. Its code default is `false`, so an unreadable config fails closed.
  - `config/features.json` sets it to **`true`**, with a `_comment_espn_signin` entry.
  - It is mirrored into `backend/tests/fixtures/flags/release.json` (the exact-mirror test) and into the four release-derived profiles (`profiles-on`, `onboarding-v2`, `release-300`, `release-espn-send-off`).
  - It is documented in `docs/config-reference.md`, `docs/api-reference.md` and `docs/runbook.md`.
  - Graduation: delete it once ESPN sign-in has run a clean TestFlight cycle after R1 says `PAIR_BOUND`.
- **Analytics:** no new events. A disabled ESPN mint reaches the client as `signin_failed.error_code = feature_disabled`, which is already in the closed domain (`docs/business/analytics/2026-10-27-signin-failed-error-codes.md`).
- **Schema:** none.
- **Evidence:** `test_espn_signin_off_404s_the_whole_espn_entry_branch_with_zero_espn_calls` sends five ESPN entry requests: `my_leagues`, two previews and two claims.
  - Each returns 404 `feature_disabled`.
  - There are zero ESPN league or fan-API calls and no limiter state, and nothing is created.
  - MFL sign-in still returns 200, and `/api/espn/link` still returns 200 with `choose_team`.
  - Sabotage: dropping the check → red (`500 == 404`: the action reached the ESPN fan API).
  - The flag-registry tests (`test_seed_ui_test_db`, `test_blind_grading_routes` and the per-flag mirror tests) stay green.
- **Client half:** hiding the ESPN chip is a separate mobile PR by another worker. This build touches no `mobile/src`.
- **Waivers:** the manual TestFlight check of the switch rides with the client PR. A server-side check is to flip `espn.signin` to `false` via `FTF_FLAGS` on a test deploy and confirm a 404.

---

## Refusal copy — final and complete (2026-10-27)

The mint's refusal `message`s are the **final 14-row set** from marketing-lead (`marketing-lead-copy.md` §6 addendum 8, C), with rows 7, 8 and 12 approved by legal (**R28.16**). No placeholder remains.

- **Where the strings live:** each one is a single constant next to the sign-in helper in `backend/server.py`:
  - `_SIGNIN_PROOF_REQUIRED_MSG` (rows 1–2);
  - `_SIGNIN_PROOF_UNAVAILABLE_MSG[reason]` (rows 3–5);
  - `_SIGNIN_ESPN_UNAVAILABLE_MSG` (6);
  - `_SIGNIN_OWNS_OTHER_TEAM_MSG` (7);
  - `_SIGNIN_NOT_OWNER_MSG[platform]` (8);
  - `_SIGNIN_ESPN_AUTH_REQUIRED_MSG` (9);
  - `_SIGNIN_MFL_BAD_LOGIN_MSG` (10);
  - `_SIGNIN_MFL_UNAVAILABLE_MSG` (11);
  - `_SIGNIN_IDENTITY_IN_USE_MSG[platform]` (12);
  - `_SIGNIN_TOO_MANY_MSG` (13);
  - `_SIGNIN_GENERIC_ERROR_MSG` (14).
- **Apostrophes:** U+2019, the codebase's user-copy convention, per the coordinator. Marketing's table and legal's text use U+0027. Row 10 (`MFL didn't accept that username and password.`) keeps its straight apostrophe, byte-identical to the `auth_leagues` / `auth-link` body (D8).
- **Sign-in only.** Rows 8, 9 and 11 have their own constants, so the link routes keep their copy:
  - `_ESPN_WRONG_ACCOUNT_MSG` is unchanged;
  - `_espn_error_payload`'s cookie-paste text still serves the preview and `/api/espn/*`;
  - `_platform_error_payload`'s "Couldn't reach MFL — try again shortly." still serves the preview, the actions and `/api/mfl/*`.
- **Mint-only behaviour for rows 9 and 11:**
  - Row 9: the sign-in's cookie read refused → 403 `espn_auth_required` with row 9's text.
  - Row 6 on that same cookie read (step 2): a 5xx, parse error or timeout → 502 `espn_unavailable` (the code is unchanged; a timeout used to surface as 500 `internal_error`) with row 6's text. The preview keeps the link-route "Couldn't reach ESPN — try again shortly."
  - Row 11: MFL not answering during the proof (host resolution, login, bundle or myleagues) → today's 502 `mfl_unavailable` with row 11's text.
- **Evidence:**
  - `test_signin_refusal_copy_is_the_final_set_verbatim` pins every row's exact body on the real route: 24 cases (incl. row 6 on the step-2 cookie read: 5xx, parse, timeout), covering both platforms for rows 7, 8 and 12, the four MFL failure points for row 11, and both 5xx codes for row 14.
  - `test_link_routes_and_previews_keep_their_own_copy` pins the non-sign-in copy.
  - Sabotage: the row-13 constant reworded → `[row13-too-many]` red. Restored.

---

## Addendum (2026-10-27) — release-lead QA follow-ups (#430 GO-with-notes)

**D7 narrowed (P3s).** These limiter changes come from the coordinator; head-eng is informed.
- **Counted, toward both the subject and IP windows:**
  - an MFL bad login (claim or `auth_leagues`);
  - the ESPN sign-in cookie read refused for auth (claim, row 9, or `my_leagues`);
  - `espn_unproven_pair`, including the no-second-owner case, which shares the reason.
- **Never counted:**
  - `espn_public_league` and `espn_ownerless_team` (facts about the league);
  - `wrong_account` (it follows a proven login);
  - upstream outages and input errors.
- **A proven claim clears its subject's count.** The IP window is left alone.
- **Admission counts in-flight attempts** under the limiter lock, so `failures + in_flight >= cap` refuses. The slot is released in `entry_platform`'s `finally`, so an exception never leaks one. QA had seen 8 admitted with a cap of 5 on 4 threads.
- **Tests:**
  - `test_d7_unproven_pair_counts`;
  - `test_d7_uncounted_refusals_never_consume_the_budget`;
  - `test_d7_a_proven_claim_clears_the_subject_count_not_the_ip`;
  - `test_d7_concurrent_bad_attempts_never_exceed_the_cap`: 12 threads behind a barrier, with a 0.2 s patched login, admit exactly 5;
  - `test_d7_in_flight_slot_is_released_on_an_exception`.
- **Sabotage:**
  - admission ignoring in-flight → the concurrency test red (`12 == 5`);
  - no subject clear on success → the clear test red.

**Second QA pass (#430 @ `6ffcfb65`).**
- `test_d7_concurrent_bad_attempts_never_exceed_the_cap` stubs `api_observability._write_event`. The obs sink on the in-memory SQLite `SingletonThreadPool` segfaulted on Python 3.14 (QA: 8 of 40 runs). It now passes 20 of 20 in a loop.
- **S12:** a window full only because of in-flight attempts answers `Retry-After: 5` (`test_s12_in_flight_saturation_answers_retry_after_5s`).
- **S16:** the `my_leagues` / `auth_leagues` gates hold their slot on the request's real audit dict (`test_s16_actions_release_their_in_flight_slot`; sabotage with a throwaway `{}` → red, the slot leaks).
- `_signin_note_failure` / `_signin_retry_after` are removed; the 300-ceiling test drives the live gate and release path.
- **MFL `year` hardening:** 2000..current season + 1 is enforced before any MFL call or limiter accounting, else 400 `mfl_bad_year`, with the existing "year must be numeric" copy (no new copy). A year that can't be an integer at all (JSON `Infinity` / `-Infinity` / `1e400`) gets the same 400, not a 500. On `auth_leagues` the check runs before the limiter gate (pinned). The same overflow gap remains in the pinned `/api/mfl/*` code (`_mfl_resolve`, `auth-link`, `auth-import`), which #430 doesn't touch. So an odd year can't turn a wrong guess into an uncounted upstream error (`test_mfl_year_out_of_range_is_400_before_any_mfl_call` ×6, `test_mfl_year_in_range_is_admitted` ×3; sabotage → all 6 red).

**XFF diagnostic.** The temporary line is now `PLATFORM-SIGNIN-XFF hops=N cf=0|1 tci=0|1`. It records only whether `CF-Connecting-IP` / `True-Client-IP` are present, never their values. `test_c4_xff_diagnostic_logs_only_the_hop_count` asserts none of the six test IPs appears in caplog.

**MFL username case (QA P2-3). Documented now; no code change yet.**
- The MFL identity is the lower-cased login (`accounts.platform_subject("mfl", …)`).
- **Risk:** if MFL usernames are case-sensitive, two different MFL users who differ only by case would share one Fleeced account. That would be a **P1**.
- **Decision rule:** settled by TestFlight checklist step 6b.
  - MFL **accepts** the same username in a different case → MFL is case-insensitive, and lower-casing is correct. No change.
  - MFL **rejects** it → MFL is case-sensitive. **Before ask 16**, switch the `mfl` branch of `platform_subject` to trim-only (case-preserving), together with the D6 conflict comparison in `platform_identity_in_use`, which goes through the same normaliser.
- The same rule is written as a code comment at `accounts.platform_subject`.

---

## Post-launch follow-ups

### MFL auth-link: D7 limiter on the password login (2026-10-27, `feat/mfl-auth-link-throttle`, stacked on #430 @ `d3248d35`)

Full gates (it changes an API contract: a new 429 on a route).

- **Problem:** `POST /api/mfl/auth-link` predates #430 and was an **unthrottled MFL password oracle** for any verified session: unlimited username/password guesses, each answered 200 or 403. `POST /api/mfl/auth-import` takes no password (it uses the stored cookie), so it needs no limiter.
- **Build:** the route's MFL login goes through #430's D7 limiter, `_signin_limit_gate` / `_signin_release`, with the in-flight bound.
  - **Keys:** the same as the sign-in. Per subject = `accounts.platform_subject("mfl", username)` (trimmed, lower-cased); per IP = `_client_ip()`. So the sign-in and auth-link **share one budget**: 5 bad guesses at either one lock both for that username.
  - **Order:** the year parse → missing credentials (400) → the year range (`_mfl_entry_year_refusal`, 2000..season+1, the sign-in's QA hardening, so an odd year can't turn a guess into an uncounted upstream error) → admission → `mfl_service.login`. The check happens **before** the MFL call.
  - **Counted:** an MFL bad login only (`MflAuthError` from `login` or `fetch_my_leagues`, the same grouping as `auth_leagues`). Outages (`MflError`), input errors and exceptions don't count. A good login (`login` + `fetch_my_leagues`) **clears the subject**, never the IP window.
  - **Over the limit:** 429 `too_many_attempts` + `Retry-After` with the row-13 constant `_SIGNIN_TOO_MANY_MSG` (reused; no new copy), and a `MFL-AUTH-LINK outcome=limited reason=…` log line (no ids).
  - **Release:** `_signin_release` runs in a `finally` around the MFL calls, so an exception never leaks an in-flight slot.
- **Year parse (coordinator addition):** a JSON `Infinity`, `-Infinity` or `1e400` year made `int(...)` raise `OverflowError` → 500 on auth-link and auth-import. Both now catch it with the existing 400 `mfl_bad_year` / "year must be numeric". `_mfl_resolve` and `/api/mfl/link` are untouched.
- **The `mfl_login` verify block — a finding; guarded in a follow-up commit (below).** The brief expected it to be dead code since #279. It isn't:
  - It runs on **every successful POST by an already-verified session**. It re-stamps `sess["verified_via"]` and `users.verified_via` (+ `verified_at`) to `mfl_login`, overwriting `sleeper` / `apple` / `google` / `espn`, and force-persists the durable session row.
  - It also runs for an **unverified synthetic demo session** (`is_demo` + `demo_user_*`): the #279 gate exempts those, so the block marks the demo session verified via `mfl_login`. Demo sessions come from `/api/session/demo`, which 404s while `landing.try_before_sync` is off (it is off today).
  - **Guard (follow-up commit, platforms-eng + onboarding-eng, which owns the accounts seam):** the block now runs only `if not sess.get("verified")`. `verified_via` / `verified_at` record how the account was **first** verified, not the latest platform connected. So an already-verified session's `verified_via` (session + `users`), `verified_at` and durable row are left alone, while the MFL credential is still stored. Demo sessions keep the old behaviour.
    - Pinned by `test_auth_link_keeps_a_verified_sleeper_sessions_verified_via` (incl. the durable row) and `test_auth_link_keeps_a_verified_apple_account_sessions_verified_via` (an `acct_*` account-only session), plus the demo pin.
    - They replace the re-stamp pin and the two 2026-08-11 tests that encoded the re-stamp: `test_auth_link_verified_owner_persists_platform_marker` and `test_auth_link_verification_grants_long_expiry_durable_row`.
    - Sabotage: the guard removed → both new tests red (`'mfl_login' == 'sleeper'` / `'apple'`).
  - So it is not provably unreachable. The block stays; its stale "login counts as verification / first-verified-wins" comment is rewritten to say what it does. Pinned by `test_auth_link_verify_block_restamps_a_verified_sessions_verified_via` and `test_auth_link_verify_block_runs_for_an_unverified_demo_session`. Whether the re-stamp should stay is platforms-eng's / head-eng's call.
- **#430's byte-identical pin:** `test_c7_the_279_gate_is_byte_identical_and_still_on_the_link_routes` hashes only the four gate functions and checks the gate wrapper on the four link routes. It does not hash `mfl_auth_link`'s body, so **no expected hash changes**; a comment in the test names this branch. Code-walk item 5's "`/api/mfl/auth-link` … untouched" no longer holds on this branch: the route body changed, the gate didn't.
- **Analytics / schema / flags:** none. `too_many_attempts` is already in the closed `signin_failed.error_code` domain; auth-link fires no sign-in events.
- **Evidence:** `backend/tests/test_mfl_auth_link_route.py` (+12 cases), recorded in `living-memory/TEST_LEDGER.md` 2026-10-27 "MFL auth-link D7 limiter":
  - `test_auth_link_d7_sixth_attempt_after_five_bad_logins_is_429_no_mfl_call`: the right password, in another case, on the 6th → 429, 5 MFL calls in all;
  - `…_shares_the_subject_window_with_platform_sign_in`;
  - `…_per_ip_window`;
  - `…_good_login_clears_the_subject_not_the_ip`;
  - `…_uncounted_outcomes_never_consume_the_budget`;
  - `…_in_flight_slot_is_released_on_an_exception`;
  - `test_auth_link_year_out_of_range_is_400_before_any_mfl_call`;
  - `test_auth_link_and_auth_import_non_finite_year_is_400_not_500` (×3);
  - the two verify-block pins (superseded by the guard commit: the re-stamp pin is replaced, the demo pin stays).
- **Docs:** `docs/api-reference.md` (the auth-link POST row: the 429, the year range, the re-stamp; the auth-import row's 400; the entry row's counted list), `docs/integrations/mfl.md` §2, `docs/runbook.md` (the lockout entry now covers auth-link). `living-memory/LLD.md` / `HLD.md` / `docs/architecture.md`: n/a (no convention or wiring change).

#### #430 round-3 P3s carried here (2026-10-27, after release-lead froze #430 at `7e52912d`)

`7e52912d` is **merged** into this branch (a merge, not a rebase), and these land in a separate commit on top. They change no copy, flag, schema or event. `/api/mfl/auth-link` and `/api/mfl/auth-import` are fixed above. #430's round-3 note that they still 500 on an overflowing year doesn't apply on this branch.

1. **Ordering pin (claim + preview):** the MFL entry branch's year check already runs before the claim's `_signin_limit_gate`; it is now pinned. `test_mfl_claim_and_preview_year_checks_run_before_the_limiter_gate` (×2: `1999`, `"abc"`) asserts:
   - a gate spy is never called;
   - no failure or in-flight state is created;
   - a locked subject still gets the 400, not a 429.

   Sabotage: the check moved below the gate → both red (`['mfl'] == []`).
2. **Non-numeric year → `mfl_bad_year`:** `_mfl_entry_year_refusal` now refuses a year that `int()` rejects with `TypeError` / `ValueError` too, not only `OverflowError` or out of range. That covers `NaN` (JSON's literal, which Python's parser accepts), `"NaN"`, `"abc"`, an array and an object.
   - The answer is 400 `mfl_bad_year`, "year must be numeric", the same as `auth_leagues`. The claim and preview used to fall through to `_mfl_resolve` and read 400 `mfl_bad_league_id`.
   - `test_mfl_non_numeric_year_is_bad_year_on_claim_preview_and_action` (×5) covers the claim, the preview and `auth_leagues`, with no MFL call and no limiter state.
   - Sabotage: the old `ValueError → None` fall-through → all 5 red, plus the `"abc"` ordering case.
   - **`""` is not a bad year.** Like a missing year it means the default season, which is how `auth_leagues`' own parse has always read it. Pinned by `test_mfl_empty_year_is_the_default_season_on_claim_preview_and_action`.

#### Lockout fix: the 5-failure lock keyed on (subject, client IP), plus a subject-wide ceiling (2026-10-27, head-eng re-opened the residual)

Full gates. These are D7 limit changes, server-only, with no new copy, flag, schema or event. Draft, not yet QA'd.

- **Problem:** the 5 / 15 min lock was keyed on the subject alone. Anyone holding a victim's SWID (league-visible) or MFL username could renew it indefinitely, and the Apple fallback lands in a different, empty account. head-eng had accepted this residual for launch and re-opened it.
- **Keys** (`_signin_limit_keys`). Each attempt is checked against three windows:
  - `ip:` — per client IP, 300 / 10 min, unchanged;
  - `subip:` — per (subject, client IP), 5 / 15 min (`_SIGNIN_SUBJECT_MAX_FAILURES` / `_WINDOW_S`, values unchanged, now keyed on the pair);
  - `sub:` — per subject across all IPs, **30 / hour** (`_SIGNIN_SUBJECT_CEILING_FAILURES` / `_SIGNIN_SUBJECT_CEILING_WINDOW_S`, new module constants): the password-guessing guard.

  The subject keys are still hashes. The sign-in claims, both actions and auth-link all use these keys.
- **What a single IP can do:** a griefer on one IP locks only their own `subip:` bucket. That bucket also caps one IP at 20 failures an hour, under the ceiling. So a single-IP griefer can no longer lock the victim out.
- **Residual:** 30 failures within an hour from **two or more** IPs still lock the subject everywhere (`reason=subject_ceiling`) until the hour passes or the subject's next proven sign-in. Any cross-IP ceiling has this property. If head-eng wants it narrower, one option is to exempt a (subject, IP) pair that has recently signed in from the ceiling. Not built.
- **Unchanged:**
  - in-flight admission per key (`failures + in_flight >= cap`, now on all three keys);
  - `Retry-After` (the longest wait among the refusing keys; 5 s when only in-flight attempts fill a window);
  - 429 `too_many_attempts` with the row-13 copy.
- **New audit / log `reason`:** `subject_ceiling`, next to `subject_limit` (now the pair) and `ip_limit`. Logs only; `signin_failed.error_code` stays `too_many_attempts`.
- **Success clears:** a proven claim or a good auth-link login clears the subject's bucket **for its IP and the subject-wide counter** (my choice, as platforms-eng suggested). It never clears the IP window or another IP's pair bucket, so a griefer's own lock survives the victim's success.
- **head-eng's #430 nit:** the sign-in's ESPN cookie-read warning now logs `espn fetch failed [<kind>]` only, never the exception message. The link routes' `_espn_error_response` warning is unchanged.
- **Evidence:** `living-memory/TEST_LEDGER.md` 2026-10-27, "Lockout fix".
