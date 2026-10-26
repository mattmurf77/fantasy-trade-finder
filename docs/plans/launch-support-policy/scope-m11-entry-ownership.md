# Feature Scope — M11: ESPN/MFL entry ownership proof: in-app deletion, data export and league import

**Date:** 2026-10-23
**Entry point:** direct ask: `head-product`'s new launch MUST M11 (2026-10-23); `legal-lead` LEG-M5; Apple guideline 5.1.1(v)
**Builder:** `onboarding-eng` (build, under `head-eng`; `head-eng` allocates the server files). Spec by `launch-onboarding-pm-4` for `onboarding-pm`.
**Operator sign-off on waivers:** signed 2026-10-23 (operator, relayed by the coordinator; quoted verbatim: "Decision 1: Agree to the waivers."). Covers W-M11-1 and W-M11-2.
**Gate 1 (head-product acceptance of this block):** accepted 2026-10-23 (P38). Option (e) fixes deletion under 5.1.1(v) and the broken ESPN/MFL import together.

> **Backlog, 2026-10-26 (head-eng; Product accepts): #372, the M11 claim-only delete, is parked out of the launch binary.**
> It can't be reached at launch: the ESPN/MFL entry chips are off (`landing.platform_options`, fallback (b), OA-8); the `entry:*` purge removes every entry user by ~11-05 (legal R28.12); and privacy §6 drops the M11 item.
> **What returns together, when ESPN/MFL entry returns:** full M11 (the proof-based verified mint and the identity-routed step-up, M11-R1 to R6), #372's claim-only delete, the G4 strings (dropped from launch), and the verify sheet's non-Sleeper path.
> This supersedes OA-8's "claim-only delete at launch". At launch, ESPN and MFL users sign in with Apple and connect their league from Settings, so they delete through the normal Apple-account path (verified at mint).

The facts, the decision and the requirements:
[prd.md §6.9](prd.md#69-m11-espnmfl-entry-ownership-proof-in-app-deletion-data-export-and-league-import).
**Decision: option (e)** (`onboarding-pm`, 2026-10-23). In short, at `origin/main` `712dcbed`
(code-derived; how many users are affected needs an `analytics-lead` prod read):

- Delete account and Download my data share one gate, `_account_data_gates`
  (`backend/server.py:27931-27942`), which denies any session without `sess["verified"]`. The gates
  check the session only, never the account (`:2653-2660`, `:2689-2696`).
- No route can verify an ESPN or MFL entry session. The mint never sets `verified`
  (`:26066-26069`, `:26107`, `:26110-26116`). The ESPN credential store and `/api/mfl/auth-link` are
  write-gated (`:28370`, `:31680`). SleeperConnect can't match an `entry:*` user (`:19307-19310`).
  Apple discards an unverified session and mints a different one (`:27558-27559`).
- So an entry user's Delete and Download end in a SleeperConnect prompt that can't succeed
  (`mobile/src/screens/settings/sections/AccountDataSection.tsx:87-100`). And **since #279
  (`a927e3a7`) a fresh entry session can't import its league either**: the mint hands off to
  `/api/{espn,mfl}/link` (`mobile/src/api/platformEntry.ts:15`), both write-gated (`server.py:28370`,
  `:31336`), and `backend/tests/test_entry_platform_route.py:231-236` asserts the 403.

**Requirements** (full text in prd.md §6.9.6):

- **M11-R1.** An entry session is minted verified only when the entry carried real proof. MFL: a
  login whose myleagues contains the claimed franchise. ESPN: a sign-in whose SWID owns the claimed
  team, proven by an authenticated, cookie-gated read; the weak `fan_profile` oracle is not enough.
  This fixes import and deletion for proven entries.
- **M11-R2.** The Delete / Download (and profile-toggle) step-up re-runs the proof that matches the
  account's identity, chosen by the user-id prefix: a numeric Sleeper id → SleeperConnect; `acct_`
  → an Apple re-auth that verifies the current session's own account, never minting or adopting a
  different session (no token swap as at `mobile/src/api/auth.ts:108-110`; a server change);
  `entry:mfl:` → the MFL login; `entry:espn:` → the ESPN sign-in. Never hard-coded to SleeperConnect.
- **M11-R3.** One rule covers Delete and Download: the single `_account_data_gates`.
- **M11-R4.** An unverified session still can't delete or export. Option (d) is rejected.
- **M11-R5.** Unproven claims (league-ID-only, ownerless ESPN teams) create no server account data
  beyond their session and device link; their "Delete" ends the session and removes this device's
  link without touching an account row a real owner could hold; the entry flow steers users to the
  proven sign-in; `legal-lead` confirms this meets 5.1.1(v). D-9 email stays the support fallback,
  not the fix.
- **M11-R6.** The step-up copy names the right identity (copy: marketing-lead).

**Rejected:** (a) route by `verified_via`: null for entry users and overwritten by every new proof
(`backend/accounts.py:435-442`). (b) Apple for every Apple-linked account: entry users can't link
Apple, and today's session swap is dangerous. (d) no step-up for never-verified accounts: entry ids
are deterministic from public data, so anyone could delete or export someone else's data; it would
reverse #279 and break `backend/tests/test_private_session_ownership.py:18-47`. (c) ESPN/MFL
re-auth is folded into (e).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** see (c).
- [x] **(c) WAIVED — no analytics needed because:** the step-up re-runs existing proofs, and those
  paths already carry the `signin_*` funnel: the entry mint fires `signin_attempted`,
  `signin_succeeded` and `signin_failed` (`mobile/src/api/platformEntry.ts:137-166`), and SignIn's
  Apple and Sleeper paths fire them too (`mobile/src/screens/SignInScreen.tsx:328`, `:371`, `:422`,
  `:518`). **Verify at build** that each step-up re-auth fires them. If one doesn't, this waiver is
  reopened with `analytics-lead`, and no event is added silently (any new event is registered in
  `backend/analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS` in the same
  commit). The stuck-user count comes from the existing `AUTH-DENY` log lines
  (`backend/server.py:2657-2659`), not from a new event. (Waiver **W-M11-1**.)

## 2. Schema & flag scope

- New/changed tables or columns: **none.** `users.verified_via` may gain values for the entry proofs
  (for example an ESPN value; `mfl_login` is already written at `server.py:31785`). If it does,
  `docs/data-dictionary.md` is updated (§4). M11-R5 changes what the mint writes for an unproven
  claim (today a users row, `server.py:25735-25740`), not the schema.
- New/changed feature flags: **none.** (Waiver **W-M11-2**.) The existing proof-path flags act as kill
  switches: with `mfl.auth_link` off (`config/features.json:118`) MFL entry stays claim-only, and
  with `espn.webview_capture` off (`:112`) ESPN entry stays claim-only. A recommendation; `head-eng`
  decides. If `head-eng` adds a flag instead, this section is amended before build to name it, its
  default, its graduation criterion and the rollback, and W-M11-2 lapses.
- New env vars / `model_config` keys: **none.**
- **Not express-lane.** This changes API contracts (the entry mint, the link routes, the step-up),
  so the full gates apply even if the operator asks for express (root `CLAUDE.md`, "Bright line").

## 3. Evidence scope

D-056: no simulator, no Maestro, no screen captures. Full evidence; nothing below is waived.

- [x] **Unit tests (backend pytest):**
  - A proven MFL entry (a login whose myleagues contains the claimed franchise) and a proven ESPN
    entry (a cookie-gated read whose SWID owns the claimed team) each get a verified session, and
    the canonical import returns 200.
  - An unproven claim (league ID only; an ownerless ESPN team; the weak `fan_profile` oracle only)
    still gets 403 on import, `DELETE /api/account` and `GET /api/account/export`.
  - `backend/tests/test_private_session_ownership.py` stays green, with `entry:espn:` and
    `entry:mfl:` ids added to `test_claimed_identity_private_routes_fail_closed` (`:18-47`).
  - Export and delete follow the same rule (one `_account_data_gates`).
  - The Apple step-up verifies the current session's own account or fails, and never returns a
    different `session_token`.
  - Each `entry:*` step-up proof marks the session verified only when it is bound to that session's
    own user id (a proof for another franchise or SWID is refused).
  - Replace the hand-set `verified=True` in `backend/tests/test_entry_platform_route.py:231-236`
    and `:484-486` with the real proof path.
  - Extend, don't fork: `test_entry_platform_route.py`, `test_mfl_auth_link_route.py` (`:192-221`),
    `test_account_data_rights.py` (`:93`), `test_verified_sessions.py`,
    `test_deletion_session_races.py`.
- [x] **Structural guard:** the step-up routes by identity and has no hard-coded
  `navigate('SleeperConnect')`. Extend `mobile/tests/check-settings-ia.js` (it already owns the
  AccountDataSection rows, `:108-110`) or add a new `mobile/tests/check-account-stepup.js` with an
  `npm run test:account-stepup` script. Pins: each user-id prefix maps to its proof (M11-R2); the
  Apple step-up path doesn't call `setSessionToken`; the "Your account is verified, but this session
  isn't" string is gone. CI runs every `mobile/tests/check-*.js` (`.github/workflows/ci.yml:42-48`).
- [x] **Code-walk proof** (file:line, re-walked against the built files):
  1. **Mint.** The `/api/entry/platform` mint marks the session verified only on the M11-R1 proof
     (today `server.py:26110-26116`, no `verified`), and writes no users row for an unproven claim
     (today `:25735-25740`).
  2. **Import.** With a verified entry session, `@_gate_unverified_write` passes
     (`server.py:2653-2660`) and `/api/espn/link` (`:28370`) and `/api/mfl/link` (`:31336`) import.
  3. **Gate.** Delete and Download still go through `_account_data_gates` (`:27931-27942`; applied at
     `:27959`, `:27994`).
  4. **Step-up routing.** `AccountDataSection`'s prompt (today `:87-100`) picks the proof by user-id
     prefix. On success the session is verified the way `/api/sleeper/link` does it
     (`server.py:19346-19371`), and the user retries in place.
  5. **Apple.** The step-up path never reaches today's discard (`:27558-27559`) and the client never
     adopts a new token (`mobile/src/api/auth.ts:108-110`).
  6. **Claim-only Delete.** It ends the session (`/api/session/signout`, `server.py:28028-28052`) and
     removes this device's `identity_links` row (`backend/database.py:2172-2190`, written at
     `server.py:26121`), and touches no account row.
- [x] **Manual TestFlight checklist** (operator, on the 11-06 binary, in the 11-07 to 11-09 window;
  log the result in `living-memory/TEST_LEDGER.md`):
  1. Fresh install. SignIn → MFL chip → "Sign in with MFL" → enter an MFL login → pick a league.
     Expected: the import succeeds and the app opens the league. Today it shows "Verify your account
     to link a league."
  2. Settings → Account & data → Download my data. Expected: no Sleeper prompt. Either the export
     shares immediately (the session is verified), or a step-up asks for the **MFL** login, and after
     it the export shares.
  3. Settings → Account & data → Delete account → confirm twice. Expected: no "Verify with your
     Sleeper login". The account deletes, and the app returns to SignIn.
  4. Re-enter with the same MFL login and league. Expected: empty boards (nothing ranked, no
     history).
  5. Repeat 1 to 4 on a fresh install with the ESPN chip → "Sign in to ESPN", on a **private**
     league. The step-up, if shown, is the ESPN sign-in.
  6. Fresh install, ESPN or MFL chip, **league ID only** (no sign-in). Expected: the entry flow
     steers to the sign-in. If you go on as a claim, Delete ends the session without a Sleeper
     prompt and the app returns to SignIn (M11-R5).
  7. Regression: a Sleeper-username account with no stored Sleeper token. Delete → the step-up is
     SleeperConnect → after it, Delete succeeds.
- `testID`s added/renamed: any step-up sheet or button gets a new `testID`, named at build; it must
  pass `mobile/scripts/testid-lint.sh`. Existing ones stay (`settings.export-data`,
  `AccountDataSection.tsx:211`).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **update at build** | `POST /api/entry/platform` (`:128`): the verified mint for proven entries; drop the stale "unverified-write grace". `/api/espn/link` and `POST /api/mfl/auth-link` (`:860`): who can verify, and the franchise / SWID binding. `GET /api/account/export` (`:220`) and `DELETE /api/account`: the step-up contract (which proof, by user-id prefix). `/api/auth/apple`: the in-place step-up. |
| `docs/data-dictionary.md` | **only if** | Only if `users.verified_via` gains values (`:254`, and the persisted-session copy `:1579`). That list is already stale: it omits `mfl_login`, which `server.py:31785` writes. Fix it in the same pass. |
| `docs/integrations/espn.md` | **update at build** | The entry identity proof: which cookie-gated read counts, and why the `fan_profile` oracle doesn't. |
| `docs/integrations/mfl.md` | **update at build** | The entry identity proof: login plus franchise ownership via myleagues. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **update at build** | The auth convention (`:805`, "Private reads/writes depend on proof on the current session"): add how an entry session gets that proof, and that step-ups route by user-id prefix. |
| `docs/architecture.md` (module wiring / data flow changed) | **only if** | Only if the build adds a new module or changes the auth data flow (for example a shared step-up service). Otherwise n/a: the change stays inside existing routes. |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | No new module, client or major flow; the entry flow keeps its shape and gains a proof. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | Delete and Download exist only in mobile: no `web/js` or `extension` caller of `DELETE /api/account` or `/api/account/export` at `712dcbed`. |
| `docs/glossary.md` (new domain term) | **only if** | Only if the build names "proven entry" or "claim-only entry" in code or UI. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **update at build** | Record option (e): entry sessions verify on proof only; step-ups route by user-id prefix; option (d) rejected and why. Next ID = max `D-` + 1 at build time. |
| `docs/runbook.md` | n/a | The D-9 email fallback is P28's runbook entry ([scope-p28-contact.md](scope-p28-contact.md) §4). M11 adds no operation. |

## 5. Ship gate declaration

- **Client in the 11-06 binary** (prd.md §8). The server part can deploy separately and earlier;
  `head-eng` sequences it. **Size M, tight for 11-06** (prd.md §6.9.9, flagged in §9).
- **CI green:** `backend-tests` + `mobile-typecheck` (runs `tsc --noEmit` and every
  `mobile/tests/check-*.js`, including the new or extended guard) + `web-structure` +
  `maestro-testid-lint` (testid-lint only), all passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the pytest counts, the guard
  result, the code-walk and the TestFlight run. `githooks/pre-push` still checks the retired
  simulator marker; under D-056 push with `FTF_SKIP_SIM_GATE=1` and name this evidence instead.
- **TestFlight verification:** the operator runs §3's checklist on the 11-06 binary, in the 11-07 to
  11-09 window.
- **Reviews before merge:** `platforms-pm` (P10); `eng-security` (the identity proofs); `legal-lead`
  (the proofs accepted for erasure and export, M11-R5, the residual 5.1.1(v) exposure); `ux-lead`
  (the step-up flow); `design-lead` (the sheets).
- **Gates still owed:** none on this block. Gate 1 was accepted (P38) and W-M11-1 and W-M11-2 were
  signed on 2026-10-23 (see the header).
- **Still open:**
  - `legal-lead` confirms M11-R5 (via `head-bizops`);
  - an `analytics-lead` count of affected `entry:*` users (`head-product` has requested it).
- **The fallback: option (b) (Product, P39, 2026-10-24; Launch Desk OA-8; still a fallback, not
  taken).** Product adopts (b) over its earlier (c). "(b)" and "(c)" here are OA-8's labels, not the
  rejected options in the header above. If M11 misses 11-06 (the decision point), turn
  `landing.platform_options` (`config/features.json:28`) off for launch. Users can sign in with Apple,
  then connect ESPN/MFL from Settings, and the listing and FAQ keep ESPN/MFL with accurate wording.
  `release-lead` flips it on the operator's word. `head-product` has asked `app-manager` to add the
  TestFlight step Apple → Settings → connect ESPN/MFL → import. The facts, what Apple sign-in still
  allows, and what else the fallback touches are in
  [prd.md §6.9.10](prd.md#6910-the-fallback-operator-decision-not-taken).
- Express lane declared by the operator? **No.** Full gates (API contracts; see §2).
