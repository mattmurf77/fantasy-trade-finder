import React, { forwardRef } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import {
  ink,
  chalk,
  volt,
  semantic,
  tier as tierColors,
  position as positionColors,
  space,
  radii,
  type,
} from '../theme/chalkline';
import { Badge, PositionBadge, TierChalkBadge, RookieBadge, InjuryBadge } from './chalkline';
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
  showInjury?: boolean;            // render the injury-status tag (default true). Off for Trios tiles (feedback #33).
}

// Normalize Sleeper injury strings to the Chalkline InjuryBadge codes.
// Unknown statuses fall back to a generic neg-bordered badge below.
function injuryCode(status: string): 'Q' | 'D' | 'Out' | 'IR' | null {
  const s = status.trim().toLowerCase();
  if (s === 'q' || s.startsWith('questionable')) return 'Q';
  if (s === 'd' || s.startsWith('doubtful')) return 'D';
  if (s === 'out') return 'Out';
  if (s === 'ir') return 'IR';
  return null;
}

// Shared player-card primitive. Consumed by RankScreen (Trios) today and
// by TiersScreen + TradesScreen + MatchesScreen in Phases 3-4. Keeping
// visual variants here so every screen renders players identically.
// Chalkline: replicates the Card primitive pattern (ink-1 surface, hairline,
// 3px position rail) because the trio loop needs Pressable + ref + rank
// accents that Card doesn't model.
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
    showInjury = true,
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
  const isRookie = player.years_experience === 0;

  // Position rail + badge — position hexes are cross-client invariants,
  // rendered only via the chalkline re-export.
  const posKey = String(player.position).toLowerCase() as keyof typeof positionColors;
  const railColor: string | undefined = positionColors[posKey];
  const isStdPos =
    player.position === 'QB' ||
    player.position === 'RB' ||
    player.position === 'WR' ||
    player.position === 'TE';

  const injury = showInjury && player.injury_status ? player.injury_status : null;
  const injCode = injury ? injuryCode(injury) : null;

  // Per-rank border accents echoing the web's .ranked-1 / .ranked-2 / .ranked-3.
  const rankBorderStyle =
    rank === 1 ? styles.rankBorder1 :
    rank === 2 ? styles.rankBorder2 :
    rank === 3 ? styles.rankBorder3 : null;
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
        rankBorderStyle,
        pressed && !disabled && styles.cardPressed,
        disabled && styles.cardDisabled,
      ]}
    >
      {/* 3px position-color left rail (Card primitive pattern) */}
      {railColor ? <View style={[styles.rail, { backgroundColor: railColor }]} /> : null}

      {/* Rank badge floating in top-right */}
      {ranked && (
        <View style={[styles.rankBadge, rankFgStyle]}>
          <Text style={styles.rankBadgeText}>{rank}</Text>
        </View>
      )}

      <View style={styles.header}>
        {isStdPos ? (
          <PositionBadge pos={player.position as 'QB' | 'RB' | 'WR' | 'TE'} />
        ) : (
          <Badge label={String(player.position)} />
        )}
        {tier && <TierChalkBadge t={tier} />}
        {posRank ? <Badge label={posRank} /> : null}
        {isRookie && <RookieBadge />}
        {injury ? (
          injCode ? (
            <InjuryBadge status={injCode} />
          ) : (
            <Badge label={injury} color={semantic.neg} colorText />
          )
        ) : null}
      </View>

      <Text style={[type.title, styles.name]} numberOfLines={1}>
        {player.name}
      </Text>

      <View style={styles.meta}>
        <Text style={type.bodySm}>{teamStr}</Text>
        {ageStr && (
          <>
            <Text style={styles.metaDot}>·</Text>
            <Text style={type.bodySm}>{ageStr}</Text>
          </>
        )}
        {expStr && !compact && (
          <>
            <Text style={styles.metaDot}>·</Text>
            <Text style={type.bodySm}>{expStr}</Text>
          </>
        )}
      </View>

      {rightSlot ? <View style={styles.rightSlot}>{rightSlot}</View> : null}
    </Pressable>
  );
});

export default React.memo(PlayerCard);

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: space.lg,
    position: 'relative',
    overflow: 'hidden',
  },
  cardCompact: {
    padding: space.md,
  },
  cardPressed: {
    backgroundColor: ink.ink3,
  },
  cardDisabled: { opacity: 0.45 },
  cardSelected: {
    borderColor: volt.base,
  },
  rail: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
  },
  // Rank accent border by assigned rank (1 gold / 2 green / 3 blue).
  // Tier hexes are data encodings (cross-client invariants) via re-export.
  rankBorder1: { borderColor: tierColors.elite },
  rankBorder2: { borderColor: tierColors.starter },
  rankBorder3: { borderColor: tierColors.solid },

  rankBadge: {
    position: 'absolute',
    top: space.sm,
    right: space.sm,
    width: 24,
    height: 24,
    borderRadius: radii.xs,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankFg1: { backgroundColor: tierColors.elite },
  rankFg2: { backgroundColor: tierColors.starter },
  rankFg3: { backgroundColor: tierColors.solid },
  rankBadgeText: {
    ...type.data,
    color: ink.ink0,
  },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: space.xs,
    marginBottom: space.sm,
  },
  name: {
    marginBottom: space.xs,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  metaDot: { color: chalk.faint, marginHorizontal: space.xs },
  rightSlot: { position: 'absolute', right: space.md, top: space.md },
});
