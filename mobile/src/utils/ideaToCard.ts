import type { AssetIdea } from '../api/trades';
import type { TradeCard } from '../shared/types';

// An `AssetIdea` (the consensus-basis idea shape served by
// POST /api/trades/asset-ideas and POST /api/trades/fair-packages) rendered as
// the shipped `TradeCard`.
//
// EXTRACTED from `components/FeaturedTradeWindow.tsx` on 2026-08-22 (#384
// W6-B) because a SECOND surface now needs it: the fair-package deck sets
// `TradesScreen`'s deck straight from `ideas.map(ideaToCard)`, and a
// presentation helper living inside a component is a helper the deck has to
// import a component to use.
//
// **Zero runtime imports on purpose** (the `feedbackBadge.ts` / `applyJobResult.ts`
// convention): both imports above are type-only and erase at compile, so
// `mobile/tests/check-calc-merged-behavior.js` can transpile this file and
// EXECUTE it under plain node. The one property that actually matters — that a
// card built from an idea carries everything `_reconstruct_swipe_card` needs —
// is then proven by running it, not by matching its source text.

/** Stable identity for an idea within one sweep — counterparty + exact
 *  package. Used for the "In window" tag, history de-dupe and testIDs (domain
 *  ids, never list indexes, per the testID grammar).
 *  `components/FeaturedTradeWindow.tsx` re-exports this so its existing
 *  importers are untouched. */
export function assetIdeaKey(idea: AssetIdea): string {
  return `${idea.counterparty_user_id}.${idea.give_player_ids.join('_')}-${idea.receive_player_ids.join('_')}`;
}

/**
 * `AssetIdea` → the `TradeCard` shape. Presentation-only for an asset idea;
 * for a FAIR PACKAGE it is also the swipe payload's source, which is why the
 * fields below are not optional decoration:
 *
 *   • `trade_id` — the server's own deterministic `fairpk_…` when the idea
 *     carries one, else the legacy `asset-idea:<key>` synthetic. The server id
 *     is what makes a swipe idempotent: `/api/trades/swipe`, `/api/trades/queue`
 *     and `/api/trades/flag` all reconstruct an unknown card from the echoed
 *     context (FB-46 `_reconstruct_swipe_card`), and the id is the row key they
 *     reconstruct it UNDER.
 *   • `give_player_ids` / `receive_player_ids` / `opponent_user_id` — exactly
 *     the three fields that reconstruction needs. `api/trades.ts` echoes them
 *     as `give_player_ids` / `receive_player_ids` / `target_user_id`.
 *   • `basis` — carried through only when the idea declares one. Asset ideas
 *     do not (the featured window's approved mock shows no consensus note), so
 *     that path stays byte-identical; fair packages do, and their cards
 *     correctly show the consensus caveat.
 *
 * `match_score` is 0 because no divergence score exists for a consensus idea —
 * read-only mounts pass `hideMatchStrength`.
 */
export function ideaToCard(idea: AssetIdea, leagueId: string): TradeCard {
  return {
    trade_id: idea.trade_id || `asset-idea:${assetIdeaKey(idea)}`,
    league_id: leagueId,
    give_players: idea.give,
    receive_players: idea.receive,
    give_player_ids: idea.give_player_ids,
    receive_player_ids: idea.receive_player_ids,
    opponent_user_id: idea.counterparty_user_id,
    opponent_username: idea.counterparty_username,
    match_score: 0,
    fairness: idea.fairness,
    give_value: idea.give_value,
    receive_value: idea.receive_value,
    favors: idea.favors,
    gap: idea.gap,
    ...(idea.basis ? { basis: idea.basis } : {}),
  };
}

export default ideaToCard;
