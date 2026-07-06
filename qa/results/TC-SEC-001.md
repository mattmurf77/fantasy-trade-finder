# TC-SEC-001 — Operator-endpoint auth enforcement (cron-secret gate + session gate)

| Field | Value |
|---|---|
| **Status** | PASS (35/35 checks) |
| **Date executed** | 2026-06-11 |
| **Layer** | security |
| **Component(s)** | `server.py::_require_cron_auth` (6207), all `/api/admin/*`, `/api/cron/*`, `/api/debug/log`, `/api/feedback/admin*`, `/api/feature-flags/reload`; `_require_session` session gate |
| **Requirement / doc ref** | docs/api-reference.md auth notes; secrets.local.env `CRON_SECRET` convention; recon claim under test |
| **Engine path & flags** | n/a (auth layer); swept across CRON_SECRET set/unset and prod/dev `DATABASE_URL` |

### Objective
Empirically confirm or refute the discovery-phase claim that operator/admin
endpoints are unauthenticated (filed as P0). Prove what the auth gate actually
does across environment configurations.

### Scope
- **In scope:** cron-auth enforcement on all 8 representative operator routes
  (missing header → 401, wrong/near-miss secret → 401, correct → success);
  prod fail-closed behavior; dev-open behavior; session-gate rejection of
  tokenless and bogus-token mutating calls.
- **Out of scope:** rate limiting, CORS, extension bearer-token issuance,
  error-message leakage (separate TC-SEC cases), whether CRON_SECRET is actually
  set on the live Render instance (operational check, not code behavior).

### Preconditions / Setup
- Scratch copy of `data/trade_finder.db`; local Flask booted per-config on
  ports 5101–5103 via `qa/lib/harness.py`. Live DB never written.
- Configs: (A) sqlite + no `CRON_SECRET`; (B) sqlite + `CRON_SECRET` set;
  in-proc logic test flips `_IS_PROD_ENV`/`_CRON_SECRET` to exercise the prod
  branch without a real Postgres (import succeeds on sqlite, globals patched,
  `_require_cron_auth()` called inside a Flask request context).

### Inputs / Steps
Automated: [qa/sec/tc_sec_001.py](../sec/tc_sec_001.py). Routes covered:
`GET/PUT /api/admin/config[/<key>]`, `GET /api/admin/engine-metrics`,
`GET /api/feedback/admin`, `PUT /api/feedback/admin/<id>/status`,
`GET /api/debug/log`, `POST /api/feature-flags/reload`,
`POST /api/cron/realtime-tick`. Session control:
`POST /api/trades/swipe`, `/api/rank3`, `/api/league/preferences`.

### Expected Result
Config B: every operator route 401s without/with-wrong secret and succeeds with
the correct one; a truncated secret still 401s (constant-time compare).
Prod branch: no secret → 503 (fail closed), correct secret → pass.
Session gate: tokenless and bogus-token mutating calls → 401.

### Actual Result
**35/35 PASS.** Config B enforced on all 8 routes (incl. near-miss → 401).
In-proc prod branch: no-secret→503, no-header→401, wrong→401, correct→pass,
dev-no-secret→open. Session gate: all four control calls → 401.
Evidence: `qa/sec/scratch/TC-SEC-001-run.json`.

### Outcome
**PASS** — the recon P0 is **REFUTED**. Operator endpoints are correctly gated;
the auth design (fail-closed in prod, open only on local sqlite) is sound.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| F-1 | **P2** | `run.py` binds `host='0.0.0.0'` with `debug=True` and the default local config has no `CRON_SECRET`. On a network-reachable machine this exposes every operator endpoint (live config mutation, feedback PII, debug log) to the LAN, and `debug=True` enables the Werkzeug interactive debugger. Prod (Render/Postgres) is unaffected — fail-closed applies — but local/self-host runs are exposed. | run.py:`app.run(debug=True, host='0.0.0.0', port=5000)`; Config A: 8/8 routes open | Bind `127.0.0.1` for local dev (or gate on an env flag), and/or document that `CRON_SECRET` should be set even locally if the host isn't isolated |
| F-2 | **P3 (process)** | The discovery-phase report asserted 5 operator endpoints were unauthenticated (P0). All call `_require_cron_auth()`. The subagent skimmed routes without tracing the auth call. | This test | Treat single-pass recon findings as hypotheses until a TC verifies them (now standard in qa/README.md WoW). |

### Observations & feedback (no change required)
- **Fail-closed prod design is the right call:** an accidentally-unset
  `CRON_SECRET` on Render makes operator/cron routes return 503 rather than
  silently going world-open. Good defensive default.
- **Constant-time compare** (`hmac.compare_digest`) is correctly used — a
  truncated/near-miss secret 401s like any other miss.
- **Asymmetry noted in recon is real but harmless:** GET and PUT on
  `/api/feedback/admin*` both gate on cron-auth (the recon "GET unprotected"
  claim was also wrong).
- Worth a follow-up *operational* check (not code): confirm `CRON_SECRET` is
  actually set in the Render dashboard, since the whole prod guarantee rests on
  it. That's a runbook item, not a test.
