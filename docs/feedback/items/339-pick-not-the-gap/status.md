# Status — 339-pick-not-the-gap

```project-status
{
  "status": "shipped",
  "updated": "2026-08-16",
  "summary": "FB-339",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-08-16 — wave `20b40db` — G6, canonical `304-positional-need-filter/`; `pick_gap_frac` band still untuned. Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# FB-339

- **Status:** planned 2026-08-16
- **Group:** G6 — Trade presentment rules
- **Canonical folder:** [`304-positional-need-filter/`](../304-positional-need-filter/) — plan, PRD, and status for this group live there.
- **Batch plan:** [`304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md)

## Reported

> Need logic in the trade calc to not include a draft pick if that draft pick is the value difference between the two sides (meaning the side giving up more is giving up a mid 1st more.. there should never be a mid 1st on their side of the offer).
