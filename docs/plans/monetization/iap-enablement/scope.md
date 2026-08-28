# Feature Scope — IAP enablement, code half (runbook steps 6–7)

**Date:** 2026-08-28
**Entry point:** direct ask — operator-directed cross-session handoff (2026-08-28), building the
code half of `docs/plans/monetization/iap-enablement-runbook-2026-08-27.md` (runbook authored on
the `app-launch-scorecard` worktree; cited by name+date until it merges). Plan of record:
[../00-platform-foundation.md](../00-platform-foundation.md) +
[../pro-subscription/lld.md](../pro-subscription/lld.md) — per the handoff, the foundation doc
wins over the runbook on conflict.
**Builder:** Claude session `monetization-features-feedback-a6fe77`, Opus 5 build subagents
**Operator sign-off on waivers:** not needed (no waivers)

**In scope (handoff = runbook B1–B5):**
- Backend: RevenueCat webhook delta — the route + ledger/projector already shipped
  (`backend/entitlements.py`, `server.py /api/billing/revenuecat/webhook`); what remains is
  `aliases[]` / `$RCAnonymousID:*` → `acct_*` reconciliation, `TRANSFER` projection,
  `BILLING_ISSUE` grace handling, sabotage tests; plus `GET /api/paywall/config` (LLD §3) so the
  paywall renders from server config.
- Mobile: `react-native-purchases` 10.8.1, `Purchases.configure` + `logIn(<working key>)`
  identity bridge, CustomerInfo listener as UI cache only (server stays authoritative via
  `check_pro()` / `GET /api/me/entitlements`), Chalkline paywall screen satisfying guideline
  3.1.2 (plan name, price+period, trial terms, auto-renew language, working Restore Purchases,
  tappable Privacy Policy + Terms links). One flag-gated entry point (Settings row) so the
  operator can reach it in TestFlight sandbox after flipping `monetize.paywall`.

**Out of scope (later builds, per handoff):** Pro gate applications (`@_require_pro` on
portfolio/knobs/league-cap), referrals/share cards, engine-knob UI, web `pro.html` + Stripe
checkout-session route, extension upsell, Apple-side ASC configuration (operator's lane).

**Packaging constraints honored (timing doc §7 + §11):** no data-generating action is tolled
anywhere — this build wraps zero routes and adds no gates; Founder Lifetime is a pre-order of
the shipped app (parity `ftf_founder` IAP SKU exists in the projector mapping), never an
in-beta unlock. Everything ships DARK behind the existing `monetize.*` flags; the operator
flips flags per runbook B9.

**Surfaced conflict (not silently resolved):** the runbook (A3/A4) names SKUs
`pro_monthly_499`, `pro_annual_3499`, `season_pass_2026`, `founder_lifetime`; the foundation
doc §2.1/§4, pro-subscription LLD §3, and the shipped projector (`entitlements._product_mapping`)
use `ftf_pro_monthly`, `ftf_pro_annual`, `ftf_season_pass_2026`, `ftf_founder`. Per the handoff
rule the foundation names are canonical in code; the projector mapping is additionally made
tolerant of the runbook aliases so either ASC choice reconciles. Logged in
`living-memory/OPEN_QUESTIONS.md` for the operator, who is configuring ASC now.

---

## 1. Analytics scope

- [x] **(a) New events specced:** client paywall funnel (registered in
  `backend/analytics_taxonomy.py` **and** classified in `analytics_queries.NON_INTENT_EVENTS`
  in the same commit as the emitter, per the taxonomy rule). Server-side conversion truth
  already exists (`entitlement_granted` fired by `entitlements.grant()`).

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `paywall_viewed` | `source`, `platform` | PaywallScreen mounts | mobile |
  | `paywall_purchase_initiated` | `product_id`, `source` | user taps a plan CTA | mobile |
  | `paywall_purchase_completed` | `product_id`, `source` | RevenueCat purchase resolves (UI echo; webhook is truth) | mobile |
  | `paywall_purchase_failed` | `product_id`, `user_cancelled` | purchase throws/cancels | mobile |
  | `paywall_restore` | `restored` | Restore Purchases completes | mobile |

## 2. Schema & flag scope

- New/changed tables or columns: **none** — `aliases` ride in the stored `payload` JSON;
  TRANSFER/grace project onto existing `entitlements` rows → data-dictionary n/a
- New/changed feature flags: **none** — reuses `monetize.entitlements` / `monetize.paywall`
  (registered + documented since the foundation build), all still false
- New env vars: `EXPO_PUBLIC_REVENUECAT_IOS_KEY` (RevenueCat publishable Apple SDK key, read
  at mobile build time; absent → purchases module no-ops) → `docs/config-reference.md`.
  `REVENUECAT_WEBHOOK_SECRET` already documented; **currently absent from
  `secrets.local.env`** — operator must fill it there + Render env when RevenueCat is
  configured (runbook step 3/5). Rollback lever: all `monetize.*` flags false = today's
  behavior (deploy-free kill switch).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-paywall.js` — pins: PaywallScreen registered as
  root-stack modal; screen renders price+period, trial terms, auto-renew language; a
  `restorePurchases` call is wired; privacy + terms URLs present and tappable; no FeedbackFAB
  mounted in the modal (#188 exception); purchases wrapper no-ops without the SDK key; flag
  gate present. Matching `npm run test:paywall`.
- [x] **Unit tests:** `backend/tests/test_entitlements.py` extended + sabotage coverage:
  wrong/missing bearer → 401, prod-unset secret → 503, malformed event → 400, replay
  idempotency, `$RCAnonymousID` → `acct_*` alias reconciliation (incl. re-key of rows written
  under the anon id), TRANSFER moves entitlement, BILLING_ISSUE grace extension, tolerant SKU
  aliases; new `backend/tests/test_paywall_config.py` (flag matrix, SKU ids vs
  cross-client-invariants, session auth).
- [x] **Code-walk proof:** file:line-cited trace in
  [code-walk-proof.md](code-walk-proof.md) covering the mobile purchase path (configure →
  logIn → purchase → CustomerInfo cache → server refresh) that D-056 evidence rules require in
  place of a sim capture.
- [x] **Manual TestFlight checklist:** [sandbox-test-checklist.md](sandbox-test-checklist.md) —
  operator-run once the Paid Apps agreement is active (purchases cannot be end-to-end tested
  before then; noted in the handoff).
- `testID`s added: `paywall-screen`, `paywall-plan-<product_id>`, `paywall-purchase-cta`,
  `paywall-restore`, `paywall-privacy-link`, `paywall-terms-link`, `paywall-close`,
  `settings-pro-row` (final list in the build; must pass `mobile/scripts/testid-lint.sh`)

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `GET /api/paywall/config` added; webhook row notes alias resolution |
| `living-memory/LLD.md` | updated | webhook alias-reconciliation + paywall-config conventions |
| `docs/architecture.md` | n/a | no new module, no wiring change (entitlements module already documented) |
| `living-memory/HLD.md` | n/a | no architecture shift — implements the already-recorded foundation design |
| `docs/cross-client-invariants.md` | updated | SKU ids, entitlement enum, paywall config enums (`kind`, `badge`, feature keys) |
| `docs/glossary.md` | updated | paywall / restore-purchases terms if absent |
| ADR or `DECISIONS.md` entry | updated | ADR: RevenueCat + server-truth entitlements (LLD §8 says write it when first code lands) — added if not already present |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs `check-*.js`) + `maestro-testid-lint`
  on the pushed sha before merge; `FTF_SKIP_SIM_GATE=1` standing posture on push (D-056)
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry on completion
- **TestFlight verification:** sandbox checklist above — operator-run, blocked on Paid Apps
  agreement activation; outcome to be logged in TEST_LEDGER when run
- Express lane declared by the operator? **No** — full gates (schema/API/flag-surface bright
  line acknowledged in the handoff)
