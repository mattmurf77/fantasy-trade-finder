# FB-418

**Status:** in_progress · 2026-09-03 · branch `claude/new-user-feedback-06dabd`, fix commit `f593020a` (worktree `happy-golick-345cf1`); QA A **PASS** / QA B **PASS**; awaiting ship

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
- **Build:** 2026-09-03 — `f593020a` on `claude/new-user-feedback-06dabd`; [`build-notes.md`](build-notes.md) (diff, sabotage proof k1–k8; §2.1 adds k3b, k9, tightened k8).
- **QA:** 2026-09-03 — [`qa-A.md`](qa-A.md) (mechanical re-proof, **PASS**, non-blocking F-1/F-2 resolved by k9/k3b/k8) · [`qa-B.md`](qa-B.md) (adversarial product review, **PASS**; B-2 added to prd D-2, B-6 corrected in §8.3 step 8, its 11-step checklist adopted as prd §8.3; B-1 cross-visit re-offer is a ruling for the operator at checklist step 10).
