import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { ink, ice, space, radii, type } from '../theme/chalkline';
import { Icon, TickLabel } from './chalkline';
import TradeCardComp from './TradeCard';
import InLeagueCalculator from './InLeagueCalculator';
import type { AssetIdea } from '../api/trades';
import type { TradeCard as TradeCardData } from '../shared/types';

// #216/#209 — the FEATURED TRADE window for single-pin find-a-trade
// (design source-of-truth: mockups/polish-lab-2026-08/asset-ideas-layout-v2
// + -v3, operator-approved: v2 layout with the v3 refinements — header is
// just "Featured trade" (no player name) and the back chip is Variant A,
// its own slim row ABOVE the header). The best idea leads as a full trade
// card with the Dynasty Value Swing verdict — the shipped TradeValueBar,
// rendered by the reused read-only TradeCard (give LEFT / receive RIGHT,
// #209), fed by the per-idea favors/gap the asset-ideas endpoint now
// serializes. Old servers omit favors/gap ⇒ the bar hides, nothing breaks.
//
// The back chip is part of the window PATTERN by default (operator call):
// ANY surface that swaps a trade into the window creates a back target —
// the host owns the history stack and simply passes `onBack` while history
// exists; the chip renders only then (no dead reserved space).

// Stable identity for an idea within one sweep — counterparty + exact
// package. Used for the "In window" tag, history de-dupe and testIDs
// (domain ids, never list indexes, per the testID grammar).
export function assetIdeaKey(idea: AssetIdea): string {
  return `${idea.counterparty_user_id}.${idea.give_player_ids.join('_')}-${idea.receive_player_ids.join('_')}`;
}

interface Props {
  idea: AssetIdea;
  leagueId: string;
  /** Renders the ‹ Previous trade chip (Variant A row) when set. */
  onBack?: () => void;
  /** #190 — the featured card keeps the calculator hand-off. Ignored when
   *  `calc` is set (the card already IS the calculator — no separate
   *  hand-off needed). */
  onEditInCalculator?: () => void;
  /** #287 (flag `trades.player_offers_calc`) — when set, renders the idea
   *  as an editable InLeagueCalculator (TradeBuildCanvas prefill
   *  technique: remounted per idea via its assetIdeaKey, with
   *  initialOpponentId/initialGiveIds/initialReceiveIds) instead of the
   *  read-only TradeCard. `userId` is required for the calculator's
   *  rosters query. Omitted (undefined) ⇒ byte-identical read-only path. */
  calc?: { userId: string };
}

// AssetIdea → the TradeCard shape, presentation-only (never persisted,
// never swiped). give/receive are already user-perspective for BOTH pin
// directions. match_score is 0 because no divergence score exists for a
// consensus idea — the card is mounted with hideMatchStrength. basis stays
// 'divergence' deliberately: the consensus-note copy ("hasn't ranked yet")
// isn't verified for idea counterparties, and the approved mock shows no
// note in the window.
function ideaToCard(idea: AssetIdea, leagueId: string): TradeCardData {
  return {
    trade_id: `asset-idea:${assetIdeaKey(idea)}`,
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
  };
}

export default function FeaturedTradeWindow({
  idea,
  leagueId,
  onBack,
  onEditInCalculator,
  calc,
}: Props) {
  return (
    <View testID="featured-trade.window" style={styles.wrap}>
      {/* Variant A — back chip on its own slim row ABOVE the header; the
          row exists only while there is history. */}
      {onBack ? (
        <View style={styles.backRow}>
          <Pressable
            testID="featured-trade.back"
            accessibilityRole="button"
            accessibilityLabel="Back to previous trade"
            onPress={onBack}
            style={({ pressed }) => [
              styles.backChip,
              pressed && styles.backChipPressed,
            ]}
          >
            <Icon name="chevron-left" size={12} color={ice.base} />
            <Text style={styles.backChipText}>Previous trade</Text>
          </Pressable>
        </View>
      ) : null}
      <TickLabel>Featured trade</TickLabel>
      {calc ? (
        // #287 — remount per idea (same TradeBuildCanvas prefill
        // technique): InLeagueCalculator "owns all state after mount", so
        // a new idea needs a fresh instance, not a prop update.
        <InLeagueCalculator
          key={assetIdeaKey(idea)}
          leagueId={leagueId}
          userId={calc.userId}
          initialOpponentId={idea.counterparty_user_id}
          initialGiveIds={idea.give_player_ids}
          initialReceiveIds={idea.receive_player_ids}
        />
      ) : (
        <TradeCardComp
          data={ideaToCard(idea, leagueId)}
          hideMatchStrength
          onEditInCalculator={onEditInCalculator}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.xs },
  backRow: { flexDirection: 'row' },
  backChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    minHeight: 28,
    paddingLeft: space.xs,
    paddingRight: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    backgroundColor: ink.ink2,
  },
  backChipPressed: { backgroundColor: ink.ink3 },
  backChipText: {
    ...type.bodySm,
    color: ice.base,
    fontFamily: type.title.fontFamily,
  },
});
