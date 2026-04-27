import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PlayerCard from './PlayerCard';
import type { TradeCard as TradeCardData } from '../shared/types';

interface Props {
  data: TradeCardData;
  variant?: 'swipe' | 'match';
  // Match-variant actions
  onAccept?: () => void;
  onDecline?: () => void;
  acting?: boolean;
}

// Shared rendering for generated trades (TradesScreen swipe deck) and
// mutual matches (MatchesScreen list). The only difference between the
// two variants is the action buttons at the bottom — swipe decks don't
// show buttons (gestures drive the decision), match cards do.
export default function TradeCardComp({
  data,
  variant = 'swipe',
  onAccept,
  onDecline,
  acting,
}: Props) {
  const matchPct = Math.round((data.match_score || 0) * 1);
  const fairPct = Math.round((data.fairness || 0) * 100);

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View>
          <Text style={styles.headerLabel}>Trade with</Text>
          <Text style={styles.headerName}>@{data.opponent_username}</Text>
        </View>
        <View style={styles.scorePill}>
          <Text style={styles.scoreText}>{matchPct}</Text>
          <Text style={styles.scoreLabel}>match</Text>
        </View>
      </View>

      <View style={styles.split}>
        <View style={styles.side}>
          <Text style={styles.sideLabel}>YOU GET</Text>
          <View style={styles.sideStack}>
            {data.receive_players.map((p) => (
              <PlayerCard key={p.id} player={p} compact />
            ))}
          </View>
        </View>
        <Text style={styles.swap}>↔</Text>
        <View style={styles.side}>
          <Text style={styles.sideLabel}>YOU GIVE</Text>
          <View style={styles.sideStack}>
            {data.give_players.map((p) => (
              <PlayerCard key={p.id} player={p} compact />
            ))}
          </View>
        </View>
      </View>

      <View style={styles.fairnessRow}>
        <Text style={styles.fairnessLabel}>Fairness</Text>
        <View style={styles.fairnessTrack}>
          <View style={[styles.fairnessFill, { width: `${fairPct}%` }]} />
        </View>
        <Text style={styles.fairnessValue}>{fairPct}%</Text>
      </View>

      {/* Human-readable reasons (flag trade_math.human_explanations is ON).
          Rendered only when the backend returns a non-empty list. */}
      {Array.isArray(data.reasons) && data.reasons.length > 0 && (
        <View style={styles.reasons}>
          {data.reasons.map((r, i) => (
            <Text key={`${i}:${r}`} style={styles.reasonLine}>• {r}</Text>
          ))}
        </View>
      )}

      {variant === 'match' && (
        <View style={styles.actions}>
          <Pressable
            disabled={acting}
            onPress={onDecline}
            style={({ pressed }) => [
              styles.btn,
              styles.decline,
              pressed && { opacity: 0.7 },
              acting && { opacity: 0.5 },
            ]}
          >
            <Text style={styles.declineText}>Decline</Text>
          </Pressable>
          <Pressable
            disabled={acting}
            onPress={onAccept}
            style={({ pressed }) => [
              styles.btn,
              styles.accept,
              pressed && { opacity: 0.85 },
              acting && { opacity: 0.5 },
            ]}
          >
            <Text style={styles.acceptText}>Accept →</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  headerName: { color: colors.text, fontSize: fontSize.base, fontWeight: '800' },
  scorePill: {
    backgroundColor: 'rgba(79,124,255,0.14)',
    borderColor: 'rgba(79,124,255,0.45)',
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    alignItems: 'center',
  },
  scoreText: { color: colors.accent, fontSize: fontSize.lg, fontWeight: '800' },
  scoreLabel: {
    color: colors.accent,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  split: {
    flexDirection: 'row',
    gap: spacing.md,
    alignItems: 'stretch',
  },
  side: { flex: 1, gap: spacing.xs },
  sideLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  sideStack: { gap: spacing.xs },
  swap: {
    color: colors.accent,
    fontSize: 24,
    alignSelf: 'center',
    paddingHorizontal: 4,
  },
  fairnessRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  fairnessLabel: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    width: 62,
  },
  fairnessTrack: {
    flex: 1,
    height: 6,
    backgroundColor: colors.border,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  fairnessFill: {
    height: '100%',
    backgroundColor: colors.green,
  },
  fairnessValue: {
    color: colors.text,
    fontSize: fontSize.xs,
    fontWeight: '700',
    width: 40,
    textAlign: 'right',
  },
  reasons: {
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderLeftWidth: 3,
    borderLeftColor: colors.accent,
    padding: spacing.sm,
    paddingLeft: spacing.md,
    borderRadius: radius.sm,
    gap: 2,
  },
  reasonLine: { color: colors.muted, fontSize: fontSize.xs, lineHeight: 18 },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  btn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: radius.md,
    alignItems: 'center',
  },
  decline: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  accept: { backgroundColor: colors.green },
  declineText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },
  acceptText: { color: '#0a1510', fontSize: fontSize.sm, fontWeight: '800' },
});
