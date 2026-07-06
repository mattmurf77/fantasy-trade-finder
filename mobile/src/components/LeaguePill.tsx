import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { ink, chalk, space, radii, type } from '../theme/chalkline';
import { Icon } from './chalkline';
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
// "tap to switch." Chalkline chip construction: hairline interactive border,
// radius xs, pressed = ink-3 fill (color change only, no transforms).
// Used at the top of TradesScreen and on LeagueScreen. Reads the active
// league from useSession so all instances stay in sync the moment a switch
// completes.
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
        pressed && !switching && styles.pillPressed,
        switching && styles.pillSwitching,
      ]}
    >
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={type.label}>{label}</Text>
        <Text
          style={[type.title, styles.name, compact && styles.nameCompact]}
          numberOfLines={1}
        >
          {league?.league_name || 'No league selected'}
        </Text>
      </View>
      {switching ? (
        <Text style={styles.busy}>…</Text>
      ) : (
        <Icon name="chevron-down" size={20} color={chalk.dim} />
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: ink.ink1,
    borderColor: ink.lineStrong,
    borderWidth: 1,
    borderRadius: radii.xs,
    padding: space.md,
    paddingHorizontal: space.lg,
    minHeight: 44,
  },
  pillCompact: { padding: space.sm, paddingHorizontal: space.md },
  pillPressed: { backgroundColor: ink.ink3 },
  pillSwitching: { opacity: 0.45 },
  name: { marginTop: 2 },
  nameCompact: { fontSize: type.bodySm.fontSize, lineHeight: type.bodySm.lineHeight },
  busy: { ...type.body, color: chalk.dim },
});
