# Feature Scope: Tip jar at launch

**Date:** 2026-10-31
**Entry point:** direct ask (operator 2026-11-01, relayed by head-product)
**Builder:** engagement-eng (via head-eng); spec by monetization-pm ([plan.md](plan.md))
**Operator sign-off on waivers:** not needed (no waivers)

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [x] **(b) Existing events cover it, with a read rule.**
  - TipJar already fires `paywall_viewed {source: 'tip_jar', platform}` on open (`TipJarScreen.tsx:107`) and `paywall_purchase_initiated / _completed / _failed {product_id: 'ftf_tip_*', source}` on a tip (`:115-135`). They answer "how many open the jar, and how many tip".
  - **The rule:** paywall-conversion reads (K0–K3) exclude views with `source = 'tip_jar'` and purchases whose `product_id` starts `ftf_tip_`. On purchases, `source` is the route param, `settings`, so the filter must use `product_id`.
  - **Owner:** analytics-lead, server-side, before the first K read. Server truth stays the RevenueCat `NON_RENEWING_PURCHASE` row, which grants nothing (`entitlements.is_tip_product`).
  - No taxonomy change; the event names and properties are already registered (`analytics_taxonomy.py:715-716, :1785-1787`).
- [ ] (c) Waived: no.

## 2. Schema & flag scope

- **New or changed tables or columns:** none. Tips use the existing `subscription_events` ledger, stored with no grant.
- **New or changed feature flags:** none. The row rides `monetize.paywall` and the server's `tips` list (#526).
- **New `model_config` key:** **`paywall_tips_enabled`** (int, default **0**). At 1, `GET /api/paywall/config?platform=ios` returns `_PAYWALL_TIPS`; at 0 (or another platform) it returns `[]`.
  - Document it in `docs/config-reference.md`.
  - **Ship-the-knob:** this is the deploy-free kill switch. At 0 the Settings row hides on the next config read, with no binary.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-tipjar.js`.
  - Update §8c: today it pins `useTipsOffered` to `enabled: false`; it should pin C1's warm query, `['paywall-config','ios']` with `enabled` tied to `monetize.paywall`, mounted outside Settings.
  - Keep §8b (`tipsOffered` truth table) and the existing guards: no entitlement refresh after a tip, no Restore, one modal registration.
  - Add a guard that the Settings hub itself still issues no fetch.
- [x] **Unit tests:** `backend/tests/test_paywall_config.py`. The knob at 0 → `tips == []`; the knob at 1 on `ios` → the three `ftf_tip_*` ids; the knob at 1 on `web` / `extension` → `[]`; and every served id passes `is_tip_product`. `test_entitlements.py:594-627` (tips grant nothing, refunds included) is unchanged and must stay green.
- [x] **Code-walk proof:** plan.md §3 traces the row gate (why it's blind today) and the purchase path (`getTipProducts` → `getProducts(ids, NON_SUBSCRIPTION)` → `purchaseStoreProduct`, no offering). engagement-eng extends it to the warm query's mount point in the build PR.
- [x] **Manual TestFlight checklist:** plan.md §4, T21–T26 (row without opening the paywall, a sandbox tip that unlocks nothing, cancel, the knob both ways, wording, unverified sessions). The operator runs them 11-07 to 11-09 on the gated build.
- [ ] Waived: no.
- **`testID`s:** none new. Existing: `settings-tip-row`, `tipjar-screen`, `tipjar-close`, `tipjar-option-<id>`, `tipjar-thanks`, `tipjar-done`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **to update** (S1 PR) | `/api/paywall/config`: `tips` served while `paywall_tips_enabled` = 1, iOS only |
| `living-memory/LLD.md` | n/a | No convention shifts: the existing knob pattern, the existing route |
| `docs/architecture.md` | n/a | No new module or data flow |
| `living-memory/HLD.md` | n/a | No architecture change |
| `docs/cross-client-invariants.md` | **check** (S1 PR) | The `ftf_tip_*` rows exist. Update their "not served at launch" note |
| `docs/config-reference.md` | **to update** (S1 PR) | The new key `paywall_tips_enabled` |
| `docs/glossary.md` | n/a | "Tip jar" is already used in code and docs |
| `docs/plans/monetization/pro-subscription/lld.md` §3 | **to update** (S1 PR) | `"tips": []` becomes knob-driven |
| ADR or `DECISIONS.md` entry | **update #393** | Decision 6, "tips stay dark", is overturned for tips by the operator (2026-11-01). Recorded in #393 and plan.md |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with `check-tipjar.js`) + testid-lint, on the S1 and C1/C2 shas.
- **Evidence recorded:** a TEST_LEDGER entry for the pytest and `check-tipjar.js` results, then the operator's T21–T26 outcome.
- **TestFlight verification:** T21–T26, run by the operator, logged by release-lead's scribe.
- **Express lane:** no, full gates.
