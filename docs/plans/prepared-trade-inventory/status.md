# Status — persistent prepared trade inventory

```project-status
{
  "status": "in-progress",
  "updated": "2026-09-23",
  "summary": "Approved chunked cache preserved all13728 offers. Revised936 telemetryON first30published1.069s locally. Prepared526 tests and PostgreSQL59 passed; feedback/admission races fixed. Production cache off; final dense/CI/canary gates remain.",
  "evidence": "Prod2cff90c7/cache0 readback2026-09-23T02:03:21UTC. Prepared526pass85.57s; codec153; store59 eachSQLite/PG; finaldiagnostics/feedback/runtime58pass7.12s. Revised936 telemetryON: prepare23.74s/first30published1.069s/full21.90s/RSS343.7MB. Earlier13728 telemetryOFF: first30durable3.855s/full338.64s/RSS1.492GB; all native proof/order preserved. No device/prod timing claim. Final dense/full hosted gates pending; no v2 release yet."
}
```

[Validation and limitations](validation.md) · [Operator runbook](runbook.md) · [Release evidence](release.md)

Durable retention is at most 24 hours subject to exact current input/model/team
validation and original card expiry. Preparation is not exposure or a user action.
No offer limit, model-quality result, three-second device claim or production
coverage figure follows from the local test results.
