# ADR-016 — RevenueCat is the purchase layer; the entitlements ledger is the truth

**Date:** 2026-08-28
**Status:** Accepted
**Author:** worktree session `claude/monetization-features-feedback-a6fe77`
(scope block: [`../plans/monetization/iap-enablement/scope.md`](../plans/monetization/iap-enablement/scope.md);
plan of record [foundation §4](../plans/monetization/00-platform-foundation.md) ·
[pro-subscription HLD §"Decision log"](../plans/monetization/pro-subscription/hld.md) ·
[pro-subscription LLD §3/§6](../plans/monetization/pro-subscription/lld.md);
IAP enablement runbook 2026-08-27 §B6, authored on the `app-launch-scorecard` worktree)

Written now because this is the build where the decision stopped being a plan: the
webhook path grew alias reconciliation, TRANSFER and grace handling, and
`GET /api/paywall/config` shipped. The pro-subscription LLD §8 says to record it when
the first code lands.

## Context

FTF needs to sell three things on iOS — an auto-renewing Pro subscription
(`ftf_pro_monthly` / `ftf_pro_annual`), a perpetual Founder Lifetime
(`ftf_founder`), and a season pass (`ftf_season_pass_2026`) — and to answer one
question correctly on every request: *does this user have `pro` right now?*

Two constraints shape the answer.

**It is a solo operator on a weekend budget.** The runbook (§B6) prices the
alternatives directly: RevenueCat is a weekend of integration, raw StoreKit 2 is
roughly two weeks of solo work.

**The client cannot be believed.** Anything the app can compute about its own paid
status is spoofable, cacheable, and wrong across re-installs, Sleeper re-links, and
account merges. FTF's identity layer makes this sharper than usual: the working key
moves (`sleeper_user_id` → `acct_*`) and a purchase can legitimately happen *before*
the user has an account at all, arriving under RevenueCat's own
`$RCAnonymousID:<uuid>`.

## Decision

**Two layers, one direction of trust.**

1. **RevenueCat (`react-native-purchases`, Expo config plugin, EAS build) is the
   purchase layer.** It owns StoreKit, receipt validation, the offerings that render
   real localized prices, restore-purchases, and promotional entitlements (which the
   referral loop needs — foundation §5). The client calls
   `Purchases.logIn(<working key>)` so RevenueCat's subscriber identity tracks ours.

2. **`backend/entitlements.py` + the `entitlements` / `subscription_events` tables
   are the truth.** The RevenueCat webhook is the *only* billing path into an
   entitlement row; client receipts are never trusted and never posted. Every gate
   (`check_pro`, `@_require_pro`) and every client bootstrap
   (`GET /api/me/entitlements`) reads the server's resolution.

**`CustomerInfo` on the device is a UI cache, nothing more.** It exists so a user who
just paid does not stare at a locked screen while the webhook lands — the HLD's
bounded optimistic unlock. It never decides a gate, and it is never written back to
the server.

Three consequences of "the server decides" that this build made concrete:

- **Identity is reconciled server-side, off `event.aliases`** — the first candidate
  that is a working key we already know wins, and rows written under a superseded id
  are re-keyed onto it (`resolve_rc_identity`). An unrecognised id is kept verbatim
  rather than dropped: an anonymous purchase is real money, and it merges the moment
  an alias identifies it.
- **Store events are projected by meaning, not by name.** `TRANSFER` *moves* an
  entitlement (not `expired`, which would claim it lapsed, and not `revoked`, which
  would claim we took it); `BILLING_ISSUE` *extends* `expires_at` through the store's
  grace window; `CANCELLATION` does nothing, because access runs to period end.
- **Presentation is server config too.** `GET /api/paywall/config` serves pages,
  feature keys and SKUs so packaging changes without an app release — with display
  prices explicitly marked fallback copy, since only StoreKit knows the user's
  storefront.

## Alternatives considered

**Raw StoreKit 2 + App Store Server Notifications v2.** Rejected on cost, not
capability. It means JWS verification, notification v2 parsing, a hand-rolled
subscription state machine, and hand-built promotional grants for paid subs —
~2 weeks of solo work against a weekend (runbook §B6), for zero user-visible
difference. It also buys nothing on the web side, where Stripe is a separate
integration regardless.

**Trust the client's `CustomerInfo` and skip the ledger.** Rejected: it makes paid
status spoofable, unauditable in a refund dispute, and unrecoverable across a working-
key change — precisely the three cases FTF's identity model guarantees will happen.
It would also leave no answer to "did this user actually pay?" other than opening
someone else's dashboard.

**RevenueCat's own entitlement check as the gate (skip our `entitlements` table).**
Rejected: it welds the gate list to one vendor, cannot express manual grants, promo
rewards, referral unlocks or the rank-set marketplace's non-store grants, and gives
web (Stripe) purchases no home. The ledger is payment-agnostic on purpose.

## Consequences

**Easier.** One projector serves Apple- and Stripe-shaped events. Gate application is
a decorator over a boolean the server already knows. Manual comps, promos and referral
rewards are rows in the same table as purchases, so `get_entitlements` needs no special
cases. Packaging and pricing copy change without an app release.

**Harder / slower.** Entitlement state is eventually consistent — the seconds-to-
minutes between a purchase completing and the webhook landing are real, and the
optimistic client unlock exists to cover them. Every new store event type is a
deliberate projector decision rather than a library default; unhandled types are stored
with a `process_error` note rather than silently applied.

**Costs.** RevenueCat takes **1% of tracked revenue above $2.5k/month** — immaterial at
launch scale and, by construction, only ever charged on money already collected.

**Risks and their mitigations.**

- *Webhook outage or ordering.* The ledger is idempotent on provider `event_id` and
  keeps `processed_at` / `process_error`, so events replay; the client's bounded
  optimistic unlock bridges the gap.
- *Vendor lock-in.* Bounded on purpose: because entitlements are payment-agnostic rows
  in our own table, swapping the purchase layer later touches the webhook adapter and
  the mobile purchase module — never a gate, never a client's notion of `pro`. The
  ledger is the portability guarantee, and it is the reason this ADR is about two
  layers instead of one vendor.
- *Anti-steering / storefront rules.* Unchanged by this decision; the web Stripe path
  and its SCOTUS-risk caveat live in the plan docs.

**Ships dark.** Every `monetize.*` flag is false and no route wears `@_require_pro`;
the webhook and `/api/paywall/config` are mounted regardless (provider traffic and
client bootstrap both precede any flag flip).
