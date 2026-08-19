import React, { useEffect, useMemo, useState } from 'react';
import { View, StyleSheet, ScrollView, ActivityIndicator, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';

import { ink, chalk, space, type } from '../theme/chalkline';
import { Text, TickLabel } from '../components/chalkline';
import EndorsedTradeCard from '../components/presentation/EndorsedTradeCard';
import FeaturedBench from '../components/presentation/FeaturedBench';
import HonestEmptyState from '../components/presentation/HonestEmptyState';
import { type DeclineReasonPanelProps } from '../components/DeclineReasonPanel';
import usePresentationDeck from '../hooks/usePresentationDeck';
import usePresentationSignals from '../hooks/usePresentationSignals';
import { useFlag } from '../state/useFeatureFlags';
import { useSession } from '../state/useSession';
import {
  usePresentationDismissed,
  dismissedSet,
} from '../state/presentationDismissed';
import {
  partitionDeck,
  confidenceBand,
  confidenceCap,
  emptyStateCopy,
} from '../utils/tradePresentation';
import type { TradeCard } from '../shared/types';

// TodaysTradeScreen — the presentation-v2 landing (flag
// `trades.presentation_v2`). Route `TodaysTrade` in the Acquire (`Trades`)
// stack. Approved lab: mockups/trade-suggestion-redesign/ states 01 (hero),
// 03 (Featured tier), 04 (confidence bands + data-volume cap) and 07 (honest
// empty state).
//
// ══ THIS SCREEN IS PURELY ADDITIVE ═══════════════════════════════════════
// It does not touch, wrap, or reconfigure TradesScreen. The existing deck
// keeps its own generate call, its own state and its own behaviour in both
// flag states; the only edit anywhere near it is one optional prop passed to
// the mode strip, which is what creates the entry chip. Flag off ⇒ nothing
// here is reachable.
//
// ══ THE PYRAMID ═══════════════════════════════════════════════════════════
// One endorsed hero -> a small Featured tier -> an UNCAPPED browse list
// (TradeBrowseAllScreen). Scarcity is the endorsement, not the catalog:
// only a `strong` card may wear the badge, and when none does we render the
// honest empty state rather than promoting a moderate card into an
// endorsement it has not earned.
//
// ══ INSTRUMENTATION ═══════════════════════════════════════════════════════
// Every disposition rides `usePresentationSignals`, which reuses the deck's
// own `swipeTrade` + `postDeclineReason` + event names. See that hook's
// header for why parity is enforced by reuse rather than re-implementation.

export default function TodaysTradeScreen() {
  const navigation = useNavigation<any>();
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id ?? null;
  const declineReasonsOn = useFlag('feedback.decline_reasons');

  const deck = usePresentationDeck(leagueId);
  const signals = usePresentationSignals();

  const byLeague = usePresentationDismissed((s) => s.byLeague);
  const dismiss = usePresentationDismissed((s) => s.dismiss);
  const dismissed = useMemo(() => dismissedSet(byLeague, leagueId), [byLeague, leagueId]);

  // "Keep my price" acknowledges the empty state without changing anything —
  // a first-class choice, so it must visibly do something (collapse the
  // pivot) rather than silently no-op.
  const [pricePinned, setPricePinned] = useState(false);

  const { hero, featured, total } = useMemo(
    () => partitionDeck(deck.cards, dismissed),
    [deck.cards, dismissed],
  );

  // Front-of-view accounting: the hero IS the fronted card. A new hero
  // (post-dismiss, or a fresh deck) restarts dwell and re-arms the >=500ms
  // `deck_card_viewed` outcome, exactly as fronting a new top card does on
  // the deck.
  useEffect(() => {
    signals.onCardFronted(hero);
  }, [hero?.trade_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const band = hero ? confidenceBand(hero) : null;
  const cap = band ? confidenceCap(band, deck.progress) : null;

  function handleInterested() {
    if (!hero) return;
    signals.dispatch(hero, 'like');
    // The like is recorded; the mutual-match inbox is where a reciprocated
    // like surfaces, so send the user there rather than inventing a receipt.
    navigation?.navigate?.('Matches');
  }

  function handlePass() {
    if (!hero || !leagueId) return;
    signals.dispatch(hero, 'pass');
    dismiss(leagueId, hero.trade_id);
  }

  // Decline-reason wiring — the SAME progressive contract as the deck: the
  // layer-1 tile commits the pass AND the reason in one gesture, layer 2 adds
  // the detail, "Other" banks before the composer opens. Built only when the
  // flag is on, so flag-off renders the plain ✓/✕ pair.
  const reasons: DeclineReasonPanelProps | undefined =
    declineReasonsOn && hero
      ? {
          onLayer1: (reason, switchedFrom) => {
            signals.reasonLayer1(hero, reason, switchedFrom);
            // Only the FIRST tile tap carries the disposition; a switch is a
            // refinement, not a second pass.
            if (switchedFrom === 'none' && leagueId && !dismissed.has(hero.trade_id)) {
              signals.dispatch(hero, 'pass');
              dismiss(leagueId, hero.trade_id);
            }
          },
          onLayer2Select: (reason, detail) => signals.reasonLayer2Select(hero, reason, detail),
          onLayer2Bank: (reason, detail) => signals.reasonLayer2Bank(hero, reason, detail),
          onLayer2Send: (reason, detail, freeText) =>
            signals.reasonLayer2Send(hero, reason, detail, freeText),
        }
      : undefined;

  function openIdea(card: TradeCard) {
    signals.markDetailExpanded();
    navigation?.navigate?.('TradeBrowseAll', { focus: card.trade_id });
  }

  const empty = emptyStateCopy({
    rostersChecked: deck.rostersChecked,
    fairnessThreshold: deck.fairnessThreshold,
    suppressedCount: deck.suppressedCount,
  });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
        automaticallyAdjustKeyboardInsets
        refreshControl={
          <RefreshControl refreshing={false} onRefresh={deck.refresh} tintColor={chalk.dim} />
        }
      >
        <View style={styles.headRow}>
          <TickLabel>Trades</TickLabel>
          {deck.streaming ? (
            <Text scale="dense" style={styles.note}>
              still checking rosters…
            </Text>
          ) : null}
        </View>

        {!leagueId ? (
          <Text variant="bodySm">Pick a league to see today's trade.</Text>
        ) : deck.loading ? (
          <View style={styles.center} testID="presentation.loading">
            <ActivityIndicator color={chalk.dim} />
            <Text variant="bodySm">Reading all rosters against your board…</Text>
          </View>
        ) : deck.error ? (
          <View style={styles.center} testID="presentation.error">
            <Text variant="bodySm">{deck.error}</Text>
          </View>
        ) : hero ? (
          <>
            <EndorsedTradeCard
              card={hero}
              cap={cap}
              onInterested={handleInterested}
              onPass={reasons ? undefined : handlePass}
              reasons={reasons}
              onRankMore={() => navigation?.navigate?.('Rank')}
            />
            <FeaturedBench
              cards={featured}
              total={total}
              onOpen={openIdea}
              onBrowseAll={() => navigation?.navigate?.('TradeBrowseAll')}
            />
          </>
        ) : pricePinned ? (
          // "Keep my price" collapses the pivot but never hides the exit to
          // the full list — discovery stays open even when endorsement does not.
          <View style={styles.center} testID="presentation.price-kept">
            <Text variant="bodySm">
              Holding your price. We'll check again next cycle.
            </Text>
            {total > 0 ? (
              <FeaturedBench
                cards={featured}
                total={total}
                onOpen={openIdea}
                onBrowseAll={() => navigation?.navigate?.('TradeBrowseAll')}
              />
            ) : null}
          </View>
        ) : (
          <>
            <HonestEmptyState
              copy={empty}
              onReviewBoard={() => navigation?.navigate?.('Rank')}
              onWidenFairness={() => navigation?.navigate?.('TradesHome', { mode: 'guided' })}
              onKeepPrice={() => setPricePinned(true)}
            />
            {/* Even with nothing endorsed, the ranked list stays reachable:
                scarcity governs the endorsement, never discovery. */}
            {total > 0 ? (
              <FeaturedBench
                cards={featured}
                total={total}
                onOpen={openIdea}
                onBrowseAll={() => navigation?.navigate?.('TradeBrowseAll')}
              />
            ) : null}
          </>
        )}
      </ScrollView>
      {/* Tab-stack screen: RootNav's single global FAB already covers it, so
          this screen mounts NONE of its own (#196/#197 double-FAB bug). */}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  body: { padding: space.lg, gap: space.md, paddingBottom: space.xxxl },
  headRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  note: { ...type.data, fontSize: 11, lineHeight: 14, color: chalk.faint },
  center: { alignItems: 'center', gap: space.md, paddingVertical: space.xl },
});
