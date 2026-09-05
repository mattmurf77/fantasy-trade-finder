# Feature scope — In-season projections and Win Now

**Date:** 2026-09-04. **Entry point:** Operator-authorized implementation of [PROPOSAL.md](PROPOSAL.md), with Astra subagents and parent review.
**Status:** PR #280 merged; backend/web live at `c28ec6d8`, all three beta flags true and final CI green. iOS 1.17.0 (147) built/uploaded; Apple processing and tester availability remain separate. Physical QA and calibrated forecast evidence remain outstanding.
**Contract:** [BUILD.md](BUILD.md) defines this restricted beta. Standard mechanical evidence/doc gates apply. The operator explicitly superseded the earlier calibration-before-championship-enablement restriction for this beta; physical runtime evidence remains outstanding. D-056 replaces obsolete simulator/Maestro requirements.

## 1. Analytics scope

`win_now_objective_selected` is emitted server-side when an authenticated search is accepted, once per submitted job, with objective, sacrifice/fairness limits, job ID, client platform and league platform. No duplicate client selection event. Raw protected lists and private ranking boards are not analytics properties. The taxonomy registration is part of this build; the event is classified as intent, and platform is derived from X-Device as ios/android/web.

Like/pass writes go only to `win_now_decisions`, retaining the objective and frozen scenario through its scenario reference. No legacy `/api/trades/swipe`, queue, match or proposal path is added by this beta; none of these actions trains dynasty Elo. Real proposal/acceptance attribution remains future work, not an implied beta capability.

## 2. Schema and flag scope

Five additive SQLAlchemy Core tables: `season_forecast_snapshots`, `season_projection_snapshots`, `win_now_jobs`, `win_now_scenarios`, `win_now_decisions`. Whole immutable forecast batches preserve player/week provenance; user-scoped jobs and scenarios retain their input revisions and expiry. See the [data dictionary](../../data-dictionary.md#win-now-evidence-tables).

| Flag | Release-candidate default | Boundary |
|---|---|---|
| `outlook.season_projections` | true | New season projection reads and entries |
| `trades.win_now` | true | Win Now search, calculator evaluation and decisions; also requires projection serving |
| `outlook.championship_probabilities` | true | Experimental new-model title display and optimization under explicit operator authorization; no calibration claim |

Source configuration: `FTF_SEASON_FORECAST_FILE` optionally imports a normalized provider snapshot; `FTF_SEASON_SIM_COUNT` sets the bounded simulation count. Shared market pricing is frozen per request; beta optimizer policy is versioned in `win_now_optimizer.py`. The 2026-09-05 release authorizes the three production flags; effective deployment is tracked separately. No provider subscription, new secret or legacy dynasty experiment change is included.

## 3. Test scope

- Backend: provider/horizon/scoring validation, legal lineup assignment, week-three starter counterfactual, paired probability accounting, trade legality, fixed-baseline budget, protected assets, fairness and partner gates, persistence/auth/freshness/decision isolation. Parent reviewed the integrated route/service code and all agent work; final backend gate results are recorded in EVIDENCE.
- Clients: TypeScript, executable formatter and web DOM race tests, structural entry/gating tests, JavaScript syntax, web structure and test-ID lint. Final client verification includes **92 structural guards**, TypeScript and testID lint; earlier feature-check counts remain historical checkpoints in EVIDENCE. Detailed completed checks and pending runtime evidence are in [EVIDENCE.md](EVIDENCE.md).
- Calibration: frozen historical or prospective source capture and held-out league/season evaluation remain outstanding. Passing unit tests does not establish forecast skill or title graduation.
- Runtime: parent browser inspection with synthetic data passed at wide/narrow widths; the physical TestFlight and live integrated source/auth checklist remains pending. No Maestro, native simulator or screen-library captures.

## 4. Docs scope

| Reference | Build update |
|---|---|
| `docs/api-reference.md` | Five new routes, units, input limits, availability and authorization |
| `docs/data-dictionary.md` | Five evidence/job/decision tables |
| `docs/config-reference.md` | Three operator-authorized beta flags, two environment settings, policy/expiry/rollback boundaries |
| `docs/integrations/sleeper.md` | Weekly projection source, RotoWire revisions, source freshness/cutoff and safe logging |
| `docs/architecture.md` + `living-memory/HLD.md` | Forecast → legal lineup → paired season simulation → constrained search → clients |
| `living-memory/LLD.md` | Snapshot/decision identities, request cancellation and separate client state |
| `docs/cross-client-invariants.md` | New objective, percentage-point and budget semantics; legacy title restriction preserved |
| `docs/glossary.md` | Forecast, sacrifice, partner evidence and percentage points |
| `docs/design/components.md` | Gated season/Win Now surface and editing/empty/error states |
| ADR / `DECISIONS.md` | ADR-018 / D-184: external forecasts with independent season simulation and no dynasty feedback |
| `docs/plans/README.md` + living memory | Live backend/web, final CI and uploaded iOS binary; pending Apple/tester confirmation and physical QA |

## 5. Ship gate declaration

Final Python 3.12 backend suite: **5,353 passed, 1 skipped in 732.08 seconds**. Parent merged focused run: **220 passed in 15.25 seconds**. Client verification: all **92** structural guards, TypeScript and testID lint passed; **190** web structure checks, **23** auth checks and actual isolated Chromium/MV3 runtime passed. All four hosted CI checks succeeded on tested head `abb1af118d3fe39f32292e99cecc64cebff1d2f3`, run `33945722395`; PR #280 squash-merged as `c28ec6d802463e048d59a97967e9bb5bb9fdc6f9`.

All three beta flags are verified true on live Render under explicit operator authorization despite uncalibrated exploratory evidence. iOS 1.17.0 (147) uploaded successfully; Apple processing/tester availability and physical QA remain unverified. The legacy `odds.title_pct` prohibition stays unchanged. [Release record](../../business/ops/2026-09-05-win-now.md) records rollout, source refusal, limitations and rollback to all three flags false / prior main `a927e3a7`.
