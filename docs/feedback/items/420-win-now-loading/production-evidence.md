# Win Now feedback 420–421 — production incident evidence

**Date:** 2026-09-06. Read-only PostgreSQL query scoped to the report window; report-owner attribution was matched in memory, then removed. No token, account ID, league ID, raw request/response body or private ranking value is reproduced here. Successful API calls are sampled; failures are captured when observability is enabled. Absence of a sampled success is not proof that it never happened.

## Observed sequence — 2026-09-05 UTC

| Time | Stored observation | Meaning |
|---|---|---|
| 09:48:52.366639 | Reporter-attributed `POST /api/session/init`, HTTP 200, 296 ms | A successful initialization preceded the redeploy. |
| 09:51:59.126135 | Render deployment `dep-daduc0bm8hqs73ckbifg` live at source `4026ebc8`; previous source `c28ec6d8` | Deployment boundary verified through Render metadata, not inferred from the error copy. |
| 09:53:34.799864–09:54:17.147782 | Repeated `GET /api/league/season-projections`, HTTP 409, `session_not_initialized`, server duration 0 ms | Requests were rejected at the session gate before forecast computation. |
| 09:53:40.416118 / 09:53:50.388758 | Client `api_request_failed` for that route: HTTP 409, 2,260 / 2,414 ms, `timeout=false` | Client retries did not restore the initialized league context. |
| 09:54:42.892281 | Reporter-attributed `POST /api/session/init`, HTTP 200, 303 ms | A later initialization succeeded. |
| 09:54:58.336267 | `GET /api/league/season-projections`, HTTP 200, 15,186 ms | The server completed an HTTP response just beyond the default client deadline. Its unavailable/available payload was not captured; 200 does not establish forecast availability. |
| 09:54:58.588210 | Client `api_request_failed` for projections: status 0, 15,034 ms, `timeout=true` | This attempt hit the client deadline; not evidence of a sleeping service or free plan. |
| 09:54:58.588210 | Client failure on `/api/trades/liked`: status 0, 15,043 ms, `timeout=true`; server recorded HTTP 200 at 09:54:58.340307 with 0 ms handler time | Consistent with contention in the one-worker service, but the stored rows do not prove transport-level queue timing. |

Both reports were submitted on iOS version 1.17.0. The feedback records do not capture a native build number, so the reported binary cannot be uniquely identified. The experimental personal-market switch was activated only later, at the 16:01:20 UTC redeploy; it did not cause these preceding incidents.

## Investigation boundaries

Current code supplies independent evidence for two defects: stale local readiness after a server restart is not repaired by a bounded same-context initialization in this path, and the shared client's deadline is labeled as a server wake-up. The fix must address context recovery and a measured bounded deadline, not merely replace the visible text. Preserve league/account/token switch cancellation and never automatically replay a non-idempotent trade write to recover a projection read.

No production user action, scenario generation, data rewrite or feedback closure was performed for this evidence. The selected records alone moved to planned, separately through the existing feedback API.
