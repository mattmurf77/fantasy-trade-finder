# Confirmed steering after the reference specification

The original specification.md is retained unchanged as a reference, not an implementation claim.

User: “Correct. it should feed the standing projections feature. And should be updated via batch on a scheduled basis rather than every time the users enter the app. Part of the implementation plan should consider content to present for newly added leagues with no run, as well as other states based on the timing and frequency of the batfch”.

User: “6 hour is way too frequent. Weekly is sufficient.”

These instructions supersede the initial manual/on-demand baseline and any six-hour implementation proposal. The app reads stored weekly results. Proposed configurable schedule: Tuesday 09:30 America/New_York, using timezone-aware weekly slots across DST. The existing 15-minute authenticated cron checks due work; it does not forecast every 15 minutes. New leagues wait for the next weekly slot. App visits, roster changes and repeated synchronization do not advance that slot. Explicit scenarios remain separately queued and cannot overwrite the baseline.

The parent verified existing Render cron configuration on November 7: realtime */15 * * * *, hourly 0 * * * *, neither suspended. This proves configured dispatch opportunities, not successful execution of this new handler. No notification route was manually invoked.

Existing mobile Projected standings and League Summary switch to the stored result when the new feature is enabled. Their legacy outlook queries are disabled in that mode. Home's Standings entry uses that same screen. Win Now/trade valuations remain independent. Web League Summary uses the same stored API. No provider call, dispatch, cleanup mutation or simulation occurs in projection GET handlers.

States distinguish no run, queued, running, current weekly snapshot, stale after the next weekly due time, refresh failed, incomplete data and unsupported policy. Current official standings remain available separately. A forecast is explicitly as-of its weekly inputs; no promise of live scoring updates is made. Last successful baseline is retained through refresh failure, including the normal seven-day history boundary. Next due time is eligibility for an attempt, not a completion estimate. Missing forecast fields never become zero.

Configuration is versioned in config/league_projections.json. Weekly cadence is confirmed; Tuesday time, variance proxy/correlation, reserve policy, exact tie policy, sample threshold and retention are still proposed operational/model choices. The initial candidate kept policy_approved false pending review; the later live-release instruction below approves that policy file. The two new feature/provider flags remain false in repository defaults and do not govern existing provider integrations.

## Latest source-use instruction (2026-11-07)

The user explicitly instructed: “projection data can be fetched via Sleeper and used for all league formats”, “so that shouldn't be a blocker”, and “Just use what we have in those cases”. This supersedes the initial whole-league refusal on incomplete forecast fields and the request for an additional source purchase/permission decision. Weekly cadence, account boundaries and default-off technical rollout remain unchanged. Existing Sleeper usage is unaffected.

Engine v4 selects `sleeper_best_available_v1`: score known contributions using the league's coefficients, retain missing contributions as unknown, and show partial/unpriced coverage. An available subtotal is not a lower bound when a penalty is missing. Entire missing player forecasts are not confirmed zeros. If a lineup has no usable forecast, existing completed team history can supply an explicitly labeled team-level fallback; it is never attributed to a missing player. No new rare-event or player-rate imputation model is introduced. Valid empty source responses are distinct from transport failures. A source outage retains the last successful run.

Known completed-game actuals lock recorded starters and exclude played bench players from the actual lineup, while hindsight Max PF may use them. A fully completed official lineup total is observed, without historical mixing or score noise; an empty lineup is observed only when the entire validated NFL week is complete. Historical official records/aggregates and the remaining-week boundary prevent double counting. Live games without a safe remaining-points source remain unavailable.

A complete feasible assignment of known actual points can establish a Max PF floor. If that observed fact contradicts the original 60/40 expectation, the model explicitly conditions its target. It records the original blend, observed bound, target adjustment and simulated mean. Future-only rows retain v3 results exactly. This is mathematical consistency with observed facts, not predictive calibration.

## Live-release instruction — 2026-11-07

The operator explicitly requested PR611 live, including best-available Sleeper estimates and preservation of Calibration through source-currentness rebuilds. The model policy file is approved; runtime flags still provide controlled activation. A secret-authenticated bounded initial batch may prepare never-attempted connected leagues immediately, then preserves weekly Tuesday scheduling. App views and ordinary league sync remain read-only/registration-only. See rollout.md for the concrete operational procedure and remaining runtime evidence.
