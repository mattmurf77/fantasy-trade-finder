# Referral first-init integration correction

2026-11-04. Authorized as part of merging the reviewed launch stacks. This
corrects their real mint/init incompatibility; all referral flags stay OFF.

The auth builders persist a users row before handing out a token. The old
referral predicate `not user_exists` therefore never recognized a real fresh
mint. The old six E2E cases injected a verified session with no user, which
privacy's daemon guard must refuse to recreate. Those cases now use the real
extension session builder and preserve their original attribution assertions.

## Durable eligibility and migration

`users.first_init_pending` is nullable INTEGER. Only `upsert_user`'s actual
INSERT sets 1. Legacy rows migrate to NULL, with no backfill from timestamps,
events or activity absence. Ordinary updates and restores never reset it.
The first initialized league session changes 1 to 0 conditionally. A missing
user raises AccountGone and cannot be recreated by init. Account-only sentinel
sessions leave eligibility until a real league is initialized.

Auth audit: fresh Sleeper/extension auth and `_account_build_session` (Apple,
Google and proven ESPN/MFL account sign-in) all funnel through that upsert.
Accounts helpers create the account/identity rows, not a users row before the
builder. The sole direct users INSERT in `accounts.migrate_board_data` copies
an existing board to a destination; it deliberately remains NULL/ineligible,
and ordinary destination updates do not copy/reset the marker.

## Atomic boundary

`first_init_transaction` holds the live users-row guard and conditionally
claims eligibility, so concurrent first inits have one winner. The winner
uses one supplied connection through existing attribution reads/writes,
including referral claim/sibling, joined notification and referral_attributed
measurement; it fills invited_by only when NULL and records signup on that
connection. The inviter's live users row is locked before any referral-row
claim, following deletion's user→referral lock order; a stale token/candidate
read cannot credit a referrer tombstoned concurrently. Errors propagate only for this explicit transaction path and roll
back the claim plus all these effects. A later attempt can retry. Losers and
legacy users record app_open and never attribute again. Handled uniqueness
conflicts use savepoints so PostgreSQL keeps the outer transaction usable.
Existing helper callers keep their default best-effort behavior. Legacy
receipt delivery and later peer pushes remain outside this atomic boundary.

The user's request/background lifecycle lease and live-user DB guard remain.
No general outbox or atomic delivery of later peer pushes, league writes or
other daemon work is promised. No credentials, provider calls, new client
fields, flags, knobs or feature activation are introduced.

## Evidence and delivery gates

Focused tests cover real mint→init, real account/ESPN/MFL builders, legacy
NULL/consumed exclusion, immutable inviter, simultaneous first inits,
rollback/retry after signup INSERT, shared-transaction uniqueness recovery,
additive migration and deletion before a held daemon. The same transaction
cases support a disposable socket-only PG test URL in
`FTF_FIRST_INIT_PG_URL`, each case owning a private synthetic schema.
Independent privacy review and full combined GitHub CI are required before
merge. Exact results are recorded in living-memory/TEST_LEDGER.md.
