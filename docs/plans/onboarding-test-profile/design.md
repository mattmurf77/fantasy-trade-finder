# Onboarding test profile — Phase 1 map and design

**Date:** 2026-11-11 · **Branch:** `feat/onboarding-test-profile` (cut from `origin/main` `fa83f57b`) · **Status:** built, uncommitted.
- §9: the base switch.
- §10: the 2026-11-11 ruling — linking must be the real production flows.
- §11: option A, real ESPN/MFL linking.
- §12: the 2026-11-12 ruling — Sleeper too, built with three defences.
- §13: the independent review's findings and their fixes.

Line numbers are from `fa83f57b`. `server.py` is 44.7k lines, so every claim here cites a line.

## 0. Contents

1. [The capability that already exists: Test Stages](#1-the-capability-that-already-exists-test-stages)
2. [Identity, session and auth today](#2-identity-session-and-auth-today)
3. [Tables keyed by user id](#3-tables-keyed-by-user-id)
4. [Onboarding gates](#4-onboarding-gates)
5. [Cross-user surfaces](#5-cross-user-surfaces)
6. [Platform credentials and writes](#6-platform-credentials-and-writes)
7. [Designs considered](#7-designs-considered)
8. [Why the build stopped: decisions needed](#8-why-the-build-stopped-decisions-needed)
9. [Build (Phase 2): base switch, code walk, TestFlight checklist](#9-build-phase-2-base-switch-code-walk-testflight-checklist)
10. [Operator ruling 2026-11-11: real linking flows](#10-operator-ruling-2026-11-11-real-linking-flows)
11. [Option A: real ESPN / MFL linking](#11-option-a-real-espn--mfl-linking)
12. [Operator ruling 2026-11-12: real Sleeper linking](#12-operator-ruling-2026-11-12-real-sleeper-linking)
13. [Review findings and fixes (2026-11-12)](#13-review-findings-and-fixes-2026-11-12)
14. [Second review, and the per-user binding merge (#666)](#14-second-review-and-the-per-user-binding-merge-666)

---

## 1. The capability that already exists: Test Stages

The operator was right: a predecessor exists. It is **Test Stages**, from commit `8789a800` ("synthetic qa_* users at any adoption stage"), with a template UI added in `2c10f4cc`.

**What it is**
- Backend: `backend/test_users.py` and the routes `POST /api/test-users` and `DELETE /api/test-users/<id>` (`server.py:36175-36328`).
- Mobile: `mobile/src/screens/TestStagesScreen.tsx`, reached from Settings → Testing (`settings/sections/TestingSection.tsx:46-69`, `SettingsScreen.tsx:1026-1045`).
- Docs: `docs/api-reference.md:1635-1642`, `docs/config-reference.md:688`.

**How it works today**
- `POST /api/test-users {stage}` mints a new random `qa_<8 hex>` user every time (`server.py:36223`). Stages are fresh, activated, board_owner, converted and power.
- The user plays in the **seeded demo league**: `DEMO_PLAYERS` plus `_build_demo_league` (`server.py:36231-36249`). It is not the operator's real league.
- The route returns a token. The app swaps its token, user, league and onboarding state to the new user (`TestStagesScreen.tsx:196-240`).
- `DELETE /api/test-users/<id>` deletes `users`, `swipe_decisions` and `member_rankings` rows for any `qa_*` id (`test_users.py:173-187`).
- `qa_*` ids are already excluded from analytics cohorts (`analytics_queries.py:567-568`).

**How it is gated**
- Server (`_test_users_denied`, `server.py:36188-36205`): the caller's `device:<X-Device-Id>` **or** session `user_id` must be in `experiments.load_tester_allowlist()`. That list is the `FTF_TESTER_ALLOWLIST` env var plus the checked-in `config/tester_allowlist.json`. Otherwise the route returns 404.
- The `testing.stage_users` flag only gates the Settings row. It is `false` in `config/features.json:225` and reaches devices through the experiment overlay.

**Is it on in production?** Unknown. The global flag is off. Whether an experiment overlay delivers it to the operator's device lives in the production `experiments` table, which this session may not read. The server routes are live for anyone on the allow-list whatever the flag says.

**Measured against the operator's request**

| Requirement | Test Stages today |
|---|---|
| Become a brand-new user | **Partly.** The `fresh` stage is a new `users` row. Only `ftf_onboarding_state_v1` is replaced. About 25 other first-run keys stay on the device (§4.2), and the navigator is never reset, so the screen says "force-quit and reopen" (`TestStagesScreen.tsx:233`). |
| Real data untouched | **Yes on the server.** It writes only `qa_*` rows. **No on the device:** the swap overwrites the real token, user and league, and the real onboarding state is lost. |
| Operator decides when to flip back | **No.** The only way back is "sign out and sign back in with your username" (`TestStagesScreen.tsx:351-354`). There is no banner and no stash of the real session. |
| Reset test profile | **Partly.** `DELETE /api/test-users/<id>` exists but covers only 3 of the roughly 60 tables a session can write (§3). |
| Uses the real linked leagues | **No.** It uses the demo league. A "Capture my leagues" template feature exists in the app, but its server routes (`/api/test-users/templates`, `TestStagesScreen.tsx:118,141,171`) **do not exist on `main`**. `git log -S` finds no server commit ever adding them, so the button returns 404 and the template list is always empty. |

**Against the safety invariants**
- **Allow-list.** It is server-side, but it accepts a **device id**, a client-supplied header, as well as an account. It also reads a **checked-in** allow-list file. `config/tester_allowlist.json` contains a real-looking account id (`3135…`) committed to the repo. The brief says no real account id may be in the repo; that id already is.
- **Isolation.** It is safe by construction for cross-user leakage only because the demo league has no real league-mates. That safety disappears the moment the profile touches real leagues.
- **Crons.** Not handled. `prepared_trade_cohort.py:162` does not skip `qa_`, but demo users are never verified for Sleeper leagues, so they drop out.
- **Analytics.** `device_exclusion` skips `qa_`. Six hand-written report filters do not (§5, row A1).

**Conclusion.** Extend Test Stages; do not build a parallel mechanism. Keep the `qa_` namespace and the analytics exclusion that already covers it, and keep the Settings → Testing entry point. Replace or add four things:
1. A deterministic per-operator profile id instead of random spawns.
2. A switch-back that restores the real session.
3. Real leagues instead of the demo league.
4. A complete reset.

## 2. Identity, session and auth today

- **Account vs league identity.** `sess["user_id"]` is the account (person). `_league_user_id(sess)` (`server.py:2829-2843`) is the team (`owner_id`) in the current league. Account-scoped state uses the former, league-scoped comparisons the latter (`backend/CLAUDE.md` § Identity).
- **What a user id looks like.** The app user is keyed by the **Sleeper user id** for Sleeper users: `upsert_user(sleeper_user_id=…)` and `users.sleeper_user_id` is the PK (`database.py:515`). Account-first users (Apple/Google, or ESPN/MFL platform sign-in) get `acct_<account_id>` (`accounts.py:101-114`). Synthetic ids already in use: `demo_user_*`, `qa_*`, `test_user_fp_*`.
- **Session store.** `_sessions` maps token to a dict, in memory (`server.py:2378`). `_get_session` falls back to a durable `sessions` row when `auth.persistent_sessions` is on. That flag is `true` in `config/features.json:215`, giving verified sessions a 90-day rolling expiry (`server.py:2517-2664`).
  - Restore rebuilds the session from `row.user_id` alone (`server.py:2630-2652`).
  - So **any per-session marker is lost on restore**. Only a property of the id itself survives.
- **Minting a session.**
  - Sleeper username → `POST /api/extension/auth`. The user id comes from Sleeper's API, never the client (`server.py:34164-34246`). The session is unverified until `POST /api/sleeper/link` proves a Sleeper JWT (`server.py:26755`, `:26813-26820`).
  - Apple/Google → `/api/auth/apple|google` mints a verified session.
  - ESPN/MFL → `POST /api/entry/platform` proves platform ownership and mints the bound account (`server.py:34721-34772`).
- **Verified gates.** `_gate_unverified_write` and `_gate_unverified_read` (`server.py:2898-2956`) refuse private reads and writes unless `sess["verified"]`.
- **Session init.** `POST /api/session/init` → `session_input.resolve_session_input` (`session_input.py:17-105`).
  - It requires `body.user_id == sess.user_id`.
  - It finds the caller's roster with `find_user_roster(rosters, uid)` for Sleeper, or `league_members.user_id == uid` for imported ESPN/MFL leagues.
  - **League membership is derived from the account id.** A second account cannot "be" the operator in a real league unless this function learns an alias.
- **Device auth.** `identity_links` maps device → user (`database.py:2659`, `_link_device_identity` `server.py:17724`). It is analytics stitching only and never authorizes anything.

## 3. Tables keyed by user id

`database.py` has 63 tables. About 60 carry a user-ish column. Grouped by scope:

**Account-scoped** (`user_id` = the person). A test profile writes these under its own id, and a reset must cover them:
- Users and ranking: `users` (PK), `swipe_decisions`, `elo_history`, `user_player_skips`, `user_taste`.
- Trade decisions and the deck: `trade_decisions`, `trade_pass_reasons`, `trade_impressions`, `deck_impressions`, `deck_diagnostic_snapshots`, `deck_candidate_sets`, `trade_page_store`, `trade_deck_lineage`, `deck_card_withdrawals`, `deck_evidence_packs`, `deck_outcomes`, `deck_suppressions`, `deck_fatigue_resets`, `deck_replenish_log`.
- Prepared trades and projections: `prepared_trade_inventories`, `prepared_trade_targets`, `prepared_trade_manifests_v2`, `league_projection_targets`, `league_projection_runs`.
- Win-now, overhauls and preferences: `win_now_jobs`, `win_now_scenarios`, `win_now_decisions`, `overhauls`, `league_preferences`, `asset_preferences`.
- Offers and proposals: `standing_offers`, `trade_proposals`, `trade_offer_outcomes`, `offer_import_consents`, `revised_offer_cards`, `trade_policy_shadow`.
- Feedback and notifications: `bad_trade_flags`, `app_feedback`, `notifications`, `notification_prefs`, `notification_events_log`, `notification_queue`, `device_tokens`.
- Credentials and consent: `sleeper_credentials`, `espn_credentials`, `mfl_credentials`, `platform_write_consents`, `platform_write_moves`.
- Sessions, billing and sharing: `sessions`, `entitlements`, `subscription_events`, `paywall_previews`, `shared_packages`, `affiliate_clicks`.
- Rank sets, drafts and grading: `rank_set_adoptions`, `accuracy_scores`, `mock_drafts`, `receipts_grades`, `grading_sessions`, `grading_cards`.
- Events: `wrapped_events`, `user_events`, `identity_links`.

**Account-written but league-visible.** These are the leak risks:
- `member_rankings` (`:826`) feeds contrarian, format-stats, coverage and board history.
- `trade_decisions` likes are read league-wide for mutual matches.
- `user_events` feeds the league activity feed.
- `league_board_history` (`:2502`).
- `rank_sets` (`:3272`), which can be published.

**League-shared** (keyed on the team or owner id, written by every member's session): `league_members` (`:695`), `leagues` (`:591`), `trade_block` (`:734`), `manager_profiles` (`:807`), `draft_picks` (`:2039`), `league_roster_history` (`:2407`).

**Cross-user** (two people per row): `trade_matches` (`:871`), `referrals` (`:3208`), `trade_proposals.target_user_id`, `trade_impressions.target_user_id`, `bad_trade_flags.target_user_id`, `overhaul_offers.counterparty_user_id`.

## 4. Onboarding gates

### 4.1 Server ("has this user done X"), all keyed by `sess["user_id"]`

| Gate | Where |
|---|---|
| `users.first_init_pending` → `_is_new_user` on first `session_init` (league-join fan-out, referral credit, `signup_at`) | `database.py:6273`, `referral_ledger.py:100-120`, `server.py:30368-30410` |
| `GET /api/rankings/progress`: `unlocked`, `ranking_method`, `unlocked_formats`, counts, `anchor_required` | `server.py:16156`, `:16425-16441` |
| `GET /api/tiers/status`: `saved`, `all_done` | `server.py:18176` |
| `GET /api/account`: `verified_via`, `account_only`, `sleeper_username` | `server.py:37117` |
| `/api/me/streak`, `/api/me/entitlements`, `/api/ranking-method`, `/api/settings/*`, `/api/tiers/dismiss` | `server.py:15884`, `:41678`, `:16445`, `:16500`, `:16545`, `:33161` |
| Replayed swipes and tier overrides build the ranking state | `server.py:29993-30039` |

A fresh `qa_tp_<id>` account reads as new on every one of these, because none of its rows exist.

### 4.2 Client (device-persisted; most are untouched by `signOut`)

The navigator chooses its start screen once (`RootNav.tsx:464-469`, `:572`). It needs `navigationRef.reset` after a swap.

**Must be stashed and cleared on enter, and restored on exit:**
- SecureStore: `ftf.sessionToken`.
- `useSession` keys: `sleeper_user`, `sleeper_league`, `sleeper_leagues`.
- Onboarding and quickset: `ftf_onboarding_state_v1`, `ftf_tiers_saved_cache_v1`, `ftf_rank_method_pref`.
- Persisted query cache: `REACT_QUERY_OFFLINE_CACHE`.
- First-run screens and tours: `ftf_whats_new_seen_version`, `ftf_team_review_collapsed`, `ftf_team_review_completed`, `ftf_roster_setup_v1`, `ftf_pick_board_confirmed_v1`, `ftf_anchor_done_v1_<fmt>`, `ftf.trios.speedMode`, `ftf:tradecalc:v1`, `ftf:trades:fairness_on`, `ftf_active_format`, `ftf.premium_import.v1`, `ftf.rating.anchor_ts.v1`, `ftf_inapp_feedback_v1`.
- `ftf.events.queue.v1`. The queue must be flushed or split: queued events are sent under whichever token is current (`api/events.ts:295-320`).

**Already scoped by user id, so no action is needed:** `ftf_trade_queue_<uid>`, `ftf_outlook_strip_<uid>`, `ftf_paywall_offer_shown_<uid>`, `ftf_founder_welcome_shown_<uid>`, `ftf_new_partners_dismissed_<uid>_…`, `sleeper.link.jwt` (replayed only when its user id matches, `sendInSleeper.ts:143`).

**In-memory module caches.** These must be re-hydrated, or the app relaunched: `quicksetProgress`, `teamReviewCompletion`, `rosterSetup`, `premiumImport`, `useFeedback`, `useTradeQueue`, `calcTour`, `auth._sessionInitCompleted`.

## 5. Cross-user surfaces

The question for each surface: what happens if a test profile (account `qa_tp_X`) plays inside the operator's **real** league (league identity `X`)? The last column says what each of the two designs in §7 must do about it.

| # | Surface | What leaks under a live alias | Design A (live alias) needs | Design B (league snapshot) |
|---|---|---|---|---|
| M1 | Mutual match on like: `swipe_trade` → `find_mirror_like` → `create_trade_match` + `create_notification` + `_send_typed_push` to B (`server.py:23222-23350`; `database.py:12213`) | B gets a "match" notification and push from a ghost | Guard: skip the match for test profiles | No leak: league id is synthetic, B is not in it |
| M2 | Match disposition and expiry pushes (`server.py:28062-28340`, `:32310-32340`) | Follows from M1 | Covered by M1 | No leak |
| M3 | League-join peer fan-out on the first session (`server.py:30368-30410`) | Every league-mate, the real X included, gets "member joined" | Guard: no first-session side effects | No leak (synthetic league) — but still skip referral credit |
| M4 | Referral credit by league match: `claim_referral` notifies the referrer, inflates K-factor, sets `signup_at` (`referral_ledger.py:120`, `:232-270`) | Real referrer notified; K-factor and cron cohort polluted | Guard | Guard (credit by token still possible) |
| M5 | First-unlock fan-out to league-mates (`server.py:16368-16416`) | Inbox rows and pushes to real league-mates | Guard | No leak |
| M6 | `member_rankings` publishing → contrarian, format-stats, profile contrarian, coverage count, board history (`server.py:29190`, `:29274`, `:35860`; `database.py:12017-12127`) | A ghost "ranker" appears in league stats | Guard in each reader, or don't publish | No leak |
| M7 | League activity feed from `user_events` by league (`database.py:11537`, `server.py:29069`) | "qa_tp_… saved tiers" in friends' feeds | Guard in `load_league_activity` | No leak |
| M8 | Universal leaderboard (`database.py:5748`, `:5831`, `:5977`) | Appears globally | Guard | Guard |
| M9 | Push token registration: `device_tokens` PK = token, upsert moves `user_id` (`database.py:16437`, `server.py:31347`) | **The real X stops getting pushes** once the test profile registers the phone | Refuse registration for test profiles | Same guard |
| M10 | ESPN/MFL link and import write the caller's team into the league-shared `league_members` with full replace (`server.py:38003-38220`, `:38415-38431`, `:42213`, `:42440-42470`, `:44460`, `:44572`) | **Rewrites the real league's member row to `qa_tp_X`**, which breaks the operator's own ESPN/MFL binding (`session_input.py:49`) | Must become read-only aliased paths | Imports write only the namespaced copy |
| M11 | Own team treated as an opponent where the account id is compared to members (`server.py:22147-22150`, `:9083`, `:27885`, `:12917`) | Not a leak, but the test profile gets wrong decks (X's real board becomes a counterparty) | Swap to `_league_user_id` at 4 sites | Same 4 sites, or keep league identity == account id in the snapshot |
| M12 | Username lookups (`get_user_by_username` `database.py:15399`; `/api/profile/<username>`; referrals) | Duplicate username makes lookups ambiguous | Give the test profile a distinct username | Same |
| M13 | Standing offers read by `prepared_trade_runtime` (`prepared_trade_runtime.py:325`) | Ghost offers in others' prepared inventory | Guard | No leak |
| M14 | Likes-you injection (`server.py:9083`) and standing-offer injection (`:9278`) | Not injected: they require league membership by account id | — | — |
| M15 | Platform writes: `/api/trades/propose`, `propose-mfl`, `respond-mfl`, `propose-espn`, FA move, overhaul send (`server.py:26954`, `:43421`, `:43787`, `:44036`, `:41146`; `overhaul_api.py:958`) | Resolve credentials by account id, so they fail today. Under an alias they would **send real trades** | Explicit refusal with an in-app message | Explicit refusal (synthetic league ids also fail) |
| M16 | Crons: hourly digest and review (`load_all_signed_up_users`, `database.py:17633`), daily re-engagement, realtime match expiry, projections `connected_targets` (`outlook_calibration.py:667`), prepared-trade cohort (`prepared_trade_cohort.py:162`), value-model refit / eval (train on all decision rows) | Pushes to the test profile (harmless); test swipes **train shared models** | Skip `qa_` in each selector; exclude from training reads | Same |
| A1 | Analytics. `/api/events` takes `user_id` from the verified session (`server.py:17393`). `device_exclusion` already strips `qa_` (`analytics_queries.py:567`). Hand-written filters at `:754`, `:907`, `:978`, `:1140`, `:1170`, `:1495`, `:1725` do not | Some reports count the test profile | Add `qa_` to the hand-written filters (one helper) | Same |

Design A needs a guard at roughly **25 seams across ~15 functions** in `server.py`, `database.py`, `referral_ledger.py`, `prepared_trade_*` and `analytics_queries.py`. Each guard is a place where one missed call leaks to a real friend. Design B makes M1–M7, M10 and M13 impossible by construction. It needs only the guards marked "Guard" (M4, M8, M9, M12, M15, M16, A1).

## 6. Platform credentials and writes

| Platform | Storage | Key | Notes |
|---|---|---|---|
| Sleeper | `sleeper_credentials.token_encrypted` (`database.py:2857`) | `user_id` (working key) PK | Captured by `POST /api/sleeper/link`, which **requires the JWT's user id == the session's user id** (`server.py:26813-26820`). A second account can never capture X's JWT. |
| ESPN | `espn_credentials.swid` + `espn_s2_encrypted` (`database.py:2972`) | `user_id` PK | Link/import look it up by `sess["user_id"]` (`server.py:37893`, `:38307`, `:38357`). |
| MFL | `mfl_credentials.cookie_encrypted` (`database.py:2998`) | `user_id` PK | `_mfl_cookie_for` (`server.py:42413`) also falls back to `sess["mfl_cookie"]` (`:42427`). Never copy that key into a test session. |
| Device | `sleeper.link.jwt` (SecureStore, user-keyed); WebView cookie jar | — | `ftf.platformCreds` is dormant. `EspnConnectScreen` **clears ESPN cookies** before its WebView mounts, so the ESPN step always asks for an ESPN login. |

**Aliasing without copying secrets is possible.** It needs one server-side resolver: `credential_owner(sess) = real_id if is_test_profile(sess.user_id) else sess.user_id`. It would be used **only by read paths**: league listing, preview and snapshot import. **Write paths stay refused** (M15). No credential row is duplicated and nothing goes to the client.

**The ESPN step cannot be both "as a new user sees it" and "no re-entering credentials".** The real ESPN step is a WebView login that captures cookies. Two options:
- (a) Keep the WebView. The operator logs in to ESPN, and the server **discards** the posted cookies for a test profile and uses the stored ones.
- (b) For a test profile, the sheet skips the WebView and goes straight to the league list served from the alias.

MFL is the same choice: its step is a username/password form.

## 7. Designs considered

All three share:
- **Profile id** `qa_tp_<real working key>`.
  - Deterministic, so "is this a test profile" is a pure function of the id, and it survives durable-session restore (§2).
  - It inherits every existing `qa_` exclusion.
  - Unreachable by sign-up: Sleeper ids are numeric strings from Sleeper's API; account keys start `acct_`; demo keys start `demo_user_`; Test Stages mints `qa_` followed by 8 **hex** characters, and `t` is not hex.
  - Plus one explicit refusal in `_extension_build_session` and `upsert_user` for any id starting `qa_tp_` that is not minted by the switch route.
- **Gate:** env `TEST_PROFILE_ACCOUNTS` (comma-separated working keys) **and** flag `dev.test_profile`. Session-derived only: no device ids, no request-supplied target. Unset ⇒ 404 and a test-profile token is refused at `_get_session`.
- **Switch:** `POST /api/test-profile/enter` from a verified real session mints a verified session for `qa_tp_<sess.user_id>` and returns its token. The client **stashes** the real token and the device state from §4.2 under one key, clears them, and resets navigation to SignIn/LeaguePicker. `POST /api/test-profile/exit` revokes the test token. The client restores the stash; the real token is a durable 90-day session, so no re-login is needed.
- **Reset:** `POST /api/test-profile/reset` deletes every account-scoped table in §3 `WHERE user_id = qa_tp_<sess real id>`. It refuses unless the id passes `is_test_profile_id` and the caller's real id is allow-listed.
- **Banner:** a container-level banner in `RootNav.tsx` (beside `<Toast/>`, `:1230-1247`), with "Back to my profile" and "Reset test profile", mounted whenever the stash exists.

**Design A — live alias (what the brief literally asks for).** The test profile's league identity *is* X in X's real leagues, via an alias in `session_input`. Rejected as the default because:
- It needs ~25 guard seams (§5), and every missed seam reaches a real league-mate's phone.
- It changes league-shared rows (M10).
- It cannot meet "quick and easy".

**Design B — snapshot of the real leagues under a synthetic league namespace (recommended).**
- On enter and on the onboarding league steps, the server reads X's real leagues with X's stored credentials (read-only alias, §6). These are Sleeper by X's id, ESPN/MFL from X's `espn_credentials`/`mfl_credentials`.
- It builds the test session's leagues under ids `qa_tp:<league_id>`. Rosters, opponents and format are real; no league-mate can ever see them, because nothing they read is keyed on those ids.
- This is exactly the "Capture my leagues → templates" feature Test Stages already promises in the app and never got a server for. Making it live per session, not stored, is the extension.
- Guards left: M4, M8, M9, M12, M15, M16, A1.
- Costs:
  - Onboarding's link steps succeed against the real accounts, but the league ids the test profile sees are not the platform's own ids.
  - `session_input` needs a test-profile branch.
  - The Sleeper username step shows the operator's own username, resolved by the alias.

**Design C — Test Stages as-is plus a switch-back.** The smallest build: deterministic id, stash/restore, banner, full reset, still on the demo league. Rejected alone because it fails requirement 4 (real leagues). It is the first slice of B.

## 8. Why the build stopped: decisions needed

The brief says to stop after Phase 1 when a safe build needs an operator decision. Four do:

1. **Existing capability (coordinator's direction).** Test Stages exists and is the right base (§1). It does not meet requirements 2, 3 or 4. Its "Capture my leagues" button calls server routes that do not exist on `main`. Extending it changes its gate: env `TEST_PROFILE_ACCOUNTS` per account instead of device or checked-in ids. Decide whether the old random-`qa_` stage spawner stays alongside, or is folded in.
2. **A vs B.** Live alias (A) is what was literally asked for. It means ~25 guard seams in shared code paths, one missed seam pushes to a real friend, and it rewrites league-shared rows. Snapshot (B) uses the same real rosters and stored credentials, is isolated by construction, and is about a third of the work. B is recommended.
3. **ESPN/MFL link steps** (§6): (a) the operator types ESPN/MFL credentials into the real step and the server ignores them in favour of the stored ones, or (b) the test profile skips the credential form and goes to the league list.
4. **Pre-existing repo hygiene.**
   - `config/tester_allowlist.json` commits a real account id and a device id.
   - `/api/test-users` accepts a client-supplied `X-Device-Id` as an allow-list key.
   - Both conflict with this brief's rules. Decide whether to remove them in this change (the file is read by experiments and the stage spawner, so removing it may switch off other tester surfaces).

Once these are decided, the build plan for B is roughly:
- **Backend:** `backend/test_profile.py`, 4 routes, about 9 guards, and a `session_input` branch.
- **Mobile:** a stash/restore module, a banner, a Settings row, and an ESPN/MFL sheet branch.
- **Tests:** a backend test file covering every invariant in the brief, `check-test-profile.js`, and the sabotage table.

## 9. Build (Phase 2): base switch, code walk, TestFlight checklist

### 9.1 What the base switch is

1. **Built beside Test Stages; it does not replace it.** The random `qa_` spawner, its gate and the committed allow-list file are unchanged. The new row sits in the same Settings → Testing area.
2. **Design B: a private league namespace.** A test profile enters only `qa_tp:X:` leagues. Every other team in them is an opaque `qa_tpo_<hash>`.
   - The first build filled the namespace from DB copies through a forked Sleeper route and an ESPN/MFL shortcut. Both were removed after the 2026-11-11 ruling, not toggled.
   - Linking now runs the production flows (§11, §12).
3. **The new routes never use the tester allow-list.** Their gate is env `TEST_PROFILE_ACCOUNTS` matched against the session's user id, plus the flag `dev.test_profile`.

### 9.2 Code walk

Server line numbers are from `backend/server.py` in this worktree.

**Enter**
1. Settings → Testing shows the row only when `useTestProfile.available` is true (`TestingSection.tsx`). `available` is filled after boot from `GET /api/test-profile`.
2. Confirm → `enterTestProfile()` → `POST /api/test-profile/enter`.
   - The gate and a verified real session are required.
   - The route mints a session for `qa_tp_<sess.user_id>` through `_extension_build_session(..., test_profile=True)`.
3. On the device:
   - The real ESPN/MFL link status is read with the real token.
   - Real queued events are flushed.
   - Every AsyncStorage key except the flag cache and the two test-profile keys is stashed, along with the real token, last username and Sleeper-JWT slot.
   - The test token goes in, memory is re-read, and navigation resets to **SignIn** (a first launch).

**First launch inside the test profile** (requirement 6)

| Landing tile | In the test profile | Why |
|---|---|---|
| Sleeper username | **Real flow.** `signIn` sends the test token; `extension_auth` runs its normal lookup and then keeps the test identity (§12) | The Sleeper id is the app identity in production; the server branch is the only difference |
| Apple / Google | Refused client-side and server-side ("Not available in the test profile") | They mint or bind a real account identity |
| ESPN / MFL ("Link your … league") | Continues to the league picker as a brand-new account with that platform's link sheet open (`pinTestAccountForLinking`) | The landing entry (`/api/entry/platform`) resolves the platform identity to the operator's REAL account (D6), so it cannot run inside the test profile. The confirm sheet says so |
| Demo | Refused | It mints a demo identity |

**Back to my profile**
- `exitTestProfile()` ends the test session and drops test events and test device keys.
- It restores every stashed key, the real token and the JWT slot, then resets navigation as a cold start would and calls `revalidateSession()`.
- It re-reads the real ESPN/MFL link status. A link that was connected at enter and is not now raises the normal re-link prompt (`TestProfileRelinkPrompt`: EspnConnect `reason:'send'` / `MflSignInSheet`).

**Reset**
- The server evicts sessions and runs `reset_profile`. Its scope is derived from every table: user columns `*user_id`/`owner_id`/`actor`, and league columns `*league_id`. That covers the credential rows and namespaced leagues created by linking.
- The device drops the test keys and restarts at SignIn.

### 9.3 Manual TestFlight checklist

1. Settings → Testing shows **Test onboarding as a new user** on your account only.
2. Note one league, one saved tier board and that the tour is done.
   - Start. Expect a first-launch sign-in screen with the TEST PROFILE bar, nothing covered.
3. **Sleeper:**
   - A friend's username → "Use your own Sleeper username…".
   - Your username → the league picker lists your Sleeper leagues → pick one → the first-run flow → a deck.
   - The "Verify Sleeper account" button may show. Tapping it is not part of the test (the test session is pre-verified, and Sleeper JWT capture is fenced).
4. **ESPN:** Reset.
   - On the landing screen choose ESPN → "Link your ESPN league" → the league picker opens the ESPN sheet.
   - Sign in to ESPN in the web view (cookies are cleared first, as for a new user) → pick the league → the team → import → the first-run flow.
   - Try a wrong password and a private league you are not in. Expect the same errors a new user sees.
5. **MFL:** Reset → MFL → sign in with username/password → import → the first-run flow. A wrong password shows the production error.
6. A trade send from any test league → "Not available in the test profile".
7. Force-quit and reopen: still in the test profile.
8. Ask a league-mate: no joined / unlocked / match notification arrived.
9. **Back to my profile:** no sign-in.
   - Same league, board and tour as in step 2.
   - If ESPN or MFL ended your old session, a "Re-link ESPN/MFL" prompt appears. Use it.
   - Your real push still arrives.
10. Remove your id from `TEST_PROFILE_ACCOUNTS`: the row disappears, and Back still works from a phone left in the test profile.

## 10. Operator ruling 2026-11-11: real linking flows

### 10.1 The ruling

> "League linking is the one thing I really want to be able to test. I'm fine if that removes tokens from my actual account and forces a re-auth later. It's the least tested feature in the app." (operator, 2026-11-11)

Linking inside the test profile must be the **real production flows end to end**:
- **Sleeper:** username step and league discovery.
- **ESPN:** the web sign-in with its cookie clearing, the cookie capture, the league list and the import.
- **MFL:** the username/password form, the login, the league list and the import.

There must be no parallel "test" implementation. These requirements still stand:
- Isolation: Design B's namespace, with the remap at the storage boundary.
- Credentials stored for the test profile's own user and deleted by Reset.
- (a) A warning on the confirm sheet about real links that may need re-linking.
- (b) Detection of a broken real link on Back, with the normal re-link prompt.
- (c) Real league data, rankings and preferences never deleted (tested).
- Every other guard.

### 10.2 What was removed

The coordinator asked for removal, not a toggle. Removed:
- The ESPN/MFL shortcut: `TestProfileLinkPanel`, its two sheet hooks and `POST /api/test-profile/link`.
- The forked Sleeper step: `POST /api/test-profile/sleeper` and the SignIn intercept.
- The DB-copy code: `test_profile.snapshot_platform_leagues` / `list_test_leagues`, and the `/api/sleeper/leagues/<qa_tp_…>` short-circuit.
- The LeaguePicker "no Verify button for qa_tp_" tweak, since the real flow verifies.

The guards, the namespace rules, enter/exit/reset and the stash/restore all stay.

### 10.3 Where the real flows would have to branch

The production linking code does not read the platform and write storage at one seam. It uses the **same id** for the platform read, the DB write and the client's later requests, and it binds identity by the session's user id. Each site below would need a test-profile branch: either "read with the real id, write with `qa_tp:X:<id>`", or "compare against the alias".

**ESPN** (`espn_link` `:38041`, `espn_import` `:38548`, helpers):
1. `_espn_import_payload` (`:37792`): the read with the real id is fine as it is.
2. The member list: the caller's team gets `user_id`; opponents get `_espn_member_id(league_id, …)`.
3. `upsert_espn_league(league_id=…)`, in both routes.
4. `replace_espn_league_members(league_id, …)`, in both routes. **This is the real-league leak if left unmapped:** a full replace that would re-key the operator's own team row.
5. `_platform_roster_history_on_sync(league_id, …)` (`:31898`), in both routes.
6. The response's `league_id`, which the client stores and sends on every later call.
7. `_espn_verify_credential(user_id, …)` (`:37829`): the #321 binding check reads the caller's bound team from their league rows and calls ESPN with that league id. It would need the reverse map.
8. Post-link readers that call ESPN with the stored id: `_espn_standings_read` (`:24816`), `_espn_suggested_order` (`:24863`), `_detect_league_draft_status` (`:26467`), `_sweep_fetch_teams` (`:31970`, cron), `_overhaul_platform_rosters` (`:44847`). Each needs the reverse map or a refusal.

**MFL** (`mfl_link` `:42366`, `mfl_import` `:42515`, `mfl_auth_link` `:42710`, `mfl_auth_import` `:42887` → `_mfl_import_league_authed` `:42644`):
- The same four storage writes per import route: `upsert_platform_league`, `replace_espn_league_members`, `_platform_roster_history_on_sync`, `_sync_mfl_owned_picks`.
- `_mfl_store_scoring_format(league_id, …)` (`:42332`).
- The response ids.
- Reverse-map readers: `_refresh_mfl_future_picks` (`:26531`), draft status, and the sweep.
- `mfl_auth_link` also calls `upsert_user` + `mark_user_verified(user_id, …)`, which are keyed to the session: fine for the test profile.

**Sleeper**: the identity itself is the problem.
- In production the Sleeper user id **is** the app user. `extension_auth` (`:34202`) mints a session for that Sleeper id.
- `sleeper_link` (`:26780`) requires the JWT's user id == the session's user id.
- `session_input` finds the roster by the session's user id.
- League discovery (`sleeper_leagues` `:29477`), the roster proxies (`sleeper_rosters` `:29543`) and every session-init daemon consumer read Sleeper **by league id**, and the downstream deck/league routes do too: 9 direct `/v1/league/{id}` reads plus `_fetch_sleeper_league_meta`, `_sleeper_lineup_slots`, `_sleeper_roster_limit`, the trade-block, transactions, owned-pick and roster-history syncs.
- Sleeper opponents **are real app users** (their Sleeper id is their app id). So the remap must also re-key every member id, or the league-scoped fan-outs reach real league-mates.
- Seams needed: an identity alias in `extension_auth` + `sleeper_link`; a live-read-and-remap in discovery, the two roster proxies and `session_input`; and a reverse map at every Sleeper read keyed by league id (or blocking them, which breaks the deck's lineup/roster data).

**Entry sign-in** (`entry_platform` `:34863`):
- ESPN/MFL "sign in with" on the landing screen resolves the platform identity to an account through `linked_identities`.
- The operator's ESPN/MFL identity is already bound to the real account. The real flow would therefore sign the device **into the real account** (D6, `platform_identity_in_use`), not into the test profile.
- This path cannot be faithful without a branch that changes what the real flow does.

### 10.4 Decision needed (build stopped here)

Count: about 6 write sites + about 6 reverse-map read sites for ESPN, a similar set for MFL, and about 15+ sites for Sleeper plus an identity alias.

**Options:**
- **A. ESPN + MFL real flows now, Sleeper later.**
  - One helper, `test_profile.storage_league_id(sess, native_id)`, applied at the ESPN/MFL storage writes and response ids listed above.
  - One reverse helper, `native_league_id(lid)`, at the ESPN/MFL platform readers.
  - Tests cover every listed site.
  - Sleeper stays unavailable in the test profile, and the landing-screen ESPN/MFL sign-in stays refused (it would land in the real account).
  - Roughly one focused build.
- **B. All three via a session-level "platform alias".**
  - The test session carries `sleeper_user_id = X`.
  - `extension_auth`, `sleeper_link` and `session_input` compare against it, and one Sleeper read/write remap sits in `_sleeper_get` plus the league-member writer.
  - This is the largest and riskiest option: every Sleeper reader keyed by league id is affected, and one missed member re-key reaches a real league-mate.
- **C. Run the real linking flows on a real but separate account.**
  - The operator signs into Fleeced with a second Apple ID, so it becomes a new `acct_*` user, and links the same Sleeper/ESPN/MFL accounts from it.
  - Every production line runs unmodified.
  - The cost is the isolation guards: that account is a real user in the operator's real leagues (pushes, matches and joins to league-mates).
  - It could be combined with this build's guards keyed on an allow-listed `acct_` instead of `qa_tp_`.

**Facts that hold under any option.** These answer the ruling's (a)/(b)/(c); "Unverified" items cannot be checked offline.
- **Server credential rows are keyed by app user**:
  - `espn_credentials.user_id`, `mfl_credentials.user_id` and `sleeper_credentials.user_id` are all PKs.
  - A test-profile link writes its own row and never replaces the real account's.
  - Reset deletes it (the derived scope covers every `*user_id` column).
- **Device:**
  - `EspnConnectScreen` clears ESPN/Disney cookies from the device WebView jar before signing in. That never touches the server-stored pair.
  - `SleeperConnectScreen` is incognito.
  - `sleeper.link.jwt` is ONE SecureStore slot holding `{user_id, token}`. A Sleeper JWT captured in the test profile would overwrite the real one on the device, so the stash must cover it (add to `stashRealDeviceState`).
- **Platform side (unverified):** whether a new ESPN, MFL or Sleeper login invalidates the session the real account stored. ESPN and Sleeper are believed to allow concurrent sessions, and MFL to issue an independent cookie, but nothing offline proves it. That uncertainty is what (a)/(b) are for.
  - **(a)** The confirm-sheet line becomes: "Linking ESPN, MFL or Sleeper here signs in again on that platform; your real profile's link may need re-linking afterwards."
  - **(b)** After Back, call the existing `GET /api/espn/link`, `GET /api/mfl/auth-link` and `GET /api/sleeper/link` status reads. On `connected: false` or `expired`, show the existing reconnect prompt.
- **(c)** Under options A/B no write path touches the real ids, which the remap guarantees. A test would seed real leagues, rankings and preferences, run a full test-profile link and import of the same league, and assert those rows are byte-identical. That test belongs with the linking build.

**Failure paths and offline coverage today** (production tests and fixtures):

| Failure | Production code | Offline coverage |
|---|---|---|
| ESPN wrong password / rejected sign-in | `espn_bad_credentials` | `test_espn_identity_binding.py`, `test_link_status_routes.py`, `test_entry_platform_route.py` |
| ESPN pair from the wrong account (#321) | `reason: wrong_account` | `test_espn_identity_binding.py`, `test_platform_sign_in.py` |
| ESPN private league without access | `espn_auth_required` | `test_espn_link_route.py`, `test_espn_my_leagues_route.py` |
| ESPN cookies incomplete / expired cookie | `espn_cookies_incomplete`; expired = `espn_bad_credentials` | `test_espn_link_route.py` (incomplete); expired is only reachable live |
| ESPN outage | `espn_unavailable` | 8 files |
| MFL wrong password | `mfl_bad_credentials` | `test_mfl_auth_link_route.py` |
| MFL missing fields | `mfl_missing_credentials` | `test_mfl_auth_link_route.py` |
| Zero leagues found | empty list | `test_espn_link_route.py` and the `fresh` UI profile |
| League already linked (by another user / the real account) | no dedicated error code in the link routes | **not covered**; under a remap it would not collide, and that needs its own test |
| Sleeper unknown username / Sleeper down | 404 `user_not_found` / 503 `sleeper_unavailable` | `test_launch_qa_fixes.py` covers unavailable only |
| Sleeper JWT for a different user | `token_user_mismatch` | `test_verified_sessions.py` |
| Real ESPN/MFL/Sleeper session invalidation by a new login | platform behavior | **cannot be covered offline** |

### 10.5 Decision (2026-11-11)

The coordinator chose **option A** and rejected B ("one missed re-key reaches a real league-mate"); C is not a build. Sleeper was first left out, then brought in by the 2026-11-12 ruling (§12).

## 11. Option A: real ESPN / MFL linking

**The seams.** Both live in `backend/test_profile.py` and are tiny pure functions:
- `storage_league_id(session_user, real_id)` is the WRITE seam.
  - It returns the real id itself for every real user (`is`-identical, tested).
  - For `qa_tp_X` it returns `qa_tp:X:<real_id>`, and it is idempotent.
- `native_league_id(stored_id)` is the READ seam: identity outside the namespace.

**WRITE call sites.** There is exactly one `store_lid = _tp.storage_league_id(...)` per linking function. Every storage writer and the response `league_id` use `store_lid`:
- `espn_link` (`server.py:38521`)
- `espn_import` (`:38695`, reading `native_league_id` first)
- `mfl_link` (`:42538`)
- `mfl_import` (`:42658`)
- `_mfl_import_league_authed` (`:42793`, which serves `mfl_auth_import`)

The writers are `upsert_espn_league`, `upsert_platform_league`, `replace_espn_league_members`, `_platform_roster_history_on_sync`, `_sync_mfl_owned_picks` and `_mfl_store_scoring_format`. The AST guard `test_every_linking_write_site_goes_through_the_write_seam` fails if any function anywhere in `server.py` calls one of them without being one of:
- the seamed routes;
- the stored-id callers (`session_init` and its daemon, `_refresh_league_draft_status`, `mfl_leagues`);
- the fenced Fleaflicker routes.

**READ call sites:**
- the platform URL builders `espn_service.league_url` (`:94`), `mfl_service.export_url` (`:306`) and `mfl_service.resolve_host` (`:138`) — every ESPN/MFL league read in the codebase goes through one of them;
- ESPN credential verification's linked-league list (`server.py:38018`);
- the two re-sync routes (above).

**Storage re-key.** `replace_espn_league_members` / `upsert_league_members` / `write_session_init_members` pass every member id of a namespaced league through `masked_member_id`. Opponents become opaque `qa_tpo_<hash>`; no `espn:<swid>` or `mfl:<league>…` survives.

**Credentials.**
- `espn_credentials`, `mfl_credentials` and `sleeper_credentials` are keyed by APP user, so a test-profile link writes its own row and Reset deletes it.
- The real account's rows cannot be touched. `test_linking_the_same_leagues_writes_nothing_real` and the scan prove it byte-for-byte.
- What can affect the real account: **only the platform side**. If ESPN or MFL ends older sessions when the operator signs in again, the real stored cookie stops working. That is unverifiable offline. The confirm sheet warns about it, and Back re-reads the real link status.
- Limit: GET `/api/espn/link` and GET `/api/mfl/auth-link` report the stored row, not a live probe. A platform-side invalidation therefore surfaces at the next send (the production reconnect prompt), not on Back.

**Failure paths** — the test profile gets byte-identical responses to a brand-new real user (`test_failure_paths_match_a_new_real_user`, `test_wrong_espn_account_is_refused_for_the_test_profile_too`):

| Failure | Production response | Covered offline by |
|---|---|---|
| Incomplete ESPN cookies | 400 `espn_cookies_incomplete` | recorded fixture + parity test |
| Private league without access | `espn_auth_required` path | fixture + parity test |
| ESPN rejected sign-in ("wrong password") | 403 `espn_bad_credentials` | parity test |
| Wrong ESPN account (#321) | 403 `espn_bad_credentials` + `reason: wrong_account` | parity test; exercises the read seam |
| ESPN outage | 502 | parity test |
| Zero ESPN leagues | 200 `{"leagues": []}` | parity test |
| MFL wrong password / missing fields / outage | `mfl_bad_credentials` / `mfl_missing_credentials` / 502 | parity tests |
| Expired ESPN cookie | 403 at the next read | **live only** |
| Platform invalidating an older session | — | **live only** |

**Finding, not fixed here: "league already linked".** Production has no handling. When a second FTF user links the same ESPN/MFL league:
- `replace_espn_league_members` rebuilds the whole league with only the CALLER's team keyed to them, so the first linker's member row becomes a synthetic id;
- `upsert_espn_league` overwrites the league-level `espn_my_team_id`.

So the first user loses their binding, which is a real user-facing bug for leagues with two FTF users. Fixing it needs a per-user team binding (a schema change), so it is an operator decision. The test profile is immune because its rows are namespaced.

## 12. Operator ruling 2026-11-12: real Sleeper linking

> "I want to cover sleeper testing too." (operator, 2026-11-12)

The production Sleeper path runs inside the test profile: username lookup, league discovery, roster resolution, session init and the first deck. It is protected by three defences, and a decisive scan proves them.

**1. Split identity.** `server._sleeper_identity(sess)` (`:2850`):
- For every real session it returns the session user id. That is pinned for `313…`, `acct_`, `demo_user_`, `qa_` and `""`.
- For `qa_tp_X` it returns X, or the Sleeper id bound to account X. It is derived, so it survives restarts, and it is never stored.

Its sites:
- `extension_auth` (`:34348`): runs the normal lookup, then keeps the test identity and accepts only the operator's own Sleeper user;
- `sleeper_leagues` discovery (`:29510`): the same read with X, ids returned namespaced;
- the `rosters` / `league_users` proxies (`:29584`, `:29637`): the same live read with the native id, re-keyed;
- `session_input` (`:77`, `:89`): `find_user_roster(rosters, sleeper_uid)`.

`test_sleeper_reads_with_a_session_id_go_through_the_accessor` pins those sites. Every other site that reads Sleeper rosters with a session id is a platform write path, fenced for the test profile: the propose core `_roster_id_for_owner`, offer import and FA move.

**2. Storage re-key at the boundary.**
- `session_input` masks every member id and the owner id. The operator's roster becomes the profile even when the operator is a co-owner (the fixture case).
- The proxies mask what they return.
- The DB member writers mask again. `test_a_missed_rekey_is_still_masked_at_the_member_writer` shows a missed upstream re-key is still caught at the write.

**3. The outbound chokepoint.** `test_profile.outbound_blocked` sits in the narrowest writers. It drops any delivery touching the test world — the request actor is a test profile, the league is namespaced, or the payload names a test id — to anyone but the profile itself:

| Chokepoint | Where |
|---|---|
| Push | `_send_typed_push` (`server.py:31356`) — the only typed push entry; the raw Expo sender is reached only through it and the queue drain |
| Inbox row | `create_notification` (`database.py:14916`) — the single `notifications` insert; `push_notification` delegates to it |
| Join coalescer | `create_or_coalesce_league_join_notification` (`:15014`) |
| Queued notification | `queue_notification` (`:17545`) |
| Match | `create_trade_match` (`:12385`) — raises `OutboundBlocked` |
| Referral credit | `claim_referral` (`:15617`) |
| Platform writes | `_sleeper_propose_core` (`server.py:27083`), `_fa_move_core` (`:41211`), `_mfl_propose_core` (`:43848`), `_espn_propose_core` (`:44461`) — overhaul sends go through these cores |
| Email | none exists in the codebase |

The request actor is set in `_test_profile_request_guard` and reset at teardown. Background writers carry no actor and are caught by the league/payload checks (tested).

**Background readers** (requirement 5):
- Projections registration is skipped for test leagues (`:30416`; the scan asserts `league_projection_targets` stays empty).
- The cron cohort, prepared-trade cohort, calibration targets, eval/value-model spine, leaderboard, analytics, and now the global F2 like-rate and F7 audition counts all skip `qa_`.
- The documented `_sleeper_get` bypass fetchers refuse a namespaced id: `trade_block_service.fetch_league_players` / `_fetch_rosters`, `sleeper_trades_service.fetch_week_transactions`, `suggestion_telemetry.fetch_league_roster_map`.
- `_sleeper_get` refuses any `qa_tp` URL (`:617`). It is the last line for every reader that reaches Sleeper with a stored id: lineup slots, roster limit, draft board, outlook, free agents, standings, roster refresh and win-now. Those degrade for a test league rather than call Sleeper.

**The decisive scan** (`test_full_sleeper_onboarding_reaches_nobody_and_writes_nothing_real`):
- **Setup:** the co-owned-league capture with synthetic ids. The operator and all eleven league-mates are app users with push tokens, and the operator already synced, ranked and saved preferences.
- **Run:** enter → username → discovery → rosters/users → session init → first deck (6 cards, 12 deck impressions, 12 trade impressions written).
- **Scan, over every table derived from `database.py`:**
  - (a) no test row carries a league-mate id, the real league id, or the operator's real id outside the namespaced ids;
  - (b) every user- or league-keyed real row is byte-identical;
  - (c) zero Expo sends, zero `notifications`/`trade_matches` rows, the push token unmoved, no projection target.
- The same scan runs for ESPN and MFL (`test_espn_and_mfl_onboarding_scan`).

**Layering, as the sabotage runs show it.** Each delivery path has two or three independent guards. Removing one guard is caught by a test aimed at that guard, not always by the scan:
- **Join fan-out:** guarded by the session-init test-profile check, the member re-key and the chokepoint. A seeded missed re-key plus the outer check removed goes red (S12, S12b).
- **Referral:** guarded by the session-init drop, the `claim_referral` refusal and the chokepoint. All three must be removed before the test goes red (S11).
- **Chokepoint alone:** removing it leaves the onboarding scan green (P2a). No onboarding path reaches it while the earlier layers hold. Its own test catches its removal at every writer (P3–P5).
- **Re-key:** removed everywhere ⇒ scan red (P6). Removed in `session_input` only ⇒ its own test red (P8, P8b). Removed at the DB writer only ⇒ writer test red (P7).
- **`league_projections.batch.register`** already refuses a non-numeric league id, so the server-side projection skip is belt-and-braces. No sabotage can turn it red.

**Real account effects (requirement 7).**
- Signing in with the same Sleeper username in the test profile writes nothing for the real account:
  - no session minted;
  - no `identity_links` row (the branch returns before `_link_device_identity`);
  - no users row change.
- Sleeper has no password in this flow.
- The device Sleeper-JWT slot is stashed and restored.
- The test session is pre-verified, so Sleeper's JWT capture (`/api/sleeper/link`) is not part of the test and stays fenced. That is a gap: the "Verify Sleeper account" step a new user meets is not exercised.

**Requirement 8 — sites that could not run unchanged:** none blocked the build. Every changed site is a branch on `_tp.is_test_profile_id` / `_tp.is_test_league_id`, or a call through the accessor or a seam that is the identity for real users. The full suite plus the identity test cover them.

## 13. Review findings and fixes (2026-11-12)

An independent read-only review found four medium and seven low gaps. In each, a guard covered the normal client path but not an edge path, or a test was stronger than production. Every fix has a test, and every test was sabotage-proven (red on the break, green on restore, checksum verified).

Tests are in `backend/tests/test_test_profile_review.py` (R) unless named otherwise.

### M1 — the request fence was bypassable with a non-JSON body

**Fix 1: the fence reads every request source.**
- `server._tp_request_league_ids` (`:37070`) reads path args, the query string, form fields, and the body parsed the way routes parse it (`get_json(force=True, silent=True)`, so any content type).
- `_tp_collect_league_ids` (`:37053`) collects every `league_id` / `league_ids` / `*_league_id(s)` / camelCase key at any depth. Comma-joined lists are split.
- Platform-native link inputs are exempt only on the three linking routes (`_TP_LINK_INPUT_KEYS`, `:37044`).

**Fix 2: default-deny at the database.**
- `database._tp_write_fence` (`database.py:89`) is registered on the SQLAlchemy `Engine` class, so it covers every engine, including test engines.
- It calls `test_profile.check_write` (`test_profile.py:288`). That function refuses any INSERT/UPDATE/DELETE made while a test profile is the request's ACTOR if a bound value of one of the statement's own `*league_id` columns is outside the actor's namespace.
- It catches writes no request-shape scan can foresee. A real request pays one contextvar read.

**Pre-existing gap, fixed:** `submit_rankings` (`:28957`) now requires membership for every caller: the session's own league, or a stored `league_members` row.
- Safe for real flows: no client calls the route (mobile, web and the extension were grepped). The default is the session league, which always passes.

**Tests:**
- `test_fence_reads_every_request_source`: text/plain, no content type, nested, list, camelCase, `league_ids` body and query, form.
- `test_linking_inputs_stay_open_only_on_the_linking_routes`.
- `test_database_write_fence_denies_a_test_request_under_a_real_league`: insert, executemany, and an UPDATE of a real league.
- `test_submit_rankings_requires_league_membership_for_every_caller`.

**Not covered by the DB fence:** raw `text()` SQL. The request fence is the guard there.

### M2 — background sweeps over `leagues` were not all guarded

**Fix:**
- Loader-level exclusion via `database._not_test_league` / `_not_test_user` (`database.py:97`) in:
  - `load_history_sweep_leagues` (`:16161`);
  - `load_league_ids_for_draft_status_refresh` (`:13851`);
  - `load_active_deck_user_leagues` (`:8026`);
  - `load_pending_matches_older_than` (`:17689`).
- Belt and braces at the two places the history sweep could still be reached:
  - `_sweep_fetch_teams` returns `(None, "test_profile")` (`:32578`) and never reads a platform with the test profile's cookies;
  - `_do_league_history_snapshot`, the shared tail of all three history triggers, refuses a namespaced league (`:32437`).
- `_do_league_history_snapshot` wrote two tables: `league_roster_history` (`snapshot_league_rosters`) and the board history (`snapshot_league_boards`). Both are now unreachable for a test league.

**Test:** `test_background_loaders_and_the_history_sweep_skip_test_leagues`.

**Audit of every background reader:**

| Path | Walks | Verdict |
|---|---|---|
| Roster-history sweep (daily tick, `/api/cron/roster-snapshot`) | `leagues` | **fixed now**: loader exclusion, adapter and writer refusal |
| Draft-status sweep (hourly tick) | `leagues` | **fixed now**: loader exclusion; `_refresh_league_draft_status` also returns early |
| Weekly replenishment (daily tick) | `trade_decisions`, `trade_impressions` | **fixed now**: loader excludes `qa_` users and `qa_tp:` leagues |
| Pending-match reminders (realtime tick) | `trade_matches` | **fixed now**: loader exclusion; matches cannot be created anyway (`create_trade_match` raises) |
| Digests, reviews, re-engagement (hourly and daily ticks) | `users` | skips: `load_all_signed_up_users` excludes `qa_` |
| Quiet-hours queue drain | `notification_queue` | cannot see: `queue_notification` refuses test rows |
| Device-token loads | `device_tokens` | cannot see: push registration is skipped for a test session |
| Sleeper offer import (daily tick) | `offer_import_consents`, `trade_offer_outcomes` | cannot see: the consent and offer-import routes are fenced; sends are refused |
| `load_member_sleeper_leagues` | `league_members` by a real member id | cannot see: test-league members are `qa_tp_` / `qa_tpo_` |
| Trade outcomes (daily tick) | `trade_offer_outcomes` | cannot see: written only by sends, which are refused |
| Receipts grading | captured completed trades | cannot see: capture reads Sleeper, which refuses namespaced ids |
| League projections dispatch | `league_projection_targets` | cannot see: `register` refuses a non-numeric league id; the server also skips |
| Prepared-trade cohort | users | skips `qa_` (`prepared_trade_cohort`) |
| Eval nightly, value-model refit | impression spine | skips `qa_` (`eval/data.load_decks`) |
| Outlook calibration | connected targets | skips `qa_` |
| Leaderboard (incl. streak board) | users | skips `qa_` after over-fetch |
| Global like-rate, archetype counts | decisions | skip `qa_` |
| Community diff, risers/fallers, consensus gap, market movers | consensus pool, per-user elo history, per-league community Elo, value snapshots | cannot see: none aggregates other users' boards across leagues; per-league reads only reach a test league for its owner (L6) |
| Usage-trends refresh, players guard, rookie monitor | nflverse / players | no user or league data |
| Deletion scrub | scrub jobs from real deletions | cannot see: a test profile cannot delete an account (fenced) |
| Boot backfills (`_backfill_*`) | users / leagues | reshape rows in place; reach no other user |
| Cleanup loop | sessions, durable sessions | now also evicts closed-gate test sessions (L2) |

### M3 — a dead test token minted a REAL session

**Server:**
- Every test token now carries `_TP_TOKEN_PREFIX` (`"tp."`, `:2769`). `'.'` is outside `token_urlsafe`'s alphabet, so no real token can carry it.
- `extension_auth` answers **401 `test_profile_ended`** to a prefixed token that does not resolve to a live test session (`:34875`). It never falls through to a mint.

**Client:**
- `api/client.testProfileAuthHeaders` refuses sign-in inside the test profile unless `GET /api/test-profile` says `active`.
- Any 401 while in the test profile marks it ended.
- `state/testProfile.verifyTestProfileWithServer` asks the server after boot.
- The banner then reads "TEST PROFILE ENDED" and offers only "Back to my profile".

**Tests:**
- `test_test_profile_sleeper.py::test_a_dead_test_token_never_mints_a_real_session` (a real sign-in without the token is unchanged);
- `check-test-profile.js` 2b1–2b4.

### M4 — the device swap was not crash-safe

**Fix:**
- The swap is now the phased state machine in `mobile/src/utils/testProfileSwap.ts`, which has zero runtime imports.
  - `SWAP_KEY` names the phase in progress.
  - `STASH_DONE_KEY` marks a complete stash.
  - `ACTIVE_KEY` is written only after the stash and the token swap complete.
  - Originals are removed only after the stash is complete.
- Exit always rolls forward and drops test keys only while the stash is complete. A restore never clears the current token unless it is a test token. Restore and drop are idempotent, and with no stash nothing is dropped.
- `hydrateTestProfile` runs `reconcileSwap` **first** in App.tsx's boot gate, before any other storage read. It also repairs a mixed state: ACTIVE with a real token, or a stray test token.

**Test:** `mobile/tests/check-test-profile-swap.js` (`npm run test:test-profile-swap`) executes the real module against an in-memory store.
- It kills enter, exit and reset after every single operation. Then it kills the relaunch's reconcile at every point and reconciles again.
- It asserts the outcome is always fully real or fully test, never mixed, and never with the real token lost.
- It also replays the review's two concrete bugs. Total: 3,364 checks.

### Low findings

| Finding | Fix | Test |
|---|---|---|
| **L1** substring matches | `test_profile.is_test_world_id` / `names_test_id` (`:204`, `:219`) match exact `qa_tp_<real id>`, `qa_tp:<real id>:…`, `qa_tpo_<16 hex>` in id FIELDS only. Callers now pass structured payloads, not JSON strings. `_sleeper_get` checks URL path segments (`_tp_url_names_test_id`, `:611`). The bypass readers use the exact `qa_tp:` prefix | `test_real_names_that_contain_the_text_are_not_test_ids` |
| **L2** direct `_sessions` readers after the kill switch | `_tp_evict_closed_sessions` (`:2785`) runs on flag reload and in the cleanup loop; `_get_session` evicts on sight | `test_closing_the_gate_evicts_test_sessions_from_memory`, `test_a_test_session_under_a_real_style_token_is_refused` |
| **L3** existence signal | `GET /api/test-profile` and `/enter` are 404 unless the session is verified AND allow-listed | `test_test_profile.py::test_enter_requires_a_verified_real_session` |
| **L4** reset races and cost | Reset runs inside `accounts.deletion_scope` (the account-deletion drain, `:37283`): it waits for in-flight leases and then `invalidate`s, so pre-reset work can never write. Trade jobs naming the profile are revoked; module caches are purged (`_TP_KEYED_CACHES`, `:37172`). **Postgres cost:** the old one-transaction, 60-table `LIKE` scan is gone. The profile's leagues are listed once from `leagues` + `league_members` (the only prefix scan, on two small tables); every table is then deleted by `=` / `IN`, which uses indexes such as `ix_user_events_user_occurred`, in its own short transaction, so no lock outlives one table's DELETE. Not measured on Postgres (no production access); reasoned from the predicates and indexes | `test_reset_invalidates_pre_reset_work_and_purges_caches`; `test_test_profile.py::test_reset_deletes_only_test_rows_across_every_table` (look-alike ids survive) |
| **L5** real identifiers in test rows | **Fixed:** history rows (`team_key` with the real league id, ESPN `espn:<SWID>` member keys) are no longer written for a test league (M2). **Acceptable, stated:** league-mates' usernames and display names (`mask_sleeper_users`, `league_members.username` / `display_name`, ESPN `owner_display`, usage-trends owner rows) stay in the test profile's own rows and responses. They are the operator's own league-mates, the same names the operator sees in the real profile, and no one else can reach them: every read of a `qa_tp:` league by anyone but its owner is now refused (L6) | — |
| **L6** unauthenticated proxies | The fence refuses any real or anonymous request that names a `qa_tp:` league (404) in its path, query, or a body of at most 8 KB. A raw-bytes pre-filter keeps it free for every other request. The fence never reads a larger body, because capped routes (projection runs 8 KB, feedback 64 KB, events 128 KB) must answer 413 before any read. A test walks every route cap in `backend/` and fails if one is ever smaller than the limit. A larger body naming a test league from a real caller is not refused here; `session_input` refuses entering it and `submit_rankings` requires membership | `test_real_and_anonymous_callers_cannot_name_a_test_league` |
| **L7** per-request cost | A non-prefixed token is decided without a lookup. **Cost now:** a real request's fence is one `startswith`, a substring check on the path and query, and one substring check on the cached body bytes (Werkzeug reuses them for the route's own parse), and only for a body of at most 8 KB (`_TP_BODY_SCAN_LIMIT`, the smallest route cap); a larger body is never read by the fence. The fence parses the cached bytes itself and never leaves a JSON parse in Werkzeug's cache, so a route's own non-forced `get_json()` behaves exactly as without the feature. The pre-existing `_acquire_user_data_lease` hook still does its own `_get_session`, as before this feature | `test_the_fence_never_looks_up_a_real_token`, `test_the_fence_never_reads_a_body_past_the_smallest_route_cap` |

### Tests now match production

- **Real threads:** `test_test_profile_sleeper.py::test_background_threads_hold_isolation_without_the_request_actor` runs the session-init daemon and the trade jobs on real threads against a file database. It asserts ACTOR is `None` inside both, and that the full decisive scan still holds. Isolation rests on the namespace and the re-key, not on the contextvar.
- **Lowest sender:** `init_harness` now patches only the Expo transport (`_send_expo_push`), and league-mates have device tokens, so the `_send_typed_push` chokepoint runs as in production.
- **Reset coverage:** `test_reset_scope_covers_every_identity_column_in_the_schema` enumerates the schema with a broad identity pattern. Each match is either covered or listed with a reason.
  - It found these columns missing and the reset now covers them: `user_a_id`, `user_b_id`, `created_by`, `recorded_by`, `assigned_by`, `creator`, `username`.
  - The delete test classifies rows independently of the code and seeds look-alike ids (a profile id with one more digit, a namespace without the colon) that must survive.
- **ACTOR reset on exception:** `test_actor_is_reset_when_the_request_raises`.

### Layered guards the sabotage table shows as backstops

Three removals leave their test green because another layer still holds. They are recorded as expected:
- **Chokepoint alone** (P2a): the outer guards and the re-key hold.
- **Join fan-out outer guard alone** (S12): the inbox and push chokepoints drop the delivery. S12b removes both and goes red.
- **Exit's "dropped" phase marker** (M17): the stash outlives the restore, so a replayed drop is re-restored.

## 14. Second review, and the per-user binding merge (#666)

**Second review (real users), four low fixes:**
- **Body scan limit.** `_TP_BODY_SCAN_LIMIT` is now 8192 bytes, the projection-runs route's cap (`league_projections/api.py`). `test_the_body_scan_limit_is_at_most_every_route_cap` walks every `content_length` cap in `backend/` and fails if a future cap is smaller.
- **No cached parse.** The fence parses `get_data(cache=True)` with `json.loads` itself. A route's own non-forced `get_json()` on a wrong content type still returns None or 415. Pinned by `test_a_wrong_content_type_request_behaves_as_without_the_feature`.
- **Purge locking.** `_TP_KEYED_CACHES` pairs each cache with the lock its own readers and writers hold: `_trade_jobs_lock` for `_trade_jobs_by_key` and `_roster_moved_reads`, plus the outlook, usage, slot-order, pick-projection, trade-block and gate-miss locks. `_session_init_inflight` was dropped: its keys are tokens, so the purge never matched it. Pinned by `test_the_cache_purge_takes_each_caches_own_lock`.
- **Flag reload.** `feature_flags_reload_route` wraps the eviction like the cleanup loop does. Pinned by `test_a_failing_sweep_never_fails_the_flag_reload`.

**The #666 merge.** #666 is the fix for the "league already linked" finding (§11). It adds `platform_league_bindings` (user, league) → team.

Conflict resolutions in `server.py`:
- In `espn_import` and `mfl_import`, both intents are kept. The native id comes from the body, the row is read under `store_lid`, and `get_platform_binding(user_id, store_lid, …)` is read under the same stored id the link wrote it under. The league upsert keeps `league_id=store_lid` and takes #666's `user_id=user_id`.
- `docs/plans/README.md` keeps both rows.

Making the two features correct together:
- A test profile's link writes its own binding `(qa_tp_X, qa_tp:X:<native>)` through the existing write seam. The database write fence refuses any binding a test request would write under a real league id.
- `_labels_from_binding_rows` keys labels by the native id, because member dicts carry the platform-native `team_key` in a namespaced league too. The profile's own team is therefore labelled with the profile's id. A label never crosses worlds: a namespaced league takes only its own profile's label, and a real league never takes a test-world id.
- Reset covers the new table automatically: it has `user_id` and `league_id` columns. Sabotage B5/B5b (excluding the table from `reset_scope`) turn the reset test and the schema-driven coverage test red.
- The reset's `_by` rule now covers `founder_label_overrides.set_by` (from `main`). `invited_by` is excluded on purpose: it names the referrer on the invited user's own row.

Tests:
- `test_founder_bound_in_the_real_league_then_the_test_profile_links_it` (the two-user case);
- `test_binding_labels_never_cross_worlds`;
- `test_reset_removes_the_profiles_binding_rows_only`;
- the AST seam test, which now also requires binding reads in the linking routes to use `store_lid`;
- the ESPN/MFL scan, which now asserts the binding rows.
