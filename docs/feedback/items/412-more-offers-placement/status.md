# FB-412 — "More offers" location

**Status:** planned · 2026-08-30 · `claude/fb-410-412-trade-card-polish`

- **Group:** G-410 — merged-canvas trade-card polish.
- **Group canonical:** [`410-found-trade-decline-position/`](../410-found-trade-decline-position/plan.md)
  holds the plan, scope and PRD for #410, #411 and #412 together (one owner —
  all three touch the same three files).
- **Findings for this item:** [plan.md §4](../410-found-trade-decline-position/plan.md#4-412--more-offers-location),
  requirements **R-8 / R-9**.

## The report

> *"Reversion from prior version.. move more offers underneath the add a player
> button"*

## Current behavior (one line)

"More offers" moved **yesterday**, in `21989cda` (v1.16.11 / PR #237): the
canvas-results browse session hid the deck card that used to carry the give-side
chip (`mobile/src/components/TradeCard.tsx:444-464`), and the entry was
re-hosted on the browse pager row
(`mobile/src/screens/TradesScreen.tsx:7347-7368`).

## No ruling conflict

The pager placement is labeled *"#402 QA B-C4 (operator-flagged design call,
built under the ship order)"* — a QA agent's compensating placement, not an
operator ruling. Searching `docs/` for `B-C4` returns only a verification step in
`402-more-offers-shop/testflight-checklist.md`. **The operator is right that it
was a reversion**, and moving it under the give column's "Add player" button
contradicts nothing on the record.
- 2026-08-30: built + dual-QA green, shipping in v1.16.13. Canonical: [410-found-trade-decline-position](../410-found-trade-decline-position/status.md).
