# Feature Scope — Shop's primary button proposes the trade on the league's platform

**Date:** 2026-11-01
**Entry point:** operator design review of #531 (11-01, via head-product): "#531 design change is wrong. The intent is that the trade gets sent on the platform they play on, not in our app." Routed by head-eng to trades-eng, GO 11-01, for the 11-06 binary.
**Builder:** trades-eng
**Operator sign-off on waivers:** none waived.

**Why:** Shop's primary button ("Show it to @name", `shop.like-btn`) only queued the trade into @name's Fleeced deck as a "likes you" card (`queueCalcTrade` → `POST /api/trades/queue`). Nothing reached Sleeper, ESPN or MFL.

**The change:**
- The Shop tile's primary action is the existing per-platform send router, `SendInSleeperButton`, which the deck, Matches and both calculators already mount. It routes by the league's platform: Sleeper (`trade.send_in_sleeper`, GraphQL propose), MFL (`trade.send_in_mfl`) and ESPN (`espn.send`).
- It brings their existing confirm, outcome-unknown handling (#513 / #527 / #539), per-platform blocks (e.g. `espn_pick_unsupported`), labels, toasts and "can't send here" lines. **No new copy.**
- **Send-only** (head-eng's call, Product's default): no deck queue, so no likes-you card for @name, and no Elo-board signal (Ruling A, #402). Keeping the Elo signal is head-product's call; if wanted, it's a stacked server follow-up (the queue's Elo half without the card).
- The ✕ dismiss is unchanged.

## 1. Analytics scope
- [x] **(a) Changed events, specced against the taxonomy:**
  - The send events' `surface` dimension gains **`shop`**: `sleeper_send_attempted` and `sleeper_send_failed`, the only send events that carry it. The MFL and ESPN buttons take `SendSurface` but fire no events today, on any mount. It's registered in `analytics_taxonomy.py`'s comment and in `tradeText.ts`'s `SendSurface` / `SEND_SURFACES` in the same commit. No new event name and no new prop name.
  - **Shift:** Shop stops firing `calc_trade_queued` (screen `ShopAsset`) and, server-side, `trade_proposed` with source `calculator` from the queue emitter. Shop sends show up in the send funnel with `surface = 'shop'`. analytics-lead is told in the PR.
  - **Grant:** analytics-lead's grant for the `shop` value is requested by head-eng through head-product. release-lead holds the merge until it's on record.

## 2. Schema & flag scope
- **New/changed tables, columns, flags, env vars or `model_config` keys:** none. The send router's existing flags gate each platform.

## 3. Evidence scope (D-056: no simulator)
- [x] **Structural guard:** `mobile/tests/check-shop-send.js`. The Shop tile mounts `SendInSleeperButton` with the idea's league, partner, ids and names, and `surface="shop"`. The Shop body never calls `queueCalcTrade` and never mentions `/api/trades/queue`. `SEND_SURFACES` includes `shop`. The ✕ dismiss is untouched. It fails on main's code.
- [x] **Updated guards:** `check-shop-deck.js` (the like's queue assertions become the send router's), `check-b5-copy.js` (the "Show it to" strings are gone, and the router's are already pinned elsewhere), `check-trade-text.js` (`SEND_SURFACES`).
- [x] **Code-walk proof:** `docs/plans/shop-platform-send/code-walk.md`. Sleeper, MFL and ESPN each traced from the Shop tap to the platform write, file:line-cited.
- [x] **Manual TestFlight checklist** (operator, 11-06 binary): `docs/plans/shop-platform-send/testflight.md`. One league per platform, including an ESPN package with a pick (`espn_pick_unsupported`).
- [x] **Before/after:** design-lead's render of the Shop tile, for the operator, in the PR body.
- `testID`s added/renamed: `shop.like-btn` is gone; the router's own testIDs apply.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change: the propose routes are reused as they are |
| `backend/analytics_taxonomy.py` (taxonomy) | updated | the `surface` enum comment gains `shop` |
| `living-memory/LLD.md` | n/a | no convention shift: a new mount of an existing component |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no wiring change |
| `docs/cross-client-invariants.md` | n/a | `SendSurface` is mobile-only |
| `docs/plans/launch-copy-b5-trades-2026-10-28.md` | n/a | history: the "Show it to" copy it records is superseded here |

## 5. Ship gate declaration
- **CI green:** `backend-tests`, `mobile-typecheck` (runs the check suites), `testid-lint`.
- **Evidence recorded:** TEST_LEDGER.
- **TestFlight verification:** the checklist, by the operator, on the 11-06 binary.
- **Merge holds:** analytics-lead's grant for `surface = 'shop'`, and the operator's design OK on the before/after.
- Express lane declared by the operator? No.
