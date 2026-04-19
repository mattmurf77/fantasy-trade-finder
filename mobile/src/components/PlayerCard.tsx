import React, { forwardRef } from 'react';
import { View, Text, StyleSheet, Pressable, Platform } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import type { Player, Tier } from '../shared/types';

export interface PlayerCardProps {
  player: Player;
  // Ranking-state props — used by RankScreen's Trios loop
  rank?: 1 | 2 | 3 | null;         // which position the user has assigned
  selected?: boolean;              // any rank assigned at all
  onPress?: () => void;
  onLongPress?: () => void;        // used for "gesture audit" info sheet
  disabled?: boolean;
  // Decorative props — used by Tiers / Trades / Matches
  tier?: Tier | null;
  posRank?: string;                // e.g. "QB4"
  compact?: boolean;               // shorter card for tier bins / trade cards
  rightSlot?: React.ReactNode;     // optional right-side widget (drag handle, trend arrow, etc.)
}

// Shared player-card primitive. Consumed by RankScreen (Trios) today and
// by TiersScreen + TradesScreen + MatchesScreen in Phases 3-4. Keeping
// visual variants here so every screen renders players identically.
const PlayerCard = forwardRef<View, PlayerCardProps>(function PlayerCard(
  {
    player,
    rank = null,
    selected = false,
    onPress,
    onLongPress,
    disabled,
    tier,
    posRank,
    compact = false,
    rightSlot,
  },
  ref,
) {
  const ranked = rank != null;
  const ageStr = player.age != null ? `${player.age} yo` : null;
  const teamStr = player.team || 'FA';
  const expStr =
    player.years_experience != null
      ? `${player.years_experience} yr${player.years_experience === 1 ? '' : 's'}`
      : null;

  // Per-rank accents pulled out so the styles prop below stays well-typed.
  const rankBgStyle =
    rank === 1 ? styles.rankBg1 :
    rank === 2 ? styles.rankBg2 :
    rank === 3 ? styles.rankBg3 : null;
  const rankFgStyle =
    rank === 1 ? styles.rankFg1 :
    rank === 2 ? styles.rankFg2 :
    rank === 3 ? styles.rankFg3 : null;

  return (
    <Pressable
      ref={ref as any}
      onPress={onPress}
      onLongPress={onLongPress}
      disabled={disabled}
      delayLongPress={400}
      style={({ pressed }) => [
        styles.card,
        compact && styles.cardCompact,
        selected && styles.cardSelected,
        rankBgStyle,
        pressed && !disabled && styles.cardPressed,
        disabled && styles.cardDisabled,
      ]}
    >
      {/* Rank badge floating in top-right */}
      {ranked && (
        <View style={[styles.rankBadge, rankFgStyle]}>
          <Text style={styles.rankBadgeText}>{rank}</Text>
        </View>
      )}

      <View style={styles.header}>
        <PositionChip position={player.position} size={compact ? 'sm' : 'md'} />
        {tier && <TierBadge tier={tier} posRank={posRank} size="sm" />}
      </View>

      <Text style={[styles.name, compact && styles.nameCompact]} numberOfLines={1}>
        {player.name}
      </Text>

      <View style={styles.meta}>
        <Text style={styles.metaText}>{teamStr}</Text>
        {ageStr && (
          <>
            <Text style={styles.metaDot}>·</Text>
            <Text style={styles.metaText}>{ageStr}</Text>
          </>
        )}
        {expStr && !compact && (
          <>
            <Text style={styles.metaDot}>·</Text>
            <Text style={styles.metaText}>{expStr}</Text>
          </>
        )}
        {player.injury_status ? (
          <>
            <Text style={styles.metaDot}>·</Text>
            <Text style={[styles.metaText, styles.injuryText]}>
              {player.injury_status}
            </Text>
          </>
        ) : null}
      </View>

      {rightSlot ? <View style={styles.rightSlot}>{rightSlot}</View> : null}
    </Pressable>
  );
});

export default PlayerCard;

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.lg,
    position: 'relative',
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.25,
        shadowRadius: 6,
      },
      android: { elevation: 2 },
    }),
  },
  cardCompact: {
    padding: spacing.md,
    borderRadius: radius.md,
  },
  cardPressed: {
    borderColor: '#3a3d4a',
    transform: [{ scale: 0.995 }],
  },
  cardDisabled: { opacity: 0.55 },
  cardSelected: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.06)',
  },
  // Subtle accent top border by rank to echo the web's .ranked-1 / .ranked-2 / .ranked-3
  rankBg1: {
    borderColor: colors.tier.elite,
    borderTopWidth: 3,
    backgroundColor: 'rgba(245,158,11,0.06)',
  },
  rankBg2: {
    borderColor: colors.tier.starter,
    borderTopWidth: 3,
    backgroundColor: 'rgba(34,197,94,0.06)',
  },
  rankBg3: {
    borderColor: colors.tier.solid,
    borderTopWidth: 3,
    backgroundColor: 'rgba(59,130,246,0.06)',
  },

  rankBadge: {
    position: 'absolute',
    top: 10,
    right: 10,
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankFg1: { backgroundColor: colors.tier.elite },
  rankFg2: { backgroundColor: colors.tier.starter },
  rankFg3: { backgroundColor: colors.tier.solid },
  rankBadgeText: { color: '#fff', fontWeight: '800', fontSize: 14 },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  name: {
    color: colors.text,
    fontSize: fontSize.lg,
    fontWeight: '800',
    letterSpacing: -0.3,
    marginBottom: 6,
  },
  nameCompact: { fontSize: fontSize.base },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  metaText: { color: colors.muted, fontSize: fontSize.sm },
  metaDot: { color: colors.border, marginHorizontal: 6 },
  injuryText: { color: colors.red },
  rightSlot: { position: 'absolute', right: 14, top: 14 },
});
