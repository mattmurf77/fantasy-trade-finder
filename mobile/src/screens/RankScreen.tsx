import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import AsyncStorage from '@react-native-async-storage/async-storage';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSequence,
  runOnJS,
  Easing,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { useNavigation } from '@react-navigation/native';
import { haptics } from '../utils/haptics';
import { startSpan } from '../observability/sentry';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PlayerCard from '../components/PlayerCard';
import Toast from '../components/Toast';
import {
  getNextTrio,
  getProgress,
  getStreak,
  submitTrioRanking,
} from '../api/rankings';
import type { Position, Trio } from '../shared/types';
import { useFlag } from '../state/useFeatureFlags';

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];
const THRESHOLD_FALLBACK = 10;
const SPEED_MODE_KEY = 'ftf.trios.speedMode';

export default function RankScreen() {
  const queryClient = useQueryClient();
  const navigation  = useNavigation();
  const [position, setPosition] = useState<Position>('QB');
  const [selectionOrder, setSelectionOrder] = useState<('a' | 'b' | 'c')[]>([]);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' } | null>(null);
  const [infoSheet, setInfoSheet] = useState<{ name: string; info: string } | null>(null);
  // I AM SPEED — when ON we auto-rank the 3rd choice + auto-submit after the
  // user picks 2. Default OFF (manual confirm). Persisted to AsyncStorage so
  // the toggle survives app restarts. Mirrors web/js/app.js's autoConfirmEnabled.
  const [speedMode, setSpeedMode] = useState(false);
  useEffect(() => {
    AsyncStorage.getItem(SPEED_MODE_KEY).then((v) => {
      if (v === '1') setSpeedMode(true);
    });
  }, []);
  const toggleSpeedMode = useCallback(() => {
    setSpeedMode((prev) => {
      const next = !prev;
      void AsyncStorage.setItem(SPEED_MODE_KEY, next ? '1' : '0');
      haptics.selection();
      return next;
    });
  }, []);

  const qcEnabled      = useFlag('swipe.qc_compliments');
  const gestureEnabled = useFlag('swipe.gesture_audit');

  // ── Data ────────────────────────────────────────────────────────────
  const trioQuery = useQuery({
    queryKey: ['trio', position],
    queryFn: () => getNextTrio(position),
    staleTime: 0,           // each trio is fresh; never reuse
    refetchOnMount: 'always',
  });

  const progressQuery = useQuery({
    queryKey: ['progress'],
    queryFn: getProgress,
    staleTime: 15_000,
  });

  const streakQuery = useQuery({
    queryKey: ['streak'],
    queryFn: getStreak,
    staleTime: 60_000,
  });

  const submitMutation = useMutation({
    // Wrap the network call in a Sentry span so we can see p50/p95
    // latency of trio submits in production. Span is a no-op when
    // Sentry isn't initialized.
    mutationFn: (rankedIds: [string, string, string]) =>
      startSpan({ name: 'trio.submit', op: 'mutation' }, () =>
        submitTrioRanking(rankedIds),
      ),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      queryClient.invalidateQueries({ queryKey: ['trio', position] });
      setSelectionOrder([]);
      // Detect streak increment from inline response — compare to the
      // currently-cached value before writing through. If the new value
      // jumped, celebrate. (Same-day re-ranks are a no-op server-side, so
      // current stays equal — no false positive.)
      const prev = streakQuery.data?.current ?? 0;
      const next = resp.streak?.current ?? 0;
      if (next > prev && next >= 2) {
        setToast({ msg: `🔥 ${next}-day streak!`, tone: 'success' });
        haptics.success();
      }
      if (resp.streak) {
        queryClient.setQueryData(['streak'], resp.streak);
      }
    },
  });

  // Skip = "show me a different trio" — DOES NOT permanently remove
  // any player from the user's eligible pool. Aligned with the web
  // client (PR #13, agent #20). Backend /api/trio/skip endpoint is
  // intentionally left in place since older clients may still call it,
  // but we no longer wire it up from this screen.
  const isRefetchingTrio = trioQuery.isFetching && !trioQuery.isLoading;
  const skipTrio = useCallback(() => {
    setSelectionOrder([]);
    queryClient.invalidateQueries({ queryKey: ['trio', position] });
  }, [queryClient, position]);

  // ── Helpers ─────────────────────────────────────────────────────────
  const trio = trioQuery.data;
  const progress = progressQuery.data;

  const rankOf = useCallback(
    (side: 'a' | 'b' | 'c'): 1 | 2 | 3 | null => {
      const idx = selectionOrder.indexOf(side);
      return idx === -1 ? null : ((idx + 1) as 1 | 2 | 3);
    },
    [selectionOrder],
  );

  const playerForSide = (t: Trio, side: 'a' | 'b' | 'c') =>
    side === 'a' ? t.player_a : side === 'b' ? t.player_b : t.player_c;

  // Submit the current selection — runs the QC celebration check then mutates.
  // Pulled out of the effect so it can be called from the Confirm button too.
  const submitCurrent = useCallback(
    (orderToSubmit: ('a' | 'b' | 'c')[]) => {
      if (orderToSubmit.length !== 3 || !trio || submitMutation.isPending) return;
      const rankedIds = orderToSubmit.map(
        (s) => playerForSide(trio, s).id,
      ) as [string, string, string];

      if (
        qcEnabled &&
        trio.is_qc_trio &&
        Array.isArray(trio.qc_expected_order) &&
        trio.qc_expected_order.length === 3 &&
        rankedIds.every((id, i) => id === trio.qc_expected_order![i])
      ) {
        setToast({ msg: '✓ Nice call — you helped verify the rankings!', tone: 'success' });
        haptics.success();
      }
      submitMutation.mutate(rankedIds);
    },
    [trio, submitMutation, qcEnabled],
  );

  // Rank a card. Tapping an already-ranked card removes it (and anything
  // ranked after it), matching the web app's behavior in selectCard().
  const rankSide = useCallback(
    (side: 'a' | 'b' | 'c') => {
      setSelectionOrder((prev) => {
        const existing = prev.indexOf(side);
        if (existing !== -1) {
          // Undo this card + all later ranks
          return prev.slice(0, existing);
        }
        if (prev.length >= 3) return prev;
        const next = [...prev, side];

        // I AM SPEED: after the user picks 2, auto-rank the 3rd (the only
        // remaining card) and submit immediately. Mirrors the web's
        // autoConfirmEnabled branch in selectCard().
        if (speedMode && next.length === 2 && trio) {
          const sides: ('a' | 'b' | 'c')[] = ['a', 'b', 'c'];
          const last = sides.find((s) => !next.includes(s));
          if (last) {
            const final = [...next, last] as ('a' | 'b' | 'c')[];
            // Defer the submit so React commits the visible rank-3 badge
            // before the trio rotates to the next one.
            setTimeout(() => submitCurrent(final), 0);
            return final;
          }
        }
        return next;
      });
      haptics.selection();
    },
    [speedMode, trio, submitCurrent],
  );

  const handleSkipEntireTrio = () => {
    // Refetch a new trio without removing any player. Matches web's
    // post-PR-#13 Skip semantics — Skip is now ephemeral.
    if (!trio) return;
    skipTrio();
  };

  // Open an info sheet for a player. Only exposed when the gesture-audit
  // flag is on; long-press is the trigger so it doesn't collide with tap.
  const showInfoSheet = (side: 'a' | 'b' | 'c') => {
    if (!gestureEnabled || !trio) return;
    const p = playerForSide(trio, side);
    const lines: string[] = [];
    if (p.team)             lines.push(`Team: ${p.team}`);
    if (p.position)         lines.push(`Position: ${p.position}`);
    if (p.age != null)      lines.push(`Age: ${p.age}`);
    if (p.years_experience != null) lines.push(`Experience: ${p.years_experience} yr${p.years_experience === 1 ? '' : 's'}`);
    if (p.injury_status)    lines.push(`Injury: ${p.injury_status}`);
    if (p.adp != null)      lines.push(`ADP: ${p.adp}`);
    setInfoSheet({ name: p.name, info: lines.join('\n') || 'No extra info on file.' });
  };

  const currentProgressForPos = progress?.[position] ?? 0;
  const threshold = progress?.threshold ?? THRESHOLD_FALLBACK;
  const isUnlockedEverywhere = progress?.unlocked ?? false;

  // ── Render ──────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        {/* Streak chip — only shown once the user has an active streak.
            Tap → jump to the League tab where leaderboards live. */}
        {(streakQuery.data?.current ?? 0) > 0 ? (
          <View style={styles.streakRow}>
            <Pressable
              onPress={() => {
                haptics.selection();
                // RankScreen is the inner screen of RankStack which is
                // hosted by the Tab navigator — getParent() returns the
                // tab nav directly. Cast because @react-navigation's
                // generic `navigate` doesn't know our route names here.
                (navigation.getParent() as any)?.navigate('League');
              }}
              style={({ pressed }) => [styles.streakChip, pressed && { opacity: 0.7 }]}
            >
              <Text style={styles.streakFlame}>🔥</Text>
              <Text style={styles.streakNum}>{streakQuery.data!.current}</Text>
              <Text style={styles.streakLabel}>day streak</Text>
              <Text style={styles.streakArrow}>›</Text>
            </Pressable>
          </View>
        ) : null}

        {/* Position switcher */}
        <View style={styles.switcher}>
          {POSITIONS.map((p) => {
            const isActive = p === position;
            const count = progress?.[p] ?? 0;
            return (
              <Pressable
                key={p}
                onPress={() => {
                  if (p === position) return;
                  setSelectionOrder([]);
                  setPosition(p);
                }}
                style={({ pressed }) => [
                  styles.switcherBtn,
                  isActive && styles.switcherBtnActive,
                  pressed && styles.switcherBtnPressed,
                ]}
              >
                <Text
                  style={[
                    styles.switcherText,
                    isActive && styles.switcherTextActive,
                  ]}
                >
                  {p}
                </Text>
                <Text
                  style={[
                    styles.switcherCount,
                    isActive && styles.switcherCountActive,
                  ]}
                >
                  {Math.min(count, threshold)}/{threshold}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {/* Progress bar for the active position */}
        <View style={styles.progressWrap}>
          <View style={styles.progressTrack}>
            <View
              style={[
                styles.progressFill,
                {
                  width: `${Math.min(100, (currentProgressForPos / threshold) * 100)}%`,
                  backgroundColor: currentProgressForPos >= threshold ? colors.green : colors.accent,
                },
              ]}
            />
          </View>
          <Text style={styles.progressText}>
            {currentProgressForPos >= threshold
              ? `${position} rankings established ✓`
              : `${currentProgressForPos} of ${threshold} ${position}s ranked`}
          </Text>
        </View>

        {/* Instruction */}
        <Text style={styles.instruction}>
          {submitMutation.isPending
            ? '✓ Submitting…'
            : selectionOrder.length === 0
            ? 'Tap in order of preference — best first'
            : selectionOrder.length === 1
            ? 'Good — now tap your 2nd choice'
            : selectionOrder.length === 2
            ? speedMode
              ? '⚡ Speed mode — releasing now'
              : 'Last one — tap your 3rd choice'
            : speedMode
            ? '✓ Submitting…'
            : '✓ All ranked — confirm when ready'}
        </Text>

        {/* Cards */}
        {trioQuery.isLoading || !trio ? (
          <View style={styles.centered}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : trioQuery.isError ? (
          <View style={styles.centered}>
            <Text style={styles.errorText}>
              {trioQuery.error instanceof Error
                ? trioQuery.error.message
                : 'Could not load next trio'}
            </Text>
            <Pressable onPress={() => trioQuery.refetch()}>
              <Text style={styles.retryText}>Try again</Text>
            </Pressable>
          </View>
        ) : (
          <View style={styles.cards}>
            {(['a', 'b', 'c'] as const).map((side) => (
              <SwipePlayerCard
                key={`${trio.player_a.id}-${side}`}
                trio={trio}
                side={side}
                rank={rankOf(side)}
                onTap={() => rankSide(side)}
                onLongPress={() => showInfoSheet(side)}
                onSwipeSkip={handleSkipEntireTrio}
                onSwipeRankFirst={() => {
                  setSelectionOrder(() => [side]);
                  haptics.selection();
                }}
                disabled={submitMutation.isPending || isRefetchingTrio}
              />
            ))}
          </View>
        )}

        {/* I AM SPEED toggle — sits ABOVE the secondary action row per spec */}
        <Pressable
          onPress={toggleSpeedMode}
          style={({ pressed }) => [
            styles.speedTile,
            speedMode && styles.speedTileOn,
            pressed && { opacity: 0.85 },
          ]}
        >
          <Text style={[styles.speedTileText, speedMode && styles.speedTileTextOn]}>
            {speedMode ? '⚡ I AM SPEED — ON' : '⚡ I AM SPEED — OFF'}
          </Text>
          <Text style={styles.speedTileCaption}>
            {speedMode
              ? 'Pick your top 2 — we auto-rank the 3rd and save.'
              : 'Tap all 3, then tap Confirm to save.'}
          </Text>
        </Pressable>

        {/* Confirm button — appears only after the user has ranked all 3
            cards (in manual mode). Pre-3 we say nothing here; the
            instruction line above the cards already coaches the user. */}
        {!speedMode && selectionOrder.length === 3 && (
          <Pressable
            onPress={() => submitCurrent(selectionOrder)}
            disabled={!trio || submitMutation.isPending}
            style={({ pressed }) => [
              styles.confirmBtn,
              styles.confirmBtnReady,
              pressed && { opacity: 0.85 },
              submitMutation.isPending && { opacity: 0.45 },
            ]}
          >
            {submitMutation.isPending ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.confirmBtnText}>Confirm ranking →</Text>
            )}
          </Pressable>
        )}

        {/* Bottom action — single Skip button. "I don't know" was removed
            in alignment with the web client (PR #13, agent #20). Skip is
            now ephemeral: refetches a different trio without persistently
            removing any player from the eligible pool. */}
        <View style={styles.actions}>
          <Pressable
            onPress={handleSkipEntireTrio}
            disabled={!trio || isRefetchingTrio}
            style={({ pressed }) => [
              styles.secondaryBtn,
              pressed && { opacity: 0.6 },
              (!trio || isRefetchingTrio) && { opacity: 0.4 },
            ]}
          >
            <Text style={styles.secondaryBtnText}>Skip ↩</Text>
          </Pressable>
        </View>

        {isUnlockedEverywhere && (
          <View style={styles.unlockedBanner}>
            <Text style={styles.unlockedText}>
              🔓 Trade Finder unlocked — check the Trades tab
            </Text>
          </View>
        )}
      </ScrollView>

      {/* Long-press info sheet, gesture-audit flag */}
      {infoSheet && (
        <View style={styles.infoOverlay}>
          <Pressable style={styles.infoBackdrop} onPress={() => setInfoSheet(null)} />
          <View style={styles.infoSheet}>
            <Text style={styles.infoTitle}>{infoSheet.name}</Text>
            <Text style={styles.infoBody}>{infoSheet.info}</Text>
            <Pressable onPress={() => setInfoSheet(null)}>
              <Text style={styles.infoClose}>Close</Text>
            </Pressable>
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

// ── SwipePlayerCard — Reanimated wrapper around PlayerCard ─────────
interface SwipeProps {
  trio: Trio;
  side: 'a' | 'b' | 'c';
  rank: 1 | 2 | 3 | null;
  onTap: () => void;
  onLongPress?: () => void;
  onSwipeSkip: () => void;
  onSwipeRankFirst: () => void;
  disabled?: boolean;
}

const SCREEN_W = Dimensions.get('window').width;
const SWIPE_THRESHOLD = 120;

function SwipePlayerCard({
  trio,
  side,
  rank,
  onTap,
  onLongPress,
  onSwipeSkip,
  onSwipeRankFirst,
  disabled,
}: SwipeProps) {
  const translateX = useSharedValue(0);
  const player = side === 'a' ? trio.player_a : side === 'b' ? trio.player_b : trio.player_c;

  // Swipe gesture: horizontal pan with threshold dismisses in one of two
  // directions. Vertical motion aborts the swipe (so the ScrollView keeps
  // its normal scroll feel).
  const pan = useMemo(
    () =>
      Gesture.Pan()
        .minDistance(10)
        .activeOffsetX([-20, 20])
        .failOffsetY([-30, 30])
        .enabled(!disabled)
        .onUpdate((e) => {
          translateX.value = e.translationX;
        })
        .onEnd((e) => {
          const dx = e.translationX;
          if (dx < -SWIPE_THRESHOLD) {
            // Swipe-left = skip the trio
            translateX.value = withTiming(-SCREEN_W, { duration: 180 }, (finished) => {
              if (finished) runOnJS(onSwipeSkip)();
              translateX.value = 0;
            });
          } else if (dx > SWIPE_THRESHOLD) {
            // Swipe-right = rank as #1
            translateX.value = withSequence(
              withTiming(SCREEN_W * 0.35, {
                duration: 140,
                easing: Easing.out(Easing.cubic),
              }),
              withTiming(0, { duration: 180 }),
            );
            runOnJS(onSwipeRankFirst)();
          } else {
            translateX.value = withTiming(0, { duration: 160 });
          }
        }),
    [disabled, onSwipeSkip, onSwipeRankFirst, translateX],
  );

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { rotate: `${translateX.value / 30}deg` },
    ],
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={animatedStyle}>
        <PlayerCard
          player={player}
          rank={rank}
          selected={rank !== null}
          onPress={onTap}
          onLongPress={onLongPress}
          disabled={disabled}
        />
      </Animated.View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
  },
  streakRow: { alignItems: 'center' },
  streakChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: 'rgba(255,140,40,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(255,140,40,0.35)',
  },
  streakFlame: { fontSize: fontSize.base },
  streakNum: { color: '#ffb27a', fontSize: fontSize.base, fontWeight: '800' },
  streakLabel: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '600' },
  streakArrow: { color: colors.muted, fontSize: fontSize.base, marginLeft: 2 },
  switcher: {
    flexDirection: 'row',
    gap: spacing.xs,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 4,
  },
  switcherBtn: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
  },
  switcherBtnActive: { backgroundColor: 'rgba(79,124,255,0.14)' },
  switcherBtnPressed: { opacity: 0.7 },
  switcherText: { color: colors.muted, fontSize: fontSize.base, fontWeight: '700' },
  switcherTextActive: { color: colors.accent },
  switcherCount: { color: colors.muted, fontSize: fontSize.xs, marginTop: 2 },
  switcherCountActive: { color: colors.accent },

  progressWrap: { gap: 6 },
  progressTrack: {
    height: 6,
    backgroundColor: colors.border,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: radius.pill,
  },
  progressText: { color: colors.muted, fontSize: fontSize.xs, textAlign: 'center' },

  instruction: {
    color: colors.text,
    fontSize: fontSize.base,
    textAlign: 'center',
    fontWeight: '600',
    paddingVertical: spacing.sm,
  },
  cards: { gap: spacing.md },
  centered: {
    paddingVertical: spacing.xxl,
    alignItems: 'center',
    gap: spacing.md,
  },
  errorText: { color: colors.red, fontSize: fontSize.sm, textAlign: 'center' },
  retryText: { color: colors.accent, fontSize: fontSize.sm, fontWeight: '700' },

  speedTile: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.lg,
    alignItems: 'center',
    gap: 4,
  },
  speedTileOn: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.10)',
  },
  speedTileText: {
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  speedTileTextOn: { color: colors.accent },
  speedTileCaption: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
  },
  confirmBtn: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 48,
    marginTop: spacing.sm,
  },
  confirmBtnReady: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  confirmBtnText: { color: '#fff', fontSize: fontSize.base, fontWeight: '800' },

  actions: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.lg,
  },
  secondaryBtn: {
    flex: 1,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 44, // thumb-friendly
  },
  secondaryBtnText: { color: colors.text, fontSize: fontSize.sm, fontWeight: '600' },

  unlockedBanner: {
    marginTop: spacing.lg,
    padding: spacing.md,
    backgroundColor: 'rgba(34,197,94,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(34,197,94,0.35)',
    borderRadius: radius.md,
    alignItems: 'center',
  },
  unlockedText: { color: colors.green, fontWeight: '700', fontSize: fontSize.sm },

  infoOverlay: {
    position: 'absolute',
    inset: 0 as any,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 40,
    justifyContent: 'flex-end',
  },
  infoBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  infoSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.xl,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  infoTitle: { color: colors.text, fontSize: fontSize.xl, fontWeight: '800' },
  infoBody: {
    color: colors.muted,
    fontSize: fontSize.sm,
    lineHeight: 22,
  },
  infoClose: {
    color: colors.accent,
    fontSize: fontSize.base,
    fontWeight: '700',
    textAlign: 'center',
    paddingTop: spacing.lg,
  },
});
