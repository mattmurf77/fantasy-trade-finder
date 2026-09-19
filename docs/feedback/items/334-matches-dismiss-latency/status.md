# Status — 334-matches-dismiss-latency

```project-status
{
  "status": "shipped",
  "updated": "2026-08-16",
  "summary": "FB-334 — group canonical folder",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-08-16 — wave `20b40db` — G9 **canonical** (#334 #335). Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# FB-334 — group canonical folder

- **Status:** built 2026-08-16 · **Phase:** 2 (build complete — awaiting merge + operator TestFlight checklist)
- **Group:** G9 — Matches polish (canonical: #334 #335)
- **Batch plan:** [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md)
- **Base:** `origin/main` @ `d3fe3ac` (v1.13.4); PRD cites re-anchored to `0b2dcee`; built on branch `feat/fb334-matches` from specs commit `56856f7` (= `origin/main 96f6945`) — the five cited files verified byte-identical to `0b2dcee`, no seventh repopulation path
- **Build evidence:** [`qa-code-walk.md`](qa-code-walk.md) (CW-1, P1–P6 + B-1 + NB-4) · [`qa-notes.md`](qa-notes.md) (10 sabotage RED runs) · suites 30/30 + 21/21, all 38 green, tsc clean

## Reported

> Dismissing trades awaiting the other players review is slow to have the tile disappear.
