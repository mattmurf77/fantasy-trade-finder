# Feature Scope — Time to trade suggestion (first card ≤ 250 ms, up-to-date offers)

<!--
Copied from docs/templates/feature-scope.md on 2026-10-15. Per D-056 the template's
§Maestro delta and §Simulator-gate tier are dead and are not carried here.
This scope is filled at PLAN stage: the build has not been designed (eng owns the HOW).
Rows that can only be finalized once eng picks an approach are marked
"BUILD OBLIGATION" — the build must replace them with an answer or an explicit waiver
before code starts. Silence is not a waiver.
-->

**Date:** 2026-10-15
**Entry point:** direct ask (operator, 2026-10-15): *"Time to trade suggestions. This should be within 250 ms of hitting find a trade and must be up to date trade offers."*
**Builder:** not yet assigned. Plan by trades-pm (PRD worker); build by head-eng → trades-eng / models-eng
**Operator sign-off on waivers:** needed. The waivers proposed below (web/extension out of scope;
pinned and targeted searches measured but not gated; cold-launch taps not gated; table B controls
measured but not gated) are listed as Decisions D1, D2 and D10 in
[prd.md](prd.md#decisions-needed-operator).

PRD: [prd.md](prd.md) · Baseline query spec: [baseline-request.md](baseline-request.md)

---

## 1. Analytics scope

- [x] **(a) New events specced.** These are **requests** pending `analytics-lead`'s grant. Each is
  registered in `backend/analytics_taxonomy.py` and classified in
  `analytics_queries.NON_INTENT_EVENTS` **in the same commit as its emitter**. Existing events are
  preferred; R1 widens existing events first.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | **R1** `find_trades_tapped` (widened) / `calc_find_a_trade_tapped` (widened). Alternative: new NON_INTENT `trade_search_started` | + `search_id` (client UUID per tap); `source` gains one value per §4.1 entry point. Monotonic tap time stays client-local and feeds R2's `ms_from_tap` | touch-up on any table A control (and table B controls if Decision D10 makes them search-starting) (prd §4.1) | iOS |
  | **R2** `trade_first_card_shown` (new, proposed NON_INTENT) | `search_id`, `ms_from_tap`, `entry_point`, `search_type` (organic / pinned / fair_sweep), `launch_state` (cold_launch / first_tap / repeat_tap), `serve_source` (prepared / cached / joined / fresh), `freshness_state` (fresh / updating / withdrawn_some), `job_id`, `card_index` | first frame with an actionable card meeting prd §4.2 | iOS |
  | **R2b** `trade_first_card_failed` (new, NON_INTENT; or a `result` prop on R2, at analytics-lead's choice) | `search_id`, `ms_from_tap`, `reason` (empty / error / abandoned / timeout) | a tap ends without an actionable card | iOS |
  | **R3** `trades_generated` (server, widened) | + `first_publish_ms`, `serve_source`, `oldest_input_age_s`, echoed `search_id` | existing server emit points | server |
  | **R4** envelope column `network_type` | wifi / cellular / offline / unknown, stamped by the SDK | every client event | iOS SDK |

  → follow-through: tracking-plan addendum in `docs/business/analytics/`; `docs/data-dictionary.md`
  if R4 adds a column. No player ids or names in props (`tracking-plan-v2.md:183`). Device platform
  stays a server-derived column (`tracking-plan-v2.md:218`).
- [ ] (b) Existing events cover it: **no**. `deck_card_viewed` requires 500 ms of exposure.
  `find_trades_tapped` misses non-TradesScreen entry points. `trades_generated.gen_ms` is
  full-worker time (prd §4.6).
- [ ] (c) Waived: no.

## 2. Schema & flag scope

- **New or changed tables/columns: BUILD OBLIGATION.**
  - R4 may add one `user_events` column.
  - Any persistent cache or prepared-page storage must state its footprint per user-league and its
    daily write volume, using prd §10.4's formulas, before it is built.
  - Per head-product P23 (2026-10-15), cache data is the first class shed under disk pressure. It
    must be rebuildable and never the system of record, with a fresh-path fallback (prd AC-11b).
  - No rollout without an explicit byte budget, per user-league and in total. head-eng checks it
    against H1–H3 in `docs/plans/db-storage-budget/requirements.md:314-317` (draft PR #337) before
    rollout. The budget number stays open under Decision D7.
  - Rows go to `docs/data-dictionary.md`, plus a migration entry.
- **Feature flags:** none decided. Existing flags and knobs on the path are listed in prd §10.6.
  The likely candidates:
  - `trade.prepared_inventory` + `model_config prepared_trade_inventory_enabled` (dark, default 0);
  - `deck.quality_filters` (on);
  - `deck.replenishment` (on);
  - `trade.value_core` (off);
  - `trades.presentation_v2` (off).

  Any new flag must:
  - default **off**;
  - be listed in `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS` and
    `docs/config-reference.md`;
  - name a graduation criterion (prd AC-3 met on the operator checklist plus analytics);
  - name a deploy-free kill switch.
- **Env vars / `model_config` keys: BUILD OBLIGATION.** Freshness bounds (prd §5.1) should be
  `model_config` knobs so they can be tuned without a deploy (the ship-the-knob rule). Name them in
  the HLD.

## 3. Evidence scope

- [ ] **Structural guard:** `mobile/tests/check-trade-first-card.js`, plus `npm run
  test:trade-first-card`. It pins:
  - every prd §4.1 table A control emits R1 with a `search_id`;
  - R2 fires only on the enabled, visible card path and never on the `SkeletonTradeCard` branch;
  - `freshness_state` from the payload drives the "updating" UI.
- [ ] **Unit tests (backend pytest):**
  - taxonomy registration and NON_INTENT classification (R1–R3);
  - one freshness test per prd §5.1 row (serve-and-refresh, refetch-before-display and block
    branches);
  - ownership-after-roster-change on every serve path (AC-5);
  - action-time revalidation per write path (AC-6);
  - fast-path vs fresh-path differential on frozen inputs with `PYTHONHASHSEED=0` and a frozen
    clock (AC-9, G-065);
  - inventory-count parity (AC-10).
- [ ] **Code-walk proof:** a file:line trace from tap → navigation → request or local read → first
  enabled card, per entry point, naming every blocking hop and every skeleton branch (prd §9.3).
- [ ] **Manual TestFlight checklist:** the 15 steps in [prd §9.4](prd.md#94-operator-testflight-checklist-the-only-runtime-evidence-run-on-the-builds-testflight-number),
  including frame-timed screen recordings. It is the only runtime evidence and the gate until
  telemetry reaches n ≥ 40 per cell.
- [ ] **Waived:** no.
- `testID`s added or renamed: **BUILD OBLIGATION.** Every §4.1 control needs a stable testID for the
  guard. Most already have one (`calc.action.find-a-trade`, `trades.find-btn`, `home.tile.find-trade`,
  `league.action.find`, `matches.go-to-trades`, `calc.find-a-trade`). They must pass `mobile/scripts/testid-lint.sh`.

## 4. Docs scope (MANDATORY: HLD / LLD / API)

This is a plan; nothing is updated yet. Each row states what the build must do.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | BUILD OBLIGATION | Any change to `/api/trades/generate` or `/api/trades/status` (response shape, freshness fields, paging), or a new prefetch route. |
| `living-memory/LLD.md` | BUILD OBLIGATION | Freshness-bound conventions and the serve-time invariant set (prd §5.3) are a new cross-path convention. |
| `docs/architecture.md` | BUILD OBLIGATION | The serve path for the first card, wherever eng puts it (prepared, device or transport). |
| `living-memory/HLD.md` | BUILD OBLIGATION, if the approach adds a client-side cache or a new background worker | Otherwise n/a, with a reason. |
| `docs/cross-client-invariants.md` | Likely n/a | Unless the freshness enum or labels are rendered by more than one client. Web is out of scope in v1. |
| `docs/glossary.md` | BUILD OBLIGATION | New terms: "time to first card", "freshness bound", "serve-and-refresh". |
| ADR or `DECISIONS.md` | BUILD OBLIGATION | The approach choice and the stale-deck rule (Decision D4) are non-obvious choices. |
| `docs/business/analytics/` tracking-plan addendum | BUILD OBLIGATION | R1–R4 per analytics-lead's grant. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) +
  `maestro-testid-lint`, all passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the guards and tests that ran,
  the code-walk, and the analytics read once n ≥ 40.
- **TestFlight verification:** prd §9.4, run by the operator. Outcomes, with frame timings, are
  logged in TEST_LEDGER.
- **Pre-push:** `FTF_SKIP_SIM_GATE=1` (D-056 standing posture), noting the evidence above.
- **Express lane declared by the operator?** No. This change touches API contracts, analytics events
  and possibly schema and flags, so it sits above the express-lane bright line.
