# Analytics & Experimentation Platform — doc set

**Date:** 2026-07-17 · **Owner:** operator (Matt) · **Status:** design complete, dual-agent validated; build not started (but see the v0 baseline note below).

The platform that turns FTF's server-side event log into full-funnel product analytics (waterfall conversion, think-time, bottlenecks, churn/error diagnosis, release health) plus a self-service A/B + multivariate experimentation engine (layered concurrent tests, attribute targeting, honest fixed-horizon stats, PFO guardrails auto-attached).

## Read in this order

| Doc | What it is |
|---|---|
| **Strategy layer** (`docs/business/`) | |
| [tracking-plan-v2](../../business/analytics/2026-07-17-tracking-plan-v2.md) | Event taxonomy + envelope + collection-path decision (an-data-architect) |
| [analytics-program-plan](../../business/analytics/2026-07-17-analytics-program-plan.md) | Report catalog R1–R10, metric definitions, north star (WAT), dashboards, Monday ritual (an-funnel) |
| [experimentation-framework](../../business/analytics/2026-07-17-experimentation-framework.md) | Layers, assignment, targeting, stats policy, self-service workflow (design) |
| [pfo-measurement-spec](../../business/product/2026-07-17-pfo-measurement-spec.md) | TTFV/guardrail definitions, R8 PFO report, release regression watch (pm-pfo) |
| **Execution layer** (this directory) | |
| [prd.md](prd.md) | Requirements: FR-1..48, NFRs, phases P0–P4, risks, OQ-1..10 · Final, dual-agent validated ([log](prd-reconciliation.md)) |
| [hld.md](hld.md) | Architecture: module map, failure envelopes, data flow, 12 key decisions · Final ([log](hld-reconciliation.md)) |
| [lld.md](lld.md) | Implementation detail: DDL, contracts, algorithms, races, tests, phase→file map · Final ([log](lld-reconciliation.md)) |

## Build phases (from the PRD; LLD §6 has the phase→file map)

- **P0 — Server truth ✅ built (2026-07-17):** WAL on + boot assertion, three engines, envelope/index deltas, `wrapped_events` atomic cutover, missing server-fired events (incl. `calc_trade_evaluated`), health counters, ADR-007. Green (backend suite).
- **P1 — Ingestion + mobile SDK ✅ built (2026-07-18):** `/api/events` rewritten to the final always-200 contract (`backend/analytics_ingest.py`, accounting invariant, `ingest_engine` BEGIN IMMEDIATE / 150 ms budget); `insert_client_events` retired; extended `GET /api/feature-flags` (additive `{experiments, configs}`, empty until P3); mobile SDK rewrite (per-session `seq`, `{v:1}` queue, funnel-critical drop-last, response-driven purge + backoff, kill-switch default-dark); `getDeviceId` canonicalized in `client.ts`; `X-Device-Id` on the flag fetch; §4.6b foreground refetch (`maybeRevalidateFlags`); `quickrank_completed` client flag. Tests: `test_events_api.py` (12, incl. accounting invariant), T-23b busy-timeout; mobile typecheck clean. `analytics.ingest` ships **false** (dark) — flip after the TestFlight build carries the P1 SDK. **Privacy-label update still required before that submission.**
- **P2 — Dashboard (MVP cut line) ✅ built (2026-07-18):** `backend/analytics_queries.py` (shared fragments + reports R1–R8/R10 on `ro_engine`, dual-dialect, honest degradation), `GET /api/admin/analytics/<report>` (CRON-gated, json/csv), and `web/admin/analytics.html` (Chalkline thin renderer, secret in sessionStorage, textContent-only, 11 tabs). Built via a design→adversarial-verify workflow that caught 7/10 reports with SQL bugs pre-build (incl. an attribution double-count and a NULL-session wipeout). Tests: `test_analytics_p2.py` (10, seeded-DB exact-number assertions incl. no-double-count, NULL-safe exclusion, dark≠zero); verified live in-browser against the fullstack server. **Live today:** WAT, engagement/streaks, adoption of server-fired ranking/trade/calc/feedback events, the signup-onward funnel. **Dark until the client SDK ships:** stages 0/1/3, think-time, client errors, per-platform/experiment slices — all render "—" with a caveat, never a fake number.
- **P3 — Experiment engine:** evaluator, layers, stats, admin API + Experiments tab, `trade.aggression_ab` migrated as Experiment #1.
- **P4 — Long tail:** web/extension SDKs, `/an-experiment` skill, Sentry arming (if approved), snapshot cron.

## ⚠️ Shipped v0 baseline

A parallel work stream already landed a v0 of tracking-plan §S1/S2 in the tree (route, envelope columns, `identity_links`, v0 `events.ts`) — **LLD §1.1 is the reconciliation contract; every build is a rewrite-in-place, never a duplicate.** Re-diff §1.1 against the tree at P0/P1 kickoff.

## Operator decisions — recorded 2026-07-17

- **OQ-2 ✅ adopted:** funnel v2 + WAT north star are canonical (`docs/business/context.md` amended).
- **OQ-1 ✅ arm Sentry now:** DSN already present in `mobile/app.json`; `sentrySetUser` stripped to pseudonymous user id only (no username); privacy policy updated. Takes effect in the next EAS build.
- **OQ-3 ✅ privacy-policy route:** `web/privacy.html` updated (first-party usage analytics, anonymize-on-delete semantics, device-identifier persistence, Sentry id-only tag). Effective date bumped to 2026-07-17.
- **Amendments ✅ approved:** folded into experimentation-framework §D2/D4/D5 and tracking-plan §S2.
- **P0 ✅ green-lit** (build in progress; see status below).
- Still open: OQ-4 (churn threshold — rec 14 d), OQ-5 (taxonomy CI, revisit at P2 exit), OQ-7 (snapshot cron, on-request for now), OQ-9 (PFO threshold recalibration after 4 weeks of P2 data).

## App Store privacy nutrition label — update at the next submission (P1 gate, PRD NFR-4)

Declare, all "linked to user" once signed in (pre-auth events link only to the random device ID):
- **Identifiers → User ID** (Sleeper/account id; `dev_` device ID) — app functionality + analytics
- **Usage Data → Product Interaction** (screens, taps, timings, experiment variant) — analytics
- **Diagnostics → Crash Data + Performance Data** (Sentry, id-only tag) — app functionality
- No tracking (no cross-app/ATT), no advertising data, no data sold — "Data Used to Track You: none".
