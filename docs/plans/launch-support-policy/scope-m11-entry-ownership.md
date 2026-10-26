# Feature Scope — M11: ESPN/MFL entry ownership proof: in-app deletion, data export and league import

**Date:** 2026-10-23 (re-scoped into launch 2026-10-26)
**Entry point:** direct ask: `head-product`'s new launch MUST M11 (2026-10-23); `legal-lead` LEG-M5; Apple guideline 5.1.1(v); operator decision 2026-10-26 (in the launch scope)
**Builder:** `onboarding-eng` (build, under `head-eng`; `head-eng` allocates the server files and is sizing the re-scope). Spec by `launch-onboarding-pm-4` for `onboarding-pm`.
**Operator sign-off on waivers:** signed 2026-10-23 for the earlier scope (operator, relayed by the coordinator; quoted verbatim: "Decision 1: Agree to the waivers."), covering W-M11-1 and W-M11-2. **Re-confirmation requested from the operator (scope changed 2026-10-26).**
**Gate 1 (head-product acceptance of this block):** accepted 2026-10-23 (P38) for the earlier scope. **Needs `head-product`'s re-acceptance of the 2026-10-26 re-scope.**

> **Decision, 2026-10-26: M11 is in the launch scope.** The operator, in `head-product`'s session,
> verbatim: "It should be in the launch scope." That means **account creation from the ESPN or MFL
> login**: M11's proof-based mint. Earlier, also verbatim: "They do allow login, we just need to
> figure out how to support it in the context of account creation." This supersedes the backlog note
> below.

> ~~**Backlog, 2026-10-26 (head-eng; Product accepts): #372, the M11 claim-only delete, is parked out of the launch binary.**~~
> ~~It can't be reached at launch: the ESPN/MFL entry chips are off (`landing.platform_options`, fallback (b), OA-8); the `entry:*` purge removes every entry user by ~11-05 (legal R28.12); and privacy §6 drops the M11 item.~~
> ~~**What returns together, when ESPN/MFL entry returns:** full M11 (the proof-based verified mint and the identity-routed step-up, M11-R1 to R6), #372's claim-only delete, the G4 strings (dropped from launch), and the verify sheet's non-Sleeper path.~~
> ~~This supersedes OA-8's "claim-only delete at launch". At launch, ESPN and MFL users sign in with Apple and connect their league from Settings, so they delete through the normal Apple-account path (verified at mint).~~
> **SUPERSEDED same day by the operator** (the decision above).

The facts, the requirements, the edge cases and the open questions:
[prd.md §6.9](prd.md#69-m11-espnmfl-entry-ownership-proof-in-app-deletion-data-export-and-league-import)
(6.9.6 for the re-scope) and [§9](prd.md#9-decisions-needed). In short, at `origin/main` `21266ddf`
(code-derived; how many users are affected needs an `analytics-lead` prod read):

- Delete account and Download my data share one gate, `_account_data_gates`
  (`backend/server.py:31537-31548`), which denies any session without `sess["verified"]`. The write
  gate checks the session only, never the account (`:2756-2763`).
- An ESPN or MFL entry session is never verified. The mint doesn't set it (`:29670-29672`, `:29710`,
  `:29714-29719`), and the import routes are write-gated: `/api/espn/link` (`:31975-31976`),
  `/api/mfl/link` (`:34964-34965`), `/api/mfl/auth-link` (`:35308-35309`). So since #279
  (`a927e3a7`) a fresh entry can't import its league, delete or export
  (`backend/tests/test_entry_platform_route.py:231-236` asserts the 403).
- Both logins are already captured and live-checked: ESPN `espn_s2` + SWID with `wrong_account`
  detection (#321; `:29660-29668`, `_espn_verify_credential` `:31764`), and the MFL login
  (`:35373-35375`, stamping `verified_via='mfl_login'` at `:35413-35414`). `POST /api/sleeper/link`
  already proves a login inline before it verifies (`:22797`, `:22808-22811`, `:22836-22847`).

**The launch flow.** ESPN/MFL chip → the platform login (the ESPN sign-in WebView; the MFL username
and password) → a verified Fleeced account → import → the first deck.

**Intended mechanism** (`head-eng`'s picture; `head-eng` confirms): the link and entry routes accept an
unverified **entry** session that carries a valid login inline, then verify it or mint the account,
as `POST /api/sleeper/link` does. This realizes M11-R1.

**Requirements** (full text in prd.md §6.9.6):

- **M11-R1. The platform login creates the account.** A valid login mints a verified account (or
  signs into an existing one, E2). MFL: the login succeeds and its myleagues contains the claimed
  franchise. ESPN: the pair is proven live by an authenticated read and its SWID owns the claimed
  team; the weak `fan_profile` oracle alone isn't enough (`server.py:31806-31813`). The MFL password
  is never stored or logged (`:29592`, `:35374`; `backend/mfl_service.py:186-189`).
- **M11-R2. Step-up by identity:** a numeric Sleeper id → SleeperConnect; `acct_` → an in-place Apple
  re-auth (never a session swap); `entry:mfl:` → the MFL login; `entry:espn:` → the ESPN sign-in.
  Never hard-coded to SleeperConnect. This un-parks `mon.verify.espn` / `mon.verify.mfl`; coordinate
  with ux-lead's §3 through `head-product` (open).
- **M11-R3. One gate** for Delete and Download: `_account_data_gates`. A minted account is verified,
  so it deletes and exports normally.
- **M11-R4. The protection stays:** an unverified session without a login is refused;
  `backend/tests/test_private_session_ownership.py` stays green.
- **M11-R5. Every ESPN/MFL entry requires the platform login, at launch, including public ESPN
  leagues.** No claim-only entry remains (`onboarding-pm`'s decision; `platforms-pm` reviews, P10).
  #372, the claim-only delete, is superseded: **recommend closing it**, with `head-eng`'s agreement.
  The `entry:*` purge (legal R28.12, by ~11-05) still proceeds; those users re-enter through the
  login (`legal-lead` confirms).
- **M11-R6. Copy:** the step-up names the account's own sign-in; error copy for E1 to E4; E5's
  prevention line (copy: marketing-lead).
- **M11-R7. Launch switch:** `landing.platform_options` (`config/features.json:30`) flips **ON** for
  launch once M11 ships, on the operator's word in `release-lead`'s session. Fallback (b) retires
  once M11 is live.

**Edge cases** (Product's intended behavior; `head-eng` confirms feasibility; details and "code today"
notes in prd.md §6.9.6):

- **E1. Wrong account:** ESPN refuses, says which team this login owns and offers to pick it; MFL
  refuses and shows the user's own franchises. *Code today:* the refusal is generic and doesn't name
  the owned team, and an ownerless ESPN team is accepted (`server.py:29660-29672`).
- **E2. Login already claimed, first controller wins:** a valid login for an identity a verified
  account already holds (`espn_credentials.swid`, `backend/database.py:2626-2634`;
  `mfl_credentials.mfl_username`, `:2652-2659`) signs into that account; never a second account,
  never a transfer. *Code today:* neither column is indexed or unique.
- **E3. Expired ESPN cookie:** a failed authenticated read at sign-in → "sign in to ESPN again"; never
  mint unverified. Later expiry affects refresh and send, not account access.
- **E4. MFL outage:** don't mint; "MFL isn't responding, try again", with Apple offered; no
  claim-only fallback.
- **E5. Already has an Apple or Sleeper account:** E2 if that account holds this identity; otherwise
  a separate account. Prevention copy on the chip sheet. **Known limit: no automatic merge at launch.**
- **E6. One person, one account:** ESPN keys on the SWID (`server.py:29670`). MFL keys per franchise
  today (`:29710`), so three MFL leagues make three accounts. Requirement: one account per MFL login;
  `head-eng` picks the mechanism (open).

**Rejected:** (a) route by `verified_via`: null for entry users and overwritten by every new proof.
(b) Apple for every Apple-linked account: entry users can't link Apple, and today's session swap is
dangerous. (d) no step-up for never-verified accounts: entry ids are deterministic from public data;
it would reverse #279 and break `test_private_session_ownership.py`. (c) is folded into (e). The
re-scope keeps option (e).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it:** `signin_attempted`, `signin_succeeded` and `signin_failed`
  already fire with `method` `espn`/`mfl` at entry (`mobile/src/api/platformEntry.ts:137`, `:159`,
  `:162-166` at `21266ddf`), so the login-creates-account funnel is measured. The step-up re-auths
  reuse those proof paths; verify at build that each fires them.
- [x] **(c) WAIVED — no new events because:** see (b). (Waiver **W-M11-1**: signed 2026-10-23 for
  the earlier scope; **re-confirmation requested from the operator, scope changed 2026-10-26**.)
  - **Open question:** the new `signin_failed.error_code` values (`wrong_account`,
    `already_claimed`, `espn_expired`, `mfl_unavailable`) may need `analytics-lead`'s registration.
    The taxonomy lists `error_code` as a `signin_failed` property with no closed value list
    (`backend/analytics_taxonomy.py:964`), unlike `sleeper_send_failed`'s closed enum (`:1186`). If
    they do need it, W-M11-1 doesn't cover them, and `analytics-lead` grants.
  - Any event that is added is registered in `backend/analytics_taxonomy.py` and classified in
    `analytics_queries.NON_INTENT_EVENTS` in the same commit as its emitter.

## 2. Schema & flag scope

- New/changed tables or columns: **none decided.** Candidates, `head-eng`'s call:
  - a new `users.verified_via` value for the ESPN login (e.g. `espn_login`; `mfl_login` already
    exists, `server.py:35414`);
  - an index or uniqueness on `espn_credentials.swid` / `mfl_credentials.mfl_username` for E2's
    lookup (`database.py:2626-2634`, `:2652-2659`; neither has one today);
  - a new MFL account key for E6.

  Any of these updates `docs/data-dictionary.md` (§4).
- New/changed feature flags: **none.** (Waiver **W-M11-2**: signed 2026-10-23 for the earlier scope;
  **re-confirmation requested from the operator, scope changed 2026-10-26**.)
  - `mfl.auth_link` (`config/features.json:120`) and `espn.webview_capture` (`:114`) remain kill
    switches. With one off, that entry is unavailable; there is no claim-only path.
  - `landing.platform_options` (`:30`) flips **ON** for launch once M11 ships (M11-R7).
  - If `head-eng` adds a flag instead, this section is amended before build, and W-M11-2 lapses.
- New env vars / `model_config` keys: **none.**
- **Not express-lane.** This changes API contracts (the entry and link routes, the step-up) and may
  change schema, so full gates apply (root `CLAUDE.md`, "Bright line").

## 3. Evidence scope

D-056: no simulator, no Maestro, no screen captures. Full evidence; nothing below is waived.

- [x] **Unit tests (backend pytest):**
  - a valid ESPN or MFL login mints a verified account, the import returns 200, and the first deck
    is served;
  - E1: a wrong-account login is refused;
  - E2: a second login for the same identity lands on the same account; no second account is made;
  - E3: an expired ESPN cookie mints nothing;
  - E4: an MFL outage mints nothing;
  - E6: one MFL login across two leagues makes one account;
  - an unverified session without a login is still refused: `test_private_session_ownership.py`
    stays green (`:20`, `:50`), with `entry:*` ids added;
  - Delete and Download on a minted account succeed;
  - replace the hand-set `verified=True` in `test_entry_platform_route.py:231-236` and `:484-486`
    with the real login path.
  - Extend, don't fork: `test_entry_platform_route.py`, `test_espn_link_route.py`,
    `test_espn_identity_binding.py`, `test_mfl_link_route.py`, `test_mfl_auth_link_route.py`,
    `test_account_data_rights.py`, `test_verified_sessions.py`, `test_deletion_session_races.py`.
- [x] **Structural guard:** the step-up routes by identity (M11-R2), with no hard-coded
  `navigate('SleeperConnect')`, and the Apple step-up never calls `setSessionToken`. Extend
  `mobile/tests/check-settings-ia.js` (it owns the AccountDataSection rows, `:115-117`) or add
  `mobile/tests/check-account-stepup.js` with an `npm run` script. CI runs every
  `mobile/tests/check-*.js` (`.github/workflows/ci.yml:42-48`).
- [x] **Code-walk proof** (file:line, re-walked against the built files):
  1. **Login.** The entry or link route takes the inline login, proves it (MFL: login plus
     myleagues; ESPN: an authenticated read plus SWID ownership), and only then verifies or mints,
     mirroring `POST /api/sleeper/link` (`server.py:22797`, `:22808-22811`, `:22836-22847`).
  2. **Identity.** E2's lookup finds an existing verified holder of the SWID or MFL username and
     signs into that account; E6's key gives one account per MFL login.
  3. **Import.** With the verified session, `@_gate_unverified_write` passes (`:2756-2763`), and the
     link routes import.
  4. **Gate.** Delete and Download go through `_account_data_gates` (`:31537-31548`, applied at
     `:31565` and `:31600`).
  5. **Step-up.** `AccountDataSection`'s prompt (today
     `mobile/src/screens/settings/sections/AccountDataSection.tsx:87-100`) routes by user-id prefix.
- [x] **Manual TestFlight checklist** (operator, fresh installs; log the result in
  `living-memory/TEST_LEDGER.md`):
  1. ESPN chip → ESPN sign-in on a **private** league → import → the first deck → Settings → Account
     & data → Delete account. Expected: each step works, and Delete succeeds with no Sleeper prompt.
  2. The same for MFL. Then sign in with the same MFL login and add a **second** MFL league. Expected:
     it lands on the same account (E6).
  3. The wrong-team path: claim a team the login doesn't own. Expected: refused, with the team or
     franchises the login does own offered (E1).
  4. An existing Apple user who has linked their ESPN SWID in Settings, then uses the ESPN chip with
     the same ESPN login. Expected: they land in their existing account (E2).
- `testID`s added/renamed: any new error or step-up control gets a `testID`, named at build; it must
  pass `mobile/scripts/testid-lint.sh`. Existing ones stay.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **update at build** | The entry and link routes (`POST /api/entry/platform` `:131`; `/api/espn/link` `:1184-1186`; `/api/mfl/link` `:1199`; `/api/mfl/auth-link` `:1210`, at `21266ddf`) accept an unverified entry session with an inline login, and mint or verify; the new error codes; drop the stale "unverified-write grace". |
| `docs/data-dictionary.md` | **update at build** | `users.verified_via` values (e.g. `espn_login`; the list at `:259` and `:1708` already omits `mfl_login`); the roles of `espn_credentials` and `mfl_credentials` as identity keys; any new MFL key or index. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **update at build** | The auth convention (`:810`, "Private reads/writes depend on proof on the current session"): a platform login is account-creation proof. |
| `docs/architecture.md` (module wiring / data flow changed) | **update at build** | ESPN and MFL logins become identity providers in the auth flow. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **update at build** | The same: new identity providers in the auth flow. |
| `docs/integrations/espn.md` | **update at build** | The ESPN login as account-creation proof: which authenticated read counts, and why `fan_profile` doesn't. |
| `docs/integrations/mfl.md` | **update at build** | The MFL login as account-creation proof, and the account key (E6). |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **update at build, if shared** | The error-code enum (`wrong_account`, `already_claimed`, `espn_expired`, `mfl_unavailable`), if mobile and web share it. |
| `docs/glossary.md` (new domain term) | **only if** | Only if the build names a new term (e.g. "platform login account") in code or UI. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **update at build** | The platform login creates the account; first controller wins (E2); one account per person (E6); no claim-only entry; option (d) rejected. Next ID = max `D-` + 1 at build time. |
| `docs/runbook.md` | n/a | No new operation. The `entry:*` purge is `legal-lead`'s and `head-eng`'s, tracked outside this block. |

## 5. Ship gate declaration

- **Timing:** Product wants it live before the **11-10 App Store submission**, so the reviewer sees it
  working. `head-eng` says whether it fits, and which parts need the **11-06 binary** (likely the E1
  to E5 error copy and the verify-sheet routing) and which are server-only.
- **CI green:** `backend-tests` + `mobile-typecheck` (runs `tsc --noEmit` and every
  `mobile/tests/check-*.js`) + `web-structure` + `maestro-testid-lint` (testid-lint only), all
  passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry with the pytest counts, the guard
  result, the code-walk and the TestFlight run. `githooks/pre-push` still checks the retired
  simulator marker; under D-056 push with `FTF_SKIP_SIM_GATE=1` and name this evidence instead.
- **Reviews before merge:** `platforms-pm` (P10, including M11-R5); `eng-security` (the identity
  proofs, E2, E6); `legal-lead` (credential-storage privacy text, the privacy §6 M11 item, the purge,
  App Review notes); `ux-lead` (the verify sheet, coordinated with its §3); `design-lead` (the sheets).
- **Launch switch:** `landing.platform_options` ON once M11 ships (M11-R7). **Fallback (b) retires
  once M11 is live.** Until then it stays the fallback at the 11-06 decision point
  ([prd.md §6.9.10](prd.md#6910-the-fallback-operator-decision-not-taken)).
- **Gates still owed:** gate 1 needs `head-product`'s re-acceptance of the re-scope, and the operator
  re-confirms W-M11-1 and W-M11-2.
- **Open questions** (prd.md §9): feasibility before 11-10; the binary vs server split; E6's MFL key;
  E2's lookup (feasibility and legal acceptability); the public-league ESPN proof and ownerless teams;
  the error-code registration; re-confirming W-M11-1/2; the ux-lead §3 verify sheet; closing #372; the
  purge confirmation; the `legal-lead` and `marketing-lead` items.
- Express lane declared by the operator? **No.** Full gates (API contracts; see §2).
