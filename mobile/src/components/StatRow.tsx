import React from 'react';
import { View, StyleSheet } from 'react-native';
import Text from './chalkline/Text';
import { ink, chalk, space, type } from '../theme/chalkline';

// One stat per row inside the Standings table's open team (and its
// projection detail): the label left in muted body-sm, the value right in
// Plex Mono (`mono`, the default) or the body font (`mono={false}`, names).
// The value never wraps; a long label truncates. Each row carries the open
// card's quiet separator on top (ink-3 on ink-2, as LeagueProjectionDetail's
// sub-sections do), so a run of rows reads as one block.
export function StatRow({ label, value, mono = true, testID }: {
  label: string;
  value: string;
  mono?: boolean;
  testID?: string;
}) {
  return (
    <View style={styles.row} testID={testID} accessible accessibilityLabel={`${label}, ${value}`}>
      <Text variant="bodySm" numberOfLines={1} style={styles.label}>{label}</Text>
      <Text scale={mono ? 'dense' : 'body'} numberOfLines={1} style={[mono ? styles.mono : styles.text, styles.value]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 28,
    borderTopWidth: 1,
    borderTopColor: ink.ink3,
  },
  label: { flex: 1, minWidth: 0, color: chalk.dim },
  mono: { ...type.data },
  text: { ...type.bodySm, color: chalk.base },
  value: { flexShrink: 0, textAlign: 'right' },
});
