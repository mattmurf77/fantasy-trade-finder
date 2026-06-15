# TC-API-002 — Public-route auth-intent audit + abuse-surface checks

| Field | Value |
|---|---|
| **Status** | PASS (4/4 checks) |
| **Date executed** | 2026-06-11 |
| **Layer** | api / security |
| **Component(s)** | all public (`none`-auth) routes in server.py; session gates `_require_session` + `_require_initialized_session` |
| **Requirement / doc ref** | TC-API-001 follow-up (44 public routes); recon CORS/rate-limit note |
| **Engine path & flags** | n/a |

### Objective
Determine whether every public route *deserves* to be public — specifically that
no state-mutating route is unauthenticated outside an intentional allowlist — and
check basic abuse hygiene (robustness, CORS).

### Scope
- **In scope:** classify public routes read vs mutating; allowlist-check public
  mutations; empty/garbage-body robustness; CORS posture.
- **Out of scope:** rate limiting on the pre-auth mutations (none exists — noted);
  per-route data-sensitivity of public reads.

### Actual Result
**4/4 PASS.** After recognizing both session gates, 13 truly-public /api routes
(8 read, 5 mutating). All 5 public mutations are intentional: `session/init`,
`session/demo`, `feedback`, `extension/auth`, `parse-url`. No 5xx on empty or
garbage bodies. CORS: no `Access-Control-Allow-Origin` header (same-origin only —
safe default). Empty `session/init` → graceful 200. Evidence:
`qa/api/scratch_api2/TC-API-002-run.json`.

### Outcome
**PASS** — **no unauthenticated state-mutating routes** beyond the intentional
pre-auth set. The recon "44 none-auth routes" concern resolves as intentional
public reads + a small allowlisted pre-auth mutation set.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| F-1 | **P3** | The pre-auth mutations (`session/init`, `extension/auth`, `feedback`) have **no rate limiting** — an attacker can spin up sessions/tokens or spam feedback in a loop (memory growth on `_sessions`; feedback is idempotent on `client_id` so lower risk). | static + TC-SEC-001 prior note | Add per-IP throttling on `session/init` + `extension/auth` before scale; session eviction (4h) caps the blast radius today. |
| F-2 | **P3 (process)** | A new auth gate `_require_initialized_session()` (25 routes) was added between TC-API-001 and this test — TC-API-001's auth counts (session 35 / none 44) are now stale. | grep: 2 session-gate helpers | Re-run TC-API-001 against the current tree for an updated count; the gate detection is now helper-agnostic. |

### Observations & feedback (no change required)
- **The session-auth refactor split one gate into two** (`_require_session` +
  the stricter `_require_initialized_session`). The QA parser now recognizes both;
  any future gate rename should update `parse_none_auth_routes`'s allowlist of
  helper names (a one-line maintenance point, flagged in the test).
- **CORS-less is the right default** for a same-origin web app + token-auth
  mobile/extension clients — no cookie CSRF surface. If a third-party browser
  integration ever needs cross-origin reads, add a *scoped* allowlist, never `*`.
- Public mutating routes failing *closed and structured* on garbage input (no
  5xx) means the pre-auth surface can't be trivially crashed.
