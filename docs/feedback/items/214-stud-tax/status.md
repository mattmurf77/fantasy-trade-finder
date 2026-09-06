# Status — 214-stud-tax

```project-status
{
  "status": "shipped",
  "updated": "2026-08-05",
  "summary": "#214 / #215 — Stud-tax retune + `stud_tax_mode` toggle — status",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-08-05 — #214/#215 stud-tax retune `6577668` — CHANGELOG 2026-08-05. Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# #214 / #215 — Stud-tax retune + `stud_tax_mode` toggle — status

**Status:** in-progress · 2026-08-05 · branch `teardown-remediation` (worktree)

`build-status.md` records the retune as built: crown phase-out, elite credit
on both sides, and an own-best-asset depth benchmark/cap in
`backend/trade_service.py`'s new `market` stud-tax mode, plus the #215
`stud_tax_mode` toggle (`GET/PUT /api/settings/stud-tax`). Backed by
`research/` (competitor values, calculator landscape), `results.md`,
`tuning-proposal.md`, and `validation-plan.md`. Built on a worktree branch;
not confirmed merged to `main` from this folder's evidence alone.

Backfilled 2026-08-08 — the folder has `build-status.md`, not `status.md`,
which is why the Phase-0 scan treated it as missing.
