# League pass, mobile client — evidence

Date: 2026-11-24. Scope: [scope-client.md](scope-client.md). Decision: D-281.

D-056 retired the simulator, so this file holds the two kinds of evidence that replace
it: a code-walk (§1) and the manual TestFlight checklist (§2). The executed and
structural guard is `mobile/tests/check-league-pass.js`.

- [1. Code-walk](#1-code-walk)
- [2. TestFlight checklist (required, not yet run)](#2-testflight-checklist-required-not-yet-run)

## 1. Code-walk

Line numbers are at the build's working tree; re-check after a merge.

**Flag off is today's app.**
`api/billing.ts:136` builds the config path through
`utils/leaguePass.ts:248` `paywallConfigPath`, which adds `caps=league_pass` only when
`monetize.league_pass` is true. Every converted pre-check reads
`utils/leaguePass.ts:51` `proForLeague`, which returns `pro` when the flag is off
(`state/useLeaguePass.ts`, `SendInSleeperButton.tsx:103-104` short-circuits on the flag).
`components/LeaguePassRows.tsx` returns null from each export unless both
`monetize.league_pass` and `monetize.paywall` are on; `LeaguePassCoveredNotice` is
not due with the flag off (`utils/leaguePass.ts:219`). `screens/LeaguePassScreen.tsx:166`
dismisses with the flag off and renders nothing (`if (!verified) return null`).

**Coverage reaches the pre-checks for the right league.**
`state/useEntitlements.ts:165` stores the server's `league_passes` on every refresh
(absent ⇒ `[]`) and `:202` / `:258` clear it on the account reset and a user change.
`screens/TradesScreen.tsx:5565` `payEntitled = useProForLeague(leagueId)` (the session's
active league, the `active` resolver's league); the existing offer-eligibility, held-page
and resume-on-entitled effect read `payEntitled` unchanged. `screens/WinNowScreen.tsx:108`
the same for Win Now's session league. `SendInSleeperButton.tsx:502` passes the button's
`leagueId` (the propose body's league, the `body` resolver); the MFL and ESPN twins pass
theirs (`SendInMflButton.tsx:336`, `SendInEspnButton.tsx:373`); `sendPreCheck` lets the
send on only for a live pass of that league (`:103-104`).

**Buying: the free month is promised only when StoreKit confirms it** (free-month
revision, operator 2026-11-24). `LeaguePassScreen.tsx:206` `choose` → `POST
/api/league-pass/intent` (always `ftf_league_annual`) → the `league` offering
(`api/purchases.ts:444`) → the package for that product → `:218` asks
`checkIntroEligibility([sp])` (`api/purchases.ts:416`, the individual paywall's call) and
reads the answer with `=== true`. That call returns true only for RevenueCat status
ELIGIBLE with an intro of exactly one free month at price 0 (`isConfirmedFreeMonth`,
`:405`); status UNKNOWN, INELIGIBLE (this Apple ID already used an intro in the
subscription group, e.g. the individual plan's free month), NO_INTRO_OFFER_EXISTS, a
missing product, an SDK error or no SDK all give no `true`. `utils/leaguePass.ts:130`
`purchasePlan` then sets `freeMonth` only when that answer is true AND a StoreKit price
exists; with no StoreKit the config's display price shows, `canBuy` is false and no free
month is promised. The quote (`LeaguePassScreen.tsx:488`) shows "1 month free, then
<price> a year", the trial disclosure (charged when the free month ends; renews until
cancelled; cancel 24 hours before the free month or the period ends) and "Start 1-month
trial" when `freeMonth`; otherwise "<price> a year", the paid disclosure and "Buy league
pass". `buy` (`:259`) always runs the plain `purchasePackage(pkg, userId)` (`:274`);
Apple decides whether the intro applies. No promotional-offer or discounted call exists.

**After the purchase.** `settle` (`LeaguePassScreen.tsx:235`) refreshes the entitlements
until a `buyer` entry appears; else `GET /api/league-pass` decides: `unbound` shows the
choose-a-league list (`bind`, `:298`), nothing yet shows "can take a few minutes".

**Settings and the paywall.** `SubscriptionSection.tsx:228,240` mount
`LeaguePassSettingsRows` in both verified branches; `PaywallScreen.tsx:700` the R26 line
under the body and `:658` the R30 entry closing the anchored block. Navigation:
`RootNav.tsx:867` registers `LeaguePass` once, as a modal.

## 2. TestFlight checklist (required, not yet run)

Prerequisites: a store build from this branch; App Store Connect product
`ftf_league_annual` ($99.99 a year) with a one-month free-trial introductory offer;
RevenueCat offering `league` holding its package; sandbox Apple IDs: one that has never
subscribed to anything in the subscription group, and one that already took the
individual plan's (`ftf_pro_annual` / `ftf_pro_monthly`) free month; the backend on a
test deploy with `monetize.paywall`, `monetize.entitlements` and the enforce knob as the
test needs. Sandbox renewal is accelerated (a one-month trial lasts minutes); note the
sandbox durations you saw. Record each step's result (pass / fail + screenshot) in
`living-memory/TEST_LEDGER.md`.

### A. Flag off (`monetize.league_pass` false on the server)

1. Sign in as a verified, non-subscribed user. Open the paywall from Settings › See
   plans. There is no "Paying for your whole league?" link under Restore / Terms /
   Privacy, and no "Your league pass covers …" line.
2. In the backend request log, the `/api/paywall/config` request from the device has
   `platform=ios` and no `caps` parameter.
3. Settings › Subscription shows exactly the rows it showed before this build.
4. Find a Trade, Win Now and Send behave as before for a non-subscriber (paywall on the
   locked action).

### B. Covered member (flag on; operator comps a pass for league L1 with the admin route)

5. User M (verified, no subscription, a team in L1 and in L2). Pull to refresh or
   foreground the app. In L1: Find a Trade runs past the first page with no paywall;
   Win Now's search runs; Send in Sleeper reaches its "Send this trade?" confirm.
6. Settings › Subscription shows "Your league pass covers L1 through <date>." and
   "Paid for by a leaguemate." (comp passes have no buyer).

### C. Other-league paywall line

7. Still as M, switch to L2. Find a Trade hits the paywall at the page end; the paywall
   shows "Your league pass covers L1 only. It does not cover this league." under the
   headline. Send in L2 opens the send paywall.

### D. Purchase with the free month (an eligible buyer)

8. Buyer B (sandbox Apple ID that has never subscribed in the group) in league L3.
   Paywall → "Paying for your whole league? See the league pass" → choose L3. The quote
   shows L3, its team count, "1 month free, then <$99.99> a year", the disclosure
   "… Payment is charged to your Apple ID when the free month ends. Renews automatically
   until cancelled …", and the button "Start 1-month trial". Apple's sheet shows the
   one-month free trial, then $99.99 a year. Confirm.
9. No charge now: the sandbox purchase history shows the trial, not a $99.99 charge.
   The screen shows "Confirming your league pass…", then "Your league pass covers L3."
   within about 15 seconds. Settings › Subscription shows "League pass: L3" and
   "Manage league pass".
10. Members are covered during the trial: as a member of L3 (verified, no subscription),
    refresh; Find a Trade runs past the first page with no paywall and Send reaches its
    confirm, while B is still in the free month.
11. Let the trial run out without cancelling: B is charged $99.99 when the free month
    ends (sandbox time), the pass stays live, and L3's members stay covered.

### E. Purchase without the free month (an ineligible buyer)

12. Buyer C (sandbox Apple ID that already took the individual plan's free month) in
    league L4. The quote shows "<$99.99> a year", the paid disclosure ("… charged to your
    Apple ID when you confirm …"), the button "Buy league pass", and no "free" anywhere
    on the screen. Apple's sheet shows $99.99 a year with no trial. Confirm: C is charged
    $99.99 now, and the pass binds to L4 as in step 9.
13. Unknown eligibility falls back to paid: with the network to StoreKit unavailable
    while the quote loads (or on a build without the RevenueCat key), the screen never
    says "free"; with no StoreKit package it shows the config price and "Purchases
    aren't available on this build yet." on Buy.

### F. Cancelling during the trial

14. Buyer D (eligible, as B) starts the trial for league L5, then turns auto-renew off
    in Apple's subscription page before the free month ends. Back in the app: Manage
    league pass shows "Covered through <trial end date>. It won't renew." L5's members
    stay covered until that date. After the trial ends (sandbox time) and the
    entitlements refresh: D is never charged, the pass is gone from Settings, and an L5
    member gets the paywall on Find a Trade again.

### G. Unbound → bind

15. Buy with no intent on record (buy, then let the intent expire before the webhook
    lands, or buy the product from a second device without choosing a league). Open
    Settings › Subscription → "Choose a league for your league pass" → the screen shows
    "Choose a league for your pass"; pick a league → "Your league pass covers <league>."

### H. Move and settings

16. As a buyer, Settings › Manage league pass: the league, "Renews <date>", the covered
    count. Turn auto-renew off in Apple's page and return: "Covered through <date>.
    It won't renew."
17. Move the pass to another league: the confirm names the target league; after it, the
    view shows the new league and "You can move it again on <date>" in place of Move.
    Coverage moved: a member of the old league now gets the paywall there.
18. Show my name on: a covered member's Settings line reads "Paid for by <buyer name>."
    after their next refresh. Off again: "a leaguemate".

### I. Refusals (each shows its own line)

19. Choose a league that already has a pass: "That league already has a league pass."
20. As a buyer, open the buy flow from the paywall: the screen opens on the manage view;
    with a pass already active, forcing the intent (another device) shows "You already
    have a league pass. You can move it to another league in Settings."
21. A league outside `LEAGUE_PASS_LEAGUE_ALLOWLIST`: "League passes aren't available for
    that league yet."
22. Move again inside the cooldown (operator shortens nothing): the move control is
    replaced by the date; a forced repoint shows "You can move your pass again on
    <date>."

### J. R29 notice and sign-out

23. User S with an individual `ftf_pro_annual` plan in a league that a leaguemate then
    covers: on the next visit to Find a Trade in that league, the strip "<league> is
    now covered by a leaguemate's league pass. Your own subscription hasn't changed."
    shows once. Dismiss, leave and return: it does not show again. A second covered
    league shows it once for that league.
24. Sign out and sign in as another account on the same device: no pass rows, lines or
    coverage from the previous account appear anywhere.
