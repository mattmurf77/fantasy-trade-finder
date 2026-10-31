# Feature Scope — Sign-in timing fix (legal R28.17 condition 4)

**Date:** 2026-10-28
**Entry point:** direct ask. Legal R28.17 condition 4; shape approved by head-eng (GO, 2026-10-27), built by
platforms-eng on branch `fix/signin-history-deferral`.
**Builder:** platforms-eng worker
**Operator sign-off on waivers:** waivers are listed below (§1 analytics, §3 structural guard, the HLD/LLD/ADR
rows). They're surfaced with the PR.

**What changes:** the two UNVERIFIED sign-ins stop loading the user's history at sign-in.

- `POST /api/extension/auth` (username only) and the `POST /api/entry/platform` mint call
  `_extension_build_session(..., load_history=False)`. The session gets fresh ranking services with seed ratings
  only (no swipe replay, no tier-override restore) and is marked `_history_pending`, with a per-session lock.
- The in-place verify routes load the history immediately **before** `verified` flips:
  `POST /api/sleeper/link` (inside the proven-live branch) and `POST /api/mfl/auth-link`.
- Every other `_extension_build_session` caller is unchanged and stays eager: the persisted-session restore,
  `_build_replenish_session`, `_account_build_session`, the Apple/Google device-loss restore and the account
  link-sleeper mint.

**Why:** loading history made the response time of an unverified username sign-in reveal whether that username
has FTF history (a timing oracle). After the change both sign-ins do the same work whether or not history exists.

**head-eng's condition:** if loading the history fails, the verify is refused with a retryable
`503 {"error": "verify_retry", "message": "We couldn't finish signing you in. Try again in a moment."}` and
`Retry-After: 5`. The session stays unverified with `_history_pending` set, so a retry loads it. The eager path's
"log and carry on" is not carried over: a verified session with empty services would let `/api/tiers/save`
(which writes `service._elo_overrides` wholesale) overwrite the user's persisted pins.

**Partial failure:** `_hydrate_session_history` loads into **fresh** service objects and swaps them into the
session only after every format loaded. A failure on the second format discards the first format's replay with
the fresh objects, and the session keeps its pristine services. A retry therefore replays exactly once.
`replay_from_db` appends, so the alternative (resetting half-replayed live services) would need to know every
piece of state the replay and override restore touch. The swap needs nothing: an unverified session cannot read
or write private state (both gates deny it), so nothing on the pending services is worth keeping.

**User effect:** none when things work. The first private read after verifying returns the same board as before.
On a store failure during verification, the user sees a failed verify they can retry, instead of a verified
session with an empty board.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** n/a.
- [x] **(c) WAIVED — no analytics needed because:** this is a server-side timing and ordering change with no new
      user action. A `verify_retry` refusal is logged server-side (`log.exception`), and the existing verify
      marker (`users.verified_via`) is still written only on a real verify.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none. The change is unflagged by design: a flag-off path would keep the timing
  oracle.
- New env vars / `model_config` keys: none. Rollback lever: revert the PR (two call-site kwargs).

## 3. Evidence scope

- [ ] **Structural guard:** WAIVED, backend-only. No mobile, web or extension code changes.
- [x] **Unit tests:** `backend/tests/test_signin_history_deferral.py` (new, 15 tests): the unverified sign-ins
      never call the loaders and mark the session pending (extension auth and a real MFL entry mint); loader calls
      and SQL statement counts are identical at `/api/extension/auth` for a username with history and one
      without; `sleeper_link` and the `mfl_auth_link` body load history while `verified` is still false; a
      second link and a concurrent hydrate never replay twice; `/api/extension/rankings` after auth + link equals
      an eager build (both formats compared at the service level too); the restore, account and default builds
      stay eager; the eager build still swallows load errors; a failed load → 503 `verify_retry` +
      `Retry-After`, still unverified, still pending, nothing half-replayed, then a retry verifies with exactly
      one replay. `backend/tests/test_entry_platform_route.py`: the fake builder accepts the new `load_history`
      kwarg (signature change only).
- [x] **Code-walk proof** (line numbers at the branch head):
  1. `backend/server.py:30794` and `:31059` — `extension_auth` and `entry_platform` pass `load_history=False`.
  2. `backend/server.py:30567` — `_extension_ranking_services` is the one per-format loop. With
     `load_history=False` it constructs services only; `_extension_build_session` then sets `_history_pending`
     and `_history_lock` (`:30723`).
  3. Nothing reads or writes a pending session's board before it verifies: private reads and writes go through
     `_verified_read_denial` / `_verified_write_denial` (`backend/server.py:2804`, `:2840`), and
     `/api/session/init` refuses unverified sessions (`backend/session_input.py:27`).
  4. `backend/server.py:24094` — `sleeper_link` calls `_hydrate_session_history(sess)` inside `if proven_live`,
     before `sess["verified"] = True`; on an exception it returns `_verify_retry_response()` (`:30643`).
  5. `backend/server.py:36764` — `mfl_auth_link` does the same before its verify. It is defensive today:
     `@_gate_unverified_write` (`:36656`) 403s every unverified session first.
  6. `backend/server.py:30610` — `_hydrate_session_history`: takes the session's lock, re-checks
     `_history_pending` on the live dict (a `_RequestSession` view resolves to `_source`), builds fresh services
     with `strict=True`, then swaps `services`/`service` and clears the flag under `_sessions_lock`.
  7. Apple/Google never verify an unverified session in place: `_provider_auth_response` drops an unverified
     session (`backend/server.py:32505`, `sess = None`) and mints a new, eager session.
- [x] **Manual TestFlight checklist** (the mobile sign-in path is `signIn` → silent Sleeper replay →
      `/api/session/init`):
  1. Sign out. Sign in with a Sleeper username that already has rankings and a saved Sleeper verification.
     Expected: the app lands on Main verified (no "Verify your account" banner), with no added delay you notice.
  2. Open Rankings for that league's format. Expected: the board shows your existing order and tier pins, not
     consensus order.
  3. Switch scoring format (1QB ↔ SF). Expected: the other format's board is also yours.
  4. Change one tier pin and save. Kill and reopen the app. Expected: the change and all your other pins are
     still there.
  5. Sign out and sign in with a username that has no FTF history. Expected: sign-in completes as before.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `/api/extension/auth` and `/api/entry/platform` rows: history loads at verification, not at sign-in. `/api/sleeper/link` and `/api/mfl/auth-link` POST rows: 503 `verify_retry` + `Retry-After` |
| `living-memory/LLD.md` | n/a because | no schema, route or invariant convention shifted; the route contracts are in `docs/api-reference.md` |
| `docs/architecture.md` | n/a because | module wiring is unchanged; one load moves later in the same flow |
| `living-memory/HLD.md` | n/a because | no new module, client or major flow |
| `docs/cross-client-invariants.md` | n/a because | no shared constant or enum. `verify_retry` is one route's error code |
| `docs/glossary.md` | n/a because | no new user-facing term |
| ADR or `DECISIONS.md` entry | n/a because | the shape was decided by head-eng (GO, 2026-10-27) and is recorded here |

## 5. Ship gate declaration

- **CI green:** required on the PR sha (backend-tests, mobile-typecheck, testid-lint).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-10-28 entry (targeted file, sabotage, full suite).
- **TestFlight verification:** the §3 checklist, by the operator after merge.
- Express lane declared by the operator? No.
