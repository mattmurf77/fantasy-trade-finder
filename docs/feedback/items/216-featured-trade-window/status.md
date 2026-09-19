# #216 — Featured-trade window for single-pin find-a-trade (covers the #209 order fix)

**Status: built (worktree branch `teardown-remediation`, pending merge) — 2026-08-02**

Operator-approved design: `mockups/polish-lab-2026-08/asset-ideas-layout-v2.html`
(layout) + `asset-ideas-layout-v3.html` (refinements). Verdicts: **v2 approved
with v3's refinements**; back chip = **Variant A** (own slim row ABOVE the
featured-window header); header **without** the player name ("Featured trade").
Ships live under the existing `trade.asset_ideas` flag — no new flag; the old
single-pin `AssetIdeasPanel` presentation is replaced, multi-pin/no-pin flows
untouched.

## What shipped

With exactly one finder pin (either direction) on `TradesScreen`:

1. **Featured trade window leads** (`FeaturedTradeWindow`, new): the
   best-signed-difference idea across all three groups renders as a full
   read-only `TradeCard` — give LEFT / receive RIGHT (#209), #190 "Edit in
   calculator" kept — with the **Dynasty Value Swing** verdict block. That
   block is the shipped `TradeValueBar` verbatim (it already renders the
   "Dynasty value swing" label, the winner headline, the margin-in-picks line
   and the diverging −1st…+1st track); nothing was rebuilt. Header row is the
   tick-label **"Featured trade"** — no player name (v3 call).
2. **Back chip (Variant A):** "‹ Previous trade" on its own slim row above
   the header, rendered only while history exists. The chip is part of the
   window pattern — the host passes `onBack` whenever its history stack is
   non-empty, so ANY future swap-in surface gets the revert affordance for
   free. History: full per-pin-session stack (not 1-level), capped at 10
   (`FEATURED_HISTORY_CAP`), reset on pin change and on a fresh sweep
   (`dataUpdatedAt` — a new payload invalidates old idea references).
3. **Idea list visible by default** below the window: `AssetIdeasPanel`
   reworked to the "More trades for &lt;pin&gt;" list (Upgrade / Lateral /
   Downgrade groups, #198 position-locked headers kept). Rows are tappable
   (chevron-right, pressed = surface shift per Chalkline, ≥48pt targets) and
   load their trade into the window; the replaced trade becomes the back
   target and the viewport scrolls the window back into view
   (`mainScrollRef`). The in-window row shows an ice-bordered **IN WINDOW**
   tag, loses its chevron and is tap-inert. Rows keep the signed diff chip
   and **drop the raw `give ↔ receive` value pair** (v2 tenet note).
4. **#209 column order:** verified give-left/receive-right in the featured
   card (TradeCard's existing YOU SEND | YOU GET order), and **fixed the
   player-mode pin board's reversed columns** — TRADE AWAY now renders LEFT,
   TRADE FOR RIGHT (v1 mock finding; testIDs unchanged), so board, card and
   rows all read give→get.
5. **Deck flow untouched:** Find a Trade, job polling, pins→generate payload,
   the deck itself, and the deck-header region (left clean for the
   `OutlookBiasReceipt` mount landing in a sibling change) are unchanged.

## Data plumbing (backend touched)

`TradeValueBar` needs `favors` + `gap` (pick-denominated); asset ideas didn't
carry them. `POST /api/trades/asset-ideas` `_idea_row` (backend/server.py) now
stamps both per idea via the existing `_value_verdict_payload` single source
(same construction as `/api/trade/evaluate` and deck cards — the three
surfaces cannot drift; `even` ⇔ the idea's `fairness` ≥ 0.95, evaluate's own
ratio test). Mobile normalizer validates defensively — an old server omits the
fields and the window simply hides the swing block.

## Files

- `backend/server.py` — `_idea_row` favors/gap stamp
- `backend/tests/test_asset_ideas.py` — `test_route_ideas_carry_value_verdict`
- `mobile/src/api/trades.ts` — `AssetIdea.favors/gap` + normalization
- `mobile/src/components/FeaturedTradeWindow.tsx` — NEW (window + Variant A
  back chip + `assetIdeaKey` export)
- `mobile/src/components/TradeCard.tsx` — optional `hideMatchStrength` (no
  honest-looking 0% bar for consensus ideas; only surgical change)
- `mobile/src/components/AssetIdeasPanel.tsx` — list rework (tappable rows,
  IN WINDOW tag, diff-chip-only meta)
- `mobile/src/screens/TradesScreen.tsx` — featured/history state + handlers,
  mount swap, #209 board column swap
- Docs: `docs/api-reference.md`, `mobile/src/components/CLAUDE.md` (rows +
  testID tranche), `mobile/src/screens/CLAUDE.md`

## testIDs

`featured-trade.window` · `featured-trade.back` ·
`featured-trade.idea.<assetIdeaKey>` (stable domain key
`<counterparty_user_id>.<give_ids>-<receive_ids>`, never a list index);
`trades.asset-ideas` retained on the panel container; `trades.board.*` ids
unchanged by the column swap.

## Verification

- `cd mobile && npx tsc --noEmit` — clean
- `python3 -m pytest backend/tests/ -q` — 1381 passed, 1 skipped (baseline)
- `backend/tests/test_asset_ideas.py` — 18 passed (incl. the new verdict test)
