# Status — persistent prepared trade inventory

```project-status
{
  "status": "in-progress",
  "updated": "2026-09-22",
  "summary": "PR305 merged and deployed; initial production canary failed before storing inventory. Prepared-cache activation was rolled back to zero. Targeted cross-batch evidence fix and renewed validation are in progress; ordinary Bilateral2 generation is unchanged.",
  "evidence": "Exact-head hosted CI35788148359 passed all four gates, backend7144/1skip. Render4903d205 live2026-09-22T22:07:49Z. Canary10e5d888d5f54d588ca930fb21e0dfbc reported prepared_payload:snapshot_conflict; zero artifacts, no new impressions/decisions/sessions, unchanged activity/ranking fingerprint. Rollout1→0 verified22:11:56UTC. See release.md for actual coverage and limitations."
}
```

[Validation and limitations](validation.md) · [Operator runbook](runbook.md) · [Release evidence](release.md)

Durable retention is at most 24 hours subject to exact current input/model/team
validation and original card expiry. Preparation is not exposure or a user action.
No offer limit, model-quality result, three-second device claim or production
coverage figure follows from the local test results.
