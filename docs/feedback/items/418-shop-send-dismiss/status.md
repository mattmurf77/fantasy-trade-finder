# FB-418

**Status:** planned · 2026-09-03 · no branch yet (planning docs on the feedback-triage worktree)

- **Path:** fast-track bug — mini-PRD + scope block + one-page plan; no HLD/LLD delta.
- **Covered IDs:** 418.
- **Report:** operator, 2026-09-02, app v1.16.14, screen `ShopAsset`, severity bug —
  *"Hitting send this offer should dismiss the card"*
- **Docs:** [`prd.md`](prd.md) (problem, root cause, R-1…R-9, decisions D-1…D-3,
  test plan, ownership) · [`scope.md`](scope.md) (filled scope block, no waivers) ·
  [`plan.md`](plan.md) (approach, platforms, risks, why fast-track).
- **Root cause (one line):** `ShopOffersBody.tsx` `handleLike` (`:696-715`) queues
  and toasts but never writes the tile's key to `suppressed`, so `visibleByMode`
  (`:509-518`) keeps rendering it; `commitDismiss` (`:540`) is the shape to match.
- **Files at build:** `mobile/src/components/ShopOffersBody.tsx` ·
  `mobile/tests/check-shop-deck.js` (section `(k)`, k1–k8). No `package.json` change.
- **Decision to note:** a like does **not** flush the pending dismiss (prd D-1).
- **Critic pass:** 2026-09-03 — [`reconciliation-log.md`](reconciliation-log.md); verdict READY FOR BUILD.
