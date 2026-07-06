import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { ink, ice, radii, space } from '../../theme/chalkline';

interface Props {
  children: React.ReactNode;
  /** Position color for the 3px left rail (player cards). */
  rail?: string;
  /** Volt border (trio winner, active selection). */
  selected?: boolean;
  style?: ViewStyle;
}

// Chalkline card: ink-1 surface, hairline border, radius 8, no shadow, no hover lift.
export default function Card({ children, rail, selected = false, style }: Props) {
  return (
    <View
      style={[
        styles.card,
        selected && styles.selected,
        style,
      ]}
    >
      {rail ? <View style={[styles.rail, { backgroundColor: rail }]} /> : null}
      <View style={[styles.body, rail ? styles.bodyWithRail : null]}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  selected: { borderColor: ice.base },
  rail: { width: 3 },
  body: { flex: 1, padding: space.lg },
  bodyWithRail: { paddingLeft: space.lg - 3 },
});
