# League pass — plan

Date: 2026-11-22. Status: DRAFT, plan only. Nothing here is built.
Code read on branch `feat/paid-launch` at `4dba6dda`.

Companion docs: [prd.md](prd.md) · [hld.md](hld.md) · [lld.md](lld.md).
Builds on [../00-platform-foundation.md](../00-platform-foundation.md) and
[../../monetization-launch/paid-launch/scope.md](../../monetization-launch/paid-launch/scope.md).

- [1. The concept](#1-the-concept)
- [2. Decisions made](#2-decisions-made)
- [3. Why the hybrid, not account-wide](#3-why-the-hybrid-not-account-wide)
- [4. Product and price](#4-product-and-price)
- [5. Who buys and how a pass binds](#5-who-buys-and-how-a-pass-binds)
- [6. Server design in brief](#6-server-design-in-brief)
- [7. What members see](#7-what-members-see)
- [8. Lapse, cancellation and refund](#8-lapse-cancellation-and-refund)
- [9. Abuse cases](#9-abuse-cases)
- [10. Copy, legal and App Review](#10-copy-legal-and-app-review)
- [11. Binary versus server-only](#11-binary-versus-server-only)
- [12. Rollout](#12-rollout)
- [13. What to measure](#13-what-to-measure)
- [14. Timing](#14-timing)
- [15. Verified and unverified](#15-verified-and-unverified)

## 1. The concept

One league member buys a league pass. The other members of that league get the Pro
features in that league without buying their own subscription.

Fleeced only works when leaguemates are in it: a match needs two ranked managers in the
same league. One keen manager paying for the league removes the paywall from exactly the
people that manager needs.

## 2. Decisions made

| # | Decision | Decided |
|---|---|---|
| D1 | **Hybrid coverage.** Members get Pro in the covered league only. The buyer gets Pro everywhere. | Operator, 2026-11-22 |
| D2 | **One auto-renewable annual subscription** at $99.99, in the existing "Fleeced Pro" group, ranked above the individual plans. No monthly plan. | Recommended; not yet contested |
| D3 | **One-month free trial; the year-one discount is dropped.** One product, `ftf_league_annual`, with a one-month free trial as its introductory offer. Trial chaining is accepted with no server limit. | Operator, 2026-11-24 |
| D4 | **No offer codes.** The trial is delivered inside the normal purchase, as the product's introductory offer. | Operator, 2026-11-22 |
| D5 | **Ships after the paid launch**, not in it. | Recommended; not yet contested |
| D6 | **Coverage is derived at read time**, not stored as one grant per member. | Recommended |
| D7 | **New flag `monetize.league_pass`.** `growth.group_unlock` and the `promo_group_unlock` source stay reserved for their original idea (a free 14-day unlock at eight activated members, foundation §5). | Recommended |

Options considered and dropped: account-wide coverage (§3), a non-renewing season pass
(§4), permanent price tiers, year-one discount tiers (dropped 2026-11-24), offer codes,
cash rebates. The HLD §7 records why.

## 3. Why the hybrid, not account-wide

Account-wide coverage (every member of the league gets full Pro in all their leagues)
is simpler: it reuses the per-account grant and works on the current binary. It has one
flaw that rules it out.

**A Sleeper league is free to create.** Twelve strangers can form a throwaway league,
one buys the pass, and all twelve hold full Pro for $8.33 each instead of $34.99. That
sets the real price of the individual plan at $8.33 for anyone organised.

League-scoped coverage makes that pointless, because coverage only works inside the
throwaway league. It also matches the reason for the pass: a match needs leaguemates in
the same league, which only justifies coverage there.

| | Account-wide | Hybrid (chosen) |
|---|---|---|
| Throwaway-league abuse | Open | Pointless |
| Upsell in members' other leagues | Gone | Kept |
| Gate change | None | A league resolver for each of the 32 gated rules |
| Covered members on the current binary | Works (`pro: true`) | Needs a client update |

The gate change is smaller than feared. Every gated handler read so far already knows
its league: from the request body or query, from the session's active league, or from
the object it acts on (a match, a deck job and an overhaul each store a league id).

## 4. Product and price

**Type.** Auto-renewable annual in the "Fleeced Pro" subscription group, ranked above
`ftf_pro_monthly` and `ftf_pro_annual`. Apple then handles an upgrade from the individual
plan with proration, and nobody can hold both.

**One product.** `ftf_league_annual`, $99.99 a year, with a one-month free trial as its
App Store introductory offer. The trial is the store's: the server neither describes it
nor limits it. A buyer in the trial covers the league exactly like a paying buyer, and a
trial cancelled before it ends stops coverage at its end.

**Who gets the trial.** Apple gives each person one introductory offer per subscription
group, so a buyer who already used the individual plan's free month is charged from day
one. The SDK decides eligibility at purchase time.

**Why $99.99.** It is about 2.9 times the $34.99 individual plan, or $8.33 per team in a
12-team league. It pays for itself once three leaguemates would otherwise subscribe. It
is a starting point to test, not a researched price.

**Why no monthly plan.** It invites a one-month purchase at the trade deadline, and
eleven people churn every month.

**Trial chaining.** Each member has their own introductory offer, so a league could
chain free months of league-wide Pro by having one member start a trial after another's
lapses. Accepted with no server limit (operator, 2026-11-24); passes ended in trial are
measured.

**Limit.** One pass per Apple ID, so one buyer covers one league. Add-ons for more
leagues are a later phase.

## 5. Who buys and how a pass binds

- **Buyer.** Any verified member with a team in the league. The code stores no
  commissioner data, and it is inconsistent across Sleeper, ESPN and MFL.
- **Binding.** A server call, never purchase metadata. The app posts the chosen league
  before the purchase sheet opens. The server confirms membership and that the league
  has no active pass, and records the chosen league. The webhook binds the pass when the
  purchase arrives.
- **Membership source.** `league_members` for Sleeper. `platform_league_bindings` for
  ESPN and MFL, because `league_members` holds a synthetic id for every ESPN or MFL team
  that no app user is bound to.
- **Sleeper season rollover.** Sleeper issues a new league id each season. The pass
  follows the `previous_league_id` chain, which the `leagues` table does not store today.
- **Re-pointing.** The buyer can move the pass to another of their leagues, once per
  30 days.

## 6. Server design in brief

The LLD has the detail.

- **Buyer's row.** A new billing source `league_pass_iap`, mapped from the `ftf_league_`
  product prefix. The buyer holds an ordinary account-level `pro` row.
- **`league_passes` table.** One row per binding: buyer, product, league, platform,
  status. At most one active pass per league and one per buyer.
- **`league_pass_intents` table.** The league the buyer chose before purchase.
- **Coverage.** A member is covered in a league when that league has an active pass, the
  buyer's billing row is active, and the member is currently in the league. Nothing is
  written per member, so lapse, refund and roster changes need no fan-out, and a
  leaguemate who joins Fleeced later is covered at once.
- **Gate.** `paywall_gate.verdict` checks coverage after the account-level Pro check
  fails. A resolver table beside `ROUTES` names the league each gated rule acts on, and
  a test pins it. A league that cannot be resolved counts as not covered.
- **`/api/me/entitlements`.** Adds a `league_passes` list. `pro` stays account-level.
- **RevenueCat.** The product attaches to the `pro` entitlement and sit in their
  own offering. The current paywall renders any configured product that matches a
  package, so the launch binary would show the pass as a plain plan row if it shared the
  default offering.

## 7. What members see

- **Covered member, in the covered league.** No paywall. Settings shows that the league
  is covered and until when.
- **Covered member, in another league.** The normal paywall, with a line saying the pass
  covers only the other league.
- **Buyer.** Picks the league, sees the price and how many teams it covers, buys, and
  manages the pass in Settings.
- **Buyer's name.** Showing it tells others about a purchase. The default is "a
  leaguemate"; the buyer can opt in to being named.
- **A member who already pays.** Nothing changes for them. They are told once that the
  league is covered, so they can decide about their own plan.

## 8. Lapse, cancellation and refund

- **Auto-renew turned off.** Nothing changes until expiry. No notice is sent; members
  see the end date in Settings.
- **Expiry.** Coverage ends at once, because it is derived from the buyer's row. Former
  members have no entitlement rows of their own, so they still qualify for the deck
  preview and the individual free month.
- **Billing problem.** Apple's grace period extends the buyer's row, so coverage
  continues through it.
- **Refund.** Coverage ends at once. That account cannot buy a pass again.
- **Buyer leaves the league.** Coverage runs to the end of the term unless the buyer
  re-points the pass.
- **Buyer deletes their account.** The pass is released. Apple keeps billing until the
  buyer cancels, so the deletion flow has to say so.

## 9. Abuse cases

| Case | Handling |
|---|---|
| A throwaway league to share Pro | Pointless: coverage only works inside that league. |
| Spreading one pass across leagues | Not possible: one pass covers one league. |
| Serial re-pointing | A 30-day cooldown. |
| Seat inflation | Covered accounts are capped at `total_rosters` plus a small co-owner allowance. |
| Chaining free trials in one league | Accepted with no server limit (operator, 2026-11-24); measured. |
| Claiming a team in a public ESPN league, or an MFL league linked without a login | Possible: the link takes any team with no proof. Accepted under the seat cap; covered accounts per league are measured. |
| Refund after the trade deadline | Coverage ends at once; no repurchase. |

## 10. Copy, legal and App Review

- **Every string is new** and needs legal review: the plan row with the trial and
  renewal price, the bind confirmation, the covered state, the other-league line and
  the terms.
- **Terms.** Coverage depends on the buyer's subscription and on league membership. A
  pass covers one league at a time.
- **A ruling needed.** A covered state tells members that someone bought. Today's paywall rules are strict
  about not revealing subscriber status.
- **App Review.** It is sold through in-app purchase and shared across app accounts,
  which family-style plans already do. The reviewer needs a demo league with two
  accounts in the review notes. The app never collects league dues.

## 11. Binary versus server-only

- **Server-only.** The two tables, coverage, the league resolvers, the endpoints, the
  webhook mapping, admin binding and the comp experiment.
- **Client.** The league picker and purchase flow, the covered state, league-aware
  pre-checks, and Settings management. Four client call sites read the account-level
  `pro` flag before a gated action today, so covered members need the update.
- **Delivery.** The client work is JavaScript-only, but it should ship in a store build
  so the reviewer sees the flow with the new products.

## 12. Rollout

1. **Baseline, no build.** After the paid launch, comp 10 to 20 leagues through
   `/api/admin/entitlements/bulk-grant` against matched controls for four weeks. Stop if
   covered leagues show no lift in matches, sends or new joins.
2. **Server, dark.** Build the server side behind `monetize.league_pass`. Bind comp
   passes through the admin route to test league-scoped coverage with real users.
3. **Client and products.** Legal copy, the App Store product and its free-trial
   introductory offer, a store build and review.
4. **Release.** An allow-list of leagues first, then everyone.
5. **Later.** Add-ons for more leagues, Android and web purchase, and an extension of
   the individual plan for members who were already paying.

## 13. What to measure

- Pass purchases per eligible league.
- Share of covered members who use a gated feature within 30 days.
- Matches and sends per league, covered against control.
- New managers joining a league after a pass.
- Individual subscriptions cancelled within 30 days of becoming covered.
- Individual or pass purchases by covered members in their other leagues.
- Share of passes started in the free trial, the trial-to-paid rate, and passes per
  league that end in trial (chaining).
- Refund rate and 12-month renewal.

It is worth keeping if revenue per active league rises and covered leagues gain ranked
managers, without individual cancellations costing more than the passes bring in.

## 14. Timing

The pass ships after the paid launch, for three reasons:

- There is no baseline for individual conversion, so neither the price nor the
  cannibalisation can be judged.
- New products with unreviewed copy raise rejection risk on the submission that matters
  most.
- League scoping changes the gate hook that the launch evidence pins.

Only account-wide coverage with stored grants would fit the launch, and it carries the
throwaway-league flaw.

## 15. Verified and unverified

**Verified in code on 2026-11-22**

- Entitlements are per account, and `paywall_gate.verdict` is the only gate that reads
  Pro. The `_require_pro` wrapper is defined in `server.py` and applied to no route.
- `growth.group_unlock` and `promo_group_unlock` are a flag, a source name and one
  paragraph in the foundation doc. No logic reads either.
- An unknown product id falls through `_product_mapping` to `pro` / `apple_iap`, so a
  league product would grant the buyer Pro today with no code change.
- Gated handlers resolve a league from the body or query, the session's active league
  (`sess["league"]`), or the object: a match carries `league_id`, a deck job's key is
  `(user_id, league_id, format)`, and `overhauls` has a `league_id` column.
- `GET /api/trades` takes `league_id` as optional and returns every league's cards
  without it.
- Four client sites read `useEntitlements.pro` before a gated action:
  `TradesScreen.tsx:5527`, `WinNowScreen.tsx:101`, `ShopOffersBody.tsx:445` and
  `sendPreCheck` in `SendInSleeperButton.tsx:85`.
- `PaywallScreen.tsx:290` renders every product in the paywall config that matches a
  RevenueCat package.
- For ESPN and MFL, `league_members.user_id` is a real app id only for teams bound in
  `platform_league_bindings`; other teams get a synthetic id.
- `previous_league_id` is read only in `season_history.py`. `leagues` does not store it.

**Not verified**

- **Refund events.** The projector deactivates on a `REFUND` event. RevenueCat may
  report refunds as `CANCELLATION` with a customer-support reason, which the projector
  treats as a no-op. If so, this affects the individual plan at launch too.
- **Upgrade events.** What RevenueCat sends when a subscriber upgrades from the
  individual plan to a pass.
- **Introductory eligibility.** That it is per group and used up by the individual free
  month.

Settled on 2026-11-22 (detail in [lld.md](lld.md) §13): the Win Now and overhaul routes
act only on the session's active league; ending notices are dropped; introductory
eligibility is left to the SDK at purchase time; refund and upgrade events are checked
after release; unproven ESPN and MFL team links are accepted under the seat cap.
