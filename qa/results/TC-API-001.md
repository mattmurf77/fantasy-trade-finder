# TC-API-001 — API consistency + doc-drift audit

| Field | Value |
|---|---|
| **Status** | COMPLETE — 7/8 checks pass; 1 FAIL is the surfaced naming finding |
| **Date executed** | 2026-06-11 |
| **Layer** | api |
| **Component(s)** | all 92 routes in `backend/server.py`; `docs/api-reference.md` |
| **Requirement / doc ref** | QA charter "consistent API naming conventions"; CLAUDE.md doc-sync |
| **Engine path & flags** | n/a |

### Objective
Audit cross-route consistency (naming, error shapes, response envelopes, status
codes) and code↔doc drift — the "consistent API conventions" charter item.

### Scope
- **In scope:** route inventory + auth-gate distribution; path naming
  (kebab/snake, singular/plural, versioning); error-body taxonomy; doc drift
  vs api-reference.md; live response-envelope shapes; 401/404/400 error contracts.
- **Out of scope:** per-route auth-intent correctness (TC-SEC-001 covered the
  operator surface); payload field-name consistency; rate limiting.

### Inputs / Steps
Automated: [qa/api/tc_api_001.py](../api/tc_api_001.py). Static plane parses
server.py route decorators + api-reference.md; dynamic plane boots a local
server, establishes a session, samples GET envelopes and error responses.

### Actual Result
93 (method,path) entries across 92 routes. Auth gates: **session 35, none 44,
cron 13, bearer/other 1**. Error contracts solid (401/404/400 all return JSON
with an `error` key and the correct status). Findings below.
Evidence: `qa/api/scratch/TC-API-001-run.json`.

### Outcome
**COMPLETE** — API is internally consistent in the load-bearing ways (every
error body carries an `error` key; status codes are correct; each route's
envelope is stable). Consistency *debt* is cosmetic/vocabulary-level, documented
below for a future cleanup pass.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| F-1 | **P2** | **39 handlers return `jsonify({"error": str(e)})`** — leaks exception type/message/paths in prod (info disclosure + confusing clients). | static scan | Wrap in a generic `{"error":"internal_error"}` (log the real exception server-side); reserve raw detail for the debug log. |
| F-2 | **P3** | **Error-value vocabulary is inconsistent**: 42 error-code style (`not_found`, `save_failed`), 44 human-sentence style (`"User not found"`), 23 code+message. A client can't reliably `switch` on `error`. | static scan | Standardize on `{"error":"<code>","message":"<human>"}`; the `error` field a stable enum, `message` the prose. |
| F-3 | **P3** | **2 routes undocumented** in api-reference.md: `/api/feedback/admin` (GET), `/api/tiers/copy-from-format`. (`/api/trades/awaiting` + deck-order note were added this cycle.) | doc-drift scan | Add both to api-reference.md. |
| F-4 | **P3** | **One snake_case path segment**: `/api/sleeper/league_users` vs kebab everywhere else (e.g. `/api/league/member-unlock-states`). | naming scan | Defensible (mirrors Sleeper's endpoint), but inconsistent — either rename to `league-users` or note the upstream-mirror rationale in api-reference.md. |
| F-5 | **P3** | **No response envelope standard**: 3 sampled GETs return bare arrays (`/api/trades`, `/api/leagues`, `/api/trades/matches`), 7 return objects. No `/vN/` version prefix on any route. | envelope sample | Acceptable today (each route is internally stable); flagged for if/when a v2 API or SDK is built — a uniform `{data, meta}` envelope + version prefix would ease breaking changes. |

### Observations & feedback (no change required)
- **The `error` key name is 100% consistent** even though its *value* style
  isn't — so clients can always detect failure; they just can't branch on the
  reason. F-2 is the higher-leverage half of the cleanup.
- **44 `none`-auth routes is not 44 missing-auth routes.** The bucket is
  dominated by intentionally-public endpoints (Sleeper passthrough, OG/share
  images, `/api/feature-flags`, `session/init`, `parse-url`). The operator
  surface was proven gated in TC-SEC-001. A full per-route auth-*intent* audit
  (does each public route deserve to be public?) is a reasonable follow-up.
- **Status-code hygiene is good**: 400 (malformed), 401 (no session), 403, 404,
  409 (already-decided), 503 (cron fail-closed), even a 502 — codes are used
  meaningfully, not just 400/500 everywhere.
- The raw-`str(e)` leak (F-1) overlaps the recon "error leakage" item — now
  quantified (39 sites) and reproduced.
