# Tracking-plan addendum — D1 free-agent moves (`fa_move_*`)

**Date:** 2026-11-01 · **Status:** granted by `analytics-lead` on 2026-11-01 with conditions C1–C6; the four client names are registered in the emitters' commit on `feat/fa-moves-client`
**Parent:** [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md)
**Origin:** `docs/plans/sleeper-fa-write/scope.md` §1 on `plan/fa-moves-launch` (the launch delta of #351's `consent.md` §6, renamed `sleeper_fa_*` → `fa_move_*`)
**Registries touched:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`), `backend/analytics_queries.py` (`NON_INTENT_EVENTS`, the two exposures) and `backend/analytics_ingest.py` (`attempt_id` joins `_HEX_ID_PROPS`, so a uuid4 with a 16-digit run isn't scrubbed). **Not** `FUNNEL_CRITICAL`, **not** WAT. Pinned by `backend/tests/test_analytics_taxonomy_fa_move.py`. The three server-fired names (`fa_move_consent_recorded`, `fa_move_consent_withdrawn`, `fa_move_write_succeeded`) are registered by the server PR with their emitters.

Mobile only. Emitter: `mobile/src/api/faMove.ts` (`trackFaMove`, `attemptMove`), called from `mobile/src/components/ClaimSheet.tsx`.

## The client events

| Event | Class | Fires when | Props |
|---|---|---|---|
| `fa_move_connect_shown` | non-intent (exposure) | the sheet shows the connect or verify step | `surface`, `reason`, `league_platform` |
| `fa_move_consent_shown` | non-intent (exposure) | the sheet shows the consent step | `surface`, `reason`, `league_platform` |
| `fa_move_write_attempted` | intent | a named-CTA tap (or Make the move) sends a request | `surface`, `has_drop`, `has_bid`, `consent_ticked`, `attempt_id`, `league_platform` |
| `fa_move_write_failed` | intent | that request fails, in any way | `surface`, `error_code`, `status`, `attempt_id`, `league_platform`, `kind` (only when the body has one) |

- **`surface`**: `free_agents` · `usage_trends`.
- **`league_platform`** (C1): `sleeper` · `mfl` · `espn`, always present. The client emits only when the server's capability says `move.mode = 'submit'`, where it's set. Never a prop named `platform`.
- **`connect_shown.reason`**: `not_linked` · `expired` · `unverified` · `other_account`. An unknown `connect` value shows the plain connect step and counts as `not_linked`.
- **`consent_shown.reason`**: `first` · `lapsed` · `version` · `withdrawn`. The server's own `consent.reason` when the consent block carries one (contract §2). Otherwise the client reads it: a 409 whose `copy_version` differs from the one shown is `version`; a Stop roster moves made in this app run is `withdrawn`; a grant the capability knew of that no longer holds is `lapsed`; otherwise `first`.
- **`error_code`** (C2, C3): closed, 21 values, platform-free: `feature_disabled` · `bad_request` · `verification_required` · `not_linked` · `expired` · `unconfigured` · `consent_required` · `roster_full_drop_required` · `asset_not_owned` · `player_unavailable` · `waiver_bid_over_budget` · `waiver_claim_unsupported` · `move_kind_changed` · `rejected` · `write_failed` · `outcome_unknown` · `move_in_progress` · `internal_error` · `network` · `timeout` · `unknown`. `status` is the HTTP status; 0 for `timeout` and `network`.
- **Two reads (C4):** "couldn't confirm" is `outcome_unknown`, `internal_error`, `timeout`, `network`, or `unknown` with `status` ≥ 500. "Repeat tap blocked" is `move_in_progress`.
- **`kind`** (C6): `network` · `roster_read`, only when the response body carries one. It separates state 11 (not sent) from 10f (the platform refused).

## Seams

- **No history before ship.** No `sleeper_fa_*` or `fa_move_*` name was ever registered, emitted or read, so there's no alias and no series break. The series starts when the server first answers `submit` (the flip, ~11-12..14), not when the 11-06 binary ships: the client is dark until then.
- **MFL and ESPN rows start with Update 1.** Until the server answers `submit` for those leagues, every row is `league_platform: sleeper`.
- **Offline taps aren't counted.** NetInfo is read before the request. Offline at the tap sends nothing, mints no `attempt_id` and records no `fa_move_write_*` event, `attempted` included. So `network` with `status` 0 always means a request went out.
- **A 2xx the client can't read** records `write_failed {error_code: unknown, status: 200}`: the move may have landed, and the user sees "Check before resending".
