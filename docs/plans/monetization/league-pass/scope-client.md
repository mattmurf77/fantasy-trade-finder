# Feature Scope — League pass, mobile client (phase 2, dark)

**Date:** 2026-11-24
**Entry point:** direct ask (operator, phase 2 of the league pass; decision D-281)
**Builder:** Opus builder subagent; the main session reviews and merges
**Branch:** `feat/league-pass-client`, stacked on `feat/league-pass-server`
**Operator sign-off on waivers:** none needed. There are no waivers in this block.

Design: [prd.md](prd.md), [hld.md](hld.md), [lld.md](lld.md) §8 (the file list) and §10
(edge cases). The server is [scope.md](scope.md) (phase 1). This block covers the iOS
client only: the purchase screen, the league-aware pre-checks, the paywall and Settings
lines, and the one-time notice. Store products, RevenueCat setup and legal copy are
outside the code and gate the flag, not this build (§5).

**Revision 2026-11-24, "Free month replaces discount" (operator).** The three tiered
products and their year-one discounts are gone. The pass is ONE product,
`ftf_league_annual`, $99.99 a year, whose App Store introductory offer is a one-month
free trial. The client buys it with a plain `purchasePackage` from the `league`
offering; Apple applies the free month to an eligible buyer. The screen says "1 month
free" only when StoreKit confirms this Apple ID's free month (`checkIntroEligibility`,
the individual paywall's rule); eligibility is per subscription group, so a buyer who
used the individual plan's free month sees the plain yearly price. Removed: the
promotional-offer wrappers, the tier → purchase-path decision, the full-price notice,
the tier fields on the intent / config / view types, and their copy.

**Revision 2026-11-25, "existing pro users need the option to purchase a league pass"
(operator; the pass is ON at the initial public launch).** A Pro user never sees the
paywall's entry, so Settings › Subscription gets a buy row (`settings-league-pass-buy`)
for any Pro user who is not already a buyer (no `league_pass_iap` source, no live
`buyer` entry), shown also when a leaguemate's pass covers them as a member (decided:
they may buy for another league; the server refuses a covered league). It opens the
existing `LeaguePass` route (`source: 'settings'`). On the quote, before Buy, an App
Store individual subscriber (`apple_iap`) reads that the pass replaces their
subscription (an upgrade in the same group; Apple refunds the unused part); any other
Pro (lifetime, comp, promo grant, Founder, a web plan) reads that it stays. No free
month is promised unless StoreKit confirms it, unchanged. New copy keys (placeholder,
pending legal): `mon.lp.pro.row`, `mon.lp.pro.row_a11y`, `mon.lp.quote.replaces`,
`mon.lp.quote.keeps`. No new event, flag, route or schema. The server's upgrade and
downgrade handling is on `feat/league-pass-server` (lld §5.1).

---

## 1. Analytics scope

- [x] **(a) No new client events.** Purchases reuse the registered
  `paywall_purchase_initiated` {`product_id`, `source`}, `paywall_purchase_completed`
  {`product_id`, `source`} and `paywall_purchase_failed` {`product_id`,
  `user_cancelled`} with the league product id (`ftf_league_annual`; a trial start
  fires `_completed` like a paid purchase, as on the individual paywall). `source` is the value that opened
  the league pass screen (the paywall's own `source`, or `settings`), so it stays inside
  the existing vocabulary. No `paywall_viewed` is fired by the new screen.
  → nothing to register in `backend/analytics_taxonomy.py` or
  `analytics_queries.NON_INTENT_EVENTS`. `tests/check-league-pass.js` 9c fails if a new
  event name appears in the new files.
- [x] **(b) Server events** (`league_pass_quote_viewed`, `_bound`, `_ended`,
  `_coverage_used`) are phase 1's and unchanged.

## 2. Schema & flag scope

- No schema change. No route change. No backend file changed.
- Flag: `monetize.league_pass` (phase 1, default off), read by the client through
  `useFlag` / `useFeatureFlags.getState()`. Purchase entry points also require
  `monetize.paywall`. With the flag off:
  - `GET /api/paywall/config` is requested exactly as today (no `caps` param);
  - `proForLeague(leagueId)` is exactly `pro` at every converted site;
  - no league pass entry, line, row or notice renders, and `LeaguePassScreen` dismisses
    itself if reached.
- Device storage: one new per-account key, `ftf_lp_covered_notice_<user>_<league>`
  (R29). It carries the user id, so the D-280 account reset keeps it by design.
  The entitlement cache blob (`ftf.entitlements.v1`) gains `leaguePasses` and `sources`;
  it is already dropped by the account reset.
- Rollback lever: `monetize.league_pass` off (no client release needed).

## 3. Evidence scope

- [x] **Structural / executed guard:** `mobile/tests/check-league-pass.js` (25 checks
  after the free-month revision, `npm run test:league-pass`). It executes `utils/leaguePass`, `api/billing`,
  `api/purchases` (fake RevenueCat), `state/useEntitlements` + `state/accountReset`,
  `state/useLeaguePass`, `sendPreCheck` and `components/LeaguePassRows` (fake React),
  and pins the gate sites, the `pro`-read allowlist, the modal registration, testIDs and
  the no-new-events rule. Sabotage-proven (9 runs, recorded in the build report; 5 more
  for the free-month revision: free month on an unknown answer, free month without
  StoreKit, a non-strict eligibility read on the screen, "free" in a paid key, the
  trial disclosure without its charge line).
- [x] **Existing guards updated, not weakened:** `check-paywall-gate.js` (8j now
  expects the Send tap to pass its league; the PaywallScreen harness stubs the one new
  child-component import), `check-win-now-recovery.js` (stubs `useProForLeague`),
  `check-monetization-cut-features.js` (scans the three new UI files too).
- [x] **Combined with `main` (launch cuts) and `feat/paid-launch`, 2026-11-25:** paid
  launch's Shop "sweep again once entitled" effect (`ShopOffersBody.tsx`) now reads
  `useProForLeague(leagueId)` (the league the sweep runs in) instead of account `pro`,
  so a covered member's notice gives way to ideas after a refresh, and only in the
  covered league. The single-pin ideas panel's effect already read TradesScreen's
  `payEntitled`. `check-league-pass` 7a now pins both unconditionally (it was
  conditional on paid launch being present); `check-paid-launch` 1c accepts
  `sendPreCheck`'s league parameter and 7a expects the league-aware Shop read.
  `check-launch-cuts` and `check-monetization-cut-features` pass with no league pass
  change (no `mon.lp.*` string names a cut feature).
- [x] **Code-walk proof:** [evidence-client.md](evidence-client.md) §1.
- [x] **Manual TestFlight checklist — REQUIRED, NOT YET RUN:**
  [evidence-client.md](evidence-client.md) §2. It needs the App Store Connect product
  `ftf_league_annual` with its one-month free-trial introductory offer, the RevenueCat
  `league` offering, and sandbox Apple IDs (one never subscribed, one that used the
  individual plan's free month). It is the only runtime evidence for the free-month
  eligibility, the trial charge timing, members' coverage during the trial and the
  binding.
- `testID`s added: `league-pass-screen`, `league-pass.close`, `league-pass.league.<id>`,
  `league-pass.buy`, `league-pass.change-league`, `league-pass.quote(.teams|.price)`, `league-pass.disclosure`,
  `league-pass.terms`, `league-pass.privacy`, `league-pass.line`, `league-pass.pick`,
  `league-pass.no-leagues`, `league-pass.confirming`, `league-pass.done`,
  `league-pass.pending`, `league-pass.done-close`, `league-pass.unbound`,
  `league-pass.manage(.renewal|.count)`, `league-pass.move`, `league-pass.move-list`,
  `league-pass.move-after`, `league-pass.show-name`, `league-pass.manage-subscription`,
  `paywall-league-pass-entry`, `paywall-league-pass-other-league`,
  `settings-league-pass(-member-<id>|-buyer|-manage|-unbound)`,
  `league-pass.covered-notice(.dismiss)`. None renamed; `league-pass.full-price` and
  `league-pass.full-price-cancel` were removed with the full-price notice (free-month
  revision). `testid-lint.sh` OK.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route changes; the client follows § League pass as written |
| `docs/cross-client-invariants.md` | updated (phase 2); free-month revision: server branch | § Monetization SKU ids …: **League pass**. The one-product / no-offer-ids / no-`tier_mismatch` rewrite is the server branch's change, not this client build's |
| `docs/api-reference.md` § League pass | server branch | The intent / config / view shapes lose `tier` and `promo_offer_id` and the bind row loses `tier_mismatch` there; `check-league-pass` 1e skips `tier_mismatch` until that lands |
| `living-memory/LLD.md` | n/a here | The main session writes living-memory (operator instruction for this build) |
| `docs/architecture.md` | n/a | No backend wiring change |
| `living-memory/HLD.md` | n/a here | As above |
| `docs/glossary.md` | n/a | Phase 1 added league pass, covered member, buyer, re-point |
| ADR / `DECISIONS.md` | n/a here | D-281 is the decision record; the main session writes DECISIONS.md |
| `lld.md` §8 | updated | Where the build differs from the table (moved file locations, the Settings split, ShopOffersBody) |
| `mobile/src/{api,state,screens,components,utils,navigation}/CLAUDE.md`, `screens/README.md`, `tests/README.md` | updated | The new screen, selector, wrappers, rows, suite |

## 5. Ship gate declaration

- **CI green:** `tsc --noEmit` clean, `scripts/testid-lint.sh` OK, `pytest backend/tests`
  unaffected (no backend change), all 207 `mobile/tests/check-*.js` suites green on the
  pushed sha (211 of 211 locally after the 2026-11-25 merge of `main` and
  `feat/paid-launch`).
- **Before the flag turns on for anyone** (not before merge; the build is dark):
  1. Legal's league pass copy replaces the placeholder `mon.lp.*` block (marked PENDING
     LEGAL REVIEW in `mobile/src/copy/monetization.ts`).
  2. `ftf_league_annual` ($99.99 a year) with its one-month free-trial introductory
     offer and the `league` offering exist in App Store Connect and RevenueCat.
  3. The TestFlight checklist in [evidence-client.md](evidence-client.md) §2 is run on
     a store build and logged in `living-memory/TEST_LEDGER.md`.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` (by the main session).
- Express lane declared by the operator? No.
