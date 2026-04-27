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
import * as Haptics from 'expo-haptics';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import TradeCardComp from '../components/TradeCard';
import Toast from '../components/Toast';
import FairnessSlider from '../components/FairnessSlider';
import OutlookSheet from '../components/OutlookSheet';
import LeaguePill from '../components/LeaguePill';
import LeagueSwitcherSheet from '../components/LeagueSwitcherSheet';
import {
  generateTrades,
  getTradeStatus,
  swipeTrade,
  getLikedTrades,
} from '../api/trades';
import {
  getLeaguePreferences,
  saveLeaguePreferences,
  type Outlook,
} from '../api/league';
import { useSession } from '../state/useSession';
import type { TradeCard, TradeJobSnapshot } from '../shared/types';

const SCREEN_W = Dimensions.get('window').width;
const SWIPE_THRESHOLD = 120;

export default function TradesScreen() {
  const queryClient = useQueryClient();
  const league = useSession((s) => s.league);
  const switching = useSession((s) => s.switching);
  const leagueId = league?.league_id || null;
  const [fairness, setFairness] = useState(0.75);
  const [deck, setDeck] = useState<TradeCard[]>([]);
  const [deckIdx, setDeckIdx] = useState(0);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  const [outlookOpen, setOutlookOpen] = useState(false);
  const [switcherOpen, setSwitcherOpen] = useState(false);

  // Preferences — open outlook sheet the first time the user lands here
  // without an outlook set.
  const prefsQuery = useQuery({
    queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId!),
    enabled: !!leagueId,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (prefsQuery.data && !prefsQuery.data.team_outlook) {
      setOutlookOpen(true);
    }
  }, [prefsQuery.data]);

  // ── Find-a-Trade: streaming job snapshot ─────────────────────────────
  // The backend runs generation in a background thread and we poll for
  // results. The job snapshot drives both the deck (cards stream in) and
  // the progress strip ("4/11 opponents searched").
  const [job, setJob] = useState<TradeJobSnapshot | null>(null);

  const generateMutation = useMutation({
    mutationFn: () =>
      generateTrades({
        league_id: leagueId!,
        fairness_threshold: fairness,
      }),
    onSuccess: (snapshot) => {
      setJob(snapshot);
      // For instant cache-hit responses (status === 'complete') the deck
      // populates immediately via the snapshot effect below. For 'running'
      // responses the polling effect takes over.
      if (snapshot.status === 'complete' && snapshot.cards.length === 0) {
        setToast({ msg: 'No fair trades found. Try lowering the fairness bar.', tone: 'warn' });
      }
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Generate failed', tone: 'warn' });
    },
  });

  // Poll while a job is running. 1500ms cadence matches the backend's
  // per-opponent budget (one opponent done every ~3s → ~2 polls per
  // increment). Cleared when status flips to complete/error or the
  // component unmounts.
  //
  // Failure handling: a single network blip is fine, but a backend that
  // 500s for an extended period would otherwise leave the user staring
  // at "Searching…" forever. After MAX_POLL_FAILURES consecutive errors
  // we surface a toast and clear the local job so the UI returns to its
  // pre-tap state. The server-side worker keeps running so the next tap
  // can hit the warm cache.
  useEffect(() => {
    if (!job || job.status !== 'running' || !job.job_id) return;
    let cancelled = false;
    let failures = 0;
    const MAX_POLL_FAILURES = 4;
    const tick = async () => {
      try {
        const next = await getTradeStatus(job.job_id);
        if (cancelled) return;
        failures = 0;
        setJob(next);
      } catch {
        if (cancelled) return;
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          setToast({
            msg: 'Network hiccup — try Find a Trade again in a moment',
            tone: 'warn',
          });
          setJob(null);
        }
      }
    };
    const id = setInterval(tick, 1500);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [job?.job_id, job?.status]);

  // Deck maintenance: append new cards as the snapshot grows, dedup by
  // trade_id so re-rendering doesn't duplicate. Don't reset the index —
  // the user may already be swiping on early cards.
  //
  // Deps: depend on cards.length, not the cards array reference. Each
  // poll returns a fresh array even when content didn't change; using
  // the array ref triggers a no-op re-render every 1.5s. The length is
  // monotonically increasing during a job so any actual growth fires
  // the effect; we still re-evaluate setDeck inside which dedups by
  // trade_id, so the rare "same length, different content" case (e.g.
  // backend resorts after the last opponent) gets the latest snapshot.
  useEffect(() => {
    if (!job) return;
    setDeck((prev) => {
      const seen = new Set(prev.map((c) => c.trade_id));
      const fresh = job.cards.filter((c) => !seen.has(c.trade_id));
      return fresh.length === 0 ? prev : [...prev, ...fresh];
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.cards.length, job?.status]);

  // When the user picks a different fairness slider position or switches
  // leagues, drop the local deck/job so the next "Find a Trade" tap kicks
  // off a fresh job instead of streaming into stale state.
  useEffect(() => {
    setDeck([]);
    setDeckIdx(0);
    setJob(null);
  }, [leagueId]);

  const swipeMutation = useMutation({
    mutationFn: ({ tradeId, decision }: { tradeId: string; decision: 'like' | 'pass' }) =>
      swipeTrade(tradeId, decision),
    onSuccess: (_, vars) => {
      if (vars.decision === 'like') {
        // Liked-trades count is per-league (backend filters by session). Use a
        // league-scoped key so switching leagues doesn't show a stale count.
        queryClient.invalidateQueries({ queryKey: ['liked-trades', leagueId] });
      }
    },
  });

  const likedQuery = useQuery({
    queryKey: ['liked-trades', leagueId],
    queryFn: getLikedTrades,
    enabled: !!leagueId,
    staleTime: 30_000,
  });

  const topCard = deck[deckIdx];
  const nextCard = deck[deckIdx + 1];

  function advance(decision: 'like' | 'pass') {
    if (!topCard) return;
    swipeMutation.mutate({ tradeId: topCard.trade_id, decision });
    setDeckIdx((i) => i + 1);
    if (decision === 'like') {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setToast({ msg: 'Liked ✓', tone: 'success' });
    } else {
      void Haptics.selectionAsync();
    }
  }

  async function handleOutlookSubmit(
    outlook: NonNullable<Outlook>,
    acquire: string[],
    away: string[],
  ) {
    if (!leagueId) return;
    await saveLeaguePreferences(leagueId, {
      team_outlook: outlook,
      acquire_positions: acquire,
      trade_away_positions: away,
    });
    queryClient.invalidateQueries({ queryKey: ['league-prefs', leagueId] });
    setToast({ msg: 'Outlook saved', tone: 'success' });
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <OutlookSheet
        visible={outlookOpen}
        initial={prefsQuery.data?.team_outlook}
        onClose={() => setOutlookOpen(false)}
        onSubmit={handleOutlookSubmit}
      />

      <LeagueSwitcherSheet
        visible={switcherOpen}
        onClose={() => setSwitcherOpen(false)}
        // No onSwitched callback — the [leagueId] useEffect above already
        // resets deck/job state when zustand's league slice changes, and
        // league-prefs refetches automatically via its query key.
      />

      {/* Full-screen overlay while a league swap is in flight. sessionInit
          can take 5–10s on Render's free tier; without this the user can
          still tap controls and trigger requests against the wrong league. */}
      {switching ? (
        <View style={styles.switchingOverlay} pointerEvents="auto">
          <ActivityIndicator color={colors.accent} size="large" />
          <Text style={styles.switchingText}>Switching league…</Text>
        </View>
      ) : null}

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        scrollEnabled={!topCard || !generateMutation.isPending}
      >
        {/* League selector pill — opens LeagueSwitcherSheet on tap. */}
        <LeaguePill
          label="Trading in"
          onPress={() => setSwitcherOpen(true)}
        />

        <View style={styles.controlCard}>
          <View style={styles.controlRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.controlLabel}>Outlook</Text>
              <Text style={styles.controlValue}>
                {prefsQuery.data?.team_outlook
                  ? cap(prefsQuery.data.team_outlook)
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

          {/* Find-a-Trade button. While a job is running, the button is
              disabled — the progress strip below acts as the live signal.
              `generateMutation.isPending` is only true during the brief
              POST round-trip; after that, status flows through `job`. */}
          <Pressable
            disabled={!leagueId || generateMutation.isPending || job?.status === 'running'}
            onPress={() => generateMutation.mutate()}
            style={({ pressed }) => [
              styles.findBtn,
              pressed && { opacity: 0.85 },
              (!leagueId || generateMutation.isPending || job?.status === 'running') && { opacity: 0.5 },
            ]}
          >
            {generateMutation.isPending ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.findBtnText}>
                {deck.length > 0 && job?.status === 'complete' ? '✨ Find more trades' : '✨ Find a Trade'}
              </Text>
            )}
          </Pressable>

          {/* Progress strip — visible only during a running job. Cards are
              streaming into the deck above; this just narrates the work. */}
          {job?.status === 'running' && (
            <View style={styles.progressStrip}>
              <View style={styles.progressInfo}>
                <ActivityIndicator color={colors.accent} size="small" />
                <Text style={styles.progressText}>
                  Searching… {job.opponents_done}/{job.opponents_total || '?'} opponents
                  {job.cards.length > 0 ? `  ·  ${job.cards.length} trade${job.cards.length === 1 ? '' : 's'}` : ''}
                </Text>
              </View>
              {/* "Hide", not "Stop": the server-side worker keeps running
                  so its results land in the warm cache for the next tap.
                  We just dismiss the in-progress UI on the client. */}
              <Pressable
                onPress={() => setJob(null)}
                style={({ pressed }) => [styles.stopBtn, pressed && { opacity: 0.6 }]}
                hitSlop={8}
              >
                <Text style={styles.stopBtnText}>Hide</Text>
              </Pressable>
            </View>
          )}

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
          ) : generateMutation.isPending || job?.status === 'running' ? (
            // Job is running but no cards have arrived yet (first ~3s of
            // the first opponent). Show a placeholder so the deck doesn't
            // look broken — the progress strip above narrates state.
            <View style={styles.emptyCard}>
              <ActivityIndicator color={colors.accent} />
              <Text style={[styles.emptyTitle, { marginTop: spacing.sm }]}>
                Looking for trades…
              </Text>
              <Text style={styles.emptyBody}>
                Cards will appear here as they're found. First few should land within a few seconds.
              </Text>
            </View>
          ) : deck.length > 0 ? (
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
  switchingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(15,17,23,0.85)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    zIndex: 50,
  },
  switchingText: {
    color: colors.text,
    fontSize: fontSize.base,
    fontWeight: '700',
  },
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
  progressStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: 'rgba(79,124,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(79,124,255,0.25)',
  },
  progressInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flex: 1,
    minWidth: 0,
  },
  progressText: {
    color: colors.accent,
    fontSize: fontSize.xs,
    fontWeight: '700',
    flexShrink: 1,
  },
  stopBtn: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  stopBtnText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
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
