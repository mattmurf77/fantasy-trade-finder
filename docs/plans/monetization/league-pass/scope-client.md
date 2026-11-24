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

---

## 1. Analytics scope

- [x] **(a) No new client events.** Purchases reuse the registered
  `paywall_purchase_initiated` {`product_id`, `source`}, `paywall_purchase_completed`
  {`product_id`, `source`} and `paywall_purchase_failed` {`product_id`,
  `user_cancelled`} with the league product ids (`ftf_league_annual`,
  `ftf_league_annual_t1`, `ftf_league_annual_t2`). `source` is the value that opened
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

- [x] **Structural / executed guard:** `mobile/tests/check-league-pass.js` (26 checks,
  `npm run test:league-pass`). It executes `utils/leaguePass`, `api/billing`,
  `api/purchases` (fake RevenueCat), `state/useEntitlements` + `state/accountReset`,
  `state/useLeaguePass`, `sendPreCheck` and `components/LeaguePassRows` (fake React),
  and pins the gate sites, the `pro`-read allowlist, the modal registration, testIDs and
  the no-new-events rule. Sabotage-proven (9 runs, recorded in the build report).
- [x] **Existing guards updated, not weakened:** `check-paywall-gate.js` (8j now
  expects the Send tap to pass its league; the PaywallScreen harness stubs the one new
  child-component import), `check-win-now-recovery.js` (stubs `useProForLeague`),
  `check-monetization-cut-features.js` (scans the three new UI files too).
- [x] **Code-walk proof:** [evidence-client.md](evidence-client.md) §1.
- [x] **Manual TestFlight checklist — REQUIRED, NOT YET RUN:**
  [evidence-client.md](evidence-client.md) §2. It needs the three App Store Connect
  products with their introductory and promotional offers, the RevenueCat `league`
  offering and the in-app purchase key (lld §7), and sandbox Apple IDs. It is the only
  runtime evidence for the purchase paths, the promotional offer and the binding.
- `testID`s added: `league-pass-screen`, `league-pass.close`, `league-pass.league.<id>`,
  `league-pass.buy`, `league-pass.full-price`, `league-pass.full-price-cancel`,
  `league-pass.change-league`, `league-pass.quote(.teams|.price)`, `league-pass.disclosure`,
  `league-pass.terms`, `league-pass.privacy`, `league-pass.line`, `league-pass.pick`,
  `league-pass.no-leagues`, `league-pass.confirming`, `league-pass.done`,
  `league-pass.pending`, `league-pass.done-close`, `league-pass.unbound`,
  `league-pass.manage(.renewal|.count)`, `league-pass.move`, `league-pass.move-list`,
  `league-pass.move-after`, `league-pass.show-name`, `league-pass.manage-subscription`,
  `paywall-league-pass-entry`, `paywall-league-pass-other-league`,
  `settings-league-pass(-member-<id>|-buyer|-manage|-unbound)`,
  `league-pass.covered-notice(.dismiss)`. None renamed. `testid-lint.sh` OK.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route changes; the client follows § League pass as written |
| `docs/cross-client-invariants.md` | updated | § Monetization SKU ids …: **League pass** (products, offer ids, the `league` offering, the `league_pass` config block, `league_passes`, refusal reasons) |
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
  pushed sha.
- **Before the flag turns on for anyone** (not before merge; the build is dark):
  1. Legal's league pass copy replaces the placeholder `mon.lp.*` block (marked PENDING
     LEGAL REVIEW in `mobile/src/copy/monetization.ts`).
  2. The three products, the two promotional offers and the `league` offering exist,
     and the in-app purchase key is uploaded to RevenueCat (lld §7).
  3. The TestFlight checklist in [evidence-client.md](evidence-client.md) §2 is run on
     a store build and logged in `living-memory/TEST_LEDGER.md`.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` (by the main session).
- Express lane declared by the operator? No.
