import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Suggestion, VERDICT_LABEL, formatDelta } from '../logic/tradeMath';
import { PositionChip } from './PositionChip';
import { colors, fontSize, radius, spacing } from '../theme';

interface Props {
  suggestion: Suggestion;
  onApply: () => void;
}

export function SuggestionCard({ suggestion, onApply }: Props) {
  const { players, evaluation } = suggestion;
  const winWin = evaluation.verdict === 'WIN_WIN';
  const color = winWin ? colors.green : colors.accent;
  return (
    <Pressable style={[styles.card, { borderColor: color + '55' }]} onPress={onApply}>
      <View style={styles.players}>
        {players.map((p) => (
          <View key={p.id} style={styles.playerRow}>
            <PositionChip pos={p.pos} />
            <Text style={styles.name}>{p.name}</Text>
          </View>
        ))}
      </View>
      <View style={styles.right}>
        <Text style={[styles.verdict, { color }]}>{VERDICT_LABEL[evaluation.verdict]}</Text>
        <Text style={styles.deltas}>
          you {formatDelta(evaluation.myDeltaPct)} · them {formatDelta(evaluation.theirDeltaPct)}
        </Text>
        <Text style={[styles.apply, { color }]}>Use this ›</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    padding: spacing.md,
    gap: spacing.md,
    alignItems: 'center',
  },
  players: { flex: 1, gap: spacing.xs },
  playerRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  name: { color: colors.text, fontSize: fontSize.sm, fontWeight: '600', flexShrink: 1 },
  right: { alignItems: 'flex-end', gap: 2 },
  verdict: { fontSize: fontSize.xs, fontWeight: '700' },
  deltas: { color: colors.muted, fontSize: fontSize.xs },
  apply: { fontSize: fontSize.xs, fontWeight: '600', marginTop: 2 },
});
