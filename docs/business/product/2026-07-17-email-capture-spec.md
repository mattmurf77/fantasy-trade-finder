# Email Capture — Spec

**Date:** 2026-07-17 · **Requested by:** operator ("email tied to user profiles for nurture streams and user-interview outreach — standard data point") · **Status:** approved direction; backend lands post-P0, UI capture routes to the onboarding stream.

## Reality check (what exists today)

- **Apple sign-in:** Apple shares the email **once, on first authorization only**. `backend/accounts.py:hash_email()` stores a SHA-256 hash (`linked_identities.email_hash`) and deliberately discards the plaintext. Existing Apple users **cannot be backfilled server-side** — Apple won't resend the address unless the user revokes and re-links.
- **Sleeper-username sign-in (most users):** no email exists anywhere in the flow.
- **Privacy policy:** currently states "We never store your email address itself" / "No email addresses" — truthful today, must flip **in the same release** that starts capturing (never before, never after).

Consequence: an in-app optional email field is the primary capture path, not Apple.

## Spec

### Schema (backend/database.py — after the P0 build agent releases the file)

`accounts` gains nullable columns:

| Column | Type | Notes |
|---|---|---|
| `email` | String | plaintext, normalized lower/trim; the hash stays for dedupe/support |
| `email_source` | String | `apple` \| `user` |
| `email_consent_at` | String ISO | stamped at capture — consent to product updates + research outreach |
| `email_unsubscribed_at` | String ISO, nullable | set on unsubscribe/STOP; never send when set |

Data-dictionary update ships in the same change. Account deletion (analytics-platform FR-22 tombstone transaction) **also nulls `email`/`email_source`** — add to that spec's transaction.

### Capture paths

1. **Apple first-auth (new users):** stop discarding — store plaintext + hash. Note: users choosing "Hide My Email" yield `@privaterelay.appleid.com` addresses; outbound mail to relays requires registering the sending domain in Apple Developer → Private Email Relay (SPF/DKIM) — checklist item before any send.
2. **In-app optional field (everyone, incl. existing users):** Settings → Account "Add your email" + a skippable one-time onboarding prompt ("Product updates + occasional research invites — no spam, unsubscribe anytime"). This is the only path for Sleeper-only users and legacy Apple users. **UI belongs to the onboarding-conversion stream** (`docs/plans/onboarding-conversion/`), which owns prompt cadence/snooze patterns.
3. Server fires `email_captured` (props: `source`) — joins the analytics taxonomy (server-fired list).

### Consent & compliance

- Capture copy states the purpose at the field; consent timestamp recorded; every send includes unsubscribe (CAN-SPAM baseline); `email_unsubscribed_at` honored everywhere.
- Privacy policy diff (ship with the feature): §1 add "Email address (optional)" bullet (what/why/optional/unsubscribe/deletion); §2 remove the "no email addresses" claim, keep "no phone numbers / payment info"; §6 note email removed on deletion.
- App Store label diff at next submission: **Contact Info → Email Address**, linked to user, purposes App Functionality + Developer Communications.

## Decisions needed

1. Onboarding prompt now vs Settings-only first (rec: **Settings-only first**, prompt after the onboarding stream's current batch lands — their surface, their cadence rules).
2. Nurture-stream tooling (rec: defer to mkt-lifecycle; capture first, tooling when there's a list worth mailing).

## Handoffs

- Backend schema + Apple-flow + deletion-txn change → this session, post-P0 (or `/eng-backend`).
- Settings/onboarding capture UI → onboarding-conversion stream / `/eng-mobile`.
- Nurture sequences + send tooling → `/mkt-lifecycle`; interview outreach lists → `/ux-research`.
- Policy + label diffs → `/legal-privacy` review at ship.

---

## Status — 2026-08-11 (P1-3, audit A-12)

**Capture is LIVE.** `auth.email_capture` flipped to `true` in `config/features.json`, in
one commit with the `web/privacy.html` §1/§2/§5/§6 rewrite. No capture code was written
for this — the schema, the gated path, and four unit tests had already shipped. The
deliverable was the governance.

### Shipped

- Schema (`accounts.email` / `email_source` / `email_consent_at` / `email_unsubscribed_at`) — deployed since the P0 era, NULL until now.
- The Apple identity-token capture path (`backend/accounts.py:find_or_create_account`), including the repeat-auth backfill.
- The flag, at `true`, across `config/features.json` **and the three derived test fixtures** (`release.json`, `profiles-on.json`, `onboarding-v2.json` — the mirror tests assert exact key sets, so all four files move together).
- The privacy policy, amended and dated, with the flag↔policy pairing enforced by `test_release_flag_and_privacy_policy_ship_together`.

### NOT shipped, by decision

| Deferred | Owner |
|---|---|
| Settings / onboarding "Add your email" field — **the only path that reaches Sleeper-username-only users, i.e. the majority** | onboarding-conversion stream / `/eng-mobile` |
| `email_captured` analytics event (AN-6, cancelled this round: capture is a server-side side effect of signing in, not a user action, and the count is exactly queryable from state) | — |
| Any send path; Apple relay-domain registration (SPF/DKIM) | `/mkt-lifecycle` |
| An unsubscribe route or any writer for `email_unsubscribed_at` | `/mkt-lifecycle` |
| Encryption at rest for `accounts.email` | operator |

### Corrections to this spec, verified in code on 2026-08-11

1. **§Reality check, first bullet is wrong about the mechanism.** "Apple shares the email once, on first authorization only … existing Apple users **cannot be backfilled server-side**." FTF never reads `ASAuthorizationAppleIDCredential.email`, the genuinely first-auth-only *native credential property*. It reads the `email` claim from the **server-verified identity-token JWT** (`backend/server.py:_provider_auth_response` → `find_or_create_account`), and `accounts.py` carries a deliberate repeat-auth backfill branch — `if email and not acct.email` — with a test pinning it. Whether the JWT actually carries the claim on repeat auths **was not measured**: the planned gate-0 probe was **cancelled by the operator** on the grounds that with a user base of 3–5 people the answer changes nothing either way. So the sentence is unproven rather than disproven, and the "permanently lost reach" urgency it generated was never evidence.
2. **§Schema is wrong about deletion.** Account deletion does **not** "also null `email`/`email_source`". `delete_user_data` **hard-deletes the whole `accounts` row**, so the address dies with it. The outcome is stronger than the spec promised.
3. **`email_source`'s domain is `apple` | `google` | `user`, not `apple` | `user`.** `find_or_create_account` writes `email_source=provider`. `'google'` is structurally reachable but 503s today without `GOOGLE_OAUTH_CLIENT_ID`; `'user'` is unreachable because `set_account_email` has no callers.
4. **`email_unsubscribed_at` has no writer anywhere in the repo**, and there is no email-sending infrastructure of any kind (zero hits for `smtp|sendgrid|mailgun|postmark|ses|resend` across `backend/`, `requirements*.txt`, `mobile/package.json`). The privacy policy therefore promises **no** unsubscribe — a promise the code could not keep on the day it published.
5. **§Consent & compliance's policy diff was followed but not its §6 wording.** §6 names the address in both the deletion enumeration and the export, and states plainly that there is no way to remove the address short of deleting the account.

### Owed

- **App Store label** — Contact Info → Email Address, linked to user (App Functionality + Developer Communications). Recorded as a mandatory row in `docs/runbook.md` § *App Store pre-submission checklist*; actioned at the **next submission**, not at deploy.
- **Post-deploy row inspection** — a fresh Apple sign-in should produce `email` + `email_source='apple'` + `email_consent_at`; a "Hide My Email" sign-in should store an `@privaterelay.appleid.com` value; a Sleeper-username sign-in should produce no `accounts` row at all.
- **Professional legal review of `web/privacy.html`** — did not happen (D-P1-06). The file's header records this, and the standing operator TODO stands.
