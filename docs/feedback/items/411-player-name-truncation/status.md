# Status — 411-player-name-truncation

```project-status
{
  "status": "shipped",
  "updated": "2026-08-30",
  "summary": "FB-411 — player name truncation",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-08-30 — satellite — chip to meta line, name 13/18 (QA-B F-1 disclosure, checklist step 11b ruling). Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# FB-411 — player name truncation

**Status:** planned · 2026-08-30 · `claude/fb-410-412-trade-card-polish`

- **Group:** G-410 — merged-canvas trade-card polish.
- **Group canonical:** [`410-found-trade-decline-position/`](../410-found-trade-decline-position/plan.md)
  holds the plan, scope and PRD for #410, #411 and #412 together (one owner —
  all three touch the same three files).
- **Findings for this item:** [plan.md §3](../410-found-trade-decline-position/plan.md#3-411--player-name-truncation),
  requirements **R-6 / R-7**.

## The report

> *"Move the position tag to the second row, leaving just the name on the top
> row. Pressure test whether the names stop getting truncated now."*

## Current behavior (one line)

In the merged calculator's column mode the position chip and the name share line
one (`mobile/src/components/TradeSide.tsx:85-90`), leaving the name **≈67pt**
(~8 characters at `type.title` 16pt) inside a `numberOfLines={1}` clamp — so
nearly every real NFL name ellipsizes.

## Pressure-test answer

Moving the tag to row 2 frees the name to **≈97.5pt** (+45%) — enough for short
names, **not** enough for the median 13–16 character name. The plan therefore
pairs the operator's ask (**R-6**, move the chip to the meta line) with **R-7**,
a two-line clamp on the compact name, which is what actually closes the
complaint. Full per-name width table in
[plan.md §3.2](../410-found-trade-decline-position/plan.md#32-quantified-what-truncates-now-and-what-still-truncates-after-the-move).
- 2026-08-30: built + dual-QA green, shipping in v1.16.13. Canonical: [410-found-trade-decline-position](../410-found-trade-decline-position/status.md).
