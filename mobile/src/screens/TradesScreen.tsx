import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  ScrollView,
  Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
  Easing,
} from 'react-native-reanimated';
import { haptics } from '../utils/haptics';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import TradeCardComp from '../components/TradeCard';
import Toast from '../components/Toast';
import FairnessSlider from '../components/FairnessSlider';
import OutlookSheet from '../components/OutlookSheet';
import {
  generateTrades,
  swipeTrade,
  getLikedTrades,
} from '../api/trades';
import {
  getLeaguePreferences,
  saveLeaguePreferences,
  type Outlook,
} from '../api/league';
import { useSession } from '../state/useSession';
import type { TradeCard } from '../shared/types';

const SCREEN_W = Dimensions.get('window').width;
const SWIPE_THRESHOLD = 120;

export default function TradesScreen() {
  const queryClient = useQueryClient();
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  const [fairness, setFairness] = useState(0.75);
  const [deck, setDeck] = useState<TradeCard[]>([]);
  const [deckIdx, setDeckIdx] = useState(0);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  const [outlookOpen, setOutlookOpen] = useState(false);

  // Preferences — open outlook sheet the first time the user lands here
  // without an outlook set.
  const prefsQuery = useQuery({
    queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId!),
    enabled: !!leagueId,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (prefsQuery.data && !prefsQuery.data.outlook_value) {
      setOutlookOpen(true);
    }
  }, [prefsQuery.data]);

  // Find-a-Trade generation is user-initiated (same UX as web). Don't
  // pre-fetch or we'll blow up unnecessary generator work.
  const generateMutation = useMutation({
    mutationFn: () =>
      generateTrades({
        league_id: leagueId!,
        fairness_threshold: fairness,
      }),
    onSuccess: (res) => {
      const trades = res?.trades || [];
      setDeck(trades);
      setDeckIdx(0);
      if (trades.length === 0) {
        setToast({ msg: 'No fair trades found. Try lowering the fairness bar.', tone: 'warn' });
      }
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Generate failed', tone: 'warn' });
    },
  });

  const swipeMutation = useMutation({
    mutationFn: ({ tradeId, decision }: { tradeId: string; decision: 'like' | 'pass' }) =>
      swipeTrade(tradeId, decision),
    onSuccess: (_, vars) => {
      if (vars.decision === 'like') {
        queryClient.invalidateQueries({ queryKey: ['liked-trades'] });
      }
    },
  });

  const likedQuery = useQuery({
    queryKey: ['liked-trades'],
    queryFn: getLikedTrades,
    staleTime: 30_000,
  });

  const topCard = deck[deckIdx];
  const nextCard = deck[deckIdx + 1];

  function advance(decision: 'like' | 'pass') {
    if (!topCard) return;
    swipeMutation.mutate({ tradeId: topCard.trade_id, decision });
    setDeckIdx((i) => i + 1);
    if (decision === 'like') {
      haptics.success();
      setToast({ msg: 'Liked ✓', tone: 'success' });
    } else {
      haptics.swipe();
    }
  }

  async function handleOutlookSubmit(
    outlook: NonNullable<Outlook>,
    acquire: string[],
    away: string[],
  ) {
    if (!leagueId) return;
    await saveLeaguePreferences(leagueId, {
      outlook_value: outlook,
      acquire_positions: acquire,
      trade_away_positions: away,
    });
    queryClient.invalidateQueries({ queryKey: ['league-prefs', leagueId] });
    setToast({ msg: 'Outlook saved', tone: 'success' });
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <OutlookSheet
        visible={outlookOpen}
        initial={prefsQuery.data?.outlook_value}
        onClose={() => setOutlookOpen(false)}
        onSubmit={handleOutlookSubmit}
      />

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        scrollEnabled={!topCard || !generateMutation.isPending}
      >
        <View style={styles.controlCard}>
          <View style={styles.controlRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.controlLabel}>Outlook</Text>
              <Text style={styles.controlValue}>
                {prefsQuery.data?.outlook_value
                  ? cap(prefsQuery.data.outlook_value)
                  : 'Not set'}
              </Text>
            </View>
            <Pressable
              style={({ pressed }) => [styles.editBtn, pressed && { opacity: 0.7 }]}
              onPress={() => setOutlookOpen(true)}
            >
              <Text style={styles.editBtnText}>Edit</Text>
            </Pressable>
          </View>

          <FairnessSlider value={fairness} onChange={setFairness} />

          <Pressable
            disabled={!leagueId || generateMutation.isPending}
            onPress={() => generateMutation.mutate()}
            style={({ pressed }) => [
              styles.findBtn,
              pressed && { opacity: 0.85 },
              (!leagueId || generateMutation.isPending) && { opacity: 0.5 },
            ]}
          >
            {generateMutation.isPending ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.findBtnText}>✨ Find a Trade</Text>
            )}
          </Pressable>

          {likedQuery.data && likedQuery.data.liked_count > 0 && (
            <Text style={styles.likedCount}>
              ❤ {likedQuery.data.liked_count} liked trade
              {likedQuery.data.liked_count === 1 ? '' : 's'} awaiting their swipe
            </Text>
          )}
        </View>

        <View style={styles.deckWrap}>
          {topCard ? (
            <>
              {/* Peek of the next card behind the top one */}
              {nextCard && (
                <View style={[styles.cardStack, styles.cardBehind]}>
                  <TradeCardComp data={nextCard} />
                </View>
              )}
              <SwipableTopCard
                key={topCard.trade_id}
                card={topCard}
                onLike={() => advance('like')}
                onPass={() => advance('pass')}
              />
              <Text style={styles.deckHint}>
                Swipe right to like · Swipe left to pass
              </Text>
            </>
          ) : generateMutation.isPending ? null : deck.length > 0 ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>That's all for now ✓</Text>
              <Text style={styles.emptyBody}>
                You've swiped on every generated trade. Rank more players or
                invite leaguemates to unlock more.
              </Text>
            </View>
          ) : (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>Hit "Find a Trade" to start</Text>
              <Text style={styles.emptyBody}>
                We'll pull trade ideas from your league and show them one at a time.
              </Text>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── SwipableTopCard — Tinder-style gesture on the top card only ─────
interface SwipableProps {
  card: TradeCard;
  onLike: () => void;
  onPass: () => void;
}

function SwipableTopCard({ card, onLike, onPass }: SwipableProps) {
  const translateX = useSharedValue(0);

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .activeOffsetX([-12, 12])
        .failOffsetY([-30, 30])
        .onUpdate((e) => {
          translateX.value = e.translationX;
        })
        .onEnd((e) => {
          if (e.translationX > SWIPE_THRESHOLD && e.velocityX > 200) {
            translateX.value = withTiming(SCREEN_W * 1.5, { duration: 220, easing: Easing.out(Easing.cubic) }, () => {
              runOnJS(onLike)();
              translateX.value = 0;
            });
          } else if (e.translationX < -SWIPE_THRESHOLD && e.velocityX < -200) {
            translateX.value = withTiming(-SCREEN_W * 1.5, { duration: 220, easing: Easing.out(Easing.cubic) }, () => {
              runOnJS(onPass)();
              translateX.value = 0;
            });
          } else {
            translateX.value = withTiming(0, { duration: 180 });
          }
        }),
    [onLike, onPass, translateX],
  );

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { rotate: `${translateX.value / 20}deg` },
    ],
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={[styles.cardStack, animatedStyle]}>
        <TradeCardComp data={card} />
      </Animated.View>
    </GestureDetector>
  );
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ── Styles ──────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.lg, paddingBottom: 96 },
  controlCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  controlRow: { flexDirection: 'row', alignItems: 'center' },
  controlLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  controlValue: { color: colors.text, fontSize: fontSize.base, fontWeight: '800' },
  editBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  editBtnText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  findBtn: {
    backgroundColor: colors.accent,
    paddingVertical: 14,
    borderRadius: radius.md,
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  findBtnText: { color: '#fff', fontSize: fontSize.base, fontWeight: '800' },
  likedCount: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    marginTop: 4,
  },
  deckWrap: {
    minHeight: 360,
    position: 'relative',
  },
  cardStack: {
    width: '100%',
  },
  cardBehind: {
    position: 'absolute',
    top: 8,
    left: 0,
    right: 0,
    opacity: 0.55,
    transform: [{ scale: 0.97 }],
  },
  deckHint: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    marginTop: spacing.md,
  },
  emptyCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    gap: spacing.sm,
  },
  emptyTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  emptyBody: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    lineHeight: 22,
  },
});
