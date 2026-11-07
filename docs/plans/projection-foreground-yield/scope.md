# Forecast work yields to active trade generation

Date: 2026-11-07. Entry: operator-directed 200 ms Find a Trade work. No waivers or express lane.

## Problem and bounded change

An isolated synthetic check on main 7e52047e found first durable trade publication at 25.14 seconds sequentially versus 62.76 seconds while the actual 250,000-draw forecast simulator ran in another thread. A harness-only priority experiment returned the first trade at 23.09 seconds while the forecast completed all draws with the exact same result; all 6,430 trade proofs, public outputs and durable valuations matched. One local sample per mode is evidence of contention, not a hosted capacity or 200 ms claim.

Inject a process-local active-trade predicate into the existing forecast dispatcher and single worker. At each existing cancellation checkpoint, give active trade work up to ten 100 ms sleeps, releasing Python execution between checks. Resume at the same simulation iteration with the same random state. Recheck cancellation after waiting; never extend the existing worker lease or deadline. Sustained trade work still allows one original simulation chunk between bounded yields. This does not introduce global admission, change weekly cadence, run forecasts on page views, lower the 250,000-draw budget, or alter published results. Source fetches and a single simulation chunk remain non-preemptible. Other processes and Calibration are not coordinated by this narrow improvement.

The predicate uses the existing locked live-trade registry and conservatively treats any running non-prepared trade job as priority work. It releases the registry lock before any sleep. A predicate failure yields for the bounded interval and then resumes normal cancellation checks; no exception text is surfaced.

## 1. Analytics scope

Existing `find_trades_tapped`, `trade_first_card_shown`, `trade_first_card_failed` and job stage timings cover user-visible latency and failures. Existing projection run status/deadline records remain authoritative. No new data collection or events. Strict device acceptance remains open.

## 2. Schema and flag scope

No table, column, API payload, configuration, feature flag or environment changes. Forecast feature disable remains the existing emergency stop; deploying the prior code restores prior scheduling. Stored successful forecasts and weekly target times are untouched.

## 3. Evidence scope

Add executable backend tests for idle work, release during pause, bounded sustained pressure, predicate failure, cancellation/deadline during pause, real worker persistence and exact deterministic simulation parity. Verify both cron entry points inject the predicate and no sleep holds the trade registry lock. Run affected projection and scheduler tests, full CI and test-ID lint. No mobile UI or test IDs change; no simulator or Maestro. Manual TestFlight timing remains necessary to establish device acceptance; engineering checks cannot substitute for it.

## 4. Docs scope

| Document | Action |
|---|---|
| API reference | No contract change; record scheduling behavior under projection runs |
| LLD | Record bounded checkpoint yielding and unchanged deadline |
| Architecture | Record process-local predicate injection |
| HLD | No new worker, client or architecture tier |
| Cross-client invariants | No shared output or constant change |
| Glossary | No new domain term |
| Decisions | Bounded fairness rationale documented here; no prior decision overturned |

## 5. Ship gates

Independent review, exact-head full CI, evidence in TEST_LEDGER, no runtime promotion before those checks. A backend release changes Calibration's source revision; root must coordinate regeneration of affected unexposed decks while preserving exposed history. Forecast output/version and supported cohort must remain unchanged. The 200 ms requirement remains open.
