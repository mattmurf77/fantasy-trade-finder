import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import type { QueuedTrade } from '../shared/types';

interface Props {
  trade: QueuedTrade;
  onRemove: () => void;
}

// Small chip rendering a queued trade's give/receive summary plus an ×
// dequeue button. Used inside the queue bottom-sheet on TradesScreen.
export default function QueueChip({ trade, onRemove }: Props) {
  return (
    <View style={styles.chip}>
      <View style={styles.main}>
        <Text style={styles.line} numberOfLines={2}>
          <Text style={styles.strong}>{trade.give_summary || '?'}</Text>
          <Text style={styles.arrow}>  ⇄  </Text>
          <Text style={styles.strong}>{trade.receive_summary || '?'}</Text>
        </Text>
      </View>
      <Pressable
        accessibilityLabel="Remove from queue"
        hitSlop={8}
        onPress={onRemove}
        style={({ pressed }) => [styles.remove, pressed && { opacity: 0.6 }]}
      >
        <Text style={styles.removeText}>×</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  main: { flex: 1, minWidth: 0 },
  line: { color: colors.text, fontSize: fontSize.sm, lineHeight: 20 },
  strong: { color: colors.text, fontWeight: '800' },
  arrow: { color: colors.accent, fontWeight: '700' },
  remove: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(239,68,68,0.10)',
  },
  removeText: { color: colors.red, fontSize: 18, fontWeight: '800', lineHeight: 20 },
});
