import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { ink, chalk, space, radii, type } from '../theme/chalkline';
import { Icon } from './chalkline';
import type { QueuedTrade } from '../shared/types';

interface Props {
  trade: QueuedTrade;
  onRemove: () => void;
}

// Chalkline chip rendering a queued trade's give/receive summary plus a
// dequeue button. Hairline border, radius xs, label type; the swap icon
// replaces the old dingbat arrow. Used inside the queue bottom-sheet on
// TradesScreen.
export default function QueueChip({ trade, onRemove }: Props) {
  return (
    <View style={styles.chip}>
      <View style={styles.main}>
        <Text style={[type.label, styles.summary]} numberOfLines={2}>
          {trade.give_summary || '?'}
        </Text>
        <Icon name="swap" size={16} color={chalk.dim} />
        <Text style={[type.label, styles.summary]} numberOfLines={2}>
          {trade.receive_summary || '?'}
        </Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Remove from queue"
        hitSlop={8}
        onPress={onRemove}
        style={({ pressed }) => [styles.remove, pressed && styles.removePressed]}
      >
        <Icon name="x" size={16} color={chalk.dim} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  main: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: space.xs,
  },
  summary: { color: chalk.base, flexShrink: 1 },
  remove: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removePressed: { backgroundColor: ink.ink3 },
});
