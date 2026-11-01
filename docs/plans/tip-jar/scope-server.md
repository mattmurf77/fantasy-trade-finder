# Feature Scope — Tip jar, server half (S1)

**Date:** 2026-11-01
**Entry point:** direct ask (operator 2026-11-01, relayed by head-product). Product spec: monetization-pm's [plan.md](plan.md) §3 S1 (PR #569, branch `plan/tip-jar` @ `7fd975cb`); whole-feature scope: [scope.md](scope.md). head-eng's GO (2026-11-01) is the knob design.
**Builder:** eng-backend worker for engagement-eng (branch `feat/tip-jar-server`)
**Operator sign-off on waivers:** not needed. One waiver (§3, mobile rows), and it is a scope split: the client half is C1/C2, not a skipped check.

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [x] **(b) Existing events cover it.** TipJar already fires `paywall_viewed {source: 'tip_jar'}` and `paywall_purchase_* {product_id: 'ftf_tip_*'}` (plan §3, Analytics). This PR adds analytics-lead's granted **doc-only** lines:
  - `backend/analytics_taxonomy.py`: `tip_jar` in the `paywall_viewed.source` closed-set comment; `ftf_tip_199 | ftf_tip_499 | ftf_tip_999` in the `product_id` vocabulary comment. Both are comments, not enforced lists.
  - `docs/cross-client-invariants.md`: `tip_jar` in `paywall_viewed.source`.
  - **No** registry, `NON_INTENT_EVENTS`, prop-set or `SERIES_BREAKS` change.
- [ ] (c) Waived: no.

## 2. Schema & flag scope

- **Tables or columns:** none.
- **Feature flags:** none. Tips still ride `monetize.paywall` (off → `{"enabled": false}` and nothing else).
- **`model_config` key:** **`paywall_tips_enabled`**, default **0**, seeded insert-if-absent (`backend/database.py`, after `app_store_live`). Exactly 1 → `tips` is `_PAYWALL_TIPS` on `GET /api/paywall/config` when the resolved platform is `ios`. Anything else → `[]`. Read live per request (`server._paywall_tips_enabled`), so it is the **deploy-free kill switch**: release-lead sets 0 to hide the tips. Documented in `docs/config-reference.md` § Tip jar.

## 3. Evidence scope

- [ ] Structural guard: none in this PR. The server change has no mobile surface. `check-tipjar.js` §9 still reads `_PAYWALL_TIPS`'s ids from `server.py`, and that list is unchanged. C1 owns the §8c update.
- [x] **Unit tests:** `backend/tests/test_paywall_config.py` §(f):
  - the default (empty table → seed 0) → `[]`; the seed row is 0;
  - knob 1 + `ios` (explicit, omitted, or unknown → `ios`) → exactly the three SKUs, in order;
  - knob 1 + `web` / `extension` → `[]`;
  - knob 0, 2, -1, 0.5, 1.0001, or a missing row → `[]`;
  - garbage at the read (`"abc"`, `""`, `None`, NaN, inf) → `[]`;
  - a failed read → 200 with `[]`;
  - flip the stored row between requests → the answer follows, with no reload;
  - flag off + knob 1 → `{"enabled": false}` on every platform;
  - the `ftf_tip_` prefix test is kept.
  - The file now runs against an autouse in-memory DB, because the route reads model_config. `test_entitlements.py` (tips grant nothing) is unchanged.
- [x] **Code-walk proof:**
  - `server.py` `paywall_config`: `_require_session()` runs first, then the `monetize.paywall` early return (unchanged).
  - `platform` is resolved next, with unknown values becoming `ios`.
  - `"tips": _PAYWALL_TIPS if platform == "ios" and _paywall_tips_enabled() else []`. The platform check comes first, so `web` and `extension` never read the knob.
  - `_paywall_tips_enabled()` returns `float(get_config().get("paywall_tips_enabled", 0.0)) == 1.0` inside `try/except → False`.
  - `get_config()` reads the table on every call, with no cache.
  - The mobile app fetches `?platform=ios` only (`PaywallScreen.tsx:198-199`, `TipJarScreen.tsx:68-69`, `useTipsOffered.ts:20`).
- [x] **Manual TestFlight checklist:** plan §4 **T24** (knob 0 → no row, 1 → row back) is this PR's runtime check, run after TJ9. T21–T26 belong to the whole feature.
- [x] **WAIVED for the mobile rows** (structural guard, testIDs): backend-only; the client half is C1/C2.
- `testID`s: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `/api/paywall/config` row: `tips[]` behind `paywall_tips_enabled`, iOS only |
| `docs/config-reference.md` | **updated** | New § Tip jar, `paywall_tips_enabled` (what it does, default 0, release-lead, deploy-free, `scripts/set_knob.py`), plus a TOC entry |
| `docs/cross-client-invariants.md` | **updated** | `ftf_tip_*` row: "Not served at launch" → served behind `paywall_tips_enabled`; `paywall_viewed.source` gains `tip_jar` |
| `living-memory/LLD.md` | n/a | No convention shift: the existing live-read knob pattern on an existing route |
| `docs/architecture.md` | n/a | No module or data-flow change |
| `living-memory/HLD.md` | n/a | No architecture change |
| `docs/glossary.md` | n/a | "Tip jar" is already in use |
| `docs/plans/monetization/pro-subscription/lld.md` §3 (`:100`, `:126`) | **not updated here** | scope.md lists it for the S1 PR, but it is outside this worker's allowed files. Flagged to engagement-eng |
| ADR or `DECISIONS.md` | n/a here | #393 decision 6's reversal for tips is recorded in plan.md and #393 (scope.md) |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (the full suite) + `mobile-typecheck` + testid-lint, on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry for the pytest run and the sabotage, written by the lead with the PR.
- **TestFlight verification:** T24 after release-lead sets the knob (TJ9), run by the operator.
- **Deploy posture:** safe to deploy at any time with the knob at 0, because the response is byte-identical to today's `tips: []`.
- **Express lane:** no; full gates.
