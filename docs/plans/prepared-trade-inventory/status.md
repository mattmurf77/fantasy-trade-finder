# Status — persistent prepared trade inventory

```project-status
{
  "status": "in-progress",
  "updated": "2026-09-23",
  "summary": "Approved chunked cache preserves all13728 offers; local first30published2.50s dense,1.18–3.28s on936 with active switches. PR307 CI findings repaired locally; final retry pending. Production cache off until green release and canary.",
  "evidence": "Prod2cff90c7/cache0 readback2026-09-23T02:42:12UTC. Prior CI35811257235/570778f2:7402pass1skip5fail874.09s; other3gatesgreen. Four legacy projection stub keyword failures fixed23pass16.66s; stale synthetic session reproduced401 then corrected12pass35.65s. Prepared526pass; finaldiagnostics58pass; flagcompat19pass; finalPG59pass16.10s. Full13728 parity703.75s/RSS1.434GB. All-team dryrun7resolved/6eligibleactors, discovery incomplete. No prod/device3sec claim or v2 deployment."
}
```

[Validation and limitations](validation.md) · [Operator runbook](runbook.md) · [Release evidence](release.md)

Durable retention is at most 24 hours subject to exact current input/model/team
validation and original card expiry. Preparation is not exposure or a user action.
No offer limit, model-quality result, three-second device claim or production
coverage figure follows from the local test results.
