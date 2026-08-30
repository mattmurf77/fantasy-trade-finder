import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { TickLabel } from './chalkline';
import InLeagueCalculator from './InLeagueCalculator';
import { chalk, fonts, ice, ink, radii, space, type } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import type { CalcPlayer } from '../data/calcTypes';
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

// D-158 (Wave B0) — a SECOND host. With `calc.inline_home` on, `TradesScreen`
// mounts this canvas as the guided landing's layout rather than as the #270
// experiment variant, and two things change, both prop-driven so the
// experiment path is byte-identical:
//
//   1. `showSuggestionRail={false}` — the deck below IS the rail there, and a
//      horizontal strip of the same cards above it is duplication, not
//      discovery (plan §3b, "Suggestion rail: dies").
//   2. The #384 handlers (`onFindATrade`, `onLikeTrade`) are threaded through
//      to `InLeagueCalculator`, which is what turns the canvas from a
//      read-only build surface into the page's primary action. `onShowMeAround`
//      is deliberately NOT passed by the flag path: beat n10 points at the
//      In-league tab this wave deletes, so the tour is off until Wave B
//      retargets it.
//
// The prefill pair (`prefill` + `prefillSeq`) is the same remount-on-prefill
// technique this file already used for the rail, exposed to the host: the
// deck's "edit in calculator" actions load the inline canvas in place instead
// of pushing `TradeCalculator`. A SEQ, not the object, is the trigger — the
// same package can legitimately be loaded twice (edit → clear → edit again)
// and value equality would swallow the second load.

export interface CanvasPrefill {
  opponentId?: string;
  give: string[];
  receive: string[];
  /** FB-406 R-10 — true ONLY on the #402 browse-session SEEDING effect's
   *  write (the one prefill that is not a user choice); forwarded to
   *  `InLeagueCalculator` as `seededPrefill` so a seeded partner never
   *  counts as chosen. Tap/handoff prefills and the blank/anchor restores
   *  leave it unset. */
  seeded?: boolean;
}

interface Props {
  leagueId: string;
  userId: string;
  /** The #269 sheet-scoped opponent, if one is chosen — prefills the canvas
   *  so a two-column build starts with a counterparty already picked.
   *  `null` lets `InLeagueCalculator` render its own opponent chooser. */
  opponentUserId: string | null;
  /** The guided deck's current cards — feeds the suggestion rail. */
  suggestions: TradeCard[];
  /** #270's horizontal tap-to-load strip. Defaults to TRUE — today's
   *  behavior, so the experiment variant is untouched. */
  showSuggestionRail?: boolean;
  /** D-158 — the canvas's primary action. Absent ⇒ `InLeagueCalculator`
   *  renders no Find a Trade button (the host owns what a search does). */
  onFindATrade?: (opts: {
    give: CalcPlayer[];
    receive: CalcPlayer[];
    opponent: { userId: string; name: string } | null;
  }) => void;
  /** D-152 — the action row's ✓ cell. Absent ⇒ the cell renders disabled. */
  onLikeTrade?: (args: {
    giveIds: string[];
    receiveIds: string[];
    opponent: { userId: string; name: string };
  }) => void | Promise<void>;
  /** D-158 — a host-driven prefill (the deck's edit-in-calculator paths).
   *  Adopted only when `prefillSeq` changes. */
  prefill?: CanvasPrefill | null;
  prefillSeq?: number;
  /** #402 canvas-results — pass-through to `InLeagueCalculator` (see its
   *  Props comment): fired when either side's ids change after mount, so
   *  the browse-session host can snapshot per-idea edits. Absent (the #270
   *  experiment path and every pre-#402 mount) ⇒ byte-identical. */
  onSidesChange?: (give: string[], receive: string[]) => void;
  /** #410 — pass-through to `InLeagueCalculator`: the host's browse state.
   *  Non-null makes the action row's middle cell the decline ✕; absent/null
   *  (every pre-#410 mount, and the kill switch) leaves it the Clear cell,
   *  byte-identical. Threaded, never derived here. */
  browseDecline?: { onPress: () => void } | null;
  /** #412 — pass-through to `InLeagueCalculator`: content for the GIVE
   *  column, under its "Add player" button. Absent ⇒ byte-identical. */
  giveBelowAdd?: React.ReactNode;
  /** #402 QA A-D5 — pass-through to `InLeagueCalculator`: while the host's
   *  browse session shows an idea, the partner is that idea's counterparty
   *  and stays fixed (spec §3), so the partner Change/Team control renders
   *  dimmed and inert. Defaults to false — every pre-#402 mount (and the
   *  #270 experiment path) is byte-identical. */
  partnerLocked?: boolean;
  /** T-3 (merged-view trim, ruling 2026-08-28) — pass-through to
   *  `InLeagueCalculator`: the flag path passes true and the merged header
   *  drops its scoring-format chips + #191 conversion note (the pushed page
   *  keeps them). Defaults to false so the #270 experiment path is
   *  byte-identical. */
  hideFormatChips?: boolean;
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
  showSuggestionRail = true,
  onFindATrade,
  onLikeTrade,
  prefill: hostPrefill,
  prefillSeq,
  onSidesChange,
  browseDecline,
  giveBelowAdd,
  partnerLocked = false,
  hideFormatChips = false,
}: Props) {
  // Bumped whenever a suggestion is tapped (or the host pushes a prefill),
  // forcing InLeagueCalculator to remount with fresh `initial*` props (see
  // file header).
  const [canvasKey, setCanvasKey] = useState(0);
  const [prefill, setPrefill] = useState<CanvasPrefill | null>(null);

  // D-158 — adopt a host prefill on every SEQ change. Absent `prefillSeq`
  // (the #270 experiment path) ⇒ this effect runs once with `undefined` and
  // does nothing, so that path is unchanged.
  useEffect(() => {
    if (prefillSeq === undefined || !hostPrefill) return;
    setPrefill(hostPrefill);
    setCanvasKey((k) => k + 1);
    // Only the seq may trigger a load — see the file header.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillSeq]);

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
        onFindATrade={onFindATrade}
        onLikeTrade={onLikeTrade}
        onSidesChange={onSidesChange}
        browseDecline={browseDecline}
        giveBelowAdd={giveBelowAdd}
        partnerLocked={partnerLocked}
        seededPrefill={!!prefill?.seeded}
        hideFormatChips={hideFormatChips}
      />

      {showSuggestionRail && suggestions.length > 0 ? (
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
