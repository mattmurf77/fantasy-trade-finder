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
