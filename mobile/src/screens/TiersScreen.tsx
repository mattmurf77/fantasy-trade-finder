import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  ScrollView,
  LayoutChangeEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PlayerCard from '../components/PlayerCard';
import TierBin from '../components/TierBin';
import Toast from '../components/Toast';
import {
  getRankings,
  saveTiers,
  getTiersStatus,
  dismissPlayer,
} from '../api/rankings';
import { autoBucket, TIERS } from '../utils/tierBands';
import type { Position, RankedPlayer, Tier, ScoringFormat } from '../shared/types';

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];

/** Which zone a card's center falls into at drag-end.  "unassigned" is
 *  a first-class zone — you can drag a player out of a tier back to the pool. */
type Zone = Tier | 'unassigned';

interface BinLayout {
  zone: Zone;
  // Absolute-to-screen Y bounds; we key drop zones on vertical overlap
  // only (the screen is single-column within the ScrollView).
  y: number;
  height: number;
}

export default function TiersScreen() {
  const queryClient = useQueryClient();
  const [position, setPosition] = useState<Position>('QB');
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // tiers[position] = { elite: [player...], starter: [...], ..., unassigned: [...] }
  const [buckets, setBuckets] = useState<Record<Zone, RankedPlayer[]>>(() => emptyBuckets());

  // ── Data ────────────────────────────────────────────────────────────
  const rankingsQuery = useQuery({
    queryKey: ['rankings', position],
    queryFn: () => getRankings(position),
    staleTime: 30_000,
  });

  const tiersStatusQuery = useQuery({
    queryKey: ['tiers-status'],
    queryFn: getTiersStatus,
    staleTime: 60_000,
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      // Only send the 5 real tiers — `unassigned` isn't a real tier on the server.
      const payload: Record<string, string[]> = {};
      for (const t of TIERS) payload[t] = buckets[t].map((p) => p.id);
      return saveTiers(position, payload);
    },
    onSuccess: () => {
      setToast({ msg: '✓ Tiers saved', tone: 'success' });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Save failed', tone: 'warn' });
    },
  });

  const dismissMutation = useMutation({
    mutationFn: (pid: string) => dismissPlayer(pid),
    onMutate: (pid) => {
      // Optimistic: pull the player out of every bucket immediately
      setBuckets((prev) => {
        const next = cloneBuckets(prev);
        for (const z of ALL_ZONES) next[z] = next[z].filter((p) => p.id !== pid);
        return next;
      });
    },
    onSuccess: () => {
      setToast({ msg: 'Player hidden from your pool', tone: 'success' });
    },
  });

  // Re-auto-bucket whenever the rankings response changes OR position switches.
  useEffect(() => {
    const data = rankingsQuery.data;
    if (!data?.rankings) return;

    // Players come back with per-position ELO + rank. The data shape is
    // any[] per api/rankings.ts so cast each row into RankedPlayer.
    const players = (data.rankings as RankedPlayer[]).slice().sort(
      (a, b) => (b.elo ?? 0) - (a.elo ?? 0),
    );

    // Best-effort scoring_format resolution. TiersStatus returns it;
    // otherwise fall back to 1qb_ppr (the default on the server).
    const fmt: ScoringFormat =
      (tiersStatusQuery.data?.scoring_format as ScoringFormat) || '1qb_ppr';

    const bucketed = autoBucket(players, position, fmt);
    setBuckets({ ...bucketed, unassigned: [] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankingsQuery.data, position, tiersStatusQuery.data?.scoring_format]);

  // ── Drag-drop infrastructure ───────────────────────────────────────
  // Bin layouts are captured via onLayout into this ref. We compare the
  // drag's finalY against every known layout and pick the first match.
  const binLayouts = useRef<BinLayout[]>([]);

  const setBinLayout = useCallback((zone: Zone, e: LayoutChangeEvent) => {
    const { y, height } = e.nativeEvent.layout;
    const existing = binLayouts.current.findIndex((b) => b.zone === zone);
    const entry: BinLayout = { zone, y, height };
    if (existing >= 0) binLayouts.current[existing] = entry;
    else binLayouts.current.push(entry);
  }, []);

  const zoneAt = useCallback((absoluteY: number): Zone | null => {
    for (const b of binLayouts.current) {
      if (absoluteY >= b.y && absoluteY <= b.y + b.height) return b.zone;
    }
    return null;
  }, []);

  const movePlayer = useCallback(
    (playerId: string, toZone: Zone) => {
      setBuckets((prev) => {
        const next = cloneBuckets(prev);
        let moved: RankedPlayer | null = null;
        for (const z of ALL_ZONES) {
          const idx = next[z].findIndex((p) => p.id === playerId);
          if (idx >= 0) {
            [moved] = next[z].splice(idx, 1);
            break;
          }
        }
        if (moved) next[toZone].push(moved);
        return next;
      });
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    },
    [],
  );

  // ── Render helpers ─────────────────────────────────────────────────
  const saving = saveMutation.isPending;
  const loading = rankingsQuery.isLoading || rankingsQuery.isFetching;

  function renderPlayerCard(p: RankedPlayer) {
    return (
      <DraggableRow
        key={p.id}
        player={p}
        zoneAt={zoneAt}
        onDrop={(zone) => zone && movePlayer(p.id, zone)}
        onLongPress={() => {
          // Secondary dismiss via long-press confirm. Kept opt-in so
          // normal users don't accidentally banish players.
          void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          dismissMutation.mutate(p.id);
        }}
      />
    );
  }

  // ── Render ──────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <View style={styles.headerRow}>
        <Text style={styles.title}>Positional Tiers</Text>
        <Pressable
          onPress={() => {
            // Reset = re-auto-bucket from current rankings
            const data = rankingsQuery.data;
            if (!data?.rankings) return;
            const players = (data.rankings as RankedPlayer[]).slice().sort(
              (a, b) => (b.elo ?? 0) - (a.elo ?? 0),
            );
            const fmt: ScoringFormat =
              (tiersStatusQuery.data?.scoring_format as ScoringFormat) || '1qb_ppr';
            const bucketed = autoBucket(players, position, fmt);
            setBuckets({ ...bucketed, unassigned: [] });
            void Haptics.selectionAsync();
          }}
          style={({ pressed }) => [styles.resetBtn, pressed && { opacity: 0.6 }]}
        >
          <Text style={styles.resetBtnText}>Reset</Text>
        </Pressable>
      </View>

      {/* Position switcher */}
      <View style={styles.switcher}>
        {POSITIONS.map((p) => {
          const isActive = p === position;
          return (
            <Pressable
              key={p}
              onPress={() => {
                if (p !== position) setPosition(p);
              }}
              style={({ pressed }) => [
                styles.switcherBtn,
                isActive && styles.switcherBtnActive,
                pressed && { opacity: 0.7 },
              ]}
            >
              <Text
                style={[styles.switcherText, isActive && styles.switcherTextActive]}
              >
                {p}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.hint}>
        Long-press + drag a card to move it to a tier. Long-press alone hides the player.
      </Text>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : rankingsQuery.isError ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>Could not load rankings.</Text>
          <Pressable onPress={() => rankingsQuery.refetch()}>
            <Text style={styles.retryText}>Try again</Text>
          </Pressable>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          {/* Unassigned pool up top */}
          <TierBin
            tier="unassigned"
            count={buckets.unassigned.length}
            onLayout={(e) => setBinLayout('unassigned', e)}
          >
            {buckets.unassigned.length === 0 ? (
              <Text style={styles.emptyBin}>Every player is in a tier.</Text>
            ) : (
              buckets.unassigned.map(renderPlayerCard)
            )}
          </TierBin>

          {/* The five tier bins */}
          {TIERS.map((t) => (
            <TierBin
              key={t}
              tier={t}
              count={buckets[t].length}
              onLayout={(e) => setBinLayout(t, e)}
            >
              {buckets[t].length === 0 ? (
                <Text style={styles.emptyBin}>Drag players here</Text>
              ) : (
                buckets[t].map(renderPlayerCard)
              )}
            </TierBin>
          ))}
        </ScrollView>
      )}

      {/* Save button pinned to the bottom */}
      <View style={styles.saveBar}>
        <Pressable
          disabled={saving || loading}
          onPress={() => saveMutation.mutate()}
          style={({ pressed }) => [
            styles.saveBtn,
            pressed && { opacity: 0.85 },
            (saving || loading) && { opacity: 0.5 },
          ]}
        >
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.saveBtnText}>Save {position} tiers</Text>
          )}
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

// ── DraggableRow — encapsulates the per-card gesture + Reanimated style.
interface DraggableRowProps {
  player: RankedPlayer;
  zoneAt: (absoluteY: number) => Zone | null;
  onDrop: (zone: Zone | null) => void;
  onLongPress?: () => void;
}

function DraggableRow({ player, zoneAt, onDrop, onLongPress }: DraggableRowProps) {
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const scale = useSharedValue(1);
  const zIndex = useSharedValue(0);

  // Pan activates after 150ms hold to avoid fighting ScrollView scrolling.
  const pan = useMemo(
    () =>
      Gesture.Pan()
        .activateAfterLongPress(220)
        .onStart(() => {
          scale.value = withTiming(1.04, { duration: 120 });
          zIndex.value = 10;
          runOnJS(Haptics.selectionAsync)();
        })
        .onUpdate((e) => {
          translateX.value = e.translationX;
          translateY.value = e.translationY;
        })
        .onEnd((e) => {
          const absoluteY = e.absoluteY;
          const z = zoneAt(absoluteY);
          // Snap back visually, then commit the move so the card re-renders
          // in its new bin.
          translateX.value = withTiming(0, { duration: 160 });
          translateY.value = withTiming(0, { duration: 160 });
          scale.value = withTiming(1, { duration: 160 });
          zIndex.value = 0;
          runOnJS(onDrop)(z);
        }),
    [zoneAt, onDrop, translateX, translateY, scale, zIndex],
  );

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { scale: scale.value },
    ],
    zIndex: zIndex.value,
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={animatedStyle}>
        <PlayerCard player={player} compact onLongPress={onLongPress} />
      </Animated.View>
    </GestureDetector>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────

const ALL_ZONES: Zone[] = ['unassigned', 'elite', 'starter', 'solid', 'depth', 'bench'];

function emptyBuckets(): Record<Zone, RankedPlayer[]> {
  return {
    unassigned: [],
    elite: [],
    starter: [],
    solid: [],
    depth: [],
    bench: [],
  };
}

function cloneBuckets(src: Record<Zone, RankedPlayer[]>): Record<Zone, RankedPlayer[]> {
  return {
    unassigned: [...src.unassigned],
    elite: [...src.elite],
    starter: [...src.starter],
    solid: [...src.solid],
    depth: [...src.depth],
    bench: [...src.bench],
  };
}

// ── Styles ──────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  title: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  resetBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  resetBtnText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  switcher: {
    flexDirection: 'row',
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: 4,
  },
  switcherBtn: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.sm,
  },
  switcherBtnActive: { backgroundColor: 'rgba(79,124,255,0.14)' },
  switcherText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },
  switcherTextActive: { color: colors.accent },
  hint: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  errorText: { color: colors.red, fontSize: fontSize.sm },
  retryText: { color: colors.accent, fontSize: fontSize.sm, fontWeight: '700' },
  scroll: {
    padding: spacing.lg,
    paddingBottom: 96, // room for the Save bar
  },
  emptyBin: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    paddingVertical: spacing.xs,
    fontStyle: 'italic',
  },
  saveBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    padding: spacing.md,
    backgroundColor: colors.bg,
    borderTopColor: colors.border,
    borderTopWidth: 1,
  },
  saveBtn: {
    backgroundColor: colors.accent,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
  },
  saveBtnText: { color: '#fff', fontSize: fontSize.base, fontWeight: '800' },
});
