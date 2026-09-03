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
- **Operator ruling, 2026-09-03 (closes QA-B B-1):** *"needs a backend follow up. This
  should be treated the same as any other 'liked' trade."* The cross-window re-offer is
  **not** accepted behavior — the server must stop offering a sent idea, exactly as the deck
  already refuses to re-offer a liked package. Recorded as
  [D-178](../../../living-memory/DECISIONS.md); spec (backend-only, not built) at
  [`followup-backend-like-exclusion.md`](followup-backend-like-exclusion.md); queued in
  [`NEXT.md`](../../../living-memory/NEXT.md) 2026-09-03c. The mobile half in this branch is
  unchanged and still correct — it becomes the bridge between a send and the next fetch,
  which is the role it already plays for a dismiss. Checklist step 10's ruling question is
  answered; the step stands as a verification that the tile leaves.
- **Backend follow-up BUILT, 2026-09-03** — branch `feat/fb418-backend-like-exclusion`
  (from `f13dd96c`), **not merged, not deployed**. `POST /api/trades/asset-ideas` and
  `POST /api/trades/fair-packages` now build the deck's own windowless awaiting-like /
  matched exclusion set (`_load_presentment_exclusions`, G6 R4 #336, gated on
  `trade.presentment_rules`) and drop every idea whose (give-set, receive-set) key is in
  it — so a sent offer is absent from the next fetch, and from the counts the client
  derives from the payload. Filter runs at emission, INSIDE both caps, so the answer still
  fills. Docs: [`backend-prd.md`](backend-prd.md) (R-1…R-9, the four design answers,
  code-walk proof, 12-test red-proof table) · [`backend-scope.md`](backend-scope.md)
  (filled scope block; §6 = two deviations from the spec) ·
  [`followup-backend-like-exclusion.md`](followup-backend-like-exclusion.md) (spec, now
  marked built). Evidence: full suite **4599 passed / 1 skipped**, `check-shop-deck`
  **153 PASS**, `tsc --noEmit` clean. `ShopOffersBody.tsx`'s "no server-side memory for a
  queued like" comment is corrected in the same commit (all three k8 `#418` sites intact).
  Remaining: operator TestFlight check (3 steps, `backend-scope.md` §3) and the prod
  `shop_opened` volume read.

