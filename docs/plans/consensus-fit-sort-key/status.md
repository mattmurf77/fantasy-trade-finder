# Status — consensus-fit-sort-key

```project-status
{
  "status": "built-unmerged",
  "updated": "2026-09-02",
  "summary": "consensus fit sort key",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **built, unmerged** · 2026-09-02 **built, unmerged** · 2026-09-02 — Roster fit as a SORT KEY for the consensus generator (84.5% of served cards): `consensus_fit_weight` blends the marginal-value asymmetry (worth in the partner's lineup minus worth in ours, both at consensus prices) into the pool sort as `seed_value × (1 + w × fit_norm)`; default 0 is byte-identical (goldens vs `origin/main` @ `ce3f443c`). Reorders only — no gate moves, the user still wins on consensus on every card. R7 of the [2026-08-22 restrictiveness review](../../reviews/2026/2026-08-22-trade-model-restrictiveness.html) in its sort-key form (the pool-prune form was rejected: 5.5× cost). [scope](scope.md) · [code-walk](code-walk.md) · [results](results.md) · harness `measure_consensus_fit.py`. Arm A pins the identity 0.0. Built on `claude/consensus-fit-sort-key`; the lead ships.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
