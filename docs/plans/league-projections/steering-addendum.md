# Confirmed steering after the reference specification

The original specification.md is retained unchanged as a reference, not an implementation claim.

User: “Correct. it should feed the standing projections feature. And should be updated via batch on a scheduled basis rather than every time the users enter the app. Part of the implementation plan should consider content to present for newly added leagues with no run, as well as other states based on the timing and frequency of the batfch”.

User: “6 hour is way too frequent. Weekly is sufficient.”

These instructions supersede the initial manual/on-demand baseline and any six-hour implementation proposal. The app reads stored weekly results. Proposed configurable schedule: Tuesday 09:30 America/New_York, using timezone-aware weekly slots across DST. The existing 15-minute authenticated cron checks due work; it does not forecast every 15 minutes. New leagues wait for the next weekly slot. App visits, roster changes and repeated synchronization do not advance that slot. Explicit scenarios remain separately queued and cannot overwrite the baseline.

The parent verified existing Render cron configuration on November 7: realtime */15 * * * *, hourly 0 * * * *, neither suspended. This proves configured dispatch opportunities, not successful execution of this new handler. No notification route was manually invoked.

Existing mobile Projected standings and League Summary switch to the stored result when the new feature is enabled. Their legacy outlook queries are disabled in that mode. Home's Standings entry uses that same screen. Win Now/trade valuations remain independent. Web League Summary uses the same stored API. No provider call, dispatch, cleanup mutation or simulation occurs in projection GET handlers.

States distinguish no run, queued, running, current weekly snapshot, stale after the next weekly due time, refresh failed, incomplete data and unsupported policy. Current official standings remain available separately. A forecast is explicitly as-of its weekly inputs; no promise of live scoring updates is made. Last successful baseline is retained through refresh failure, including the normal seven-day history boundary. Next due time is eligibility for an attempt, not a completion estimate. Missing forecast fields never become zero.

Configuration is versioned in config/league_projections.json. Weekly cadence is confirmed; Tuesday time, variance proxy/correlation, reserve policy, exact tie policy, sample threshold and retention are still proposed operational/model choices. policy_approved is false pending review. The two new feature/provider flags are also false and do not govern existing provider integrations.
