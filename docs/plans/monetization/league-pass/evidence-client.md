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
`api/billing.ts:133-137` builds the config path through
`utils/leaguePass.ts:294` `paywallConfigPath`, which adds `caps=league_pass` only when
`monetize.league_pass` is true. Every converted pre-check reads
`utils/leaguePass.ts:52` `proForLeague`, which returns `pro` when the flag is off
(`state/useLeaguePass.ts`, `SendInSleeperButton.tsx:103-104` short-circuits on the flag).
`components/LeaguePassRows.tsx` returns null from each export unless both
`monetize.league_pass` and `monetize.paywall` are on; `LeaguePassCoveredNotice` is
not due with the flag off (`utils/leaguePass.ts:265`). `screens/LeaguePassScreen.tsx:169`
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

**Buying shows one price and charges that price.**
`LeaguePassScreen.tsx:209` `choose` → `POST /api/league-pass/intent` → the `league`
offering (`api/purchases.ts:445`) → tier 1/2: `checkIntroPriceEligible` (`:460`), else
`getPromoOffer` with the config's `promo_offer_id` (`:476`, priced from the discount
itself) → `utils/leaguePass.ts:159` `purchasePlan` decides the path and the prices
before the quote renders. `buy` (`LeaguePassScreen.tsx:274`) runs that path:
`purchaseCallFor(plan.path) === 'discounted'` (`:289`) requires the signed offer and
calls `purchaseDiscountedPackage` (`api/purchases.ts:496`); every other path calls
`purchasePackage`. No offer ⇒ the plan is `full_price`, the screen states the full price
and offers Continue at full price or Cancel.

**After the purchase.** `settle` (`LeaguePassScreen.tsx:250`) refreshes the entitlements
until a `buyer` entry appears; else `GET /api/league-pass` decides: `unbound` shows the
choose-a-league list (`bind`, `:320`), nothing yet shows "can take a few minutes".

**Settings and the paywall.** `SubscriptionSection.tsx:228,240` mount
`LeaguePassSettingsRows` in both verified branches; `PaywallScreen.tsx:700` the R26 line
under the body and `:658` the R30 entry closing the anchored block. Navigation:
`RootNav.tsx:867` registers `LeaguePass` once, as a modal.

## 2. TestFlight checklist (required, not yet run)

Prerequisites: a store build from this branch; App Store Connect products
`ftf_league_annual`, `ftf_league_annual_t1` (intro + promotional offer `league_t1_y1`)
and `ftf_league_annual_t2` (intro + `league_t2_y1`); RevenueCat offering `league` with
the three packages and the in-app purchase key uploaded; sandbox Apple IDs; the backend
on a test deploy with `monetize.paywall`, `monetize.entitlements` and the enforce knob
as the test needs. Record each step's result (pass / fail + screenshot) in
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

### D. Purchase, tier 0 (no paid annual leaguemates)

8. Buyer B (sandbox Apple ID never subscribed) in league L3 with no annual subscribers.
   Paywall → "Paying for your whole league? See the league pass" → choose L3. The quote
   shows L3, its team count and "<$99.99> a year" with the matching disclosure. Buy →
   Apple's sheet shows the same price. Confirm.
9. The screen shows "Confirming your league pass…", then "Your league pass covers L3."
   within about 15 seconds. Settings › Subscription shows "League pass: L3" and
   "Manage league pass".

### E. Purchase, tier 1 and tier 2

10. Tier 1, never-subscribed sandbox ID, a league with 1–2 paid annual leaguemates:
    the quote shows "<$84.99> for the first year, then <$99.99> a year"; Apple's sheet
    shows the introductory price; the sandbox receipt is the intro offer.
11. Tier 1, a sandbox ID that holds `ftf_pro_annual`: the quote shows the same split
    price, and Apple's sheet shows the promotional offer at that price (lld §13 item 1;
    record what Apple shows).
12. Promotional offer unavailable (temporarily remove `league_t1_y1` in App Store
    Connect, or test with the in-app purchase key removed from RevenueCat): the quote
    shows the full price only, "The first-year discount isn't available right now" and
    "Continue at full price" / "Cancel". Cancel returns to the league list with nothing
    bought. Continue opens Apple's sheet at the full price.
13. Tier 2 (3+ paid annual leaguemates): repeat 10 with "<$69.99> for the first year".

### F. Unbound → bind

14. Buy with no intent on record (buy, then let the intent expire before the webhook
    lands, or buy the product from a second device without choosing a league). Open
    Settings › Subscription → "Choose a league for your league pass" → the screen shows
    "Choose a league for your pass"; pick a league → "Your league pass covers <league>."
15. Bind to a league that qualifies for a higher price than the product bought: the
    screen shows the tier-mismatch line and stays on the list.

### G. Move and settings

16. As a buyer, Settings › Manage league pass: the league, "Renews <date>", the covered
    count. Turn auto-renew off in Apple's page and return: "Covered through <date>.
    It won't renew."
17. Move the pass to another league: the confirm names the target league; after it, the
    view shows the new league and "You can move it again on <date>" in place of Move.
    Coverage moved: a member of the old league now gets the paywall there.
18. Show my name on: a covered member's Settings line reads "Paid for by <buyer name>."
    after their next refresh. Off again: "a leaguemate".

### H. Refusals (each shows its own line)

19. Choose a league that already has a pass: "That league already has a league pass."
20. As a buyer, open the buy flow from the paywall: the screen opens on the manage view;
    with a pass already active, forcing the intent (another device) shows "You already
    have a league pass. You can move it to another league in Settings."
21. A league outside `LEAGUE_PASS_LEAGUE_ALLOWLIST`: "League passes aren't available for
    that league yet."
22. Move again inside the cooldown (operator shortens nothing): the move control is
    replaced by the date; a forced repoint shows "You can move your pass again on
    <date>."

### I. R29 notice and sign-out

23. User S with an individual `ftf_pro_annual` plan in a league that a leaguemate then
    covers: on the next visit to Find a Trade in that league, the strip "<league> is
    now covered by a leaguemate's league pass. Your own subscription hasn't changed."
    shows once. Dismiss, leave and return: it does not show again. A second covered
    league shows it once for that league.
24. Sign out and sign in as another account on the same device: no pass rows, lines or
    coverage from the previous account appear anywhere.
