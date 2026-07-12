import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { chalk, ice, ink, radii, space, type } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import type { RankMethodPref } from '../state/useSession';

// "We steer ↔ You steer" ranking-method selector (Settings). Five dots on a
// track, one per ranking flow, ordered most-guided → most-manual — the same
// axis the Build-your-board chooser (RankHomeScreen) presents as cards. The
// selected dot names the flow by its process; changing it re-routes where
// the Rank tab opens at next launch.

const STOPS: { pref: RankMethodPref; title: string; sub: string }[] = [
  // #119 — Quick set: the lowest-effort flow, leading the guided end in the
  // same order as the rank-home chooser.
  {
    pref: 'quickset',
    title: 'Tap players into tiers',
    sub: 'One value tier at a time — tap who belongs, save, next. The fastest board.',
  },
  {
    pref: 'trio',
    title: 'Answer quick head-to-heads',
    sub: 'We show three players, you order them — your board builds itself.',
  },
  {
    pref: 'anchor',
    title: 'Price players in picks',
    sub: 'One player at a time: worth two 1sts? A mid 2nd? You set the price.',
  },
  {
    pref: 'tiers',
    title: 'Sort players into groups',
    sub: 'You shape the board by dragging players into value groups.',
  },
  {
    pref: 'manual',
    title: 'Order every player yourself',
    sub: 'The full list in your exact order — total control of every slot.',
  },
];

export default function SteerSlider({
  value,
  onChange,
  disabled,
}: {
  /** Null = never chosen (the Rank tab still shows the chooser). */
  value: RankMethodPref | null;
  onChange: (m: RankMethodPref) => void;
  disabled?: boolean;
}) {
  const active = STOPS.find((s) => s.pref === value) ?? null;

  return (
    <View style={styles.wrap}>
      <View style={styles.labels}>
        <Text style={styles.axisLabel}>WE STEER</Text>
        <Text style={styles.axisLabel}>YOU STEER</Text>
      </View>

      <View style={styles.trackRow}>
        <View style={styles.track} />
        {STOPS.map((s) => {
          const selected = s.pref === value;
          return (
            <Pressable
              key={s.pref}
              disabled={disabled}
              onPress={() => {
                if (s.pref === value) return;
                haptics.selection();
                onChange(s.pref);
              }}
              hitSlop={space.md}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              accessibilityLabel={s.title}
              style={styles.stop}
            >
              <View style={[styles.dot, selected && styles.dotSelected]} />
            </Pressable>
          );
        })}
      </View>

      {active ? (
        <>
          <Text style={styles.activeTitle}>{active.title}</Text>
          <Text style={styles.activeSub}>{active.sub}</Text>
        </>
      ) : (
        <Text style={styles.activeSub}>
          Not chosen yet — the Rank tab opens on the chooser until you pick.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    padding: space.md,
    gap: space.sm,
  },
  labels: { flexDirection: 'row', justifyContent: 'space-between' },
  axisLabel: { ...type.label, color: chalk.faint },
  trackRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 28,
  },
  track: {
    position: 'absolute',
    left: 6,
    right: 6,
    height: 1,
    backgroundColor: ink.lineStrong,
  },
  stop: { alignItems: 'center', justifyContent: 'center' },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: chalk.dim,
    backgroundColor: ink.ink1,
  },
  dotSelected: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderColor: ice.base,
    backgroundColor: ice.base,
  },
  activeTitle: { ...type.title },
  activeSub: { ...type.bodySm },
});
