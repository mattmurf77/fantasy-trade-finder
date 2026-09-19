# Account Auth Plan — hiding ranks behind a real account (#102)

*Planning doc, 2026-07-11. Branch `trade-engine-v2`. No code changes land with this doc (plan-only; see §5). Companion reading: [auth-multiplatform-plan-2026-06-11.md](auth-multiplatform-plan-2026-06-11.md) (the broader identity/multi-platform strategy — this doc is the **security-first, ship-now slice** of its Part A + Part C), [sleeper-write-capture-runbook.md](sleeper-write-capture-runbook.md) (the Send-in-Sleeper JWT capture this plan reuses), [../architecture.md](../architecture.md).*

> **Issue #102 (operator):** "I want my ranks hidden behind an account. Either Apple or Google or Sleeper."
>
> **One-line answer.** The app has **no identity proof today** — a Sleeper *username* (public, guessable) is the only thing standing between an attacker and full write access to any user's rankings, tiers, trade likes, and — worst — their linked Sleeper account's trade-proposal power. The fix is a **verified-session flag**: prove control of the account (P1: reuse the Send-in-Sleeper JWT you already capture; P2: add Sign in with Apple + optional Google as identity anchors), then **write-protect** the sensitive routes so an unverified username session can read but not mutate.

---

## 1. Threat model — what a username-only attacker can do today

### The identity chain (grounded)

Everything keys on a Sleeper `user_id`, and that id is obtained with **zero proof of control**:

1. **Sign-in.** [`SignInScreen.tsx`](../../mobile/src/screens/SignInScreen.tsx) posts a username to `POST /api/extension/auth` ([server.py:8331](../../backend/server.py)). The handler lowercases it, does a **public, keyless** Sleeper lookup (`GET https://api.sleeper.app/v1/user/<username>` — no token, anyone can call it), takes the returned `user_id`, and mints a session token via `_extension_build_session`. **No password, no OAuth, no possession check.** Sleeper usernames are public (they appear on every league roster, in share links `/u/<username>`, and in league-mate lists), so "know a username" ≈ "know a target."
2. **Session.** The token is an opaque `secrets.token_urlsafe(32)` string in the in-memory `_sessions` dict ([server.py:984](../../backend/server.py)). `_require_session()` ([server.py:1049](../../backend/server.py)) just looks the token up and returns `sess["user_id"]`. Every write route reads `sess["user_id"]` and trusts it.
3. **Session-init.** `POST /api/session/init` ([server.py:6440](../../backend/server.py)) takes `user_id` **straight from the request body** (defaults to `DEMO_USER_ID`). Even without the auth route, a client can name any `user_id` it likes and the backend builds that user's ranking/trade services and replays their stored swipes/overrides.

There is **no point in the chain where the server verifies the human is who they claim.** Username → user_id → session → all writes.

### What a session-as-victim unlocks (every mutating route)

Once an attacker holds a session bound to a victim's `user_id`, these all act **as the victim** (route → what it corrupts):

| Route | Effect on the victim |
|---|---|
| `POST /api/rank3` ([:2221](../../backend/server.py)) | Inject swipes → **rewrite their Elo rankings** (persisted to `swipe_decisions`) |
| `POST /api/rankings/reorder` ([:3414](../../backend/server.py)) | Overwrite their manual board / tier overrides |
| `POST /api/rankings/submit` ([:5358](../../backend/server.py)) | **Publish forged `member_rankings`** — poisons trade math for the whole league, not just the victim |
| `POST /api/tiers/save` ([:3047](../../backend/server.py)), `/api/tiers/copy-from-format`, `/api/tiers/dismiss` | Overwrite `users.tier_overrides` / `tiers_saved` |
| `POST /api/anchor/save` ([:3138](../../backend/server.py)) | Rewrite pick-anchor valuations (authoritative override used in trade math + shown to league-mates) |
| `POST /api/reset` ([:3403](../../backend/server.py)) | **Wipe a whole position's rankings** |
| `POST /api/ranking-method`, `POST /api/scoring/switch` | Flip their ranking method / active format |
| `POST /api/trades/swipe` ([:4200](../../backend/server.py)) | Forge trade **likes** → manufacture fake mutual matches |
| `POST /api/trades/generate`, `POST /api/trades/flag` | Run/poison trade generation, flag good trades as bad |
| `POST /api/trades/matches/<id>/dismiss` \| `/disposition` | Dismiss/alter their real match inbox |
| `POST /api/league/preferences`, `/asset-prefs`, `/scoring` | Rewrite their league config / detected scoring format |
| `POST /api/notifications/register-device`, `PUT /prefs`, `/read`, `/read-all` | **Bind an attacker device to the victim's push stream**, silence or mark-read their notifications |
| `POST /api/feedback` | Submit feedback as the victim |
| **`POST /api/sleeper/link`** ([:4610](../../backend/server.py)) | Store/replace the Sleeper **write token** stored under the victim's `user_id` |
| **`POST /api/trades/propose`** ([:4669](../../backend/server.py)) | **If the victim has connected Send-in-Sleeper, fire real trade proposals into their actual Sleeper league from their real account.** Highest blast radius — this reaches *outside* FTF. |

### The asymmetry that makes #102 urgent

The two `/api/sleeper/*` write routes are the crux. Send-in-Sleeper (flag `trade.send_in_sleeper`, **currently `true`** in [config/features.json:53](../../config/features.json)) stores a **full-account Sleeper JWT** encrypted under the victim's `user_id`. A username-only impersonator with a session then reaches `POST /api/trades/propose`, which decrypts that token and posts real proposals. So today the *weakest* auth (public username) gates the *strongest* capability (writing to someone's real Sleeper account). Closing #102 is what makes shipping Send-in-Sleeper broadly safe.

### Secondary impersonation surfaces (reconcile when auth lands)

- **`test_user_fp_*` bypass** ([server.py:6082](../../backend/server.py)) — synthetic login, **gated off in prod** by `_IS_PROD_ENV` ([:7468](../../backend/server.py)). OK for now.
- **Seeded `User1..User5` logins** ([server.py:6100](../../backend/server.py)) — bypass Sleeper if the name is seeded in the DB; **live in prod**. Low value (only the seeded test league), but it's a real impersonation path — remove or prod-gate when auth lands.
- **`/api/session/demo`** ([:8896](../../backend/server.py)) mints throwaway `demo_user_*` sessions that persist nothing — not a threat, leave as-is.

### Scope note — what stays out

Operator routes (`/api/cron/*`, `/api/admin/*`, `/api/feedback/admin`, `/api/feature-flags/reload`) are guarded by `_require_cron_auth()` (`X-Cron-Secret`) — a **separate axis** from user auth. This plan does not touch them. Read routes (`/api/players`, `/api/rankings`, public profiles) staying open is fine and intended.

---

## 2. Options analysis

Three identity mechanisms, plus the binding/migration problem that sits underneath all of them.

### 2a. Sign in with Apple — the App-Store gate, and a real identity anchor

- **What.** `expo-apple-authentication` native button → Apple returns a signed **identity token** (JWT). Backend verifies it against Apple's JWKS (`https://appleid.apple.com/auth/keys`): check signature by `kid`, `iss=https://appleid.apple.com`, `aud=<FTF bundle id>`, `exp`, and the `nonce`. Extract the stable `sub` as the account key. Apple returns name/email **only on first authorization** — never key on email; key on `(provider='apple', sub)`.
- **App Store constraint (mandatory, not optional).** Guideline **4.8** (["Login Services"](https://developer.apple.com/app-store/review/guidelines/)) requires that **any app offering a third-party/social login to set up or authenticate the primary account must also offer an equivalent privacy-preserving login** — one that limits data to name+email, lets the user keep email private, and doesn't track for ads without consent. The 2024 revision softened "must be Sign in with Apple *specifically*" to "must offer *an* equivalent option," **but Sign in with Apple is the only turnkey one that qualifies.** Practical rule: **if we ship Google (or any social provider) as account login, Apple ships in the same iOS release.** ([Apple 4.8](https://developer.apple.com/app-store/review/guidelines/), [Apple news 2024 update](https://developer.apple.com/news/?id=7j1f99yf))
- **Effort.** Medium. Native module + one JWKS-verify route (`POST /api/auth/apple`) + the `accounts`/`auth_identities` tables. Apple sign-in button per HIG. The 4.8 rule means this is a **hard dependency of any social-login work**, so it's cheapest to build first among the identity anchors.
- **Tradeoff.** Real, durable identity that survives device loss and is App-Store-clean. But it's a **new** provider relationship (Apple Developer config, Services ID) and, on its own, proves identity without proving control of the *Sleeper* account the user's data is keyed to — so it must be **paired with a Sleeper link** (see §2d).

### 2b. Google via `expo-auth-session`

- **What.** OIDC. Either `expo-auth-session` (browser flow) or the provider-native `@react-native-google-signin/google-signin` (native sheet, requires a dev build + config plugin — Expo now recommends the provider-native lib where available). App gets Google's **id_token**; backend verifies against Google JWKS (`https://www.googleapis.com/oauth2/v3/certs`) exactly like Apple — **same verification code path**, different issuer/aud. ([Expo authentication guide](https://docs.expo.dev/develop/authentication/), [Expo Google auth](https://docs.expo.dev/guides/google-authentication/))
- **Effort.** Low *incremental* once Apple's JWKS-verify plumbing exists — it's one more issuer + one more route (`POST /api/auth/google`). The native-sheet path adds a config-plugin/dev-build cost.
- **Tradeoff.** Broad familiarity, good conversion. But **triggers 4.8** — cannot ship without Apple. Same "identity but not Sleeper-control" gap as Apple; needs the same binding step.

### 2c. "Sleeper-proof" auth — reuse the Send-in-Sleeper JWT (recommended P1)

- **What.** The app **already captures a real Sleeper login** in [`SleeperConnectScreen.tsx`](../../mobile/src/screens/SleeperConnectScreen.tsx): a WebView to `sleeper.com/login`, then it reads the 365-day HS256 JWT out of `localStorage['token']` and posts it to `POST /api/sleeper/link`, which validates it and stores it encrypted ([server.py:4646](../../backend/server.py)). [`sleeper_write.py`](../../backend/sleeper_write.py) already exposes `token_claims()`, `token_sleeper_user_id()`, `token_expiry()`, `is_expired()`. **A valid Sleeper JWT whose `user_id` claim equals the session's `user_id` is cryptographic-ish proof that the human controls that Sleeper account** — you cannot obtain that token without logging into Sleeper with real credentials.
- **The upgrade.** When a user completes the Sleeper login and the linked token's `user_id` claim matches the session's `user_id`, mark the session **verified** (`sess["verified"] = True`, plus a persisted `users.verified_at` / a `verified_via='sleeper'` marker). No new identity provider, no new SDK, no new App-Store surface — it's the app's *existing* Sleeper-keyed identity model, finally *proven*.
- **Effort.** **Low** — the capture UI, the encrypted token store, and the JWT-claim readers already exist. New work is: a "does this token's `user_id` match the session user?" check, a `verified` flag on the session + a persisted column, and the write-protection gate (§3, P1). Reuses `_sleeper_write.token_sleeper_user_id` / `is_expired` verbatim.
- **Tradeoffs / caveats.**
  - **Signature is not cryptographically verified.** `sleeper_write.py` decodes the JWT **without verifying the HS256 signature** (Sleeper's signing key is private/undocumented). So a *forged* token with an arbitrary `user_id` claim would pass `token_sleeper_user_id()`. **Mitigation that closes this:** before trusting the claim, **exercise the token against Sleeper's authenticated API once** (the same GraphQL surface `propose_trade` uses, or a cheap authenticated read) — a forged token fails auth (401/1010), a real one succeeds. Sleeper itself is the signature oracle. This is a P1 must; a bare unverified-claim check is not sufficient proof.
  - **ToS/fragility.** The write surface is undocumented and flag-gated (`trade.send_in_sleeper`); Sleeper could change it. Verification-by-use inherits that fragility, so keep it best-effort with a clear failure path (stay unverified, don't hard-error).
  - **Not App-Store-neutral forever.** Sleeper-only verification is perfect for today's Sleeper-keyed app, but ESPN (#101) will bring users with **no Sleeper account** — see §4.
  - **4.8 exposure is low but confirm.** "Connect Sleeper" is framed as a **capability grant on an already-established session** (the user already signed in with a username), not a primary-account social login, so 4.8 likely does **not** apply to it. If a reviewer disagrees, Apple (§2a) is the fallback that satisfies it. Confirm at submission.

### 2d. Account binding / migration / squatting

All three mechanisms share one hard problem: **FTF data is keyed on `sleeper_user_id`** (`users.sleeper_user_id` PK, and every downstream table by convention). Whatever identity we add has to *bind* to that key without a heavy data migration.

- **Binding model (recommend Path 1 from the multi-platform plan).** Keep `sleeper_user_id` as the working key for all engine/ranking/match tables — **zero churn** — and add a thin identity layer above it. Minimal P1 shape: a `verified` marker on the user row (who has proven control) rather than a full `accounts`/`auth_identities` schema. The full `accounts` + `auth_identities` + `linked_sources` tables from [auth-multiplatform-plan-2026-06-11.md §Part A](auth-multiplatform-plan-2026-06-11.md) come in P2 when Apple/Google add a provider `sub` that must map to the Sleeper key.
- **Legacy unverified sessions.** Existing username-only sessions **keep working read-only** through a grace period. They are not force-logged-out; they simply can't hit write routes once enforcement (P3) turns on. During the grace window, writes from unverified sessions are *allowed but logged* (measure how many real users would be blocked before flipping to hard-deny).
- **Username-squatting ("a league-mate signed in as me before I did").** This is the core injustice #102 fixes and the migration's sharp edge. Today, whoever types the username first "owns" that user_id's rankings. On the day verification ships, the **rankings/tiers/overrides already sitting under a `sleeper_user_id` may have been authored by a squatter.** Decisions to pin:
  - **First *verified* controller wins.** When someone proves control of a Sleeper `user_id` via §2c, they become the authoritative owner. If the pre-existing data was squatter-authored, offer the verified owner a **"reset my rankings"** action (a scoped `/api/reset`-style wipe) rather than silently trusting inherited data.
  - **Verified state is sticky and exclusive.** Once a `user_id` is verified, unverified sessions for that same `user_id` lose write access immediately (they were the squatter). Log the transition for support.
  - **No global uniqueness assumption on Sleeper id** beyond this — shared family Sleeper accounts exist. Verification proves *control*, which is exactly what shared-account members legitimately have.
- **Grace period.** ~2–4 weeks of "writes allowed but instrumented" after P1 ships, then P3 enforcement. Long enough to see the funnel, short enough that the impersonation window closes soon.

---

## 3. Recommended phased path

**Guiding principle:** ship the *protection* before the *polish*. The security hole (§1) is real today; the identity anchor is a durability/UX upgrade. So verify-then-protect (P1) comes first and is small; Apple/Google (P2) follow; hard enforcement (P3) closes the window.

### P1 — Verified-session flag via Sleeper JWT proof + write-protection *(recommended first; size: S–M)*

- Add `sess["verified"]` (+ persisted `users.verified_at`, `verified_via`). Set it when the linked Sleeper token's `user_id` claim matches the session `user_id` **and** the token passes a one-shot live Sleeper auth check (closes the unverified-signature gap in §2c).
- Add a `@require_verified` gate (a thin wrapper over `_require_session`) and apply it to the **write routes in §1's table**. Read routes stay open.
- **Behavior during P1:** unverified writes are **allowed but logged** (grace period) — no user is blocked yet; we're measuring and giving people a path to verify. The two highest-risk routes — `POST /api/sleeper/link` and `POST /api/trades/propose` — can go **hard-verified immediately** (linking already *is* the verification step, and propose already requires a stored credential, so requiring verification there blocks nothing legitimate).
- **Client:** surface a "Verify your account to protect your ranks" prompt that routes into the existing `SleeperConnectScreen` flow. No new SDK.
- **Why first:** lowest friction, reuses shipped machinery (WebView capture, encrypted store, JWT readers), and immediately neutralizes the worst blast radius (real Sleeper writes) without waiting on Apple Developer config.

### P2 — Sign in with Apple as identity anchor + optional Google *(size: M–L)*

- Add `accounts` + `auth_identities` (per [auth-multiplatform-plan §Part A](auth-multiplatform-plan-2026-06-11.md)); `users.account_id` nullable column linking Sleeper-keyed users to accounts.
- `POST /api/auth/apple` (JWKS verify) → creates/attaches an account; **auto-binds the session's Sleeper `user_id`** as a linked source. Ship Apple **before/with** Google (4.8).
- `POST /api/auth/google` — same JWKS code path, different issuer. Optional, flag-gated; only ships alongside Apple.
- This gives **device-loss recovery** ("sign in with Apple on a new phone → restore your Sleeper-linked ranks") that Sleeper-only P1 can't, and is the platform-neutral anchor #101/ESPN will need (§4).
- **Interaction with P1:** an Apple/Google account is an *identity* anchor; the *Sleeper-control* proof from P1 is still what grants write access to Sleeper-keyed data. An account with a verified Sleeper link is fully trusted; an account with only Apple and no proven Sleeper link can read but not write Sleeper-keyed rankings (or must complete the P1 Sleeper proof to bind).

### P3 — Enforcement *(size: S)*

- Flip the grace-period write routes from "allow + log" to **hard-deny for unverified sessions.** Gate the flip on the P1/P2 funnel data (how many real users converted).
- Remove/prod-gate the seeded `User1..User5` bypass ([server.py:6100](../../backend/server.py)).
- Persist sessions (a `sessions` table or signed stateless token) so a Render restart doesn't log everyone out now that "stay signed in" is an expectation — called out as a latent reliability gap in the multi-platform plan.

**Sequencing rationale.** P1 is independent and ships now. P2 depends only on the account tables + JWKS verify (no dependency on P1). P3 depends on P1 (and ideally P2) funnel data. This mirrors — and is the security-first realization of — Phase 1 / Phase 1.5 in the [multi-platform plan](auth-multiplatform-plan-2026-06-11.md), scoped down to what #102 actually needs.

---

## 4. Parallel context — don't design Sleeper-only forever

- **Legal docs (#114) landing now.** Verification + a persisted account introduce account-data handling (a stored provider `sub`, `verified_at`, the encrypted Sleeper token). Make sure the privacy policy / terms being added under #114 cover: the Sleeper token storage (full-account credential, encrypted, revocable via "Disconnect"), Apple/Google `sub` storage, and the account-recovery model ("lose your provider → lose the account"). Flag this to whoever owns #114.
- **ESPN (#101) needs platform-neutral identity.** ESPN users may have **no Sleeper account**, so Sleeper-JWT proof (P1) cannot be their verification path. This is exactly why P2's Apple/Google anchor matters: it's the identity that isn't tied to any one league platform. Design the P1 `verified` flag as **`verified_via` (a source), not a boolean tied to Sleeper** — so "verified via Apple + linked ESPN league" is representable later without a schema rework. The [multi-platform plan's](auth-multiplatform-plan-2026-06-11.md) `accounts` → `linked_sources` model is the target; P1 just adds the minimal marker that's forward-compatible with it.

---

## 5. Groundwork code

**None landed.** Per the task constraint (seven agents editing shared files in parallel; code only if truly zero-risk and isolated), the natural P1 helper — a `verified`-session gate and the token-claim-matches-session check — must live in `server.py` (the most-contended shared file) to be useful, so it is **not** isolatable without collision risk. The pure primitives it would call already exist in [`sleeper_write.py`](../../backend/sleeper_write.py) (`token_sleeper_user_id`, `is_expired`, `token_claims`), so there is no zero-risk standalone module worth pre-creating. **Recommendation: implement P1 as a single focused change once the parallel work settles**, not as speculative groundwork now.

The one concrete pre-req to line up (no code): a **live Sleeper auth "is this token real" probe** for the §2c signature-gap mitigation — decide whether to reuse a cheap authenticated GraphQL read or piggyback the existing `propose_trade` auth path in a dry-run mode. Capture that during the next Send-in-Sleeper session.

---

## Appendix — key code anchors (branch `trade-engine-v2`, 2026-07-11)

- Username auth (no proof): `POST /api/extension/auth` — [server.py:8331](../../backend/server.py); public Sleeper lookup — [server.py:6061](../../backend/server.py)
- Session resolution: `_require_session` — [server.py:1049](../../backend/server.py); `_require_initialized_session` — [server.py:1089](../../backend/server.py); in-memory `_sessions` — [server.py:984](../../backend/server.py)
- `session_init` trusts body `user_id` — [server.py:6440,6457](../../backend/server.py)
- Sleeper write token: link/store — [server.py:4610](../../backend/server.py); propose real trade — [server.py:4669](../../backend/server.py); JWT readers — [sleeper_write.py:134-161](../../backend/sleeper_write.py); WebView capture — [SleeperConnectScreen.tsx](../../mobile/src/screens/SleeperConnectScreen.tsx)
- Impersonation surfaces: `test_user_fp_*` (prod-gated) — [server.py:6082](../../backend/server.py); `User1..User5` (live in prod) — [server.py:6100](../../backend/server.py)
- Identity key: `users.sleeper_user_id` PK — [database.py:53](../../backend/database.py); `sleeper_credentials` table — [database.py:673](../../backend/database.py)

*Sources: [Apple App Store Review Guidelines 4.8](https://developer.apple.com/app-store/review/guidelines/) · [Apple Developer news — updated guidelines](https://developer.apple.com/news/?id=7j1f99yf) · [Expo authentication guide](https://docs.expo.dev/develop/authentication/) · [Expo Google authentication](https://docs.expo.dev/guides/google-authentication/) · [Expo AuthSession SDK](https://docs.expo.dev/versions/latest/sdk/auth-session/). Code grounding: `backend/server.py`, `backend/sleeper_write.py`, `backend/database.py`, `mobile/src/screens/SignInScreen.tsx`, `mobile/src/screens/SleeperConnectScreen.tsx`, `config/features.json` on branch `trade-engine-v2` @ 2026-07-11.*

---

## P2 implementation status (2026-07-11)

Implemented on `trade-engine-v2` (Phase 2 agent), flag `auth.accounts` = **false** (dark):

- [x] `accounts` + `linked_identities` tables (`backend/database.py`) — binding lives on `accounts.sleeper_user_id` (one query for the restore path) rather than a `users.account_id` column; working key unchanged.
- [x] `users.verified_at` / `verified_via` columns declared additively (idempotent ALTER guards — safe if P1 declares the same).
- [x] `backend/accounts.py` — JWKS-verified RS256 identity tokens (Apple + Google, no PyJWT; uses the existing `cryptography` dep), find-or-create, **sticky binding** (no silent rebind; conflict surfaced), deletion matrix.
- [x] Routes (append-only in `server.py`): `POST /api/auth/apple`, `POST /api/auth/google` (503 until `GOOGLE_OAUTH_CLIENT_ID` set), `GET /api/account`, `DELETE /api/account` (ungated — 5.1.1(v)); session gets `verified`/`verified_via` + persisted marker on successful bind.
- [x] Mobile: Sign in with Apple button on `SignInScreen` (official component, flag-gated, `expo-apple-authentication` ~8.0.8 + `usesAppleSignIn`), "Link your Sleeper username" bind step, Settings → Account (identity display / Verify → `SleeperConnect` / double-confirm Delete).
- [ ] Google mobile flow — **stubbed** (backend route ready; `expo-auth-session` wiring deferred; 4.8 says it can only ship with Apple anyway).
- [ ] Operator: ASC Sign in with Apple capability + privacy-policy Apple/Google-`sub` coverage before flag flip — see runbook §"Sign in with Apple — App Store Connect".
- Note for P1/P3: `_provider_auth_response` marks sessions `verified_via='apple'|'google'` on bind. Per §3-P2, an Apple-anchored bind made from a *username-only* session inherits that session's squat risk — if P3 wants provider verification to imply Sleeper-write access only after a Sleeper-JWT proof, tighten there.

---

## P1 implementation status (2026-07-11)

Implemented on `trade-engine-v2` (Phase 1 agent). Grace mode ships ON (flag `auth.enforce_verified_writes` = **false**):

- [x] **Verification primitive** — `sleeper_write.verify_token_live()`: one-shot, schema-independent `__typename` GraphQL query against Sleeper's authed endpoint (raw-token auth + browser headers, same surface as `propose_trade`). Sleeper is the signature oracle (§2c mitigation): 401/403 ⇒ forged/dead; transport failure ⇒ inconclusive (never treated as proof **or** as forgery).
- [x] **`POST /api/sleeper/link` doubles as verification** — claim-must-match-session (403 `token_user_mismatch`), oracle-rejected token never stored (403 `token_rejected`), oracle-inconclusive stores but stays unverified; on proof `sess["verified"]=True` + `users.verified_at`/`verified_via='sleeper'` persisted (via `accounts.mark_user_verified`, shared with P2). Response gains `verified`.
- [x] **Write gate** (`@_gate_unverified_write` on all §1-table mutating routes; reads untouched): verified → allow; unverified + verified controller exists → 403 `verification_required` **even in grace** (first-verified-controller-wins, immediate — DB check per write); else grace → allow + one stable `AUTH-GRACE` log line (runbook §"Verified-session grace monitoring"); enforcement flag → 403. (`/api/trio/skip` postdates the §1 table and is currently ungated — fold into P3.)
- [x] **Hard-verified now, no grace:** `POST /api/sleeper/link` (proof inline), `POST /api/trades/propose` (403 `verification_required` — client copes: unknown errors already fall back to deep-link), `POST /api/account/reset-rankings`.
- [x] **Squatter remedy** — `POST /api/account/reset-rankings` (verified-only): wipes `swipe_decisions` + `member_rankings` + tier overrides/saved/ranking-method (all formats; `database.reset_user_rankings`) and resets the session's in-memory services. **UI entry point → P2's Settings account section** (add a "Reset my rankings" row next to Verify).
- [x] **`/api/session/init`** — additive `verification` response field `{session_verified, user_verified, verified_via, enforced}`; verified state survives same-user re-init, cleared when the token is re-pointed at a different user_id.
- [x] **Mobile:** SleeperConnect capture = verification (success state shows "Account verified"; mirrors into `useSession.verification`); quiet dismissible `VerifyAccountBanner` at the authed root (RootNav → Main) shown only when unverified AND (controller exists OR enforcement on), routing into SleeperConnect.
- [x] Tests: `backend/tests/test_verified_sessions.py` (oracle matrix, link proof paths, write-gate matrix, first-verified-wins, reset-rankings, session_init contract) + updated `test_sleeper_write_route.py`.
- [ ] P3 (unchanged): flip `auth.enforce_verified_writes`, prod-gate `User1..User5`, persist sessions; tighten P2's provider-implies-verified path (see note above); gate `/api/trio/skip`.

---

## P2.5 implementation status (2026-07-11) — read privacy

Implemented on `trade-engine-v2` (read-gate agent). Operator directive: "ranks **hidden** behind an account" means reads too — with P1 alone, a username-only attacker could still mint a session and *view* the victim's board.

- [x] **Read gate** — `@_gate_unverified_read` (server.py, beside the write gate; shares the controller lookup via `_verified_controller_via`). Rule = the write rule's verified-controller branch ONLY: unverified session + `users.verified_via` set → 403 `verification_required` (**no grace** — the owner has verified; squatters get nothing). Unverified with **no** controller reads normally (grace-era behavior — otherwise nobody could onboard), and `auth.enforce_verified_writes` is deliberately not consulted for reads (enforcement is a write-only concept). Same per-request DB check as the write gate, so a squatter's reads die the moment the owner verifies.
- [x] **Gated read routes** (board / board-derived content): rankings, progress ×2, me/streak, tiers status/community-diff/stability, anchor/scale GET, trades + trades/status + liked + matches + matches/all + awaiting, league/preferences GET, league/asset-prefs GET, feedback/mine, notifications inbox, trends ×3, extension/rankings, and `POST /api/trade/evaluate` **Mode B** inline (prices by the caller's board; Mode A stays public). Full gated/left-open matrix with per-route reasoning: [docs/api-reference.md §"The read gate"](../api-reference.md).
- [x] **Mobile:** `client.ts` exposes `ApiError.isVerificationRequired` + a central `setOnVerificationRequired` listener; `useSession` registers it and flips `verification` (user_verified=true, session_verified=false) so the existing `VerifyAccountBanner` appears — no per-screen toasts. Gated screens' load-error copy says "Verify your account to view your data." (shared `utils/verification.readErrorCopy`; applied to ManualRanks/Matches/Trends — TiersScreen owned by the tier-taxonomy thread, its generic error path is acceptable for now).
- [x] Tests: `backend/tests/test_verified_reads.py` (full deny matrix across every gated route, no-controller allow, enforcement-doesn't-deny-reads, verified allow, Mode A/B split, two-session owner-verifies-squatter-dies) + updated the "reads are never gated" premise test in `test_verified_sessions.py`.
- Known limitation (carry to P3): web + extension clients have no verification flow, so a verified owner's own username-only web/extension sessions read-403. The extension's `/api/extension/rankings` had to be gated regardless — it is the board, and leaving it open would have left a one-call bypass of the whole feature.

---

## P2.6 — Account-first identity (feedback #116, 2026-07-12)

> **Operator (#116, 1.6.0):** "I don't want sleeper to be the primary auth method. My primary leagues are on espn so I want my account to be stored using apple or google."

P2 built the Apple/Google anchor but still binds INTO a Sleeper-keyed world: a brand-new Apple identity with no Sleeper username was a dead end (`linked=false`, client forced the "Link your Sleeper username" step before anything worked). P2.6 inverts the model: **the account is the primary identity; league platforms (Sleeper username, ESPN league) are LINKED SOURCES on it.** A user can sign in with Apple and use the ranking product with no Sleeper id at all.

### The keying decision — synthetic working key `acct_<account_id>`

The engine keys *everything* on a single opaque `user_id` string (`users.sleeper_user_id` PK plus every user-keyed table by convention). Two options existed:

1. **Re-key the engine on `account_id`** — a migration touching ~20 tables, every service (`RankingService._user_id`, trade matching, notifications, feedback), and every client. Rejected: massive churn for zero behavior gain, and Sleeper-first users (the entire current base) have no account row.
2. **Synthetic namespaced working key** `acct_<account_id>` for account-only users — the engine keeps treating `user_id` as opaque (zero churn); precedent already exists for synthetic ids in the same keyspace (`demo_user_*`, `test_user_fp_*`, seeded `User1..5`). The `acct_` prefix cannot collide with Sleeper's numeric ids. **Chosen.**

**Audit of `user_id` flows for Sleeper-id assumptions** (what actually assumes the key is a real Sleeper id):

| Flow | Sleeper-id assumption? | Account-only behavior |
|---|---|---|
| swipes/Elo (`swipe_decisions`, `elo_history`), tier overrides/saved, anchors (`anchor_scale`), ranking method, prefs, streaks, feedback, notifications, user_events | none — opaque key | works under `acct_` key |
| `POST /api/extension/auth` leagues fetch, mobile `getLeagues()` | yes — calls `api.sleeper.app/v1/user/<id>/leagues` | never called with an `acct_` key (account-only flow skips the league picker; `useSession.connectLeague`/`revalidateSession` guarded) |
| `/api/session/init` | trusts body `user_id`; empty `opponent_rosters` triggers the **simulated-opponent demo fallback** | account-only sessions are built server-side (`_account_build_session`) with a real *empty* league — never via session_init, so no fake opponents |
| trade generation / matches / league routes | league-scoped; members' ids are real Sleeper ids | empty league → zero cards / empty inbox / "link a league" states (ESPN agent's surface fills these) |
| `POST /api/sleeper/link` + `/api/trades/propose` | JWT claim must equal session user_id | claim can never equal an `acct_` key → clean 403; propose additionally requires a stored credential that account-only users can't have |
| P1/P2.5 gates | none — `users.verified_via` lookup by key | account-only users are born verified (`verified_via='apple'`), so a hostile `/api/session/init` naming an `acct_` key gets read/write-403'd by the existing gates (tested) |

**Documented boundary:** league-scoped features (trades, matches, league screen, member unlocks) are structurally empty for account-only users until a source is linked — that is the honest product state, not a bug. Web + extension have no Apple flow (extends the P2.5 known limitation).

### Session flow

- `/api/auth/apple|google` with **no session + unbound account** now mints an **account-keyed session** instead of returning a dead `linked=false`: working key `acct_<account_id>`, users row upserted, `verified_via=<provider>` persisted (the provider proof IS the identity proof for an account-keyed user — there is no Sleeper account to squat), session marked verified. Response is additive: `account_only: true, session_token, user_id, league_id: "no_league", league_name: "No league linked"`.
- `_account_build_session` = `_extension_build_session` (per-format RankingServices with replayed swipes/overrides) **plus** an empty `League(members=[])` + per-format TradeServices, so `_require_initialized_session` routes (rank3, tiers/save, anchor/save, reorder, rankings/submit) work instead of 409ing. Trades generate → 0 cards (no members), matches → empty. Re-auth with the same Apple sub restores the same `acct_` key → board persists across sign-out/sign-in and device loss.
- **Sessions present:** a session already keyed `acct_*` never gets bound into `accounts.sleeper_user_id` (guard in `_provider_auth_response`) — the synthetic key must not masquerade as a linked Sleeper source.
- Mobile: Apple is the **primary portal** on SignInScreen (flag-gated as before); Sleeper username demoted to "Continue with Sleeper" (flow unchanged). Account-only sign-in pins the sentinel league `{no_league, "No league linked"}` so RootNav routes to Main.

### Linking + merge (`POST /api/account/link-sleeper`)

Body `{username, strategy?}`; requires an account-backed session (`sess.account_id`). Resolves username → Sleeper `user_id` S via the public API, then:

1. **Sticky binding (P2's rule):** account already bound to a different Sleeper id → 409 `sleeper_conflict`, nothing touched. Bound to S already → idempotent ok.
2. **First-verified-wins:** S has a verified controller (`users.verified_via` set — the real owner proved control via Sleeper-JWT, or another account claimed it) → **403 `sleeper_already_claimed`**, nothing touched. An account-only user cannot take over a claimed Sleeper id in P2.6 — the anti-takeover property outranks the convenience edge case (owner of a JWT-verified id linking it to a fresh Apple account must contact support / P3).
3. **Merge matrix** (A = account board has data, S = Sleeper board has data):
   - !A, !S / !A, S → bind, adopt S (keep S's data).
   - A, !S → bind, **migrate** account board → S.
   - A, S → **explicit user choice** required: without `strategy` → 409 `merge_choice_required` + both boards' summaries (swipe counts, per-format tiers/overrides/anchors flags). `strategy='keep_sleeper'` → account board wiped (`reset_user_rankings`, the shipped explicit-consent wipe) then adopt S; `strategy='keep_account'` → S's board wiped, account board migrated in. **No silent data loss** — every destructive path is either the user's explicit strategy choice or a pure migration.
   - Migration (`accounts.migrate_board_data`) re-keys `swipe_decisions`, `elo_history`, `user_player_skips` and copies the users-row board columns (`tiers_saved`, `tier_overrides`, `ranking_method`, `anchor_scale`, `unlocked_formats`); `member_rankings` under the `acct_` key are deleted (they reference the sentinel `no_league` and are meaningless under S); notifications/device tokens/events stay behind and die with the acct_ row (push re-registers on next launch under the new key).
4. On success: bind, `mark_user_verified(S, provider)` (same posture as P2's bind — carries the documented P3 tighten note), evict all `acct_` sessions, mint a fresh full session for S, return `{session_token, user_id, username, ...}` → client routes to the league picker.

Settings → Account lists linked sources (provider identities + the bound Sleeper username; ESPN leagues will append here — seam coordinated via report notes, not code) and shows "Link Sleeper username" for account-only users.

### Gate composition (proved in tests)

- Account-backed session ⇒ `sess.verified=True, verified_via='apple'` ⇒ passes P1 write gates + P2.5 read gates.
- `users.verified_via='apple'` on the `acct_` row ⇒ any *other* session naming that key (e.g. hostile `/api/session/init`) hits the verified-controller branch ⇒ 403 on reads AND writes, even in grace.
- Linked Sleeper id: `verified_via='apple'` on S composes with first-verified-wins — a later username-only session for S is read/write-403'd; and link-sleeper itself refuses ids that already have a controller.

### Status (2026-07-12)

- [x] `accounts.py`: `account_user_id`/`is_account_user_id`, `board_data_summary`, `migrate_board_data`.
- [x] `server.py`: account-first branch in `_provider_auth_response` (+ acct-key bind guard), `_account_build_session`, `POST /api/account/link-sleeper`, `GET /api/account` additive `account_only`/`sleeper_username` fields.
- [x] Mobile: SignInScreen restructure (Apple primary / "Continue with Sleeper" secondary), account-only landing (RootNav `onAccountSignedIn` → Main), Settings link-Sleeper row + merge-choice dialog, `useSession` account-only guards, `api/auth.ts` `linkSleeperUsername`.
- [x] Tests: `backend/tests/test_account_first.py` (account-only lifecycle, merge matrix, gate composition, flag-off parity).
- [ ] Operator prerequisite unchanged from P2: **ASC Sign in with Apple capability is not enabled yet** — everything stays behind `auth.accounts` (dark). Google mobile flow still stubbed.
- [ ] P3 additions from P2.6: support path for "JWT-verified Sleeper owner wants to link to a fresh account" (`sleeper_already_claimed` today); persistent sessions matter more now (account-only users can't revalidate via league handshake — a backend restart requires a fresh Apple tap).

---

## P2.7 — Settings surfacing fix (2026-07-12, post-1.7.1 / build 40)

> **Operator (build 40, flags live):** "I didn't see the option for either apple sign in or sleeper linking."

Diagnosis: both affordances existed but were invisible to the operator's session type. The Apple button lived only on `SignInScreen` (never seen by signed-in users), and Settings → Account's "Link Sleeper username" card rendered only for `account_only` sessions. A Sleeper-session user with no account row saw just "Linked sign-in — None" + Verify + Delete.

Fix (mobile-only; the backend session-bind path in `_provider_auth_response` already handled Sleeper-session callers and was fully tested):

- [x] Settings → Account now renders the official `AppleAuthenticationButton` (same HIG construction as SignInScreen; gated on `auth.accounts` + `isAvailableAsync` + resolved `GET /api/account` with no Apple identity). Tap → `signInAsync` → `POST /api/auth/apple` with the live session → bind + session verified. `conflict: true` (sticky binding — identity anchors a different Sleeper user) surfaces an honest toast; success mirrors `verified_via='apple'` into `useSession.verification` (no re-launch needed) and invalidates the account query.
- [x] Account section always renders meaningful state per session type: identities list, Apple-link card (or "Linked sign-in — None" where Apple is unavailable), Sleeper row (bound username, falling back to the session's own username for Sleeper sessions with no account row), link-Sleeper card (account-only, unchanged), Verification status row (P1 state, not flag-gated), Verify-account row (Sleeper sessions only, unchanged), Delete account. Demo sessions get a "Demo session — sign in to save your data" row instead of an empty header.
- No API contract changes; no backend changes.
