# Weekly projection release procedure

The operator explicitly requested this capability live using best-available Sleeper data. Source omissions are displayed estimate limitations, not a separate source-purchase or permission gate. This document describes the release procedure; it is not evidence that deployment or activation occurred.

## Configuration and delivery

The reviewed configuration sets `policy_approved:true` in `config/league_projections.json`. Both runtime feature flags remain false in repository defaults. Production must enable `league.projections` and `league.projections_provider_approved` together through its existing `FTF_FLAGS` overlay, preserving every unrelated value. The latter is a historical key name and now serves as the new capability's technical enable switch. Rollback either disables the capability; do not alter existing provider, trade, ranking, KTC or Calibration policy flags.

The baseline uses current Sleeper data, league-specific scoring and the versioned best-available contract. Stored results expose partial/unpriced player inputs and historical fallback rather than pretending missing events were confirmed zero. Malformed identities, unsafe live-game timing and provider transport failures still preserve the last valid forecast. Uncalibrated probability estimates are labeled as such.

Normal refresh is weekly, Tuesday at 09:30 America/New_York (14:30 UTC in standard time, 13:30 UTC in daylight time). This exact hour is a configurable implementation default; weekly frequency is the user requirement. The existing authenticated 15-minute dispatcher checks whether a weekly attempt is due; it does not recalculate every 15 minutes. A scheduled timestamp is earliest eligibility, not a completion guarantee. One serial worker processes at most eight queued/running runs globally, one per account, with four-target dispatch and existing request bounds. Account-scoped duplicate league work remains possible.

Web code ships with the backend. The native stored-result surfaces require a new TestFlight build containing PR611; build176 predates these changes. The existing projected standings, League Summary, and the new Home banner read the saved result. They must not start simulations or fetch provider projections on entry. Native device rendering remains a concrete TestFlight verification item, not a simulator claim.

## Initial preparation, without waiting for Tuesday

`POST /api/cron/league-projections` retains its existing `X-Cron-Secret` authentication and no-body weekly behavior. Explicit JSON `{"initial":true,"limit":1}` requests at most one never-attempted baseline from the currently confirmed own-action connected cohort. Optional `user_id` and `league_id` must be supplied together for a private operator-selected canary; these are scope filters, not account impersonation or borrowed provider credentials. The route returns aggregate status and queue count, never private results. The maximum limit is the configured batch_limit (currently4).

Initial selection and target claiming both require `last_attempt_id IS NULL`. Existing queued, running, successful or failed attempts cannot be refreshed by repeating this request. Account/target generation locks, lease fences, queue limits, model-version stamps and durable atomic publication are identical to weekly preparation. Enqueue atomically records the initial attempt and advances the target to the next weekly slot, so a crash or overlapping weekly tick cannot produce a second baseline. A declined admission consumes no initial attempt. The existing one interrupted-worker recovery is unchanged. New leagues normally show current facts and wait until the next weekly slot; no app view or ordinary sync invokes this operator-only initial mode.

## Bounded production canary and release order

1. Merge only after exact-head full CI and independent review. Coordinate the backend revision change with Calibration: unexposed comparisons become stale under its existing source identity. Preserve exposed comparisons and feedback, prepare replacements on the final deployed revision, and reverify currentness before considering the Calibration release complete.
2. Deploy the exact candidate with the two projection flags enabled and all unrelated configuration preserved. Read back actual deployed commit/config and verify database tables were created. Avoid invoking notification/daily ticks; use the dedicated projection route only.
3. Select one authorized connected Sleeper owner/league privately. Invoke initial mode with limit1 and both scope keys. Read aggregate run status from an authorized operational query; verify one queued/running job, eventual complete result, finite team probabilities, expected team/week counts, explicit missing-source coverage, model version and capture time. Do not paste private team/player data into public artifacts or chat.
4. Verify the saved baseline pointer and next Tuesday eligibility, then repeat the same initial request and require queued0. Check failure/retention behavior through existing synthetic regressions; do not deliberately damage production inputs. If the canary fails, inspect its bounded reason and preserve the feature's honest unavailable state; do not substitute a synthetic result.
5. Continue bounded initial batches for remaining eligible connected pairs, observing queue depth and completion rather than increasing worker concurrency or simulation budgets. Unsupported/non-Sleeper cases remain explicit. The first useful estimate does not establish prospective forecast accuracy or hosted p95 capacity.
6. Ship the updated native build to TestFlight and verify stored forecast display, Home navigation, league switching, missing-result messaging, last-valid retention, score coverage and draft ownership. Root coordinates TestFlight and production operations.

## Stored-result states

| State | User-visible behavior |
|---|---|
| Newly linked / no_run | Current official standings; no fabricated odds; next scheduled attempt when registered. |
| queued / running | Existing valid result remains visible with its capture time; otherwise preparation state. |
| current | Latest successful saved weekly estimate, coverage and model attribution. |
| stale | Last successful estimate remains dated; next eligible attempt shown, without a completion promise. |
| refresh_failed | Preserve last success and explain refresh failure; never replace with zero probabilities. |
| unsupported / incomplete / unavailable | Explain the actual unsupported rule, unsafe source state or insufficient usable input; retain last success when present. |

No source or engine accuracy claim is inferred from a completed job. Prospective calibration requires contemporaneously frozen forecasts and later outcomes.
