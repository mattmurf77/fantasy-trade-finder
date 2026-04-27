import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { useSession } from '../state/useSession';

interface Props {
  /** Tap handler — typically opens a LeagueSwitcherSheet. Parent owns the
   *  sheet state so the pill can be reused on multiple screens without
   *  spawning multiple sheets. */
  onPress: () => void;
  /** Caption shown above the league name. Defaults to "League". Use
   *  e.g. "Trading in" on the Find a Trade screen for context. */
  label?: string;
  /** Variant for screens that already have heavy chrome above. Slimmer
   *  padding, smaller font. Default false. */
  compact?: boolean;
}

// Pressable widget showing the active league name + a chevron, signalling
// "tap to switch." Used at the top of TradesScreen and on LeagueScreen.
// Reads the active league from useSession so all instances stay in sync
// the moment a switch completes.
export default function LeaguePill({ onPress, label = 'League', compact = false }: Props) {
  const league = useSession((s) => s.league);
  const switching = useSession((s) => s.switching);

  return (
    <Pressable
      onPress={onPress}
      disabled={switching}
      style={({ pressed }) => [
        styles.pill,
        compact && styles.pillCompact,
        pressed && !switching && { opacity: 0.7 },
        switching && { opacity: 0.6 },
      ]}
    >
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={styles.label}>{label}</Text>
        <Text style={[styles.name, compact && styles.nameCompact]} numberOfLines={1}>
          {league?.league_name || 'No league selected'}
        </Text>
      </View>
      <Text style={styles.chevron}>{switching ? '…' : '⇅'}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.md,
    paddingHorizontal: spacing.lg,
  },
  pillCompact: { padding: spacing.sm, paddingHorizontal: spacing.md },
  label: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  name:        { color: colors.text, fontSize: fontSize.base, fontWeight: '800', marginTop: 2 },
  nameCompact: { fontSize: fontSize.sm },
  chevron:     { color: colors.muted, fontSize: 20, fontWeight: '700' },
});
