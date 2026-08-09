import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { TickLabel } from './chalkline';
import InLeagueCalculator from './InLeagueCalculator';
import { chalk, fonts, ice, ink, radii, space, type } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import type { TradeCard } from '../shared/types';

// #270 — inline trades home, experiment `trades_home_inline` variant
// `canvas` (mockups/polish-lab-2026-08/trades-home-inline.html frames B1
// empty / B2 populated). "The page IS a manual-calc canvas" — this mounts
// the SAME `InLeagueCalculator` the pushed Trade Calculator screen already
// uses in "In league" mode (real rosters, TradeSide rows with tier badges,
// evener rows, lineup impact, Send-in-Sleeper, share) wholesale, not a
// re-skinned subset — reuse, not reinvention, per the lab's own note ("same
// component, same `tierOf` tier-badge treatment").
//
// Suggestion rail: the SAME deck the guided landing already generates
// (`TradeCard[]`, passed in as `suggestions`) rendered as a horizontal strip
// of compact cards; tapping one prefills the canvas. `InLeagueCalculator`
// documents that it "owns all state after mount" (initial* props are read
// once) — so loading a suggestion re-mounts a fresh instance via a bumped
// `key`, the same prefill technique the app already uses for the deck's
// "Edit in calculator" hand-off (TradeCalculatorScreen's route-param
// prefill).
//
// Deliberate scope bound (see docs/feedback/items/270-inline-trades-home/
// status.md): this canvas renders ABOVE the existing swipe deck rather than
// replacing it — the deck stays fully reachable below, unmodified. The lab's
// own "Con" for a full replacement flagged the loss of the deck's
// zero-effort discovery loop (the app's core PFO surface) as a real
// regression; keeping the deck intact avoids that risk while still
// delivering the literal ask — hand-built add/remove trading directly on
// the page — and still uses the deck's cards to feed the rail.

interface Props {
  leagueId: string;
  userId: string;
  /** The #269 sheet-scoped opponent, if one is chosen — prefills the canvas
   *  so a two-column build starts with a counterparty already picked.
   *  `null` lets `InLeagueCalculator` render its own opponent chooser. */
  opponentUserId: string | null;
  /** The guided deck's current cards — feeds the suggestion rail. */
  suggestions: TradeCard[];
}

function summarizeSwap(card: TradeCard): string {
  const give = card.give_players[0]?.name ?? 'Asset';
  const giveMore = card.give_players.length > 1 ? ` +${card.give_players.length - 1}` : '';
  const get = card.receive_players[0]?.name ?? 'Asset';
  const getMore = card.receive_players.length > 1 ? ` +${card.receive_players.length - 1}` : '';
  return `${give}${giveMore} → ${get}${getMore}`;
}

export default function TradeBuildCanvas({
  leagueId,
  userId,
  opponentUserId,
  suggestions,
}: Props) {
  // Bumped whenever a suggestion is tapped, forcing InLeagueCalculator to
  // remount with fresh `initial*` props (see file header).
  const [canvasKey, setCanvasKey] = useState(0);
  const [prefill, setPrefill] = useState<{
    opponentId: string;
    give: string[];
    receive: string[];
  } | null>(null);

  const effectiveOpponentId = prefill?.opponentId ?? opponentUserId ?? undefined;

  function loadSuggestion(card: TradeCard) {
    haptics.selection();
    setPrefill({
      opponentId: card.opponent_user_id,
      give: card.give_player_ids,
      receive: card.receive_player_ids,
    });
    setCanvasKey((k) => k + 1);
  }

  return (
    <View style={styles.wrap} testID="trades.build-canvas">
      <TickLabel>Build a trade</TickLabel>
      <InLeagueCalculator
        key={`${canvasKey}-${effectiveOpponentId ?? 'none'}`}
        leagueId={leagueId}
        userId={userId}
        initialOpponentId={effectiveOpponentId}
        initialGiveIds={prefill?.give}
        initialReceiveIds={prefill?.receive}
      />

      {suggestions.length > 0 ? (
        <>
          <TickLabel>Or tap a suggestion to load it</TickLabel>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.suggestRow}
          >
            {suggestions.slice(0, 10).map((card) => (
              <Pressable
                key={card.trade_id}
                testID={`trades.build-canvas.suggestion.${card.trade_id}`}
                accessibilityRole="button"
                accessibilityLabel={`Load suggested trade with @${card.opponent_username}: ${summarizeSwap(card)}`}
                onPress={() => loadSuggestion(card)}
                style={({ pressed }) => [
                  styles.suggestCard,
                  pressed && styles.suggestCardPressed,
                ]}
              >
                <Text style={styles.suggestWho} numberOfLines={1}>
                  @{card.opponent_username}
                </Text>
                <Text style={styles.suggestSwap} numberOfLines={2}>
                  {summarizeSwap(card)}
                </Text>
                {card.gap?.pick_equivalent ? (
                  <Text style={styles.suggestTag} numberOfLines={1}>
                    {card.gap.pick_equivalent.label}
                  </Text>
                ) : null}
                <Text style={styles.suggestTap}>Tap to load</Text>
              </Pressable>
            ))}
          </ScrollView>
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm, marginBottom: space.md },
  suggestRow: { gap: space.sm, paddingBottom: space.xs },
  suggestCard: {
    width: 150,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    backgroundColor: ink.ink1,
    padding: space.sm,
    gap: 4,
  },
  suggestCardPressed: { backgroundColor: ink.ink3 },
  suggestWho: { ...type.bodySm, color: chalk.dim },
  suggestSwap: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  suggestTag: { fontSize: 10, color: chalk.dim },
  suggestTap: {
    fontSize: 9.5,
    color: ice.base,
    fontFamily: fonts.uiSemi,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
});
