# Deck player-changer — counter-suggestions as swap suggestions on find-a-trade cards

- **Source:** operator decision in `docs/business/product/2026-07-26-dynastydealer-dtf-teardowns.md`: counter suggestions "loved; shipped as calculator eveners … ALSO to serve as the 'player changer' on find-a-trade deck cards → follow-up after the asset-ideas build lands." Reuses the calc-eveners backend (`docs/feedback/items/2026-07-26-calc-eveners/status.md`).
- **Status:** BUILT 2026-07-27 (branch `teardown-remediation`, isolated worktree). Not flag-gated (calc-eveners precedent): additive server param + client surfaces that degrade to their honest empty state on old servers.

## Affordance (and why)

**Long-press context-menu row** on any asset of the top deck card: "Swap suggestions" (`ux.player_context_menu` is ON in prod; the menu is the S3 standard command surface where "Swap player" already lives, so the suggestion variant sits directly above it). Chosen over another per-row icon button because the give-side rightSlot already stacks OTB/UNTOUCHABLE badges + lock + swap (+ the new #194 remove ✕) — a fourth button would overflow the split-column width. Row testID `trade-card.swap-suggest.<asset_id>` (via the new optional `PlayerMenuAction.testID` seam; rows without it keep `player-menu.<key>`). Trade-off, documented: with `ux.player_context_menu` OFF the entry point is hidden (the classic #86 swap icon remains).

## Flow

1. Menu row → `openSwapSuggestions` → `SwapSuggestSheet` opens; ONE Mode B `POST /api/trade/evaluate` fires for the card's trade **minus that asset** (league_id + opponent_user_id from the card; `useQuery` keyed on trade_id + asset + side, 60s staleTime).
2. The response's `eveners` (≤3 players/owned picks + at most one 2-piece package) render as one-tap replacements — but only when the shortfall is on the removed asset's side (`gap.add_to === side`; a one-sided read counts when the removed asset was its side's only one). The removed asset itself is filtered out client-side (it's no longer "in the trade" in the request, so the server would return it as its own best replacement). Rows: `trade-card.swap-option.<id>`.
3. Picking swaps it in via the shared `applyPackageEdit` machinery (#86 swap's clear-values → EDITED overlay → Mode B re-price → value bar refills). Package rows swap in BOTH pieces; pieces resolve metadata from the consensus values pool, unresolvable pieces are owned picks (name from the row's "A + B" order, position/team `PICK` matching the backend's pick pseudo-players; the re-price resolves owned pick ids via `league_id`, #158).
4. Honest states: spinner while pricing, plain error copy, and an empty state ("No close-value replacements for this swap — swapping here would tip the trade") — never padded. Every state carries a "Browse full roster" escape hatch into the classic #86 `SwapPlayerSheet` for the same asset.

## Backend — thin additive param (unavoidable)

The dominant card shape is 1-for-1: "trade minus the asset" empties a side, and the existing eveners block only fires on an uneven TWO-sided read (`favors`≠even, `gap.add_to` set) — so pure client reuse returns nothing exactly where the feature matters most. Added `one_sided_eveners: true` (Mode B only) to `POST /api/trade/evaluate`: when exactly one side is empty, `_roster_eveners` runs for the EMPTY side's owner, window sized against the other side's full package value (same 0.4×–1.5×/cap-3/closest-first/untouchable rules — zero new evener math). Param absent → byte-identical responses (one-sided reads carry no eveners, as before); inert in Mode A and on two-sided reads, so the calculator's `EvenerRows` never see it.

## Files

- `backend/server.py` — `trade_evaluate_route`: `one_sided_eveners` elif + docstring.
- `backend/tests/test_trade_evaluate.py` — 5 new tests (below).
- `mobile/src/api/calc.ts` — `evaluateForSwapSuggestions` (Mode B + the param).
- `mobile/src/components/SwapSuggestSheet.tsx` — NEW sheet (Chalkline bottom-sheet construction, Reduce Motion fade).
- `mobile/src/components/PlayerContextMenu.tsx` — additive optional `PlayerMenuAction.testID`.
- `mobile/src/screens/TradesScreen.tsx` — `suggestTarget` state + minus-asset query + `swapSuggestions` gating memo + `handleSuggestPick` + menu row + sheet mount; cleared on every deck reset alongside `swapTarget`.
- Events: `trade_swap_suggest_opened {side}`, `trade_swap_suggestion_picked {side, asset_kind: player|pick|package}`.

## Verification

- `python3 -m pytest backend/tests -q` → **1341 passed, 1 skipped** (baseline before change: 1336 passed, 1 skipped). New tests:
  - `test_mode_b_one_sided_eveners_opt_in_for_emptied_give_side`
  - `test_mode_b_one_sided_eveners_from_opponent_for_emptied_receive_side`
  - `test_mode_b_one_sided_eveners_absent_without_param`
  - `test_mode_b_one_sided_eveners_param_ignored_on_two_sided_read`
  - `test_mode_a_one_sided_eveners_param_is_mode_b_only`
- `cd mobile && npx tsc --noEmit` → clean.

## Notes / follow-ups

- If `ux.player_context_menu` is ever retired rather than folded in, the swap-suggest entry point needs a new home (candidate: fold into the #86 swap sheet as its "Suggested" section).
- Demo league: same degradation as calc eveners (no picks; roster eveners only if demo `league_members` rows exist) → honest empty state.
