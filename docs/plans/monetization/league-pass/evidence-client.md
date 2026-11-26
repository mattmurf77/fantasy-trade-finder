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
`utils/leaguePass.ts:292` `paywallConfigPath`, which adds `caps=league_pass` only when
`monetize.league_pass` is true. Every converted pre-check reads
`utils/leaguePass.ts:53` `proForLeague`, which returns `pro` when the flag is off
(`state/useLeaguePass.ts`, `SendInSleeperButton.tsx:103-104` short-circuits on the flag).
`components/LeaguePassRows.tsx` returns null from each export unless both
`monetize.league_pass` and `monetize.paywall` are on; `LeaguePassCoveredNotice` is
not due with the flag off (`utils/leaguePass.ts:221`). `screens/LeaguePassScreen.tsx:182`
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

**Paid launch's refetch-once-entitled effects (merged 2026-11-25).** Shop:
`ShopOffersBody.tsx:447` `entitled = useProForLeague(leagueId)`, the same `leagueId` prop
the sweep sends (`:399` query key, `:402` `league_id`), so when a refresh brings a live
pass for that league the gated sweep is re-run and the server decides; a pass for
another league leaves `entitled` false and the gate notice stays. The single-pin ideas
panel: `TradesScreen.tsx:5683` refetches on `payEntitled` (`:5566`, the active league).
The notice itself (`PaywallGateNotice`) renders only from a 402 on the sweep and reads
no entitlement, so a covered member whose sweep the server lets through never sees it.

**Buying: the free month is promised only when StoreKit confirms it** (free-month
revision, operator 2026-11-24). `LeaguePassScreen.tsx:222` `choose` → `POST
/api/league-pass/intent` (always `ftf_league_annual`) → the `league` offering
(`api/purchases.ts:444`) → the package for that product → `:234` asks
`checkIntroEligibility([sp])` (`api/purchases.ts:416`, the individual paywall's call) and
reads the answer with `=== true`. That call returns true only for RevenueCat status
ELIGIBLE with an intro of exactly one free month at price 0 (`isConfirmedFreeMonth`,
`:405`); status UNKNOWN, INELIGIBLE (this Apple ID already used an intro in the
subscription group, e.g. the individual plan's free month), NO_INTRO_OFFER_EXISTS, a
missing product, an SDK error or no SDK all give no `true`. `utils/leaguePass.ts:132`
`purchasePlan` then sets `freeMonth` only when that answer is true AND a StoreKit price
exists; with no StoreKit the config's display price shows, `canBuy` is false and no free
month is promised. The quote (`LeaguePassScreen.tsx:505`) shows "1 month free, then
<price> a year", the trial disclosure (charged when the free month ends; renews until
cancelled; cancel 24 hours before the free month or the period ends) and "Start 1-month
trial" when `freeMonth`; otherwise "<price> a year", the paid disclosure and "Buy league
pass". `buy` (`:275`) always runs the plain `purchasePackage(pkg, userId)` (`:290`);
Apple decides whether the intro applies. No promotional-offer or discounted call exists.

**After the purchase.** `settle` (`LeaguePassScreen.tsx:251`) refreshes the entitlements
until a `buyer` entry appears; else `GET /api/league-pass` decides: `unbound` shows the
choose-a-league list (`bind`, `:314`), nothing yet shows "can take a few minutes".

**Settings and the paywall.** `SubscriptionSection.tsx:228,240` mount
`LeaguePassSettingsRows` in both verified branches; `PaywallScreen.tsx:700` the R26 line
under the body and `:658` the R30 entry closing the anchored block. Navigation:
`RootNav.tsx:867` registers `LeaguePass` once, as a modal.

**Existing Pro users can buy (operator 2026-11-25).** `LeaguePassRows.tsx:113`
`buy = proBuyEntry(pro, sources, passes, now)` (`utils/leaguePass.ts:268`: pro, no
`league_pass_iap` source, no live buyer entry; a covered member still qualifies) adds
the row at `:149`, which navigates to `LeaguePass` with `{ source: 'settings' }`. It is
mounted through the existing Pro branch (`SubscriptionSection.tsx:242`); the non-Pro
branch (`:228`) never shows it because `proBuyEntry` needs `pro`. In the screen nothing
decides a state on `pro`: `pro` and `sources` are read only for
`currentProOnBuy` (`utils/leaguePass.ts:280`, `LeaguePassScreen.tsx:503`), which puts
the replace line (`apple_iap`) or the keep line (anything else) in the quote above the
Buy button (`:527`). The post-purchase loop (`:251`) waits for a `buyer` entry in
`league_passes` (`:254`), never for `pro`, which a Pro buyer already had.

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
   Privacy, and no "A league pass covers you in …" line.
2. In the backend request log, the `/api/paywall/config` request from the device has
   `platform=ios` and no `caps` parameter.
3. Settings › Subscription shows exactly the rows it showed before this build.
4. Find a Trade, Win Now and Send behave as before for a non-subscriber (paywall on the
   locked action).

### B. Covered member (flag on; operator comps a pass for league L1 with the admin route)

5. User M (verified, no subscription, a team in L1 and in L2). Pull to refresh or
   foreground the app. In L1: Find a Trade runs past the first page with no paywall;
   Win Now's search runs; Send in Sleeper reaches its "Send this trade?" confirm.
6. Settings › Subscription shows "A league pass covers you in L1 through <date>. It
   can end sooner, or be renewed." and
   "Paid for by a leaguemate." (comp passes have no buyer).
6a. Shop a player in L1 (a player's Shop action): the ideas load, no "See plans"
   notice. In L2 the same Shop shows the gate notice (enforcement on).
6b. With M not yet covered and the Shop notice showing in L1, comp the pass, then
   foreground the app: the sweep re-runs and the ideas replace the notice.

### C. Other-league paywall line

7. Still as M, switch to L2. Find a Trade hits the paywall at the page end; the paywall
   shows "A league pass covers you in L1 only. It does not cover this league." under the
   headline. Send in L2 opens the send paywall.

### D. Purchase with the free month (an eligible buyer)

8. Buyer B (sandbox Apple ID that has never subscribed in the group) in league L3.
   Paywall → "Paying for your whole league? See the league pass" → choose L3. The quote
   shows L3, its team count, "<$99.99> a year" as the largest text with "1 month free,
   then <$99.99> a year" in small text beneath it, the four cover lines ("Covers finding
   and sending trades for the managers in L3 …", "Coverage lasts while …", "You can move
   the pass …", "Leaguemates can see …"), the disclosure "Fleeced League Pass for L3: …
   Payment is charged to your Apple ID when the free month ends. Renews automatically
   until cancelled …", the button "Start 1-month trial", and Restore purchases · Terms ·
   Privacy below. At 375 pt wide nothing is clipped and the links row fits. Apple's sheet shows the
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
    Apple ID when you confirm …"), the button "Subscribe", and no "free" anywhere
    on the screen. Apple's sheet shows $99.99 a year with no trial. Confirm: C is charged
    $99.99 now, and the pass binds to L4 as in step 9.
13. Unknown eligibility falls back to paid: with the network to StoreKit unavailable
    while the quote loads (or on a build without the RevenueCat key), the screen never
    says "free"; with no StoreKit package it shows the config price and "The league
    pass can't be bought right now. Try again later." on Buy.
13a. Restore purchases on the quote (and on the choose-a-league step): tap it as a
    user with no purchases: "No subscription found for this Apple ID. …" (the
    paywall's `mon.pay.restore_none`); as a buyer on a fresh install: "Welcome back.
    Your subscription is restored." and the pass shows after the refresh.

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
    "Choose a league for your pass" and "… It covers that league only, and you can't
    move it for 30 days after you choose."; pick a league → "Your league pass covers
    <league>."

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
    now covered by a leaguemate's league pass. Your own subscription hasn't changed and
    still renews."
    shows once. Dismiss, leave and return: it does not show again. A second covered
    league shows it once for that league.
24. Sign out and sign in as another account on the same device: no pass rows, lines or
    coverage from the previous account appear anywhere.

### K. Existing Pro users (operator 2026-11-25)

25. User A with an active `ftf_pro_annual` (or `ftf_pro_monthly`) subscription, not a
    buyer: Settings › Subscription shows "Buy a league pass for your league". Tap it:
    the league list opens. Choose a league: the quote shows "Buying the league pass
    replaces your current Fleeced Pro subscription. … If your plan is at the Founder
    price, you may lose the Founder price." above the Buy button, and the paid price (no "1
    month free" if A used the individual free month). Buy in sandbox: Apple's sheet
    shows an upgrade; afterwards the done state names the league, a leaguemate is
    covered there, and Settings shows "League pass: <league>" with Manage, no buy row.
    Check `subscription_events` for the event sequence the upgrade produced (lld §13
    item 4).
26. User B with a lifetime grant (`manual_grant`, no store subscription): the same row;
    the quote shows "You already have Fleeced Pro, and it stays as it is. This pass is a
    separate subscription for your leaguemates. If the pass ends, your Pro is not
    affected." and no replace line. After the sandbox purchase (24 h lapse), B's
    league is covered; once the sandbox row lapses the leaguemate is gated again and B
    is still Pro.
27. User C covered as a member by a leaguemate's pass and Pro by their own plan: sees
    the member line AND the buy row; choosing the covered league shows "That league
    already has a league pass."
28. A non-Pro user: no buy row in Settings (See plans → the paywall's entry instead).
