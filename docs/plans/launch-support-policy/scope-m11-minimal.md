# Feature Scope — M11 minimal path: claim-only "Delete account" for unverified ESPN/MFL entry sessions

**Date:** 2026-10-24
**Entry point:** direct ask: `head-eng`'s ruling (2026-10-24) on launch MUST M11. This is an addendum to [scope-m11-entry-ownership.md](scope-m11-entry-ownership.md) (PR #354 at `3ca8383c`, branch `plan/launch-support-policy`), which stays the full design.
**Builder:** `onboarding-eng`, server half (branch `feat/m11-entry-delete`). The mobile half follows once its copy is ready.
**Operator sign-off on waivers:** W-M11-1 and W-M11-2, signed by the operator and relayed 2026-10-23 (relayed to `onboarding-eng` by its lead).

## 0. What ships for launch, and what doesn't

- **Ships (launch):** M11-R5's "Delete" for an unproven claim. `DELETE /api/account` from an
  **unverified** session whose `user_id` starts with `entry:` (`entry:espn:…` / `entry:mfl:…`)
  runs a **claim-only delete** instead of `_account_data_gates`' 403:
  1. it requires body `{"confirm": "delete"}` (400 `confirmation_required` otherwise; nothing
     changes), so a stray call can't end a session;
  2. it removes what **this device** wrote for the id: its `identity_links` rows and the
     `user_events` with this `device_id`. The device id is read from body `device_id` or the
     `X-Device-Id` header, the derivation `_link_device_identity` uses; with neither, those rows
     are skipped and their counts are `null`;
  3. it ends **this** session the way `/api/session/signout` does;
  4. it touches nothing else: no `users` row, rankings, swipes, league or member rows, or another
     device's links and events. An entry id is deterministic from public league data, so that data
     may be another person's.
  - Response: `200 {"ok": true, "deleted": "session_only", "removed": {"identity_links": n, "user_events": n, "push_tokens": 0}}`.
  - **Push tokens:** none to remove. `device_tokens` is keyed by the Expo token, not the device, and
    `POST /api/notifications/register-device` is write-gated, so an unverified session can never
    have stored one.
- **Unchanged:** every other unverified session still gets the 403 (M11-R4); verified sessions,
  including a future proven `entry:` session, keep the full deletion matrix; `GET /api/account/export`
  stays gated for every unverified session.
- **Deferred to post-launch:** the proof design, M11-R1 (proven entries minted verified) and M11-R2
  (step-ups routed by user-id prefix), plus the M11-R5 mint change (no users row for an unproven
  claim). Until then an unproven claim's server rows written by the mint and by session init stay
  in place, as they are today; the claim-only delete is honest about that ("session only").

## 1. Analytics scope

- [x] **(c) WAIVED (W-M11-1, signed):** no new event. The branch is a server-side variant of an
  existing route; the stuck-user count still comes from the `AUTH-DENY` log lines, and the
  claim-only path logs `delete_account: claim-only …` with its counts.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** One new query helper,
  `backend/database.py:delete_device_claim_rows`, over existing tables.
- New/changed feature flags: **none** (W-M11-2, signed). The branch is unflagged; the rollback is a
  revert of the server commit, after which entry sessions get today's 403 again.
- New env vars / `model_config` keys: **none.**
- **Not express-lane:** `DELETE /api/account`'s contract changes for one session class.

## 3. Evidence scope

D-056: no simulator, no Maestro, no captures.

- [x] **Unit tests:** new `backend/tests/test_account_delete_entry_claim.py` (12 tests, on
  `test_account_data_rights.py`'s fixture):
  - unverified `entry:mfl:` and `entry:espn:` with the confirm → 200; this device's link and events
    are gone, and the next call with the token is 401;
  - another device's link and events for the same id, the server-fired (device-less) event, the
    users row and the rankings are untouched;
  - the device id is read from the body too; with no device id only the session ends (counts null);
  - no or wrong confirm → 400, nothing changes, the session stays live;
  - an unverified Sleeper-username session → still 403;
  - a verified session, and a verified `entry:` session → the full deletion;
  - export for an unverified entry session → still 403.
  - **Sabotage:** dropping the device filter on `user_events`, or on `identity_links`, fails 4 tests
    each, including "other device untouched"; letting the branch catch verified entries fails 1;
    dropping the confirm check fails 3.
  - Neighbouring suites stay green: `test_account_data_rights`, `test_deletion_session_races`,
    `test_private_session_ownership`, `test_account_deletion_coverage`, `test_accounts`,
    `test_user_data_lifecycle`, `test_persistent_sessions`, `test_entry_platform_route`.
- [x] **Code-walk proof (server):** `delete_account_route` sends an unverified `entry:` session to
  `_entry_claim_delete` before `_account_data_gates`; that function checks the confirm, derives the
  device id, calls `delete_device_claim_rows` (one transaction, both deletes filtered by user id AND
  device id), then pops the session from `_sessions` (marking it `_revoked`) and deletes its
  persisted row.
- [ ] **Manual TestFlight checklist:** with the mobile half. It must cover, on a fresh install with
  an ESPN or MFL **league-ID-only** entry: Delete account → typed confirmation → the app returns to
  SignIn with no Sleeper prompt; and a regression that a Sleeper-username account's Delete still
  asks for SleeperConnect.
- **For the mobile half:** the client must send `{"confirm": "delete"}` after its typed confirmation,
  and `X-Device-Id` (as sign-in already does, `mobile/src/api/auth.ts`); without the header the
  server can only end the session.
- `testID`s: none (server only).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** (own commit, pending `head-eng`'s grant) | The `DELETE /api/account` row gains the claim-only branch. |
| `docs/data-dictionary.md` | n/a | No schema change. |
| `living-memory/LLD.md` | n/a now | The auth convention changes with the full proof design (post-launch), not with this branch. |
| `docs/architecture.md`, `living-memory/HLD.md` | n/a | No module or data-flow change. |
| `docs/cross-client-invariants.md` | n/a | Deletion exists only in mobile; no shared constant. |
| `docs/glossary.md` | n/a | "Claim-only delete" lives in code comments and this addendum only. |
| `DECISIONS.md` | **scribe** | Record the minimal path: claim-only delete for unverified entry sessions at launch; the proof design deferred; why nothing keyed only by the id is deleted. |

## 5. Ship gate declaration

- **Server half:** CI green (`backend-tests` at minimum) on the pushed sha; evidence above logged
  in `living-memory/TEST_LEDGER.md`. It can deploy before the mobile half: today's client sends no
  confirm, so an entry user's Delete gets the 400 and `AccountDataSection.performDeleteAccount`
  (`mobile/src/screens/settings/sections/AccountDataSection.tsx:142-157`) shows its message as a
  toast, "Confirm the deletion to continue.", instead of today's SleeperConnect prompt, which can't
  succeed for an entry user. That server message is placeholder copy for `marketing-lead`.
- **Mobile half:** its own scope rows (copy from `marketing-lead`, the typed confirmation, the
  TestFlight steps above) before it builds.
- **Reviews:** `head-eng` (the ruling and the API grant); `legal-lead` (M11-R5 against 5.1.1(v)
  for the session-only delete); `eng-security` (no account data reachable from a claim).
- Express lane declared by the operator? **No.** Full gates.
