# Feature scope — In-season projections and Win Now

**Date:** 2026-09-04. **Entry point:** Operator-authorized implementation of [PROPOSAL.md](PROPOSAL.md), with Astra subagents and parent review.
**Status:** Implementation and parent mechanical verification complete; hosted CI/runtime/calibration rollout gates remain. Not merged, deployed, enabled or submitted to TestFlight.
**Contract:** [BUILD.md](BUILD.md) defines this restricted beta. All standard evidence/doc gates apply; no waivers. D-056 replaces obsolete simulator/Maestro requirements.

## 1. Analytics scope

`win_now_objective_selected` is emitted server-side when an authenticated search is accepted, once per submitted job, with objective, sacrifice/fairness limits, job ID, client platform and league platform. No duplicate client selection event. Raw protected lists and private ranking boards are not analytics properties. The taxonomy registration is part of this build; the event is classified as intent, and platform is derived from X-Device as ios/android/web.

Like/pass writes go only to `win_now_decisions`, retaining the objective and frozen scenario through its scenario reference. No legacy `/api/trades/swipe`, queue, match or proposal path is added by this beta; none of these actions trains dynasty Elo. Real proposal/acceptance attribution remains future work, not an implied beta capability.

## 2. Schema and flag scope

Five additive SQLAlchemy Core tables: `season_forecast_snapshots`, `season_projection_snapshots`, `win_now_jobs`, `win_now_scenarios`, `win_now_decisions`. Whole immutable forecast batches preserve player/week provenance; user-scoped jobs and scenarios retain their input revisions and expiry. See the [data dictionary](../../data-dictionary.md#win-now-evidence-tables).

| Flag | Default | Boundary |
|---|---|---|
| `outlook.season_projections` | false | New season projection reads and entries |
| `trades.win_now` | false | Win Now search, calculator evaluation and decisions; also requires projection serving |
| `outlook.championship_probabilities` | false | New-model title display and optimization after independent graduation |

Source configuration: `FTF_SEASON_FORECAST_FILE` optionally imports a normalized provider snapshot; `FTF_SEASON_SIM_COUNT` sets the bounded simulation count. Shared market pricing is frozen per request; beta optimizer policy is versioned in `win_now_optimizer.py`. No provider subscription, secret, production flag flip or legacy dynasty experiment change is part of this build.

## 3. Test scope

- Backend: provider/horizon/scoring validation, legal lineup assignment, week-three starter counterfactual, paired probability accounting, trade legality, fixed-baseline budget, protected assets, fairness and partner gates, persistence/auth/freshness/decision isolation. Parent reviewed the integrated route/service code and all agent work; final backend gate results are recorded in EVIDENCE.
- Clients: TypeScript, executable formatter and web DOM race tests, structural entry/gating tests, JavaScript syntax, web structure and test-ID lint. Latest feature suite: **24 checks passed**. Detailed completed checks and pending runtime evidence are in [EVIDENCE.md](EVIDENCE.md).
- Calibration: frozen historical or prospective source capture and held-out league/season evaluation remain outstanding. Passing unit tests does not establish forecast skill or title graduation.
- Runtime: parent browser inspection with synthetic data passed at wide/narrow widths; the physical TestFlight and live integrated source/auth checklist remains pending. No Maestro, native simulator or screen-library captures.

## 4. Docs scope

| Reference | Build update |
|---|---|
| `docs/api-reference.md` | Five new routes, units, input limits, availability and authorization |
| `docs/data-dictionary.md` | Five evidence/job/decision tables |
| `docs/config-reference.md` | Three default-off flags, two environment settings, policy/expiry boundaries |
| `docs/integrations/sleeper.md` | Weekly projection source, RotoWire revisions, source freshness/cutoff and safe logging |
| `docs/architecture.md` + `living-memory/HLD.md` | Forecast → legal lineup → paired season simulation → constrained search → clients |
| `living-memory/LLD.md` | Snapshot/decision identities, request cancellation and separate client state |
| `docs/cross-client-invariants.md` | New objective, percentage-point and budget semantics; legacy title restriction preserved |
| `docs/glossary.md` | Forecast, sacrifice, partner evidence and percentage points |
| `docs/design/components.md` | Gated season/Win Now surface and editing/empty/error states |
| ADR / `DECISIONS.md` | ADR-017 / D-180: external forecasts with independent season simulation and no dynasty feedback |
| `docs/plans/README.md` + living memory | Implementation under review, pending full verification and rollout |

## 5. Ship gate declaration

Implementation is complete and unshipped. Parent reviewed all agent changes, resolved the public contract, and recorded backend, TypeScript, web and test-ID evidence. Hosted Python 3.12 CI remains a merge gate. A controlled runtime pass and projection-source/quality review remain separate from mechanical correctness. The three flags stay false; title calibration and explicit graduation are mandatory before exposing the new championship output. The legacy `odds.title_pct` prohibition is unchanged.
