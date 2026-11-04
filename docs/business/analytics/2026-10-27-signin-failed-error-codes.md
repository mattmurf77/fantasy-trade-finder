# Addendum — `signin_failed.error_code` values for ESPN/MFL sign-in (2026-10-27)

**Scope:** value-only addition. No new event, no new prop, no registry change.
`error_code` is already a registered key on `signin_failed` (pre-auth funnel,
`backend/analytics_taxonomy.py`). Granted by analytics-lead on 2026-10-26
(ESPN/MFL sign-in grants, item 1); this answers onboarding-pm's Q6 on #354:
the codes need documenting, not registering.

**Why:** proof-based platform sign-in (`docs/plans/platform-sign-in/scope.md`)
turns the `POST /api/entry/platform` team claim into "prove, then sign in".
It adds four refusal codes. The mobile client already passes the server's
`error` straight through as `error_code` (`entryErrorCode`,
`mobile/src/api/platformEntry.ts`), so the four values start arriving with
no client change. History: none of the four exists before this server
change ships; earlier `method: espn|mfl` failures never carry them.

**New values (all four granted):**

| Value | Meaning |
|---|---|
| `proof_required` | A team claim arrived without proof: no ESPN `espn_s2`+SWID pair, or no MFL username+password |
| `proof_unavailable` | The claim can't be proven through the platform. The response `reason` (not tracked) is `espn_public_league`, `espn_unproven_pair`, `espn_ownerless_team` or `espn_unavailable` |
| `platform_identity_in_use` | The proven ESPN/MFL identity is already an imported-league credential of another Fleeced account (409). Names the condition, never the identity |
| `too_many_attempts` | The per-IP or per-identity failure limit was hit (429) |

## The closed domain of `signin_failed.error_code` (`method` = `espn` / `mfl`)

Codes only. No value may ever carry an identity (SWID, MFL username, email,
cookie, password) — the server never puts one in `error`, and the client
emits only the server's `error` or one of the fixed client codes below.

**Server refusals from `POST /api/entry/platform`** (the response `error`):

| Code | Platform | Status |
|---|---|---|
| `proof_required` | espn, mfl | 403 |
| `proof_unavailable` | espn | 403 |
| `platform_identity_in_use` | espn, mfl | 409 |
| `too_many_attempts` | espn, mfl | 429 |
| `espn_bad_credentials` (incl. `reason: wrong_account`) | espn | 403 |
| `mfl_bad_credentials` (incl. `reason: wrong_account`) | mfl | 403 |
| `espn_auth_required` | espn | 403 |
| `mfl_auth_required` | mfl | 403 |
| `espn_cookies_incomplete` | espn | 400 |
| `espn_bad_league_id` / `mfl_bad_league_id` | espn / mfl | 400 |
| `espn_bad_season` | espn | 400 |
| `espn_bad_team_id` / `mfl_bad_team_id` | espn / mfl | 400 |
| `espn_league_not_found` / `mfl_league_not_found` | espn / mfl | 404 |
| `espn_unavailable` / `mfl_unavailable` | espn / mfl | 502 |
| `feature_disabled` | espn, mfl | 404 |
| `bad_platform` | — | 400 |
| `session_build_failed` | espn, mfl | 500 |
| `internal_error` | espn, mfl | 500 |
| `session_expired` | espn, mfl | 401 (a sign-in raced an account deletion) |

**Client-side codes** (`entryErrorCode` when the response carries no `error`):

| Code | Meaning |
|---|---|
| `timeout` | The request timed out |
| `http_<status>` | A non-2xx response with no JSON `error` (e.g. an edge page), `<status>` = the HTTP status |
| `unknown` | Anything else (network failure with no status) |

**Existing sign-in-screen codes** (`mobile/src/screens/SignInScreen.tsx`,
smart-start path; listed so the domain is closed):
`owner_resolve_failed`, `platform_unsupported`, `smart_start_invalid`.

**Downstream:** queries that bucket `signin_failed` by `error_code` gain four
buckets; nothing existing changes meaning. Class unchanged: pre-auth rows are
`device:` ids and are stripped from DAU anyway.
