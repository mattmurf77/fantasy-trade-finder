# #194 — Remove the "rookie" tag from draft picks + remove an asset from a suggested trade

- **Source:** operator feedback #194 (verbatim): "Remove the 'rookie' tag from draft picks. Add the ability to remove an asset from a suggested trade."
- **Status:** BUILT 2026-07-27 (branch `teardown-remediation`, isolated worktree). Not flag-gated — same additive precedent as the calc-eveners item: a bug fix plus deck-only affordances that render exactly as before when the screen doesn't pass the new handler.

## a) Rookie tag on picks (bug)

`mobile/src/components/PlayerCard.tsx` — `isRookie` was `years_experience === 0`, which is true for PICK pseudo-assets (the backend serializes pick players with `years_experience: 0`, meaning "no experience", not "rookie season"). Fixed to `years_experience === 0 && String(position) !== 'PICK'`. One condition feeds all three renderings, so all are fixed together: the classic-card `RookieBadge`, the dense-branch `RK` micro-tag, and the composed accessibility label's `rookie` token. `RookieBadge` has no other data-driven consumer (only the static StyleGuide).

## b) Remove an asset from a suggested trade

- **Affordance:** per-asset 28px ✕ icon button (`trade-card.remove-asset.<asset_id>`) in each player row's rightSlot on the TOP deck card, beside the #86 swap affordance — both sides, swipe variant only (match cards and the behind-card peek never receive the handler). Also a "Remove from trade" row in the shared long-press context menu (`player-menu.remove-asset`) and a `remove` VoiceOver custom action on the row.
- **Min one per side:** the last asset on a side renders the ✕ dimmed (`accessibilityState.disabled`) but still tappable — the tap answers with the honest hint toast "A trade needs at least one asset on each side." instead of a silent no-op.
- **Reprice:** removal goes through the same edit machinery as the #86 swap — shared `applyPackageEdit` helper (extracted from `handleSwapPick`, byte-identical clearing semantics): edited card overlaid under `<rawId>::edited` with engine numbers cleared (value bar hides, "Re-pricing…" shows), then Mode B `/api/trade/evaluate` refills `give_value/receive_value/favors/gap`.
- **Compose with pinning (#174):** removing a give asset that is PINNED while "Trade as one package" (`pinned_give_mode:'all'`) is ON gets a small `Alert` confirm ("Break up the package?") — the removal breaks the whole-package request for this card; the pins themselves are left set (they're generation-time constraints for the next deck, which the copy says explicitly). All other removals are immediate.
- Event: `trade_asset_removed {side}`.

## Files

- `mobile/src/components/PlayerCard.tsx` — isRookie condition (badge + RK tag + a11y label).
- `mobile/src/components/TradeCard.tsx` — `onRemoveAsset` prop, `removeSlot` (✕ + disabled dim), a11y `remove` action, rightSlot wiring both sides, `removeBtnDisabled` style.
- `mobile/src/screens/TradesScreen.tsx` — `applyPackageEdit` (shared with swap + swap-suggestions), `handleRemoveAsset` (min-1 hint + pinned-package confirm), context-menu row, SwipableTopCard pass-through.

## Verification

- `cd mobile && npx tsc --noEmit` → clean.
- Backend untouched by this item (the reprice reuses the existing evaluate flow); suite green on the branch (`python3 -m pytest backend/tests -q` → 1341 passed, 1 skipped, incl. the sibling player-changer item's new tests).
