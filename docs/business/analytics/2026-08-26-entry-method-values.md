# Addendum — `signin_*` method values `espn` / `mfl` (2026-08-26)

**Scope:** value-only addition. No new event, no new prop, no registry change.

The tracking plan (`2026-07-17-tracking-plan-v2.md` §"Pre-auth funnel")
enumerates `signin_attempted.method` as `apple/sleeper/last_user/demo`. The
sessionless platform entry (landing platform options v2, D-164;
`docs/plans/landing-platform-options/scope.md` §V2) adds two values on the
already-whitelisted `method` prop:

| Value | Fires when | Emitter |
|---|---|---|
| `espn` | The user claims an ESPN team at entry (`POST /api/entry/platform` mint) | `mobile/src/api/platformEntry.ts` |
| `mfl` | The user claims an MFL franchise at entry (same route) | same |
| `espn` / `mfl` | **Web (2026-09-03):** the same claim on the web landing (`_entryClaim`) | `web/js/app.js` |
| `sleeper` | **Web (2026-09-03):** the web Sleeper username door — it emitted no funnel events before this date, so web funnel history starts here | `web/js/app.js` `handleLogin` |

All three funnel events carry it: `signin_attempted` at the claim,
`signin_succeeded` on a stored token, `signin_failed {error_code}` on
refusal. Semantics deliberately mirror Sleeper: the *claim* is the attempt —
opening the sheet or previewing a league is not.

Downstream: funnel queries that bucket by `method` gain two buckets; nothing
existing changes meaning. `league_selected.platform` continues to carry the
platform on the far side of the picker.
