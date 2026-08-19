import React, { useCallback, useMemo, useState } from 'react';
import { View, StyleSheet, FlatList, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';

import { ink, chalk, space, radii, type } from '../theme/chalkline';
import { Text, TickLabel, Badge } from '../components/chalkline';
import TradeIdeaRow from '../components/presentation/TradeIdeaRow';
import EndorsedTradeCard from '../components/presentation/EndorsedTradeCard';
import usePresentationDeck from '../hooks/usePresentationDeck';
import usePresentationSignals from '../hooks/usePresentationSignals';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { type DeclineReasonPanelProps } from '../components/DeclineReasonPanel';
import {
  usePresentationDismissed,
  dismissedSet,
} from '../state/presentationDismissed';
import {
  partitionDeck,
  confidenceBand,
  confidenceCap,
  FEATURED_CAP,
} from '../utils/tradePresentation';
import type { TradeCard } from '../shared/types';

// TradeBrowseAllScreen — the UNCAPPED ranked list (flag
// `trades.presentation_v2`). Route `TradeBrowseAll` in the Acquire (`Trades`)
// stack. Approved lab: mockups/trade-suggestion-redesign/09-browse-all.html.
//
// ══ UNCAPPED IS A DELIBERATE DECISION, NOT AN OVERSIGHT ═══════════════════
// The hero and the Featured tier are scarce because choice overload at the
// top of the funnel produces a rejection mind-set. Discovery below them is
// NOT capped: every viewed and every dismissed card is ranking-training
// signal, and mining declines is the single highest-leverage input the engine
// programme has (IBM/ESPN: 76.9% -> 97.3%). Slicing this list would delete
// the data the whole thing runs on. Do not add a `.slice()` here.
//
// A dismissed row STAYS IN PLACE, dimmed, carrying its acknowledgement and an
// Undo. Removing it would both delete the visible proof that the model
// learned something and make the list jump under the reader's thumb.
//
// The list header pins the hero as rank 1 and separates the Featured band
// from the tail, so the ordering the landing implied is visible here too.

export default function TradeBrowseAllScreen({ route }: any) {
  const navigation = useNavigation<any>();
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id ?? null;
  const declineReasonsOn = useFlag('feedback.decline_reasons');

  const deck = usePresentationDeck(leagueId);
  const signals = usePresentationSignals('TradeBrowseAll');

  const byLeague = usePresentationDismissed((s) => s.byLeague);
  const dismiss = usePresentationDismissed((s) => s.dismiss);
  const restore = usePresentationDismissed((s) => s.restore);
  const dismissedIds = useMemo(() => dismissedSet(byLeague, leagueId), [byLeague, leagueId]);

  const { hero, all } = useMemo(
    () => partitionDeck(deck.cards, dismissedIds),
    [deck.cards, dismissedIds],
  );

  // Ordered so the hero is rank 1 wherever it sits in the raw deck; the rest
  // keep the server's mutual-fit ordering untouched.
  const ordered = useMemo(() => {
    if (!hero) return all;
    return [hero, ...all.filter((c) => c.trade_id !== hero.trade_id)];
  }, [all, hero]);

  const [focused, setFocused] = useState<TradeCard | null>(null);
  const focusId: string | undefined = route?.params?.focus;
  const focusCard = useMemo(
    () => focused ?? (focusId ? ordered.find((c) => c.trade_id === focusId) ?? null : null),
    [focused, focusId, ordered],
  );

  // A browse row only counts as VIEWED once the user opens it — a row title
  // scrolling past is not a look at the trade. Opening fronts the card, which
  // arms the same >=500ms `deck_card_viewed` outcome the deck uses.
  const openCard = useCallback(
    (card: TradeCard) => {
      setFocused(card);
      signals.onCardFronted(card);
    },
    [signals],
  );

  const handleDismiss = useCallback(
    (card: TradeCard) => {
      if (!leagueId) return;
      // The dismiss IS the pass — the same disposition the deck writes, with
      // the same signal fields when the card carried an impression_id.
      signals.dispatch(card, 'pass');
      dismiss(leagueId, card.trade_id);
      if (focused?.trade_id === card.trade_id) setFocused(null);
    },
    [leagueId, signals, dismiss, focused],
  );

  const handleUndo = useCallback(
    (card: TradeCard) => {
      if (!leagueId) return;
      // Local restore only. The server-side signal stands, and the copy never
      // claimed otherwise — "we'll rank ideas like this lower" remains true.
      restore(leagueId, card.trade_id);
    },
    [leagueId, restore],
  );

  const focusBand = focusCard ? confidenceBand(focusCard) : null;
  const focusCap = focusBand ? confidenceCap(focusBand, deck.progress) : null;

  const focusReasons: DeclineReasonPanelProps | undefined =
    declineReasonsOn && focusCard
      ? {
          onLayer1: (reason, switchedFrom) => {
            signals.reasonLayer1(focusCard, reason, switchedFrom);
            if (switchedFrom === 'none' && !dismissedIds.has(focusCard.trade_id)) {
              handleDismiss(focusCard);
            }
          },
          onLayer2Select: (reason, detail) =>
            signals.reasonLayer2Select(focusCard, reason, detail),
          onLayer2Bank: (reason, detail) => signals.reasonLayer2Bank(focusCard, reason, detail),
          onLayer2Send: (reason, detail, freeText) =>
            signals.reasonLayer2Send(focusCard, reason, detail, freeText),
        }
      : undefined;

  const header = (
    <View style={styles.header}>
      <View style={styles.headRow}>
        <TickLabel>All trades</TickLabel>
        <Text scale="dense" style={styles.count} testID="presentation.browse-count">
          {ordered.length} ideas
        </Text>
      </View>
      <Text variant="bodySm">
        Ranked by mutual fit — viewing and dismissing sharpens your board.
      </Text>

      {focusCard ? (
        <View style={styles.focus} testID="presentation.browse-focus">
          <EndorsedTradeCard
            card={focusCard}
            cap={focusCap}
            onInterested={() => {
              signals.dispatch(focusCard, 'like');
              navigation?.navigate?.('Matches');
            }}
            onPass={focusReasons ? undefined : () => handleDismiss(focusCard)}
            reasons={focusReasons}
            onRankMore={() => navigation?.navigate?.('Rank')}
          />
        </View>
      ) : null}
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {deck.loading ? (
        <View style={styles.center} testID="presentation.browse-loading">
          <ActivityIndicator color={chalk.dim} />
          <Text variant="bodySm">Reading all rosters against your board…</Text>
        </View>
      ) : (
        <FlatList
          testID="presentation.browse-list"
          data={ordered}
          keyExtractor={(c) => c.trade_id}
          ListHeaderComponent={header}
          contentContainerStyle={styles.body}
          refreshing={false}
          onRefresh={deck.refresh}
          ListEmptyComponent={
            <Text variant="bodySm" style={styles.empty}>
              No ideas in this cycle. Nothing is hidden — there simply isn't a
              package that clears the bar for both sides yet.
            </Text>
          }
          renderItem={({ item, index }) => (
            <>
              {/* Band separators mirror the landing's pyramid so the ordering
                  reads the same in both places. */}
              {index === 1 ? (
                <View style={styles.sep}>
                  <Badge label="Featured" color={ink.lineStrongA11y} />
                </View>
              ) : null}
              {index === FEATURED_CAP + 1 ? (
                <View style={styles.sep}>
                  <Badge label="All trades" />
                  <Text scale="dense" style={styles.sepNote}>
                    ranked by fit
                  </Text>
                </View>
              ) : null}
              <TradeIdeaRow
                card={item}
                rank={index + 1}
                hero={index === 0 && item.trade_id === hero?.trade_id}
                dismissed={dismissedIds.has(item.trade_id)}
                onOpen={openCard}
                onDismiss={handleDismiss}
                onUndo={handleUndo}
              />
            </>
          )}
        />
      )}
      {/* Root-stack pushes mount their own FAB; this is a TAB-stack screen, so
          RootNav's global mount covers it. Nothing to add here — see
          mobile/CLAUDE.md § FeedbackFAB. */}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  body: { padding: space.lg, paddingBottom: space.xxxl },
  header: { gap: space.xs, marginBottom: space.md },
  headRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  count: { ...type.data, fontSize: 11, lineHeight: 14, color: chalk.faint },
  focus: { marginTop: space.md },
  sep: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    backgroundColor: ink.ink2,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  sepNote: { ...type.bodySm, fontSize: 12, lineHeight: 16, color: chalk.faint },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.md },
  empty: { paddingVertical: space.xl, textAlign: 'center' },
});
