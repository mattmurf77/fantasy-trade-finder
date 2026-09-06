# Status — quickset-analytics-via

```project-status
{
  "status": "needs-review",
  "updated": "",
  "summary": "quickset analytics via",
  "evidence": "Disposition remains absent, unclear, or internally qualified; preserve existing claims until reconciled. Last documented index disposition: **shipped (PR #196, merged 2026-08-25); lights up at the next mobile release** · 2026-08-25 **shipped (PR #196, merged 2026-08-25); lights up at the next mobile release** · 2026-08-25 — Unscoped mobile Quick Set saves now tag `via:'quickset'` on `POST /api/tiers/save` — the value the server has branched on since analytics P0 (FR-20 `quickset_completed`, `tier_save.props.via`, point-of-use `ranking_method`) but which **no client ever sent**, so all three reads were dark for every production Quick Set walk while docs called the server row \"the authoritative completion\". One-line emitter fix + semantics correction (per tagged tier COMMIT, never per completed position — a consensus-accepting walk saves nothing); no registry change. [scope](scope.md) · [addendum](../../business/analytics/2026-08-24-quickset-via-gap.md) · guard `mobile/tests/check-quickset-via.js`. Takes effect from the next TestFlight build.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
