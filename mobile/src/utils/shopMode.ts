// #402/#403 — shop-a-player mode vocabulary (PRD R-3, lld-delta.md §0.3).
//
// The three user-facing shop modes mapped to the server's asset-ideas group
// keys (`POST /api/trades/asset-ideas` → groups.upgrade/lateral/downgrade).
// ONE exported constant so the mapping cannot drift between the mode chips
// and the pager's group read — all three values are string literals of the
// same union, so `tsc` cannot tell a swapped pair apart; the mapping is
// EXECUTED and asserted by `mobile/tests/check-shop-deck.js` instead.
//
// **Zero runtime imports on purpose** (the `ideaToCard.ts` convention): the
// check suite transpiles this file and runs it under plain node.

export type ShopMode = 'tier_up' | 'tier_down' | 'same_value';

/** Server group key for the asset-ideas response, per shop mode. */
export const SHOP_MODE_GROUP = {
  tier_up: 'upgrade',
  tier_down: 'downgrade',
  same_value: 'lateral',
} as const;

// NOTE — chip labels live in `ShopOffersBody.tsx`, NOT here: PRD R-13 reads
// the two tier labels from the shipped `TRADE_INTENT_LABEL` constant
// (TradeDnaSheet.tsx) so #402/#403 can never diverge from the DNA sheet's
// vocabulary, and that constant is a runtime import this file must not take.

/** Chip order — tier_up first; it is also the default mode on open. */
export const SHOP_MODES: readonly ShopMode[] = [
  'tier_up',
  'tier_down',
  'same_value',
] as const;
