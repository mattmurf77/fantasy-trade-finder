# League pass — PRD

Owner: operator. Date: 2026-11-22. Status: DRAFT.
Plan and decision record: [plan.md](plan.md). Design: [hld.md](hld.md), [lld.md](lld.md).

- [1. Problem and opportunity](#1-problem-and-opportunity)
- [2. Goals and non-goals](#2-goals-and-non-goals)
- [3. Users and stories](#3-users-and-stories)
- [4. Functional requirements](#4-functional-requirements)
- [5. Success metrics and instrumentation](#5-success-metrics-and-instrumentation)
- [6. Rollout](#6-rollout)
- [7. Risks](#7-risks)
- [8. Open questions](#8-open-questions)

## 1. Problem and opportunity

Fleeced produces a match only when two ranked managers in the same league like the same
trade. The paid launch puts finding and sending trades behind an individual
subscription. A subscriber whose leaguemates do not pay gets a deck with nobody to match
against, so the paywall on leaguemates lowers the value of the subscriber's own plan.

A league pass lets one manager pay for the league. It removes the paywall from the
people that manager needs, in the one league where it matters to them.

The opportunity is revenue from leagues that would otherwise produce one subscriber or
none, and more ranked managers per league.

## 2. Goals and non-goals

**Goals**

- G1. One purchase unlocks the Pro features for every member of one league, in that
  league.
- G2. The buyer keeps full Pro in all their leagues.
- G3. The individual plan keeps its value: a pass cannot be turned into cheap
  account-wide Pro.
- G4. Lapse, refund and roster changes take effect without operator work.
- G5. The pass can be judged against a measured baseline before a full release.

**Non-goals**

- Collecting or splitting league dues in the app.
- A monthly pass or a lifetime pass.
- More than one covered league per buyer (a later phase).
- Android or web purchase (a later phase). Coverage itself applies on every client the
  gate applies to.
- Apple Family Sharing or Apple multiseat purchasing as a way to cover a league. Family
  Sharing stays off. Multiseat is left at Apple's default, allowed (operator, 2026-11-25).
- Shipping in the first paid release.

## 3. Users and stories

- **The keen manager (buyer).** "I pay for Fleeced and nobody in my league is on it. I
  would pay more to get them in."
- **The commissioner (buyer).** "I already collect dues. I'll add this for the league."
- **The covered leaguemate.** "Someone covered our league. I can find and send trades
  here without paying."
- **The covered leaguemate with other leagues.** "It works in one league. I want it in
  my other two." This is the upsell to the individual plan or a second pass.
- **The existing subscriber whose league gets covered.** "I pay already. Tell me what
  changed so I can decide about my own plan."
- **The operator.** "I can comp a league, see every pass, and end one."

## 4. Functional requirements

### 4.1 Coverage

- **R1.** A covered member can use every gated feature (the `GATED` rows of
  `backend/paywall_gate.ROUTES`) in the covered league, on a verified session.
- **R2.** A covered member is gated as normal in every other league.
- **R3.** The buyer holds account-level Pro for the life of the subscription.
- **R4.** A member is covered while all three hold: the league has an active pass, the
  buyer's subscription is active, and the member is currently in the league.
- **R5.** A leaguemate who joins Fleeced, or joins the league, after the purchase is
  covered without any action by the buyer.
- **R6.** A member who leaves the league stops being covered at the next roster sync.
- **R7.** Covered accounts per league are capped at the league's team count plus a
  co-owner allowance (default 2).
- **R8.** An unverified session is never treated as covered, and its answer never
  depends on whether a pass exists.
- **R9.** A request allowed by a pass never spends the member's free deck preview.

### 4.2 Product and price

- **R10.** One auto-renewable annual product, `ftf_league_annual`, in the "Fleeced Pro"
  group, ranked above the individual plans, at $99.99 a year.
- **R11.** Withdrawn 2026-11-24 (the year-one discount tiers were dropped; plan D3).
- **R12.** Withdrawn 2026-11-24 (one product, so nothing to choose between).
- **R13.** A one-month free trial, delivered as the product's App Store introductory
  offer in the normal purchase sheet. Eligibility is Apple's (one introductory offer per
  person per group). No codes, no promotional offers.
- **R14.** No monthly plan. No server limit on trials per league: a buyer in the trial
  covers the league like a paying buyer, and trial chaining is accepted (operator,
  2026-11-24).
- **R15.** The plan row shows the trial and the renewal price together.

### 4.3 Purchase and binding

- **R16.** Any verified member with a team in a league can buy a pass for it.
- **R17.** The buyer chooses the league before the purchase sheet opens. The server
  refuses the choice if the buyer is not a member, the league already has a pass, or the
  buyer already has an active pass.
- **R18.** The pass binds to the chosen league when the purchase reaches the server,
  even if the app closed during the purchase.
- **R19.** A purchase with no usable choice on record leaves the buyer with Pro and an
  unbound pass. The app asks the buyer to choose a league.
- **R20.** Withdrawn 2026-11-24 (there are no discounted versions to check at bind).
- **R21.** The buyer can move the pass to another of their leagues once per 30 days.
  Coverage moves at once.
- **R22.** When a Sleeper league rolls over to a new season, the pass follows it without
  using the buyer's move.
- **R23.** A league has at most one active pass. A buyer has at most one active pass.

### 4.4 What people see

- **R24.** A covered member sees no paywall in the covered league.
- **R25.** Settings › Subscription shows a covered member the covered league and the
  date coverage runs to.
- **R26.** In an uncovered league, a covered member sees the normal paywall with a line
  saying the pass covers only the other league.
- **R27.** The buyer sees, in Settings, the covered league, the renewal date, how many
  leaguemates are covered, and the control to move the pass.
- **R28.** The buyer is shown as "a leaguemate" unless they opt in to being named.
- **R29.** An existing individual subscriber is told once when a league of theirs
  becomes covered. Nothing about their plan changes automatically.
- **R30.** The paywall offers the pass as a separate entry, not as a third plan row
  beside monthly and annual.

### 4.5 Lapse, cancellation and refund

- **R31.** Turning auto-renew off changes nothing until expiry.
- **R32.** No notice is sent about a pass ending. Covered members see the end date in
  Settings (R25), and the buyer sees how many leaguemates are covered (R27).
- **R33.** Coverage ends within one webhook cycle of expiry or refund, including the
  end of a free trial that was cancelled.
- **R34.** Coverage continues through Apple's billing grace period.
- **R35.** A former covered member keeps their eligibility for the free deck preview and
  the individual free month.
- **R36.** An account that had a pass refunded cannot buy a pass again without operator
  action.
- **R37.** A buyer who leaves the league keeps the pass bound there until they move it
  or it ends.
- **R38.** Account deletion by the buyer releases the pass, and the deletion flow says
  the App Store subscription must be cancelled separately.

### 4.6 Operator

- **R39.** The operator can comp a pass for a league for a set number of days, list
  passes, and end one. These routes are secret-guarded like the other admin routes.
- **R40.** Everything is dark behind `monetize.league_pass`. With the flag off, the gate
  and the entitlements response are byte-identical to today.
- **R41.** Release can be limited to an allow-list of leagues.

## 5. Success metrics and instrumentation

**Primary**

- Revenue per active league, pass leagues against matched leagues without one.
- Ranked managers per league, 30 days after a pass against 30 days before.

**Secondary**

- Pass purchases per eligible league (a league with at least three active users).
- Share of covered members who use a gated feature within 30 days.
- Matches and sends per league per week.
- Individual subscriptions cancelled within 30 days of becoming covered.
- Individual or pass purchases by covered members in their other leagues.
- Share of passes started in the free trial, trial-to-paid conversion, and passes per
  league that end in trial (trial chaining).
- Refund rate, and renewal at 12 months.

**Guardrail**

- Individual cancellations attributable to coverage cost less than pass revenue.

**Events** (names to be confirmed in the analytics taxonomy review; the LLD §9 lists
them): quote viewed, pass bound, pass moved, pass ended, coverage used. Purchase events
reuse the existing `paywall_purchase_*` events with the new product ids.

## 6. Rollout

| Phase | What | Exit |
|---|---|---|
| 0 | After the paid launch: comp 10 to 20 leagues with the existing bulk-grant route, against matched controls, for four weeks. No build. | Covered leagues show a lift in matches, sends or new joins. If not, stop. |
| 1 | Server side, dark. Comp passes bound through the admin route. | League-scoped coverage is correct for real users on all three platforms. |
| 2 | Legal copy, the product and its free-trial introductory offer, the client, a store build, App Review. | Approved build with the flag off. |
| 3 | Flag on for an allow-list of leagues, then everyone. | Metrics in §5 hold for four weeks. |
| 4 | Add-ons for more leagues; Android and web purchase; an extension of the individual plan for members who were already paying. | Separate decisions. |

## 7. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Covered members cancel individual plans | Lower revenue from the best leagues | The guardrail metric; phase 0 baseline |
| A gated route acts on a different league than the gate resolved | A member gets Pro outside the covered league | A pinned resolver per gated rule, and a handler check (LLD §4) |
| The buyer stops paying | Up to eleven people lose access at once | The end date shows in Settings; preview and free month stay available |
| Refund after heavy use | Free league-wide Pro for a season | Coverage ends at once; no repurchase |
| App Review rejects the model | Delay | Demo league and two accounts in the notes; clear plan-row disclosure |
| Members chain free trials in one league | Free league-wide Pro month after month | Accepted with no server limit (operator, 2026-11-24); measured |
| The launch binary shows the pass as a plain plan row | A purchase with no league | Separate RevenueCat offering; the config block is served only to clients that ask for it |

## 8. Open questions

1. **Price.** Is $99.99 right? Phase 0 does not answer this; a price test in phase 3
   would.
2. **Naming.** "League pass" is a working name. The App Store display name and the
   in-app name need a marketing and legal call.
3. **Commissioner-only buying.** Any member can buy in this draft. Should a
   commissioner be able to block or take over a pass?
4. **Showing the buyer.** Is opt-in naming acceptable, or should the buyer never be
   named?
5. **Members who were already paying.** Should they get anything when their league is
   covered? The plan defers this to phase 4.
6. **Re-point limit.** Is once per 30 days right?
7. **Legal ruling.** The covered-state disclosure in plan §10.
