# FB-418 — plan (one page)

> Fast-track bug. Read [`prd.md`](prd.md) for the requirements and test plan,
> [`scope.md`](scope.md) for the gates. This page is the approach and the why.

## The bug in one line

In the shop window, **Send this offer** queues the trade but leaves the tile in
the pager; **Dismiss** removes it. The user acted; the surface didn't.

## Approach

One function, one file. `handleLike` in
`mobile/src/components/ShopOffersBody.tsx` (`:696-715` today) gains the
committed-removal half that `commitDismiss` (`:534-561`) already has:

```
try {
  const res = await queueCalcTrade(…);         // unchanged
  if (res.queued) {                            // incl. alreadyQueued (R-1); then-branch only (k4)
    requestPagerScroll(index);                 // P-1: request BEFORE the write; `index` is a
                                               //   closure constant — `const at = index` is optional (D-2)
    setSuppressed((s) => new Set(s).add(key)); // committed ⇒ session-authoritative
  }
  onToast(res.toast);                          // unchanged
} finally {
  setBusyKey(null);                            // unchanged (k7)
}
```

Everything downstream is already built and already pinned: `visibleByMode`
filters `suppressed` out of the pager, the `1 / X` counter, the chip counts and
the Clear-positions label (`:492-519`); the single reactive scroll effect
(`:731-747`) clamps and fronts the next tile, or the existing empties render
when the list hits zero (`:878-934`). **No count, no effect, no empty state is
touched** — a counter that fails to drop is a regression, not a follow-up.

Why `suppressed` and not `locallyRemoved`: a dismiss is *held* (5 s undo, POST
not yet sent) and lives in `locallyRemoved` until it commits; a like is
committed **by the queue call itself** — no undo route exists — so it enters
the committed set directly, exactly as a dismiss does at `:540`. The file's
three "one gate" comments (`:77-82`, `:306-309`, `:536-537`) get one clause each
so they stay true (R-9) — and the `suppressed` block's clause also says that
for a like this set is the *only* memory (the server re-offers a queued idea
on the next fetch; only a dismiss has the D-067 cooldown behind it).

Decisions, recorded in prd §5: **no** `flushPendingDismiss()` from the like
(D-1 — R-9's flush triggers are second-pending / invalidation events, and the
shipped B-4 comment at `:572-578` already lets a ✓ toast replace the Undo toast
without committing); tap-time index (D-2); extend `check-shop-deck.js` rather
than add a file (D-3).

## Platforms

**Mobile only.** No `web/` or `extension/` file renders the shop
(`git grep -n "shop-ideas\|ShopOffersBody" -- web extension` is empty).
Backend untouched.

## Files

| File | Owner | Change |
|---|---|---|
| `mobile/src/components/ShopOffersBody.tsx` | build agent | `handleLike` + three comment clauses (each tagged `#418`) |
| `mobile/tests/check-shop-deck.js` | build agent | section `(k)`, assertions k1–k8; one clause on the header bullet `:50-51` |

No `mobile/package.json` change (`test:shop-deck` exists, `:85`).

## Risks

| Risk | Why it is bounded |
|---|---|
| Pager position after a mid-flight swipe or refetch | D-2: render-time index, clamped by the effect — the pager fronts the tile that took the liked tile's slot; a coinciding refetch rewinds to 0 then jumps to that index. Sub-second windows; a position, never a wrong tile removed. |
| A refused queue removes the tile | Guard k4 pins the write inside the `then` branch of `res.queued`; k7 pins it after the `await` (never optimistic); checklist step 8 (Airplane Mode) proves it at runtime. |
| A like triggers the refetch rewind / flush by the back door | Verified: the queue call invalidates nothing (`api/trades.ts:601-620` is a bare `api.post`; no `invalidateQueries` in the three files) — prd D-1 premise. |
| Second `scrollToOffset` slips in | Guard n3a fails on any second call site. |
| Like clears or flushes the pending dismiss | k2 (never `locallyRemoved`), k6 (never `flushPendingDismiss`); checklist step 9. |
| Stale comments contradict the code | R-9 lists the three lines; diff review. |
| Queued idea reappears in a **new** window | Expected — asset-ideas does not consult the queue; out of scope (prd §6). Re-✓ shows "Already queued" and the tile leaves again. |

## Why fast-track

Two files; no schema, route, flag, analytics or copy change; the mechanism is
the one the same file already uses for the sibling control; every ruling it
touches (Fix A, P-1, R-5, R-9, B-4) is already pinned by the suite this change
extends. The full HLD/LLD delta would restate `402-more-offers-shop/` without
adding a decision.

## Sequence

1. Build agent: edit `handleLike` + comments → add `(k)` → `npm run
   test:shop-deck` green → sabotage S-1…S-8 each red, revert, green →
   `npx tsc --noEmit`.
2. QA agent: code-walk proof (prd §8.2) against the diff; confirm ownership
   diff; confirm k1–k8 sabotage pairs independently.
3. Ship: PR to `main` → EAS → TestFlight; operator runs prd §8.3; TEST_LEDGER +
   CHANGELOG + INDEX row flipped to `shipped`.
